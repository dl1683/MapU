"""Grounding: resolves extraction candidates to persisted entities and propositions."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.extraction.abstention import AbstentionDecision, AbstentionResult
from mapu.extraction.types import EntityMention
from mapu.models.attestation import Attestation, AttestationSituation
from mapu.models.entity import Handle
from mapu.models.proposition import Proposition, PropositionParticipant


@dataclass(frozen=True)
class MaterializedExtraction:
    """Result of grounding a candidate into the database."""

    proposition_id: uuid.UUID
    attestation_id: uuid.UUID
    proposition_created: bool
    handle_ids: list[uuid.UUID]


class CandidateGrounder:
    """Resolves candidates to handles, propositions, and attestations."""

    def __init__(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
    ) -> None:
        self._session = session
        self._corpus_id = corpus_id
        self._handle_cache: dict[tuple[str, str], Handle] = {}
        self._proposition_cache: dict[str, Proposition] = {}
        self._participant_cache: set[tuple[uuid.UUID, uuid.UUID, str]] = set()

    async def materialize(
        self,
        result: AbstentionResult,
        source_policy_eval_id: uuid.UUID,
        default_situation_id: uuid.UUID | None = None,
    ) -> MaterializedExtraction | None:
        if result.decision == AbstentionDecision.REJECTED:
            return None

        frame = result.frame

        subject_handle = await self._resolve_handle(frame.subject)
        handle_ids = [subject_handle.id]

        object_handle: Handle | None = None
        if frame.object is not None:
            object_handle = await self._resolve_handle(frame.object)
            handle_ids.append(object_handle.id)

        semantic_key = _compute_semantic_key(
            frame_type=frame.frame_type.value,
            subject_handle_id=subject_handle.id,
            predicate=frame.predicate,
            object_handle_id=object_handle.id if object_handle else None,
            value=frame.value,
            polarity=frame.polarity,
            modality=frame.modality,
            valid_range=frame.valid_range,
        )

        db_valid_range = _to_pg_range(frame.valid_range)

        prop, created = await self._get_or_create_proposition(
            frame_type=frame.frame_type.value,
            subject_handle_id=subject_handle.id,
            predicate=frame.predicate,
            object_handle_id=object_handle.id if object_handle else None,
            value=frame.value,
            polarity=frame.polarity,
            modality=frame.modality,
            valid_range=db_valid_range,
            normalized_text=frame.normalized_text,
            qualifiers=frame.qualifiers,
            semantic_key=semantic_key,
        )

        await self._ensure_participant(prop.id, subject_handle.id, "subject", 0)
        if object_handle is not None:
            await self._ensure_participant(prop.id, object_handle.id, "object", 1)

        attestation_status = (
            "accepted" if result.decision == AbstentionDecision.ACCEPTED
            else "candidate"
        )

        att = Attestation(
            id=uuid.uuid4(),
            span_id=frame.span_id,
            proposition_id=prop.id,
            corpus_id=self._corpus_id,
            source_policy_eval_id=source_policy_eval_id,
            stance=frame.stance.value,
            extraction_method=frame.extraction_method,
            extraction_confidence=frame.extraction_confidence,
            attestation_strength=(
                frame.attestation_strength.value
                if frame.attestation_strength else None
            ),
            status=attestation_status,
            system_created=datetime.now(UTC),
        )
        self._session.add(att)

        if default_situation_id is not None:
            assn = AttestationSituation(
                attestation_id=att.id,
                situation_id=default_situation_id,
                corpus_id=self._corpus_id,
                assignment_confidence=1.0,
                assignment_basis="default_document_situation",
            )
            self._session.add(assn)

        await self._session.flush()

        return MaterializedExtraction(
            proposition_id=prop.id,
            attestation_id=att.id,
            proposition_created=created,
            handle_ids=handle_ids,
        )

    async def _resolve_handle(self, mention: EntityMention) -> Handle:
        """Get or create a handle for an entity mention."""
        cache_key = (mention.text, mention.kind)
        cached = self._handle_cache.get(cache_key)
        if cached is not None:
            return cached

        from sqlalchemy import select

        stmt = select(Handle).where(
            Handle.corpus_id == self._corpus_id,
            Handle.canonical_name == mention.text,
            Handle.kind == mention.kind,
            Handle.status == "active",
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            self._handle_cache[cache_key] = existing
            return existing

        handle = Handle(
            id=uuid.uuid4(),
            corpus_id=self._corpus_id,
            canonical_name=mention.text,
            kind=mention.kind,
            aliases=[],
            status="active",
            created_at=datetime.now(UTC),
        )
        self._session.add(handle)
        self._handle_cache[cache_key] = handle
        return handle

    async def _get_or_create_proposition(
        self,
        *,
        frame_type: str,
        subject_handle_id: uuid.UUID,
        predicate: str,
        object_handle_id: uuid.UUID | None,
        value: dict[str, Any] | None,
        polarity: bool,
        modality: str | None,
        valid_range: Range[datetime] | None,
        normalized_text: str,
        qualifiers: dict[str, Any],
        semantic_key: str,
    ) -> tuple[Proposition, bool]:
        """Get existing proposition by semantic_key or create new one."""
        cached = self._proposition_cache.get(semantic_key)
        if cached is not None:
            return cached, False

        from sqlalchemy import select

        stmt = select(Proposition).where(
            Proposition.corpus_id == self._corpus_id,
            Proposition.semantic_key == semantic_key,
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            self._proposition_cache[semantic_key] = existing
            return existing, False

        prop = Proposition(
            id=uuid.uuid4(),
            corpus_id=self._corpus_id,
            frame_type=frame_type,
            subject_handle_id=subject_handle_id,
            predicate=predicate,
            object_handle_id=object_handle_id,
            value=value,
            polarity=polarity,
            modality=modality,
            valid_range=valid_range,
            normalized_text=normalized_text,
            qualifiers=qualifiers,
            semantic_key=semantic_key,
            system_created=datetime.now(UTC),
        )
        self._session.add(prop)
        self._proposition_cache[semantic_key] = prop
        return prop, True

    async def _ensure_participant(
        self,
        proposition_id: uuid.UUID,
        handle_id: uuid.UUID,
        role: str,
        ordinal: int,
    ) -> None:
        cache_key = (proposition_id, handle_id, role)
        if cache_key in self._participant_cache:
            return

        from sqlalchemy import select

        stmt = select(PropositionParticipant.id).where(
            PropositionParticipant.proposition_id == proposition_id,
            PropositionParticipant.handle_id == handle_id,
            PropositionParticipant.corpus_id == self._corpus_id,
            PropositionParticipant.role == role,
        )
        result = await self._session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            self._participant_cache.add(cache_key)
            return

        self._session.add(PropositionParticipant(
            id=uuid.uuid4(),
            proposition_id=proposition_id,
            handle_id=handle_id,
            corpus_id=self._corpus_id,
            role=role,
            ordinal=ordinal,
        ))
        self._participant_cache.add(cache_key)


def _to_pg_range(
    valid_range: tuple[datetime | None, datetime | None] | None,
) -> Range[datetime] | None:
    if valid_range is None:
        return None
    return Range(valid_range[0], valid_range[1], bounds="[)")


def _compute_semantic_key(
    *,
    frame_type: str,
    subject_handle_id: uuid.UUID,
    predicate: str,
    object_handle_id: uuid.UUID | None,
    value: dict[str, Any] | None,
    polarity: bool,
    modality: str | None,
    valid_range: tuple[datetime | None, datetime | None] | None = None,
) -> str:
    """Deterministic semantic key from grounded content only."""
    range_str = ""
    if valid_range is not None:
        start = valid_range[0].isoformat() if valid_range[0] else ""
        end = valid_range[1].isoformat() if valid_range[1] else ""
        range_str = f"{start}-{end}"
    parts = [
        frame_type,
        str(subject_handle_id),
        predicate,
        str(object_handle_id) if object_handle_id else "",
        str(sorted(value.items())) if value else "",
        str(polarity),
        modality or "",
        range_str,
    ]
    content = "|".join(parts)
    digest = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{frame_type}:{predicate}:{digest}"
