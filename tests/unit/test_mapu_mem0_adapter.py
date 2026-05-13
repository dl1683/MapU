import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from mapu_mem0_adapter import _enrich_with_temporal_hints


def test_temporal_hints_skip_out_of_range_relative_years() -> None:
    text = "I mentioned this 999999999 years ago."

    enriched = _enrich_with_temporal_hints(text, timestamp=0)

    assert enriched == text


def test_temporal_hints_keep_valid_relative_years() -> None:
    text = "I mentioned this two years ago."

    enriched = _enrich_with_temporal_hints(text, timestamp=1_700_000_000)

    assert "relative_time_hint=2 years before" in enriched
    assert "date_hint=" in enriched
