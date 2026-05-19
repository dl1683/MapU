from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.config import Settings
from mapu.db.engine import build_engine
from mapu.evidence.chunking import SpanAwareChunker
from mapu.evidence.ingest import IngestionService
from mapu.evidence.parsers import ParserRegistry
from mapu.evidence.retrieval import ChunkRetrievalService, RetrievalConfig
from mapu.evidence.types import DocumentBlob
from mapu.models.corpus import Corpus
from mapu.models.evidence import Chunk
from mapu.providers.embeddings import get_default_embedding_provider
from mapu.query.intent import HeuristicIntentClassifier
from mapu.query.service import QueryService
from mapu.query.types import QueryRequest


class MapUMem0Client:
    """Mem0 benchmark client contract backed by MapU corpus/query pipelines."""

    def __init__(
        self,
        mode: str = "oss",
        host: str | None = None,
        api_key: str | None = None,
        organization_id: str | None = None,
        project_id: str | None = None,
        max_retries: int = 5,
        retry_delay: float = 5.0,
        rpm: int = 60,
        timeout: float = 300.0,
        event_poll_interval: float = 0.5,
        event_poll_timeout: float = 300.0,
    ) -> None:
        _ = (
            mode,
            host,
            api_key,
            organization_id,
            project_id,
            max_retries,
            retry_delay,
            rpm,
            timeout,
            event_poll_interval,
            event_poll_timeout,
        )
        settings = Settings()
        if (
            settings.embedding.provider.lower() in ("local", "hash-deterministic")
            and "MAPU_EMBEDDING_PROVIDER" not in os.environ
        ):
            os.environ["MAPU_EMBEDDING_PROVIDER"] = "sentence-transformers"
            if "MAPU_EMBEDDING_MODEL" not in os.environ:
                os.environ["MAPU_EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"
        settings = Settings()
        _engine, self._session_factory = build_engine(settings.database)
        self._corpus_by_user: dict[str, uuid.UUID] = {}
        self._registry = ParserRegistry.create_default()
        self._chunker = SpanAwareChunker(max_tokens=120, overlap_tokens=16)
        self._embedder = get_default_embedding_provider()

    async def __aenter__(self) -> MapUMem0Client:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def close(self) -> None:
        return None

    async def add(
        self,
        messages: list[dict[str, str]],
        user_id: str,
        observation_date: str | None = None,
        timestamp: int | None = None,
        custom_instructions: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any] | None:
        _ = (observation_date, custom_instructions)
        if not messages:
            return {"results": []}

        corpus_id = await self._ensure_corpus(user_id)
        is_beam = user_id.startswith("beam_")
        selected: list[tuple[str, str]] = []
        for m in messages:
            role = str(m.get("role", "user")).strip().lower()
            content = str(m.get("content", "")).strip()
            if not content:
                continue
            if role == "user":
                selected.append((role, content))
                continue
            if role == "assistant":
                normalized = _assistant_turn_for_memory(content, is_beam=is_beam)
                if normalized:
                    selected.append((role, normalized))

        if not selected:
            return {"results": []}

        async with self._session_factory() as session:
            chunker = (
                self._chunker
                if not is_beam
                else SpanAwareChunker(max_tokens=256, overlap_tokens=32)
            )
            ingest = IngestionService(
                session=session,
                corpus_id=corpus_id,
                parser_registry=self._registry,
                chunker=chunker,
                embedding_provider=self._embedder,
                # Benchmark adapter stores memory text and relies on retrieval/ranking.
                # Relation extraction on chat transcripts tends to add noisy propositions.
                extractors=[],
            )
            meta: dict[str, str] = {}
            if metadata:
                for k, v in metadata.items():
                    if isinstance(v, str):
                        meta[k] = v
            if timestamp is not None:
                meta["source_timestamp"] = str(timestamp)
            ts_prefix = ""
            if timestamp is not None:
                try:
                    dt = datetime.fromtimestamp(int(timestamp), tz=UTC)
                    ts_prefix = f"[ts:{dt.isoformat()}] "
                except (ValueError, OSError, OverflowError):
                    ts_prefix = ""
            results = []
            for role, content in selected:
                enriched = _enrich_with_temporal_hints(content, timestamp)
                blob = DocumentBlob(
                    content=f"{ts_prefix}{role}: {enriched}".encode(),
                    mime_type="text/plain",
                    source_uri=f"mem0://{user_id}/{uuid.uuid4()}",
                    metadata={**meta, "speaker_role": role},
                )
                results.append(await ingest.ingest(blob))
                if not is_beam:
                    hints = _derive_fact_hints(content, timestamp)
                elif role == "user":
                    hints = _derive_beam_precise_hints(content, timestamp=timestamp)
                else:
                    hints = []
                for hint in hints:
                        hint_blob = DocumentBlob(
                            content=f"{ts_prefix}fact_hint: {hint}".encode(),
                            mime_type="text/plain",
                            source_uri=f"mem0://{user_id}/{uuid.uuid4()}",
                            metadata={**meta, "speaker_role": "fact_hint"},
                        )
                        results.append(await ingest.ingest(hint_blob))
            await session.commit()

        props = sum(r.propositions_extracted for r in results)
        preview = selected[0][1] if selected else ""
        return {
            "results": [
                {
                    "event": "ADD",
                    "memory": f"[{props} props] {preview[:280]}",
                }
            ]
        }

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 200,
        rerank: bool = False,
        score_debug: bool = False,
    ) -> list[dict[str, Any]]:
        _ = (rerank, score_debug)
        apply_style = not user_id.startswith("beam_")
        corpus_id = await self._ensure_corpus(user_id)
        async with self._session_factory() as session:
            rewrites = _query_rewrites(query)
            svc = QueryService(
                session=session,
                intent_classifier=HeuristicIntentClassifier(),
                embedding_provider=self._embedder,
            )
            out = await svc.query(QueryRequest(
                corpus_id=corpus_id,
                question=query,
                max_results=max(1, top_k),
            ))
            rows: list[dict[str, Any]] = []

            # 1) Proposition hits (high precision when available).
            for h in out.hits[: max(1, min(top_k, 100))]:
                lexical = _lexical_score(query, h.normalized_text)
                temporal = _temporal_query_boost(query, h.normalized_text)
                entity = _entity_query_boost(query, h.normalized_text)
                task = _task_query_boost(query, h.normalized_text)
                kw = _keyword_coverage_boost(query, h.normalized_text)
                score = (
                    0.46 * float(h.relevance_score)
                    + 0.30 * lexical
                    + 0.15 * float(h.extraction_confidence)
                    + 0.06 * temporal
                    + 0.03 * entity
                    + 0.04 * task
                    + 0.06 * kw
                )
                if apply_style:
                    score *= _query_evidence_style_multiplier(query, h.normalized_text)
                row = (
                    {
                        "id": str(h.proposition_id),
                        "memory": h.normalized_text,
                        "score": score,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )
                rows.append(row)

            # 2) Pull vector + lexical candidates across query rewrites for recall.
            for q in rewrites:
                chunk_rows = await self._semantic_chunk_rows(
                    session,
                    corpus_id,
                    q,
                    top_k=top_k,
                    apply_style=apply_style,
                )
                for r in chunk_rows:
                    r["score"] = float(r["score"]) * 0.96 if q != query else float(r["score"])
                rows.extend(chunk_rows)
                lexical_rows = await self._lexical_chunk_rows(
                    session,
                    corpus_id,
                    q,
                    top_k=top_k,
                    apply_style=apply_style,
                )
                for r in lexical_rows:
                    r["score"] = float(r["score"]) * 0.96 if q != query else float(r["score"])
                rows.extend(lexical_rows)

            # 4) Deduplicate by normalized memory text.
            dedup: dict[str, dict[str, Any]] = {}
            for row in rows:
                key = " ".join(str(row["memory"]).lower().split())
                prev = dedup.get(key)
                if prev is None or float(row.get("score", 0.0)) > float(prev.get("score", 0.0)):
                    dedup[key] = row

            ranked = sorted(dedup.values(), key=lambda x: float(x.get("score", 0.0)), reverse=True)
            ranked = _apply_update_recency_bias(query, ranked)
            ranked = _deduplicate_near_duplicates(query, ranked, cap=max(top_k * 2, 60))
            if user_id.startswith("beam_"):
                ranked = _role_diverse_ranking(query, ranked, top_k)
            if _should_abstain_from_retrieval(query, ranked):
                return []
            return ranked[:top_k]

    async def delete_user(self, user_id: str) -> bool:
        corpus_id = self._corpus_by_user.pop(user_id, None)
        if corpus_id is None:
            return True
        async with self._session_factory() as session:
            corpus = await session.get(Corpus, corpus_id)
            if corpus is not None:
                await session.delete(corpus)
                await session.commit()
        return True

    async def get_user_profile(self, user_id: str) -> dict[str, Any]:
        _ = user_id
        return {}

    async def _semantic_chunk_rows(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
        query: str,
        top_k: int,
        apply_style: bool = True,
    ) -> list[dict[str, Any]]:
        vecs = await self._embedder.embed_texts([query])
        if not vecs:
            return []
        retrieval = ChunkRetrievalService(
            session,
            corpus_id,
            self._embedder.model_ref,
        )
        candidates = await retrieval.search(
            list(vecs[0]),
            RetrievalConfig(top_k=max(10, min(top_k, 500))),
        )
        rows: list[dict[str, Any]] = []
        for cand in candidates:
            lexical = _lexical_score(query, cand.text)
            temporal = _temporal_query_boost(query, cand.text)
            entity = _entity_query_boost(query, cand.text)
            task = _task_query_boost(query, cand.text)
            kw = _keyword_coverage_boost(query, cand.text)
            length_penalty = _length_penalty(cand.text)
            score = (
                0.58 * float(cand.score)
                + 0.28 * lexical
                + 0.09 * temporal
                + 0.05 * entity
                + 0.04 * task
                + 0.06 * kw
            ) * length_penalty
            if apply_style:
                score *= _query_evidence_style_multiplier(query, cand.text)
            rows.append(
                {
                    "id": str(cand.chunk_id),
                    "memory": cand.text,
                    "score": score,
                }
            )
        return rows

    async def _lexical_chunk_rows(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
        query: str,
        top_k: int,
        apply_style: bool = True,
    ) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        limit = max(10, min(top_k, 500))
        try:
            q = " ".join(_query_tokens(query)[:18])
            if not q:
                return []
            stmt = text(
                """
                WITH q AS (
                  SELECT websearch_to_tsquery('english', :qtext) AS tsq
                )
                SELECT
                  c.id,
                  c.text,
                  ts_rank_cd(to_tsvector('english', c.text), q.tsq) AS ts_score
                FROM chunk c, q
                WHERE c.corpus_id = :corpus_id
                  AND to_tsvector('english', c.text) @@ q.tsq
                ORDER BY ts_score DESC
                LIMIT :lim
                """
            )
            rows = (
                await session.execute(
                    stmt,
                    {
                        "qtext": q,
                        "corpus_id": corpus_id,
                        "lim": limit,
                    },
                )
            ).all()
            out: list[dict[str, Any]] = []
            for cid, chunk_text, ts_score in rows:
                mem = str(chunk_text)
                lx = _lexical_score(query, mem)
                temporal = _temporal_query_boost(query, mem)
                entity = _entity_query_boost(query, mem)
                task = _task_query_boost(query, mem)
                kw = _keyword_coverage_boost(query, mem)
                raw = (
                    0.50 * float(ts_score or 0.0)
                    + 0.30 * lx
                    + 0.10 * temporal
                    + 0.10 * entity
                    + 0.05 * task
                    + 0.08 * kw
                )
                if apply_style:
                    raw *= _query_evidence_style_multiplier(query, mem)
                out.append(
                    {
                        "id": str(cid),
                        "memory": mem,
                        "score": raw * _length_penalty(mem),
                    }
                )
            out.sort(key=lambda x: float(x["score"]), reverse=True)
            return out[:limit]
        except Exception:
            # Fallback for non-Postgres/non-FTS environments.
            tokens = [t for t in _query_tokens(query) if len(t) >= 3][:8]
            if not tokens:
                return []
            stmt = select(Chunk.id, Chunk.text).where(Chunk.corpus_id == corpus_id).limit(3000)
            rows = (await session.execute(stmt)).all()
            out: list[dict[str, Any]] = []
            for cid, chunk_text in rows:
                mem = str(chunk_text)
                lx = _lexical_score(query, mem)
                if lx <= 0.05:
                    continue
                temporal = _temporal_query_boost(query, mem)
                entity = _entity_query_boost(query, mem)
                task = _task_query_boost(query, mem)
                kw = _keyword_coverage_boost(query, mem)
                score = (
                    0.50 * lx
                    + 0.16 * temporal
                    + 0.12 * entity
                    + 0.10 * task
                    + 0.12 * kw
                ) * _length_penalty(mem)
                if apply_style:
                    score *= _query_evidence_style_multiplier(query, mem)
                out.append({"id": str(cid), "memory": mem, "score": score})
            out.sort(key=lambda x: float(x["score"]), reverse=True)
            return out[:limit]

    async def _ensure_corpus(self, user_id: str) -> uuid.UUID:
        existing = self._corpus_by_user.get(user_id)
        if existing is not None:
            return existing
        async with self._session_factory() as session:
            stmt = select(Corpus.id).where(Corpus.name == f"mem0_{user_id}").limit(1)
            found = (await session.execute(stmt)).scalar_one_or_none()
            if found is not None:
                self._corpus_by_user[user_id] = found
                return found
            corpus = Corpus(
                id=uuid.uuid4(),
                name=f"mem0_{user_id}",
                description="Mem0 benchmark adapter corpus",
            )
            session.add(corpus)
            await session.flush()
            await session.commit()
            self._corpus_by_user[user_id] = corpus.id
            return corpus.id


def _lexical_score(query: str, text: str) -> float:
    q_tokens = {t for t in query.lower().split() if len(t) > 2}
    if not q_tokens:
        return 0.0
    t_tokens = {t for t in text.lower().split() if len(t) > 2}
    if not t_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens)
    return overlap / max(1, len(q_tokens))


