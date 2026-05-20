import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

adapter = importlib.import_module("mapu_mem0_adapter")
_derive_beam_precise_hints = adapter._derive_beam_precise_hints
_derive_fact_hints = adapter._derive_fact_hints
_enrich_with_temporal_hints = adapter._enrich_with_temporal_hints
_focus_ranked_memory_snippets = adapter._focus_ranked_memory_snippets
_lexical_score = adapter._lexical_score
_refine_with_sentence_evidence = adapter._refine_with_sentence_evidence


def test_temporal_hints_skip_out_of_range_relative_years() -> None:
    text = "I mentioned this 999999999 years ago."

    enriched = _enrich_with_temporal_hints(text, timestamp=0)

    assert enriched == text


def test_temporal_hints_keep_valid_relative_years() -> None:
    text = "I mentioned this two years ago."

    enriched = _enrich_with_temporal_hints(text, timestamp=1_700_000_000)

    assert "relative_time_hint=2 years before" in enriched
    assert "date_hint=" in enriched


def test_temporal_hints_include_natural_resolved_event_date() -> None:
    text = "I went to the support group yesterday."

    enriched = _enrich_with_temporal_hints(text, timestamp=1_683_552_960)

    assert "resolved_event_date=7 May 2023" in enriched
    assert "date_hint_human=7 May 2023" in enriched


def test_fact_hints_promote_common_identity_and_duration_facts() -> None:
    text = "My cat's name is Luna. My daily commute takes 45 minutes each way."

    hints = _derive_fact_hints(text, timestamp=1_683_552_960)

    assert "identity_fact: user's cat name is Luna" in hints
    assert "duration_fact: commute takes 45 minutes each way" in hints


def test_beam_precise_hints_promote_common_identity_and_duration_facts() -> None:
    text = "My cat's name is Luna. My daily commute takes 45 minutes each way."

    hints = _derive_beam_precise_hints(text, timestamp=1_683_552_960)

    assert "identity_hint: user's cat name is Luna" in hints
    assert "duration_hint: commute takes 45 minutes each way" in hints


def test_lexical_score_ignores_punctuation_boundaries() -> None:
    score = _lexical_score("cat name Luna", "My cat's name is Luna.")

    assert score == 1.0


def test_sentence_refinement_promotes_query_relevant_snippet() -> None:
    ranked = [
        {
            "id": "chunk-1",
            "memory": (
                "We discussed unrelated setup details. "
                "The setup notes covered package managers, temporary folders, "
                "shell commands, and build warnings that do not answer the question. "
                "My cat's name is Luna. "
                "Then we changed topics to project planning, release audits, "
                "and other material unrelated to the pet identity fact."
            ),
            "score": 0.30,
        }
    ]

    refined = _refine_with_sentence_evidence("What is my cat's name?", ranked, top_k=5)

    assert refined[0]["memory"] == "My cat's name is Luna."
    assert float(refined[0]["score"]) > float(ranked[0]["score"])


def test_sentence_refinement_preserves_recall_tail() -> None:
    ranked = [
        {
            "id": "top",
            "memory": (
                "We discussed unrelated setup details. "
                "My cat's name is Luna. "
                "Then we changed topics to project planning."
            ),
            "score": 0.30,
        }
    ]
    ranked.extend(
        {"id": f"tail-{i}", "memory": f"Tail memory {i}", "score": 0.1}
        for i in range(79)
    )

    refined = _refine_with_sentence_evidence("What is my cat's name?", ranked, top_k=100)

    assert any(row["id"] == "tail-78" for row in refined)


def test_focused_ranked_memory_snippets_trim_long_irrelevant_context() -> None:
    long_memory = (
        "First we reviewed a long unrelated deployment checklist. "
        "It covered ports, retries, and logging. "
        "The deployment checklist had many details about worker pools, retries, "
        "socket timeouts, and observability dashboards. "
        "The allergy plan says Jamie must avoid peanuts during the trip. "
        "After that we discussed packaging and release notes. "
        "The release notes included migration cleanup, command examples, "
        "and several unrelated operator warnings."
    )

    focused = _focus_ranked_memory_snippets(
        "What should Jamie avoid during the trip?",
        [{"id": "chunk-1", "memory": long_memory, "score": 0.7}],
        cap=3,
    )

    assert any(
        "Jamie must avoid peanuts" in row["memory"] and len(row["memory"]) < len(long_memory)
        for row in focused
    )


def test_focused_ranked_memory_snippets_preserve_original_memory() -> None:
    long_memory = (
        "First we reviewed a long unrelated deployment checklist. "
        "It covered ports, retries, and logging. "
        "The allergy plan says Jamie must avoid peanuts during the trip. "
        "After that we discussed packaging and release notes."
    )

    focused = _focus_ranked_memory_snippets(
        "What should Jamie avoid during the trip?",
        [{"id": "chunk-1", "memory": long_memory, "score": 0.7}],
        cap=3,
    )

    assert any(row["memory"] == long_memory for row in focused)
