from __future__ import annotations

import asyncio
import json
import os
import traceback
from typing import Any

from mapu.mcp import server as mcp_server


DOCS: list[dict[str, str]] = [
    {
        "source_uri": "memory://msa-v1",
        "content": (
            "Master Services Agreement. Acme Corp shall deliver quarterly security reports "
            "to Beta Bank. Beta Bank may request clarification in writing."
        ),
        "document_type": "contract",
        "publication_context": "official_filing",
        "source_identity": "acme_legal",
    },
    {
        "source_uri": "memory://amendment-v2",
        "content": (
            "Amendment No. 1. Section 4.2 is amended. Acme Corp shall deliver monthly "
            "security reports to Beta Bank beginning January 1, 2026."
        ),
        "document_type": "contract_amendment",
        "publication_context": "official_filing",
        "source_identity": "acme_legal",
    },
    {
        "source_uri": "memory://board-minutes",
        "content": (
            "Board minutes: Ops team reports that report delivery moved from quarterly to monthly. "
            "No other service-level obligations were changed."
        ),
        "document_type": "internal_minutes",
        "publication_context": "internal_document",
        "source_identity": "acme_ops",
    },
]

QUESTIONS: list[str] = [
    "What reporting obligation does Acme Corp have to Beta Bank?",
    "Did the reporting cadence change over time?",
    "List obligations involving Acme Corp and reports.",
]


def _set_extraction_env() -> None:
    os.environ["MAPU_EMBEDDING_PROVIDER"] = "sentence-transformers"
    os.environ["MAPU_EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"
    os.environ["MAPU_EXTRACTION_AUTO_ACCEPT_MIN"] = "0.45"
    os.environ["MAPU_EXTRACTION_CANDIDATE_MIN"] = "0.2"
    os.environ["MAPU_EXTRACTION_GLINER_ENABLED"] = "false"
    os.environ["MAPU_EXTRACTION_GLINER_RELEX_ENABLED"] = "true"
    os.environ["MAPU_EXTRACTION_GLINER_RELEX_ENTITY_THRESHOLD"] = "0.35"
    os.environ["MAPU_EXTRACTION_GLINER_RELEX_RELATION_THRESHOLD"] = "0.6"
    os.environ["MAPU_EXTRACTION_LLM_ENABLED"] = "false"


async def _run() -> dict[str, Any]:
    _set_extraction_env()

    create_result = await mcp_server.create_corpus(
        name="mcp_relex_smoke",
        description="GLiNER-Relex MCP smoke test corpus",
    )
    corpus_id = create_result["id"]

    ingests: list[dict[str, Any]] = []
    for doc in DOCS:
        ingests.append(
            await mcp_server.ingest_document(
                corpus_id=corpus_id,
                content=doc["content"],
                source_uri=doc["source_uri"],
                mime_type="text/plain",
                document_type=doc["document_type"],
                publication_context=doc["publication_context"],
                source_identity=doc["source_identity"],
            )
        )

    queries: list[dict[str, Any]] = []
    for question in QUESTIONS:
        result = await mcp_server.query(
            corpus_id=corpus_id,
            question=question,
            max_results=10,
        )
        queries.append(
            {
                "question": question,
                "intent": result.get("intent"),
                "tier_used": result.get("tier_used"),
                "epistemic_status": result.get("epistemic_status"),
                "synthesis": result.get("synthesis"),
                "hit_count": len(result.get("hits", [])),
                "top_hits": result.get("hits", [])[:3],
            }
        )

    return {
        "corpus_id": corpus_id,
        "ingests": ingests,
        "queries": queries,
    }


def main() -> None:
    try:
        result = asyncio.run(_run())
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