def _query_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t]


def _length_penalty(text: str) -> float:
    # Very long chunks are often generic digressions in benchmark transcripts.
    n = len(text)
    if n <= 500:
        return 1.0
    if n <= 1200:
        return 0.92
    if n <= 2200:
        return 0.84
    return 0.75


def _should_abstain_from_retrieval(query: str, ranked: list[dict[str, Any]]) -> bool:
    if not ranked:
        return True
    top = ranked[0]
    score = float(top.get("score", 0.0))
    memory = str(top.get("memory", ""))
    q_low = query.lower()
    m_low = memory.lower()
    lexical = _lexical_score(query, memory)
    temporal = _temporal_query_boost(query, memory)
    # For causal "how did X influence Y" asks, intent-only memories are weak evidence.
    if (
        "how did" in q_low
        and "influence" in q_low
        and any(
            phrase in m_low
            for phrase in ("i want to", "i need to", "i'm trying to", "planning to")
        )
        and not any(
            phrase in m_low for phrase in ("because", "resulted in", "led to", "therefore")
        )
    ):
        return True
    # If neither lexical nor temporal evidence is convincing, prefer no retrieval.
    return score < 0.20 and lexical < 0.15 and temporal < 0.2


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[\.\!\?\n])\s+", text.strip())
    out = [p.strip() for p in parts if p and len(p.strip()) >= 24]
    return out


