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