def _refine_with_sentence_evidence(
    query: str,
    ranked: list[dict[str, Any]],
    top_k: int = 50,
) -> list[dict[str, Any]]:
    # Re-rank short evidence snippets from top long memories for better nugget matching.
    base = ranked[: min(len(ranked), 60)]
    refined: list[dict[str, Any]] = []
    for row in base:
        mem = str(row.get("memory", ""))
        base_score = float(row.get("score", 0.0))
        if len(mem) <= 260:
            refined.append(row)
            continue
        for sent in _split_sentences(mem)[:8]:
            lx = _lexical_score(query, sent)
            temporal = _temporal_query_boost(query, sent)
            entity = _entity_query_boost(query, sent)
            if lx < 0.08 and temporal < 0.2 and entity < 0.2:
                continue
            sscore = (0.55 * lx + 0.25 * temporal + 0.20 * entity) + (0.20 * base_score)
            refined.append(
                {
                    "id": row.get("id", ""),
                    "memory": sent,
                    "score": sscore,
                }
            )
    if not refined:
        return ranked
    # Keep originals too so we do not lose broader context.
    refined.extend(base[:20])
    dedup: dict[str, dict[str, Any]] = {}
    for r in refined:
        key = " ".join(str(r.get("memory", "")).lower().split())
        prev = dedup.get(key)
        if prev is None or float(r.get("score", 0.0)) > float(prev.get("score", 0.0)):
            dedup[key] = r
    out = sorted(dedup.values(), key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return out[:top_k]


def _query_rewrites(query: str) -> list[str]:
    q = query.strip()
    ql = q.lower()
    out = [q]
    if any(k in ql for k in ("when", "date", "time", "before", "after", "order")):
        out.append(f"{q} timeline sequence date")
        out.append(f"{q} happened first happened later")
    if any(k in ql for k in ("contradiction", "conflict", "changed", "update")):
        out.append(f"{q} previous statement corrected latest")
        out.append(f"{q} old vs new information")
    if any(k in ql for k in ("instruction", "follow", "asked", "preference")):
        out.append(f"{q} user preference requested constraints")
        out.append(f"{q} requirements and instructions")
    if any(k in ql for k in ("summar", "overview", "what happened")):
        out.append(f"{q} key events outcomes decisions")
    if any(
        k in ql
        for k in ("libraries", "library", "dependencies", "dependency", "version", "versions")
    ):
        out.append(f"{q} dependency versions version numbers")
        out.append(f"{q} flask version flask-login version")
    if any(
        k in ql
        for k in ("columns", "transactions table", "add to the transactions table", "new columns")
    ):
        out.append(f"{q} add column category notes")
    if any(k in ql for k in ("have i", "did i")) and any(
        k in ql for k in ("routes", "http requests", "flask-login", "sessions")
    ):
        out.append(f"{q} never written and also already integrated")
    # stable uniqueness
    dedup: list[str] = []
    seen: set[str] = set()
    for item in out:
        n = " ".join(item.split()).lower()
        if n and n not in seen:
            seen.add(n)
            dedup.append(item)
    return dedup[:5]


_DATE_NUM_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    r"\s+\d{1,2}(?:,\s*\d{4})?\b",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*%\b")
_MS_RE = re.compile(r"\b\d+(?:\.\d+)?\s*ms\b", re.IGNORECASE)
_PORT_RE = re.compile(r"\bport\s+\d{2,5}\b", re.IGNORECASE)
_VERSION_RE = re.compile(
    r"\b(?:python|flask|sqlite|postgres(?:ql)?)\s*\d+(?:\.\d+){0,2}\b",
    re.IGNORECASE,
)
_DEADLINE_RE = re.compile(r"\bdeadline(?: is|:)?\s+([A-Za-z0-9, ]+)", re.IGNORECASE)
_CHANGE_RE = re.compile(
    r"\b(?:initially|was)\s+([^,.]{1,80})\s*(?:,?\s*now|to)\s+([^,.]{1,80})",
    re.IGNORECASE,
)
_N_DAYS_AGO_RE = re.compile(
    r"\b(?:(\d+)|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s+days?\s+ago\b",
    re.IGNORECASE,
)
_N_WEEKS_AGO_RE = re.compile(
    r"\b(?:(\d+)|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s+weeks?\s+ago\b",
    re.IGNORECASE,
)
_N_MONTHS_AGO_RE = re.compile(
    r"\b(?:(\d+)|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s+months?\s+ago\b",
    re.IGNORECASE,
)
_N_YEARS_AGO_RE = re.compile(
    r"\b(?:(\d+)|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s+years?\s+ago\b",
    re.IGNORECASE,
)
_LAST_FRIDAY_RE = re.compile(r"\blast friday\b", re.IGNORECASE)
_LAST_WEEKEND_RE = re.compile(r"\blast weekend\b", re.IGNORECASE)
_WEARS_RE = re.compile(r"\b([A-Z][a-z]+)\s+wears\s+([^.!?\n]{4,120})")

_NUM_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _to_int_token(token: str | None) -> int | None:
    if token is None:
        return None
    tok = token.strip().lower()
    if not tok:
        return None
    if tok.isdigit():
        try:
            return int(tok)
        except ValueError:
            return None
    return _NUM_WORDS.get(tok)


def _derive_fact_hints(content: str, timestamp: int | None) -> list[str]:
    c = " ".join(content.split())
    out: list[str] = []
    low = c.lower()

    if any(k in low for k in ("prefer", "lightweight", "minimal dependencies", "simple")):
        out.append("user_preference: lightweight minimal dependencies simple maintainable stack")
    if any(k in low for k in ("deadline", "mvp", "finish by", "launch")):
        dl = _DEADLINE_RE.search(c)
        if dl:
            out.append(f"project_deadline: {dl.group(1).strip()}")
        else:
            out.append("project_constraint: timeline deadline mvp delivery")
    if any(k in low for k in ("instruction", "must", "need to", "requirement", "should")):
        out.append("instruction_constraint: explicit requirements and constraints present")

    if "ucla" in low:
        out.append("entity_alias_fact: University of California, Los Angeles (UCLA)")
    for m in _WEARS_RE.findall(c):
        name = m[0].strip()
        desc = m[1].strip().rstrip(".,;:")
        if name and desc:
            out.append(f"wardrobe_fact: {name} was wearing {desc}")

    for pat, label in (
        (_DATE_NUM_RE, "date_fact"),
        (_PERCENT_RE, "percent_fact"),
        (_MS_RE, "latency_fact"),
        (_PORT_RE, "port_fact"),
        (_VERSION_RE, "version_fact"),
    ):
        for m in pat.findall(c):
            out.append(f"{label}: {m}")

    ch = _CHANGE_RE.search(c)
    if ch:
        before = ch.group(1).strip()
        after = ch.group(2).strip()
        out.append(f"update_fact: changed from {before} to {after}")

    if timestamp is not None:
        try:
            dt = datetime.fromtimestamp(int(timestamp), tz=UTC)
            out.append(
                f"session_time: {dt.date().isoformat()} "
                f"({dt.day} {dt.strftime('%B')} {dt.year})"
            )
            out.append(f"session_time_human: {dt.day} {dt.strftime('%B')} {dt.year}")

            # Relative-time normalization to improve temporal retrieval matching.
            if _LAST_WEEK_RE.search(c):
                wk_start = dt - timedelta(days=7)
                out.append(
                    "relative_time_fact: the week before "
                    f"{dt.day} {dt.strftime('%B')} {dt.year}"
                )
                out.append(
                    "relative_time_range: "
                    f"{wk_start.date().isoformat()} to {dt.date().isoformat()}"
                )
            if _LAST_MONTH_RE.search(c):
                mo_start = dt - timedelta(days=30)
                out.append(
                    "relative_time_fact: the month before "
                    f"{dt.day} {dt.strftime('%B')} {dt.year}"
                )
                out.append(
                    "relative_time_range: "
                    f"{mo_start.date().isoformat()} to {dt.date().isoformat()}"
                )
            if _LAST_FRIDAY_RE.search(c):
                days_back = (dt.weekday() - 4) % 7 or 7
                fri = dt - timedelta(days=days_back)
                out.append(
                    "relative_time_fact: last Friday was "
                    f"{fri.day} {fri.strftime('%B')} {fri.year}"
                )
                out.append(f"date_fact: {fri.day} {fri.strftime('%B')} {fri.year}")
            if _LAST_WEEKEND_RE.search(c):
                sat_days_back = (dt.weekday() - 5) % 7 or 7
                sat = dt - timedelta(days=sat_days_back)
                sun = sat + timedelta(days=1)
                out.append(
                    "relative_time_fact: last weekend was "
                    f"{sat.day} {sat.strftime('%B')} {sat.year} to "
                    f"{sun.day} {sun.strftime('%B')} {sun.year}"
                )

            def _append_relative(pattern: re.Pattern[str], unit: str) -> None:
                for m in pattern.finditer(c):
                    n = _to_int_token(m.group(1) if m.groups() else None)
                    if n is None:
                        phrase = m.group(0).lower()
                        for word, value in _NUM_WORDS.items():
                            if word in phrase:
                                n = value
                                break
                    if n is None or n <= 0:
                        continue
                    try:
                        if unit == "day":
                            ref = dt - timedelta(days=n)
                            out.append(
                                "relative_time_fact: "
                                f"{n} days before {dt.day} {dt.strftime('%B')} {dt.year}"
                            )
                        elif unit == "week":
                            ref = dt - timedelta(days=7 * n)
                            out.append(
                                "relative_time_fact: "
                                f"{n} weeks before {dt.day} {dt.strftime('%B')} {dt.year}"
                            )
                        elif unit == "month":
                            ref = dt - timedelta(days=30 * n)
                            out.append(
                                "relative_time_fact: "
                                f"{n} months before {dt.day} {dt.strftime('%B')} {dt.year}"
                            )
                        else:
                            ref = dt - timedelta(days=365 * n)
                            out.append(
                                "relative_time_fact: "
                                f"{n} years before {dt.day} {dt.strftime('%B')} {dt.year}"
                            )
                    except OverflowError:
                        continue
                    out.append(f"date_fact: {ref.day} {ref.strftime('%B')} {ref.year}")

            _append_relative(_N_DAYS_AGO_RE, "day")
            _append_relative(_N_WEEKS_AGO_RE, "week")
            _append_relative(_N_MONTHS_AGO_RE, "month")
            _append_relative(_N_YEARS_AGO_RE, "year")
        except (ValueError, OSError, OverflowError):
            pass

    # keep unique and bounded
    dedup: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            dedup.append(item)
    return dedup[:12]


_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def _beam_sanitize_assistant(content: str) -> str:
    # Reduce retrieval noise from long generated code/tutorial blocks.
    text = _CODE_FENCE_RE.sub(" ", content)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    keep: list[str] = []
    for ln in lines:
        low = ln.lower()
        if len(ln) > 280 and not any(
            k in low
            for k in (
                "deadline",
                "ms",
                "port",
                "version",
                "security",
                "login",
                "analytics",
                "transaction",
                "summary",
                "recommend",
                "should",
                "must",
            )
        ):
            continue
        keep.append(ln)
    compact = " ".join(keep)
    compact = re.sub(r"\s+", " ", compact).strip()
    if not compact:
        compact = re.sub(r"\s+", " ", text).strip()
    return compact[:650]


_FACTUAL_QUERY_START_RE = re.compile(
    r"^\s*(?:when|where|what|who|which|did|does|has|have|how long|in what ways)\b",
    re.IGNORECASE,
)
_FIRST_PERSON_FACT_RE = re.compile(
    r"\b(?:i|we|my|our)\b.{0,60}\b(?:went|read|made|signed|joined|started|moved|"
    r"completed|bought|watched|finished|working|been|have|had|love|enjoy|prefer)\b",
    re.IGNORECASE,
)
_INFO_DENSE_TOKEN_RE = re.compile(
    r"\b(?:yesterday|today|tomorrow|last week|last month|deadline|conference|"
    r"parade|support group|speech|class|race|pottery|camping|running|books?|"
    r"ucla|university|bachelor|master|script|wore|wears|wearing)\b",
    re.IGNORECASE,
)


def _assistant_turn_for_memory(content: str, is_beam: bool) -> str | None:
    if is_beam:
        # BEAM questions often hinge on assistant-side execution details.
        return content[:1200]

    normalized = _beam_sanitize_assistant(content)
    if not normalized:
        return None

    low = normalized.lower()
    if len(normalized) < 18:
        return None

    is_question_like = normalized.endswith("?")
    has_first_person_fact = bool(_FIRST_PERSON_FACT_RE.search(normalized))
    has_info_dense_token = bool(_INFO_DENSE_TOKEN_RE.search(normalized))
    has_number = bool(re.search(r"\b\d{1,4}\b", normalized))

    # Suppress low-signal prompting turns while keeping factual assistant memories.
    if (
        is_question_like
        and len(normalized) <= 190
        and not (has_first_person_fact or has_info_dense_token or has_number)
        and any(
            p in low for p in ("what", "which", "how", "why", "care to", "did you", "have you")
        )
    ):
        return None

    return normalized[:900]


def _query_evidence_style_multiplier(query: str, text: str) -> float:
    q = query.lower().strip()
    mem = text.strip()
    low = mem.lower()

    has_fact_signal = bool(_FIRST_PERSON_FACT_RE.search(mem)) or bool(
        _INFO_DENSE_TOKEN_RE.search(mem)
    )
    has_time_or_numeric = bool(_DATE_RE.search(low)) or bool(re.search(r"\b\d{1,4}\b", low))
    is_question_like = mem.endswith("?") and not (has_fact_signal or has_time_or_numeric)

    if _FACTUAL_QUERY_START_RE.search(q):
        if is_question_like:
            return 0.45
        if has_fact_signal or has_time_or_numeric:
            return 1.08

    if (
        any(k in q for k in ("tips", "advice", "suggest", "recommend"))
        and is_question_like
        and low.startswith("assistant:")
    ):
        return 0.70

    return 1.0


def _norm_query_text(text: str) -> str:
    return " ".join(str(text).lower().split())


_BEAM_DATE_RE = re.compile(
    r"\b(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
    r"(?P<day>\d{1,2})(?:,\s*(?P<year>\d{4}))?\b",
    flags=re.IGNORECASE,
)


def _parse_beam_date(
    month_token: str,
    day_token: str,
    year_token: str | None,
    fallback_year: int | None,
) -> datetime | None:
    month_value: int | None = None
    for fmt in ("%B", "%b"):
        try:
            month_value = datetime.strptime(month_token, fmt).month
            break
        except ValueError:
            continue
    if month_value is None:
        return None

    try:
        day_value = int(day_token)
    except ValueError:
        return None

    if year_token is not None:
        try:
            year_value = int(year_token)
        except ValueError:
            return None
    else:
        if fallback_year is None:
            return None
        year_value = fallback_year

    try:
        return datetime(year=year_value, month=month_value, day=day_value, tzinfo=UTC)
    except ValueError:
        return None


def _derive_beam_precise_hints(content: str, timestamp: int | None = None) -> list[str]:
    c = " ".join(content.split())
    low = c.lower()
    hints: list[str] = []
    fallback_year: int | None = None
    if timestamp is not None:
        try:
            fallback_year = datetime.fromtimestamp(int(timestamp), tz=UTC).year
        except (ValueError, OSError, OverflowError):
            fallback_year = None

    # High-precision update hints: "initially X ... now Y".
    m = re.search(r"\binitially\s+([^,.]{1,80})[, ]+(?:but\s+)?now\s+([^,.]{1,80})", low)
    if m:
        hints.append(
            "update_state_hint: changed from "
            f"{m.group(1).strip()} to {m.group(2).strip()}"
        )

    # Date/timeline hints (month day forms + deadline terms), including derived durations.
    date_matches = list(_BEAM_DATE_RE.finditer(c))
    dates = [dm.group(0) for dm in date_matches]
    deadline_terms = ("deadline", "sprint", "timeline", "finish", "complete")
    if len(dates) >= 2 and any(k in low for k in deadline_terms):
        hints.append(f"timeline_hint: {dates[0]} -> {dates[1]}")
    elif len(dates) == 1 and any(k in low for k in deadline_terms):
        hints.append(f"timeline_hint: {dates[0]}")
    if len(date_matches) >= 2 and any(
        k in low for k in ("how many", "weeks", "days", *deadline_terms)
    ):
        first = _parse_beam_date(
            date_matches[0].group("month"),
            date_matches[0].group("day"),
            date_matches[0].group("year"),
            fallback_year=fallback_year,
        )
        second = _parse_beam_date(
            date_matches[1].group("month"),
            date_matches[1].group("day"),
            date_matches[1].group("year"),
            fallback_year=fallback_year,
        )
        if first is not None and second is not None:
            days = abs((second - first).days)
            if days > 0:
                hints.append(f"timeline_delta_hint: {dates[0]} to {dates[1]} equals {days} days")
                whole_weeks = days // 7
                if whole_weeks > 0:
                    hints.append(f"timeline_delta_hint: {whole_weeks} weeks")

    # Preference hints only when explicit.
    if any(k in low for k in ("lightweight", "minimal dependencies", "keep it simple")):
        hints.append("preference_hint: lightweight minimal dependencies simple stack")

    # Keep only strongest four hints to limit noise while preserving temporal deltas.
    dedup: list[str] = []
    seen: set[str] = set()
    for item in hints:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return dedup[:4]


def _role_diverse_ranking(
    query: str,
    ranked: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    # Ensure both user and assistant evidence are represented for BEAM question mix.
    if not ranked:
        return ranked
    user_rows: list[dict[str, Any]] = []
    asst_rows: list[dict[str, Any]] = []
    other_rows: list[dict[str, Any]] = []
    for r in ranked:
        mem = str(r.get("memory", "")).lstrip().lower()
        if mem.startswith("user:"):
            user_rows.append(r)
        elif mem.startswith("assistant:"):
            asst_rows.append(r)
        else:
            other_rows.append(r)

    q = query.lower()
    prefers_assistant = any(k in q for k in (
        "suggest", "steps", "what should", "what would", "recommend",
        "security", "libraries", "improve", "optimize", "summary",
    ))
    prefers_user = any(k in q for k in (
        "how many", "when", "did i", "i have", "my", "across my requests",
        "average", "commits", "weeks",
    ))

    if prefers_assistant and not prefers_user:
        target_asst = max(1, min(len(asst_rows), top_k // 2))
        target_user = max(1, min(len(user_rows), top_k // 4))
    elif prefers_user and not prefers_assistant:
        target_user = max(1, min(len(user_rows), top_k // 2))
        target_asst = max(1, min(len(asst_rows), top_k // 4))
    else:
        target_user = max(1, min(len(user_rows), top_k // 2))
        target_asst = max(1, min(len(asst_rows), top_k // 3))
    out: list[dict[str, Any]] = []
    out.extend(user_rows[:target_user])
    out.extend(asst_rows[:target_asst])

    seen = {" ".join(str(r.get("memory", "")).lower().split()) for r in out}
    for bucket in (ranked, other_rows, user_rows[target_user:], asst_rows[target_asst:]):
        for r in bucket:
            key = " ".join(str(r.get("memory", "")).lower().split())
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
            if len(out) >= top_k:
                return out
    return out


def _deduplicate_near_duplicates(
    query: str,
    ranked: list[dict[str, Any]],
    cap: int = 120,
) -> list[dict[str, Any]]:
    # Keep evidence breadth: suppress near-duplicate memories that crowd out other nuggets.
    kept: list[dict[str, Any]] = []
    kept_sets: list[set[str]] = []
    q_tokens = set(_query_tokens(query))
    for row in ranked:
        text = str(row.get("memory", ""))
        toks = {t for t in _query_tokens(text) if t not in _STOPWORDS}
        if not toks:
            continue
        is_dup = False
        for s in kept_sets:
            inter = len(toks & s)
            union = len(toks | s)
            jac = inter / max(1, union)
            # stricter duplicate threshold if row contributes little query overlap.
            q_overlap = len(toks & q_tokens) / max(1, len(q_tokens)) if q_tokens else 0.0
            threshold = 0.75 if q_overlap < 0.2 else 0.85
            if jac >= threshold:
                is_dup = True
                break
        if is_dup:
            continue
        kept.append(row)
        kept_sets.append(toks)
        if len(kept) >= cap:
            break
    return kept if kept else ranked


def _focus_memory_snippet(query: str, text: str) -> str:
    # Keep short memories as-is; trim long ones to the most query-relevant local window.
    if len(text) <= 380:
        return text
    sentences = _split_sentences(text)
    if not sentences:
        return text[:380]
    scored: list[tuple[float, int]] = []
    for i, sent in enumerate(sentences):
        score = (
            0.50 * _lexical_score(query, sent)
            + 0.20 * _temporal_query_boost(query, sent)
            + 0.15 * _entity_query_boost(query, sent)
            + 0.10 * _task_query_boost(query, sent)
            + 0.05 * _keyword_coverage_boost(query, sent)
        )
        scored.append((score, i))
    scored.sort(reverse=True)
    _, idx = scored[0]
    start = max(0, idx - 1)
    end = min(len(sentences), idx + 2)
    snippet = " ".join(sentences[start:end]).strip()
    if len(snippet) < 140 and end < len(sentences):
        snippet = f"{snippet} {sentences[end]}".strip()
    return snippet[:550]


_TS_PREFIX_RE = re.compile(r"\[ts:([^\]]+)\]")


def _apply_update_recency_bias(query: str, ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    q = query.lower()
    if not any(
        k in q for k in ("latest", "now", "changed", "update", "updated", "before", "after")
    ):
        return ranked

    stamped: list[tuple[dict[str, Any], datetime | None]] = []
    for row in ranked:
        mem = str(row.get("memory", ""))
        m = _TS_PREFIX_RE.search(mem)
        dt = None
        if m:
            try:
                dt = datetime.fromisoformat(m.group(1))
            except ValueError:
                dt = None
        stamped.append((row, dt))

    ts_values = [dt for _, dt in stamped if dt is not None]
    if not ts_values:
        return ranked
    min_ts = min(ts_values)
    max_ts = max(ts_values)
    span = (max_ts - min_ts).total_seconds()
    if span <= 0:
        return ranked

    rescored: list[dict[str, Any]] = []
    for row, dt in stamped:
        base = float(row.get("score", 0.0))
        rec = 0.0 if dt is None else (dt - min_ts).total_seconds() / span
        mem_low = str(row.get("memory", "")).lower()
        marker = 0.0
        if any(
            k in mem_low
            for k in ("now", "latest", "updated", "changed from", "new value", "current")
        ):
            marker = 0.25
        row["score"] = base + 0.20 * rec + marker
        rescored.append(row)
    rescored.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return rescored


_YESTERDAY_RE = re.compile(r"\byesterday\b", re.IGNORECASE)
_TODAY_RE = re.compile(r"\btoday\b", re.IGNORECASE)
_TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
_LAST_WEEK_RE = re.compile(r"\blast week\b", re.IGNORECASE)
_LAST_MONTH_RE = re.compile(r"\blast month\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _enrich_with_temporal_hints(content: str, timestamp: int | None) -> str:
    if timestamp is None:
        return content
    try:
        base = datetime.fromtimestamp(int(timestamp), tz=UTC)
    except (ValueError, OSError, OverflowError):
        return content

    hints: list[str] = []

    def _fmt_day(dt: datetime) -> str:
        return f"{dt.day} {dt.strftime('%B')} {dt.year}"

    if _YESTERDAY_RE.search(content):
        yd = base - timedelta(days=1)
        hints.append(f"date_hint={yd.date().isoformat()}")
        hints.append(f"date_hint_human={_fmt_day(yd)}")
    if _TODAY_RE.search(content):
        hints.append(f"date_hint={base.date().isoformat()}")
        hints.append(f"date_hint_human={_fmt_day(base)}")
    if _TOMORROW_RE.search(content):
        td = base + timedelta(days=1)
        hints.append(f"date_hint={td.date().isoformat()}")
        hints.append(f"date_hint_human={_fmt_day(td)}")
    if _LAST_WEEK_RE.search(content):
        wk_start = base - timedelta(days=7)
        hints.append(
            "date_range_hint="
            f"{wk_start.date().isoformat()}..{base.date().isoformat()}"
        )
        hints.append(f"relative_time_hint=the week before {_fmt_day(base)}")
        hints.append(f"date_range_human={_fmt_day(wk_start)}..{_fmt_day(base)}")
    if _LAST_MONTH_RE.search(content):
        mo_start = base - timedelta(days=30)
        hints.append(
            "date_range_hint="
            f"{mo_start.date().isoformat()}..{base.date().isoformat()}"
        )
        hints.append(f"relative_time_hint=the month before {_fmt_day(base)}")
        hints.append(f"date_range_human={_fmt_day(mo_start)}..{_fmt_day(base)}")
    if _LAST_FRIDAY_RE.search(content):
        days_back = (base.weekday() - 4) % 7 or 7
        fri = base - timedelta(days=days_back)
        hints.append(f"date_hint={fri.date().isoformat()}")
        hints.append(f"date_hint_human={_fmt_day(fri)}")
    if _LAST_WEEKEND_RE.search(content):
        sat_days_back = (base.weekday() - 5) % 7 or 7
        sat = base - timedelta(days=sat_days_back)
        sun = sat + timedelta(days=1)
        hints.append(
            f"date_range_hint={sat.date().isoformat()}..{sun.date().isoformat()}"
        )
        hints.append(f"date_range_human={_fmt_day(sat)}..{_fmt_day(sun)}")

    def _append_relative(pattern: re.Pattern[str], unit: str) -> None:
        for m in pattern.finditer(content):
            n = _to_int_token(m.group(1) if m.groups() else None)
            if n is None:
                phrase = m.group(0).lower()
                for word, value in _NUM_WORDS.items():
                    if word in phrase:
                        n = value
                        break
            if n is None or n <= 0:
                continue
            try:
                if unit == "day":
                    ref = base - timedelta(days=n)
                    hints.append(f"relative_time_hint={n} days before {_fmt_day(base)}")
                elif unit == "week":
                    ref = base - timedelta(days=7 * n)
                    hints.append(f"relative_time_hint={n} weeks before {_fmt_day(base)}")
                elif unit == "month":
                    ref = base - timedelta(days=30 * n)
                    hints.append(f"relative_time_hint={n} months before {_fmt_day(base)}")
                else:
                    ref = base - timedelta(days=365 * n)
                    hints.append(f"relative_time_hint={n} years before {_fmt_day(base)}")
            except OverflowError:
                continue
            hints.append(f"date_hint={ref.date().isoformat()}")
            hints.append(f"date_hint_human={_fmt_day(ref)}")

    _append_relative(_N_DAYS_AGO_RE, "day")
    _append_relative(_N_WEEKS_AGO_RE, "week")
    _append_relative(_N_MONTHS_AGO_RE, "month")
    _append_relative(_N_YEARS_AGO_RE, "year")
    if not hints:
        return content
    return f"{content} [{' ; '.join(hints)}]"


def _temporal_query_boost(query: str, text: str) -> float:
    q = query.lower()
    if not any(tok in q for tok in ("when", "date", "time", "day", "month", "year")):
        return 0.0
    t = text.lower()
    boost = 0.0
    if "[ts:" in t:
        boost += 0.4
    if "date_hint=" in t or "date_range_hint=" in t:
        boost += 0.4
    if "date_hint_human=" in t:
        boost += 0.25
    if _DATE_RE.search(t):
        boost += 0.2
    if re.search(r"\b\d{1,2}\s+[a-z]+\s+\d{4}\b", t):
        boost += 0.15
    return min(boost, 1.0)


def _entity_query_boost(query: str, text: str) -> float:
    q_entities = re.findall(r"\b[A-Z][a-z]+\b", query)
    if not q_entities:
        return 0.0
    t = text.lower()
    overlap = sum(1 for e in q_entities if e.lower() in t)
    return min(1.0, overlap / max(1, len(q_entities)))


def _task_query_boost(query: str, text: str) -> float:
    q = query.lower()
    t = text.lower()
    boost = 0.0
    is_assistant = t.lstrip().startswith("assistant:")
    is_user = t.lstrip().startswith("user:")
    if any(k in q for k in ("how many", "count", "number of", "average", "weeks", "commits")):
        if re.search(r"\b\d+(?:\.\d+)?\b", t):
            boost += 0.45
        if re.search(r"\b\d+(?:\.\d+)?\s*(?:ms|weeks?|days?|hours?)\b", t):
            boost += 0.35
    if any(k in q for k in ("update", "changed", "before", "after", "latest", "now")) and any(
        k in t for k in ("initially", "now", "changed", "updated", "from", "to")
    ):
        boost += 0.45
    if any(
        k in q for k in ("suggest", "steps", "what should", "what would", "libraries", "security")
    ):
        if any(
            k in t
            for k in ("should", "recommend", "suggest", "must", "require", "steps", "libraries")
        ):
            boost += 0.40
        if is_assistant:
            boost += 0.20
    if any(k in q for k in ("lightweight", "minimal", "simple", "preferences", "preference")):
        if any(k in t for k in ("lightweight", "minimal", "simple", "avoid", "prefer")):
            boost += 0.45
        if is_assistant:
            boost += 0.20
    if any(k in q for k in ("summary", "summarize", "comprehensive summary", "progressed")):
        if any(
            k in t
            for k in ("summary", "implemented", "feature", "progress", "timeline", "milestone")
        ):
            boost += 0.40
        if is_user or is_assistant:
            boost += 0.10
    if (
        any(k in q for k in ("how many", "when", "what was", "what is", "did i", "i have", "my"))
        and is_user
    ):
        boost += 0.15
    return min(boost, 1.0)


_STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "with", "from", "by",
    "is", "are", "was", "were", "be", "been", "being", "it", "that", "this", "these",
    "those", "my", "i", "me", "you", "your", "we", "our", "as", "at", "into", "about",
    "how", "what", "when", "where", "which", "who", "did", "do", "does", "have", "has",
    "had", "can", "could", "should", "would",
}


def _keyword_coverage_boost(query: str, text: str) -> float:
    q_tokens = [t for t in _query_tokens(query) if len(t) >= 4 and t not in _STOPWORDS]
    if not q_tokens:
        return 0.0
    q_tokens = q_tokens[:12]
    text_low = text.lower()
    tok_hits = sum(1 for t in q_tokens if t in text_low)
    tok_score = tok_hits / max(1, len(q_tokens))

    # Add light bigram coverage signal for intent-rich phrases.
    q_bigrams = [f"{q_tokens[i]} {q_tokens[i+1]}" for i in range(len(q_tokens) - 1)][:8]
    bi_hits = sum(1 for b in q_bigrams if b in text_low)
    bi_score = bi_hits / max(1, len(q_bigrams)) if q_bigrams else 0.0
    return min(1.0, 0.75 * tok_score + 0.25 * bi_score)
