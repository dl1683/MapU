"""Unit tests for benchmark scoring gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mapu.evaluation import ama_bench, memoryarena


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_memoryarena_score_enforces_min_exact_match(tmp_path: Path) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    out = tmp_path / "memoryarena_score.json"

    _write_jsonl(
        scenarios,
        [
            {
                "config": "bundled_shopping",
                "scenario_id": "bundled_shopping:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "expected_answer": "Blue mug",
                    },
                    {
                        "turn_index": 1,
                        "expected_answer": "Two towels",
                    },
                ],
            }
        ],
    )
    _write_jsonl(
        predictions,
        [
            {
                "config": "bundled_shopping",
                "scenario_id": "bundled_shopping:1",
                "turn_index": 0,
                "prediction": "blue mug",
            },
            {
                "config": "bundled_shopping",
                "scenario_id": "bundled_shopping:1",
                "turn_index": 1,
                "prediction": "wrong",
            },
        ],
    )

    rc = memoryarena.score(
        str(scenarios),
        str(predictions),
        str(out),
        min_exact_match=0.75,
    )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1
    assert report["status"] == "fail"
    assert report["evaluated"] == 2
    assert report["exact_match"] == 0.5
    assert report["token_f1"] > 0
    assert report["by_config"]["bundled_shopping"]["token_f1"] == 0.5
    assert report["passed_min_exact_match"] is False
    assert "below required" in report["failure_reason"]
    assert len(report["item_scores"]) == 2
    assert report["item_scores"][0]["config"] == "bundled_shopping"
    assert report["item_scores"][0]["exact_match"] is True
    assert report["item_scores"][1]["token_f1"] == 0.0
    assert report["worst_items"][0]["turn_index"] == 1
    assert report["worst_items"][0]["prediction_preview"] == "wrong"


def test_memoryarena_score_rejects_invalid_jsonl_with_line_number(tmp_path: Path) -> None:
    scenarios = tmp_path / "bad_scenarios.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    out = tmp_path / "score.json"
    scenarios.write_text("{bad json\n", encoding="utf-8")
    _write_jsonl(predictions, [])

    with pytest.raises(SystemExit) as exc_info:
        memoryarena.score(str(scenarios), str(predictions), str(out))

    message = str(exc_info.value)
    assert "Invalid JSONL" in message
    assert "line 1" in message


def test_ama_score_rejects_non_object_jsonl_with_line_number(tmp_path: Path) -> None:
    scenarios = tmp_path / "bad_scenarios.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    out = tmp_path / "score.json"
    scenarios.write_text("[]\n", encoding="utf-8")
    _write_jsonl(predictions, [])

    with pytest.raises(SystemExit) as exc_info:
        ama_bench.score(str(scenarios), str(predictions), str(out))

    message = str(exc_info.value)
    assert "Invalid JSONL" in message
    assert "line 1" in message
    assert "expected object" in message


def test_memoryarena_score_passes_when_threshold_met(tmp_path: Path) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    out = tmp_path / "memoryarena_score.json"

    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:1",
                "sessions": [{"turn_index": 0, "expected_answer": {"a": 1}}],
            }
        ],
    )
    _write_jsonl(
        predictions,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:1",
                "turn_index": 0,
                "prediction": {"a": 1},
            }
        ],
    )

    rc = memoryarena.score(
        str(scenarios),
        str(predictions),
        str(out),
        min_exact_match=1.0,
    )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["status"] == "ok"
    assert report["exact_match"] == 1.0
    assert report["token_f1"] == 1.0
    assert report["by_config"]["progressive_search"]["token_f1"] == 1.0


def test_memoryarena_predict_emits_structured_predictions_without_answers(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "bundled_shopping",
                "scenario_id": "bundled_shopping:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "Product 1\n**Available Options:**\n"
                            "- A red cotton shirt.\n"
                            "- A blue ceramic mug."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"]["target_asin"] == ""
    assert rows[0]["method"] == "mapu_benchmark_agnostic_memoryarena_v1"
    assert "expected_answer" not in rows[0]


def test_memoryarena_predict_applies_shopping_compatibility_rule(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "bundled_shopping",
                "scenario_id": "bundled_shopping:1",
                "sessions": [
                    {
                        "turn_index": 2,
                        "prompt": (
                            "Product 3:\n### Select Coloring Base\n"
                            "**Available Options:**\n"
                            "- An AmeriColor blue airbrush food color.\n"
                            "- A U.S. Cake Supply Liqua-Gel Cake Food Coloring.\n"
                            "- A Whishine powder food coloring kit with 8 colors "
                            "for cake decorating."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["evidence"]["selected_option"].startswith("A Whishine")
    assert "powder food coloring" in rows[0]["prediction"]["attributes"]


def test_memoryarena_predict_answers_progressive_search_entity_question(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "In a 2020 interview, which individual was in the "
                            "first year of university when they went for an "
                            "audition that later became their first gig?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "Ihuoma Sonia Uche" in rows[0]["prediction"]
    assert "Exact Answer" in rows[0]["prediction"]
    assert rows[0]["evidence"]["selected_option"] is None


def test_memoryarena_default_predictor_does_not_use_benchmark_specific_entity_fact(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "In a 2020 interview, which individual was in the "
                            "first year of university when they went for an "
                            "audition that later became their first gig?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "Ihuoma Sonia Uche" not in json.dumps(rows[0]["prediction"])
    assert "not have enough non-answer context" in rows[0]["prediction"]
    assert rows[0]["method"] == "mapu_benchmark_agnostic_memoryarena_v1"


def test_shopping_selector_applies_color_avoid_rules_for_prior_multicolor_item() -> None:
    prompt = (
        "**Goal:** Compatibility notes: Fudge pairs well with Chocolate. "
        "Red pairs well with Gold. Pink pairs well with Pearl. "
        "Blue pairs well with Silver. Yellow pairs well with Rainbow.\n"
        "**Avoid:** Fudge avoids Rainbow, Confetti, Pearl, Silver. "
        "Red avoids Green, Silver, Rainbow. Pink avoids Chocolate, Green, Orange.\n"
        "**Available Options:**\n"
        "- A 4oz pack of gold metallic dragees sprinkle mix for decorating cakes.\n"
        "- A Vintage Rose Gold Sprinkles Mix with 4oz for weddings and bridal showers.\n"
        "- A Manvscakes 4 oz sprinkle mix with St Patrick's Day theme and green and gold colors."
    )
    prior_memory = [
        "Selected option: A Whishine powder food coloring kit with 8 colors. "
        "Attributes: powder food coloring, cake decorating, 8 colors."
    ]

    selected = memoryarena._select_option_by_instructions(  # noqa: SLF001
        prompt,
        [
            "A 4oz pack of gold metallic dragees sprinkle mix for decorating cakes.",
            "A Vintage Rose Gold Sprinkles Mix with 4oz for weddings and bridal showers.",
            "A Manvscakes 4 oz sprinkle mix with St Patrick's Day theme and green and gold colors.",
        ],
        prior_memory,
    )

    assert selected == "A 4oz pack of gold metallic dragees sprinkle mix for decorating cakes."


def test_shopping_selector_treats_numeral_as_number_avoid_term() -> None:
    prompt = (
        "**Goal:** Compatibility notes: Wedding pairs well with Gold.\n"
        "**Avoid:** Wedding avoids Number, Colorful, Striped.\n"
        "**Available Options:**\n"
        "- A BBTO 50th birthday cake topper decoration with glitter numeral candles in rose gold.\n"
        "- A Amscan #5 metallic birthday candle in gold for my party."
    )
    prior_memory = [
        "Selected option: A Gyufise gold glitter cake topper for Thanksgiving "
        "and wedding party decoration. Attributes: gold glitter, cake topper, "
        "wedding party, supplies."
    ]

    selected = memoryarena._select_option_by_instructions(  # noqa: SLF001
        prompt,
        [
            "A BBTO 50th birthday cake topper decoration with glitter numeral "
            "candles in rose gold.",
            "A Amscan #5 metallic birthday candle in gold for my party.",
        ],
        prior_memory,
    )

    assert selected == "A Amscan #5 metallic birthday candle in gold for my party."


def test_shopping_attributes_are_extracted_from_option_text() -> None:
    color_attrs = memoryarena._shopping_attributes(  # noqa: SLF001
        "A BrightBake powder food coloring kit with 8 colors for cake decorating."
    )
    sprinkle_attrs = memoryarena._shopping_attributes(  # noqa: SLF001
        "An Acme gold metallic dragees sprinkle mix for decorating cakes and cupcakes."
    )

    assert "powder food coloring" in color_attrs
    assert "8 colors" in color_attrs
    assert "cake decorating" in color_attrs
    assert "gold" in sprinkle_attrs
    assert "metallic" in sprinkle_attrs
    assert "dragees" in sprinkle_attrs
    assert "sprinkle mix" in sprinkle_attrs


def test_memoryarena_web_grounded_predictor_uses_search_sources(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"

    def fake_web_search(query: str, *, max_results: int = 5, timeout_seconds: float = 8.0):
        assert "audition" in query
        assert max_results == 5
        assert timeout_seconds == 8.0
        return [
            memoryarena.WebSearchHit(
                title="Maya Rao interview",
                url="https://example.test/maya-rao",
                snippet=(
                    "Maya Rao said she started her career through an audition "
                    "during her first year at university."
                ),
            )
        ]

    monkeypatch.setattr(memoryarena, "_web_search", fake_web_search)
    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "In a 2020 interview, which individual stated that "
                            "they started a career through an audition?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="web_grounded",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "Maya Rao" in rows[0]["prediction"]
    assert rows[0]["method"] == "mapu_web_grounded_memoryarena_v1"
    assert rows[0]["evidence"]["web"]["sources"][0]["url"] == "https://example.test/maya-rao"


def test_memoryarena_web_query_prioritizes_distinctive_clues() -> None:
    query = memoryarena._web_query(
        "Which individual was born between 1986 and 1996, as stated in a 2023 article?",
        [
            (
                "Which individual was in the first year of university when they "
                "went for an audition that later became their first gig?"
            ),
            "Which individual stated in a 2020 interview that they owned a business?",
            "Which individual stated in a 2020 interview that they were a child of divorce?",
            (
                "Which individual was speculated to have their first child, but "
                "the speculation was later proven false?"
            ),
        ],
    )

    query_terms = query.split()
    assert {"audition", "business", "child", "divorce"} <= set(query_terms[:8])
    assert "first" not in query_terms
    assert "stated" not in query_terms


def test_memoryarena_web_entity_extraction_ignores_meta_titles() -> None:
    hits = [
        memoryarena.WebSearchHit(
            title='Search results for "first year of university" audition',
            url="https://example.test/search",
            snippet="A generic search page mentioning First Year and Audition.",
        ),
        memoryarena.WebSearchHit(
            title="Before Stardom With Sonia Uche - Punch Newspapers",
            url="https://example.test/sonia-uche",
            snippet=(
                "Sonia Uche found an audition notice during her first year "
                "in the university and later became an entrepreneur."
            ),
        ),
    ]

    answer = memoryarena._best_web_entity_answer(  # noqa: SLF001
        "Which individual was in the first year of university when they auditioned?",
        hits,
    )

    assert answer == "Sonia Uche"


def test_memoryarena_web_grounded_filters_low_value_search_sources(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"

    def fake_web_search(query: str, *, max_results: int = 5, timeout_seconds: float = 8.0):
        return [
            memoryarena.WebSearchHit(
                title="Audio recording and editing software | Adobe Audition",
                url="https://adobe.example/audition",
                snippet="Adobe Audition is audio editing software.",
            ),
            memoryarena.WebSearchHit(
                title="FIRST | English meaning - Cambridge Dictionary",
                url="https://dictionary.example/first",
                snippet="FIRST means coming before all others.",
            ),
            memoryarena.WebSearchHit(
                title="Personal Banking, Credit Cards & Loans",
                url="https://bank.example/",
                snippet="First City offers bank accounts and credit cards.",
            ),
        ]

    monkeypatch.setattr(memoryarena, "_web_search", fake_web_search)
    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:noise",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": "Who was in the first year of university when they auditioned?",
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="web_grounded",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == memoryarena._ABSTAIN_ANSWER
    assert rows[0]["evidence"]["web"]["sources"][0]["title"].startswith("Audio")


def test_memoryarena_web_grounded_rejects_low_relevance_generic_sources(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"

    def fake_web_search(query: str, *, max_results: int = 5, timeout_seconds: float = 8.0):
        return [
            memoryarena.WebSearchHit(
                title="Drinks That Make You Poop Immediately",
                url="https://health.example/constipation",
                snippet="Find constipation relief with one of these laxative drinks.",
            ),
            memoryarena.WebSearchHit(
                title="Largest Cities by Population",
                url="https://cities.example/largest",
                snippet="A list of large cities and metropolitan areas.",
            ),
            memoryarena.WebSearchHit(
                title="International Trucks",
                url="https://trucks.example/",
                snippet="Explore medium-duty and heavy-duty trucks.",
            ),
        ]

    monkeypatch.setattr(memoryarena, "_web_search", fake_web_search)
    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:noise",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "Which individual stated in a 2020 interview that "
                            "they were a child of divorce?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="web_grounded",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == memoryarena._ABSTAIN_ANSWER


def test_memoryarena_default_predictor_returns_grounded_text_for_non_option_tasks(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": "Which lemma proves the quotient map?",
                        "background": (
                            "Irrelevant note.\n\n"
                            "Lemma 2.13 proves the quotient map is a "
                            "homeomorphism for the zero set."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"].startswith("Lemma 2.13 proves")
    assert "Lemma 2.13" in rows[0]["prediction"]
    assert rows[0]["evidence"]["selected_option"] is None


def test_memoryarena_default_predictor_extracts_embedded_answer_sentence(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "Construct a map from A to B. "
                            "The map f(x) := x + 1 is a bijection."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == "The map f(x) := x + 1 is a bijection."


def test_memoryarena_default_predictor_does_not_echo_unanswered_prompt(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": "Which external source names the release manager?",
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == (
        "I do not have enough non-answer context in this scenario to answer directly."
    )


def test_memoryarena_default_predictor_does_not_echo_prior_unanswered_prompt(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": "Which individual signed the launch memo?",
                        "expected_answer": "hidden",
                    },
                    {
                        "turn_index": 1,
                        "prompt": "Which person later revised that memo?",
                        "expected_answer": "hidden",
                    },
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[1]["prediction"] == (
        "I do not have enough non-answer context in this scenario to answer directly."
    )


def test_memoryarena_diagnostic_predictor_derives_vanishing_ideal_zero_set(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "Let $M$ be a manifold, $C\\subset M$ a closed subset "
                            "and $I\\subset \\cin(M)$ the vanishing ideal of $C$. "
                            "What is the zero set Z of I?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == "The zero set Z of I is exactly C."


def test_memoryarena_diagnostic_predictor_extracts_constructed_map_definition(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "Construct a map $\\nu: Z_J\\to X_\\scA$.\n"
                            "The map\n\\[\n"
                            "\\nu: Z_J\\to X_\\scA, \\qquad "
                            "\\nu( p) := \\overline{ev}_p\n"
                            "\\]\n"
                            "is a homeomorphism."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == r"A correct function is $\nu( p) := \overline{ev}_p$."


def test_memoryarena_diagnostic_predictor_derives_locality_coefficients_without_c0(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Definition (contact polynomial ansatz): "
                            "$\\mathcal{P}(s,t)=c_0+c_2 S_2+c_3 S_3$. "
                            "Locality constraint: coefficients in the large-s "
                            "expansion vanish."
                        ),
                        "prompt": (
                            "For $\\mathcal{A}=\\{1,3\\}$ with $\\sigma=4$, "
                            "determine $(c_2,c_3,c_0)$ from locality."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "$c_2=-4$" in rows[0]["prediction"]
    assert "$c_3=-2$" in rows[0]["prediction"]
    assert "does not include the normalization equation" in rows[0]["prediction"]


def test_memoryarena_diagnostic_predictor_derives_symmetric_normalized_c0(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Definition (pole kernel): $K_a(x)=\\frac{x^4}{x-a}$. "
                            "Definition (contact polynomial ansatz): "
                            "$\\mathcal{P}(s,t)=c_0+c_2 S_2+c_3 S_3$. "
                            "The full amplitude is crossing symmetric and "
                            "locality cancels the large-s polynomial terms."
                        ),
                        "prompt": (
                            "For $\\mathcal{A}=\\{1,3\\}$ with $\\sigma=4$, "
                            "determine $(c_2,c_3,c_0)$ from \\eqref{eq:locality} "
                            "and \\eqref{eq:norm}."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == (
        r"For $\sigma=4$ and $\mathcal{A}=\{1,3\}$: "
        r"$(c_2,c_3,c_0)=(-4,-2,\frac{64}{5})$."
    )


def test_memoryarena_diagnostic_predictor_carries_prior_background_context(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Definition (contact polynomial ansatz): "
                            "$\\mathcal{P}(s,t)=c_0+c_2 S_2+c_3 S_3$. "
                            "Locality constraint: coefficients in the large-s "
                            "expansion vanish."
                        ),
                        "prompt": "Record the amplitude setup.",
                        "expected_answer": "hidden",
                    },
                    {
                        "turn_index": 1,
                        "background": "",
                        "prompt": (
                            "For $\\mathcal{A}=\\{1,3\\}$ with $\\sigma=4$, "
                            "determine $(c_2,c_3,c_0)$."
                        ),
                        "expected_answer": "hidden",
                    },
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "$c_2=-4$" in rows[1]["prediction"]
    assert "$c_3=-2$" in rows[1]["prediction"]


def test_memoryarena_diagnostic_predictor_carries_prior_normalization_reference(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Definition (contact polynomial ansatz): "
                            "$\\mathcal{P}(s,t)=c_0+c_2 S_2+c_3 S_3$. "
                            "Locality constraint: coefficients in the large-s "
                            "expansion vanish."
                        ),
                        "prompt": (
                            "For $\\mathcal{A}=\\{1\\}$ with $\\sigma=4$, determine "
                            "$(c_2,c_3,c_0)$ from \\eqref{eq:locality} and "
                            "\\eqref{eq:norm}."
                        ),
                        "expected_answer": "hidden",
                    },
                    {
                        "turn_index": 1,
                        "background": "",
                        "prompt": (
                            "For $\\mathcal{A}=\\{1,3\\}$ with $\\sigma=4$, "
                            "determine $(c_2,c_3,c_0)$."
                        ),
                        "expected_answer": "hidden",
                    },
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[1]["prediction"] == (
        r"For $\sigma=4$ and $\mathcal{A}=\{1,3\}$: "
        r"$(c_2,c_3,c_0)=(-4,-2,\frac{64}{5})$."
    )


def test_memoryarena_diagnostic_predictor_derives_relative_coordinate_identity(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:relative",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            r"\begin{eqnarray}x_i=\sum_{k=1}^NA_{ik}y_{k}."
                            r"\end{eqnarray}"
                            r"Definition ($b^{[i,j]}$): "
                            r"\begin{equation}b^{[i,j]}_k = "
                            r"\frac{1}{\sqrt{2}}\left(A_{ik}-A_{jk}\right)."
                            r"\end{equation}"
                            r"\begin{equation}r\,\cos\Theta^a = "
                            r"\mathbf{b}^a\cdot \mathbf{y}="
                            r"\sum_{i=1}^{N-1}b^a_iy_i.\end{equation}"
                        ),
                        "prompt": (
                            r"How to write $x_i - x_j$ in terms of $r$ and "
                            r"$\Theta^a$?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert r"x_i-x_j" in rows[0]["prediction"]
    assert r"\sqrt{2} r \cos\Theta^a" in rows[0]["prediction"]


def test_memoryarena_default_predictor_uses_source_grounded_formal_synthesis(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:relative",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            r"\begin{eqnarray}x_i=\sum_{k=1}^NA_{ik}y_{k}."
                            r"\end{eqnarray}"
                            r"Definition ($b^{[i,j]}$): "
                            r"\begin{equation}b^{[i,j]}_k = "
                            r"\frac{1}{\sqrt{2}}\left(A_{ik}-A_{jk}\right)."
                            r"\end{equation}"
                            r"\begin{equation}r\,\cos\Theta^a = "
                            r"\mathbf{b}^a\cdot \mathbf{y}="
                            r"\sum_{i=1}^{N-1}b^a_iy_i.\end{equation}"
                        ),
                        "prompt": (
                            r"How to write $x_i - x_j$ in terms of $r$ and "
                            r"$\Theta^a$?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_benchmark_agnostic_memoryarena_v1"
    assert r"x_i-x_j" in rows[0]["prediction"]
    assert r"\sqrt{2} r \cos\Theta^a" in rows[0]["prediction"]


def test_memoryarena_default_predictor_does_not_use_prompt_only_select_all_shortcut(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:select-all",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": "",
                        "prompt": (
                            "Which of these is an isomorphism of what structures? "
                            "Select all that apply. A. rings. B. modules. C. sets."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_benchmark_agnostic_memoryarena_v1"
    assert rows[0]["prediction"] != "The correct answer is A,B,C."


def test_memoryarena_default_predictor_uses_explicit_prompt_math_when_grounded(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:explicit",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": "",
                        "prompt": (
                            r"Construct a map $u: Z_J\to X_\scA$. The map "
                            "\n"
                            r"\[ u: Z_J\to X_\scA, \qquad "
                            r"u( p) := \overline{ev}_p \]"
                            " is a homeomorphism."
                        ),
                        "expected_answer": "hidden",
                    },
                    {
                        "turn_index": 1,
                        "background": "",
                        "prompt": (
                            r"Let $M$ be a manifold, $C\subset M$ a closed subset "
                            r"and $I\subset \cin(M)$ the vanishing ideal of $C$. "
                            "What is the zero set Z of I?"
                        ),
                        "expected_answer": "hidden",
                    },
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == r"A correct function is $u( p) := \overline{ev}_p$."
    assert rows[1]["prediction"] == "The zero set Z of I is exactly C."


def test_memoryarena_default_predictor_derives_source_grounded_vdm_identities(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    background = (
        r"Definition (Dilatation Generator): $D$ is defined as follows. "
        r"Definition (Special Conformal Transformation): $K$ is defined as follows. "
        r"Definition ($\vdm(\mathbf{y})$): "
        r"\begin{equation}\vdm(\mathbf{y}) ="
        r"\prod_{j<i}\left(\frac{\mathbf{b}^{[i,j]}\cdot \mathbf{y}}{r}\right)"
        r"= \prod_a\,\cos\Theta^a\end{equation}"
        r"Definition (Similarity Transformation): "
        r"\begin{equation}\mathcal{D}= \vdm^{-\lambda} D\vdm^\lambda,"
        r"\qquad \mathcal{K}= \vdm^{-\lambda} K\vdm^\lambda,"
        r"\qquad \hat{\mathcal{L}}^2_{S^{N-2}}="
        r"\vdm^{-\lambda} \hat{L}^2_{S^{N-2}} \vdm^\lambda.\end{equation}"
        r"Definition (Polar Coordinates for $N=3$): In the $N=3$ case, "
        r"we define $(r,\vartheta)$ by "
        r"\begin{equation}\mathbf{y}=(r\cos\vartheta,r\sin\vartheta).\end{equation}"
    )
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:vdm",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": background,
                        "prompt": (
                            r"How to write $\mathcal{D}$ and $\mathcal{K}$ "
                            r"in terms of $D$ and $K$?"
                        ),
                        "expected_answer": "hidden",
                    },
                    {
                        "turn_index": 1,
                        "background": background,
                        "prompt": (
                            r"For each $1\le i \le N-1$, what are "
                            r"$\pa_{y_i}\log\vdm$ and "
                            r"$\pa_{y_i}^2\log\vdm$, in terms of $y_i$, $r$, "
                            r"and $\mathbf{b}^c$?"
                        ),
                        "expected_answer": "hidden",
                    },
                    {
                        "turn_index": 2,
                        "background": background,
                        "prompt": (
                            r"In the $N=3$ case, how to write "
                            r"$\hat{\mathcal{L}}^2_{S^{1}}$ in terms of "
                            r"$\vdm$, $\vartheta$, and $\lambda$?"
                        ),
                        "expected_answer": "hidden",
                    },
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert r"\mathcal{D} = D" in rows[0]["prediction"]
    assert r"\mathcal{K} = K" in rows[0]["prediction"]
    assert r"\pa_{y_i}\log\vdm" in rows[1]["prediction"]
    assert r"\sum_c\frac{b^c_i}{\mathbf{b}^c\cdot \mathbf{y}}" in rows[1]["prediction"]
    assert r"\hat{\mathcal{L}}^2_{S^{1}}" in rows[2]["prediction"]
    assert r"\vdm^{-2\lambda}" in rows[2]["prediction"]


def test_memoryarena_diagnostic_predictor_derives_conformal_commutators(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:commutators",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Definition (Dilatation Generator): $D$ is defined. "
                            "Definition (Special Conformal Transformation): $K$ "
                            "is defined. The Hamiltonian is $H$."
                        ),
                        "prompt": (
                            "What are the commutators $[D,H]$, $[D,K]$, and "
                            "$[K,H]$, in terms of $H$, $K$, and $D$?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert r"[D,H]=iH" in rows[0]["prediction"]
    assert r"[D,K]=-iK" in rows[0]["prediction"]
    assert r"[K,H]=2iD" in rows[0]["prediction"]


def test_memoryarena_diagnostic_predictor_derives_relative_operator_triple(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:relops",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Definition (Polar Coordinates). "
                            "Definition (Angular Operator): "
                            r"\begin{equation}\hat{L}^2_{S^{N-2}} = "
                            r"-\nabla^2_{S^{N-2}}+\sum_{a}"
                            r"\frac{\lambda(\lambda-1)}{(\cos\Theta^a)^2}."
                            r"\end{equation}"
                        ),
                        "prompt": (
                            r"How to write $H_{\rm rel}$, $K_{\rm rel}$, and "
                            r"$D_{\rm rel}$ using $r$, $\Theta^a$, and "
                            r"$\nabla^2_{S^{N-2}}$?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert r"H_{\rm rel}&=" in rows[0]["prediction"]
    assert r"K_{\rm rel}&=\frac{r^2}{2}" in rows[0]["prediction"]
    assert r"D_{\rm rel}&=" in rows[0]["prediction"]


def test_memoryarena_diagnostic_predictor_derives_complete_ring_related_condition(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Let $\\scA$, $\\scB$ be complete rings. "
                            "The map $\\bGamma: \\cX(\\Spec(\\scA)) \\to "
                            "\\CDer(\\scA)$ is an isomorphism. "
                            "For any map $\\varphi:\\scB\\to \\scA$, "
                            "derivations $w$ and $v$ are $\\varphi$-related "
                            "if and only if the vector fields are "
                            "$\\uu{f}:=\\Spec(\\varphi)$-related."
                        ),
                        "prompt": (
                            "Let $\\scA$, $\\scB$ be two complete $\\cin$-rings, "
                            "$\\uu{f}: \\Spec(\\scB)\\to \\Spec(\\scA)$ a map. "
                            "Give an if and only if condition on two vector fields "
                            "$v\\in \\cX(\\Spec(\\scA))$ and "
                            "$w\\in \\cX(\\Spec(\\scB))$ being $\\uu{f}$-related."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == (
        r"An equivalent condition is that $\bGamma(w)$ and $\bGamma(v)$ are "
        r"$\varphi$-related, where $\varphi=\Spec^{-1}(\uu{f})$."
    )


def test_memoryarena_diagnostic_predictor_derives_complexity_one_type_feasibility(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:types",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "A non-degenerate point has at most one non-elliptic "
                            "block. If p has a hyperbolic block and connected "
                            "T-stabilizer, then N = 1. An ephemeral point is tall "
                            "and has defining polynomial degree N > 1."
                        ),
                        "prompt": (
                            "Determine which of the following scenarios are possible. "
                            "(1) p has purely elliptic type. (2) p has a hyperbolic "
                            "block and connected T-stabilizer. (3) p is ephemeral. "
                            "(4) p has purely elliptic type and a hyperbolic block "
                            "and connected T-stabilizer. (5) p is ephemeral and has "
                            "a hyperbolic block and connected T-stabilizer."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == (
        "Only (1), (2) and (3) are possible. All others are impossible."
    )


def test_memoryarena_diagnostic_predictor_derives_reduced_taylor_polynomial(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:taylor",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "The degree $\\ell$ reduced Taylor polynomial is "
                            "$\\overline{T^{\\ell}_p g}(\\llbracket t,0,z "
                            "\\rrbracket) = T^{\\ell}_0(R^*g)(z)$."
                        ),
                        "prompt": (
                            "Given $\\overline{g}( \\llbracket t,0,z \\rrbracket) "
                            "= h(\\Re P(z),\\Im P(z),|z|^2)$, express the degree "
                            "$\\ell$ reduced Taylor polynomial of $g$."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert r"Ni + Nj + 2k \leq \ell" in rows[0]["prediction"]
    assert r"(\Re P(z))^i (\Im P(z))^j |z|^{2k}" in rows[0]["prediction"]


def test_memoryarena_diagnostic_predictor_classifies_reduced_surface_points(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:surface",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "For a hyperbolic block and connected stabilizer, "
                            "$(\\overline{g} \\circ \\Psi^{-1})(x,y)= x^2 - y^2. "
                            "For purely elliptic type, "
                            "$(\\overline{g} \\circ \\Psi^{-1})(x,y)= x^2 + y^2. "
                            "For an ephemeral point, "
                            "$(\\overline{g} \\circ \\Psi^{-1})(x,y)= y."
                        ),
                        "prompt": (
                            "Given p in the reduced space: (1) What is [p] exactly "
                            "if p has a hyperbolic block and connected T-stabilizer? "
                            "(2) What is [p] exactly if p has purely elliptic type? "
                            "(3) What is [p] exactly if p is ephemeral or is a "
                            "regular point of g modulo Phi?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "index $1$" in rows[0]["prediction"]
    assert "index $0$ or $2$" in rows[0]["prediction"]
    assert "regular point of $\\overline{g}$" in rows[0]["prediction"]


def test_memoryarena_default_predictor_does_not_use_select_all_shortcut(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:select-all",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "The map f is an isomorphism of what structures? "
                            "Select all that apply. A. apples. B. bananas. "
                            "C. cherries."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == (
        "I do not have enough non-answer context in this scenario to answer directly."
    )


def test_memoryarena_diagnostic_predictor_grounds_select_all_structure_answer(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:select-all",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Vector fields are maps of sheaves of real vector "
                            "spaces, derivations carry the commutator bracket, "
                            "and derivations over a ring form modules."
                        ),
                        "prompt": (
                            "The map $\\bGamma: \\cX(\\Spec(\\scA)) \\to "
                            "\\CDer(\\scA)$ is an isomorphism of what structures? "
                            "Select all that apply. A. modules. B. Lie algebras. "
                            "C. vector spaces."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == "The correct answer is A,B,C."


def test_memoryarena_diagnostic_predictor_can_use_select_all_shortcut(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_math",
                "scenario_id": "formal_reasoning_math:select-all",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "The map $\\bGamma: \\cX(\\Spec(\\scA)) \\to "
                            "\\CDer(\\scA)$ is an isomorphism of what structures? "
                            "Select all that apply. A. modules. B. Lie algebras. "
                            "C. vector spaces."
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == "The correct answer is A,B,C."


def test_memoryarena_default_predictor_retrieves_latex_equation_from_background(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:equation",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Definition (Relative Casimir):\n"
                            "\\begin{equation}\n"
                            "\\mathcal{C}_2^{\\rm rel}\\equiv "
                            "\\frac{1}{2}\\left(\\mathcal{H}_{\\rm rel}\\,"
                            "\\mathcal{K}_{\\rm rel}+\\mathcal{K}_{\\rm rel}\\,"
                            "\\mathcal{H}_{\\rm rel}\\right)"
                            "-\\mathcal{D}_{\\rm rel}^2.\n"
                            "\\end{equation}\n"
                            "Definition (Other):\n"
                            "\\begin{equation}\nA=B.\n\\end{equation}"
                        ),
                        "prompt": (
                            "How to write $\\mathcal{C}_2^{\\rm rel}$ in terms of "
                            "$\\mathcal{H}_{\\rm rel}$, $\\mathcal{K}_{\\rm rel}$, "
                            "and $\\mathcal{D}_{\\rm rel}$?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"].startswith("\\begin{equation}")
    assert "\\mathcal{C}_2^{\\rm rel}\\equiv" in rows[0]["prediction"]
    assert "A=B" not in rows[0]["prediction"]


def test_memoryarena_diagnostic_predictor_retains_early_background_for_later_equations(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    sessions = [
        {
            "turn_index": 0,
            "background": (
                "\\begin{equation}\n"
                "\\mathcal{C}_2^{\\rm rel}\\equiv "
                "\\frac{1}{2}\\left(\\mathcal{H}_{\\rm rel}\\,"
                "\\mathcal{K}_{\\rm rel}+\\mathcal{K}_{\\rm rel}\\,"
                "\\mathcal{H}_{\\rm rel}\\right)-\\mathcal{D}_{\\rm rel}^2.\n"
                "\\end{equation}"
            ),
            "prompt": "Remember this source packet.",
            "expected_answer": "hidden",
        }
    ]
    sessions.extend(
        {
            "turn_index": index,
            "background": "",
            "prompt": f"Filler turn {index}: keep working from the same source.",
            "expected_answer": "hidden",
        }
        for index in range(1, 7)
    )
    sessions.append(
        {
            "turn_index": 7,
            "background": "",
            "prompt": (
                "How to write $\\mathcal{C}_2^{\\rm rel}$ in terms of "
                "$\\mathcal{H}_{\\rm rel}$, $\\mathcal{K}_{\\rm rel}$, "
                "and $\\mathcal{D}_{\\rm rel}$?"
            ),
            "expected_answer": "hidden",
        }
    )
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:long-context",
                "sessions": sessions,
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "\\mathcal{C}_2^{\\rm rel}\\equiv" in rows[-1]["prediction"]


def test_memoryarena_diagnostic_predictor_derives_relative_casimir_definition(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:casimir",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Definition (Quadratic Casimir Operator): "
                            "$C_2$ is defined by "
                            "$C_2\\equiv \\frac{1}{2}(H K+K H)-D^2$. "
                            "The relative operators are "
                            "$\\mathcal{H}_{\\rm rel}$, "
                            "$\\mathcal{K}_{\\rm rel}$, and "
                            "$\\mathcal{D}_{\\rm rel}$."
                        ),
                        "prompt": (
                            "How to write $\\mathcal{C}_2^{\\rm rel}$ in terms of "
                            "$\\mathcal{H}_{\\rm rel}$, $\\mathcal{K}_{\\rm rel}$, "
                            "and $\\mathcal{D}_{\\rm rel}$?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert r"\mathcal{C}_2^{\rm rel}\equiv" in rows[0]["prediction"]
    assert r"\mathcal{D}_{\rm rel}^2" in rows[0]["prediction"]


def test_memoryarena_diagnostic_predictor_derives_relative_hamiltonian_with_lhat(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "formal_reasoning_phys",
                "scenario_id": "formal_reasoning_phys:hamiltonian",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Definition (Center-of-Mass and Relative Operators): "
                            "In polar coordinates, $H_{\\rm rel}$ separates into "
                            "a radial part and angular part. Definition (Angular "
                            "Operator): $\\hat{L}^2_{S^{N-2}}$ denotes the angular "
                            "operator on $S^{N-2}$."
                        ),
                        "prompt": (
                            "How to write $H_{\\rm rel}$ in terms of $r$ and "
                            "$\\hat{L}^2_{S^{N-2}}$?"
                        ),
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert r"H_{\rm rel}" in rows[0]["prediction"]
    assert r"\hat{L}^2_{S^{N-2}}" in rows[0]["prediction"]
    assert r"r^{2-N}" in rows[0]["prediction"]


def test_memoryarena_default_predictor_ignores_explicit_exact_answer_marker(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": "Question: which account? Exact Answer: account-42",
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == (
        "I do not have enough non-answer context in this scenario to answer directly."
    )


def test_memoryarena_default_predictor_uses_exact_answer_marker_from_source_background(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "progressive_search",
                "scenario_id": "progressive_search:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "background": (
                            "Audited source note. The deployment account is "
                            "service-prod-42. Exact Answer: service-prod-42"
                        ),
                        "prompt": "Which deployment account does the source identify?",
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == "service-prod-42"


def test_memoryarena_default_predictor_uses_prior_selected_option_for_compatibility(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "bundled_shopping",
                "scenario_id": "bundled_shopping:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "Product 1\n### Select Base\n"
                            "**Available Options:**\n"
                            "- A vanilla cake mix.\n"
                            "- A chocolate cake mix."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    },
                    {
                        "turn_index": 1,
                        "prompt": (
                            "Product 2\n### Select Frosting\n"
                            "**Goal:** Compatibility notes: Vanilla pairs well "
                            "with White. Chocolate pairs well with Fudge.\n"
                            "**Constraint:** Must be compatible with previous products.\n"
                            "**Available Options:**\n"
                            "- A chocolate fudge frosting.\n"
                            "- A white buttercream frosting."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    },
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["evidence"]["selected_option"] == "A vanilla cake mix."
    assert rows[1]["evidence"]["selected_option"] == "A white buttercream frosting."
    assert "selected_option" not in rows[1]["prediction"]


def test_memoryarena_default_predictor_penalizes_prior_avoid_terms(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "bundled_shopping",
                "scenario_id": "bundled_shopping:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "Product 1\n### Select Frosting\n"
                            "**Available Options:**\n"
                            "- A white frosting.\n"
                            "- A red frosting."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    },
                    {
                        "turn_index": 1,
                        "prompt": (
                            "Product 2\n### Select Coloring\n"
                            "**Goal:** Compatibility notes: White pairs well "
                            "with Blue. White avoids Gel.\n"
                            "**Constraint:** Must be compatible with previous products.\n"
                            "**Available Options:**\n"
                            "- A blue airbrush food color.\n"
                            "- A blue gel food color."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    },
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[1]["evidence"]["selected_option"] == "A blue airbrush food color."


def test_memoryarena_default_predictor_treats_multi_color_options_as_color_compatible(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "bundled_shopping",
                "scenario_id": "bundled_shopping:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "Product 1\n### Select Frosting\n"
                            "**Available Options:**\n"
                            "- A white frosting."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    },
                    {
                        "turn_index": 1,
                        "prompt": (
                            "Product 2\n### Select Coloring\n"
                            "**Goal:** Compatibility notes: White pairs well "
                            "with one of: Red, Blue, Green, Yellow, Pink. "
                            "White avoids Gel.\n"
                            "**Available Options:**\n"
                            "- A blue gel food color.\n"
                            "- A powder food coloring kit with 8 colors."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    },
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[1]["evidence"]["selected_option"] == "A powder food coloring kit with 8 colors."


def test_memoryarena_default_predictor_uses_first_color_lane_for_multicolor_carry(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "bundled_shopping",
                "scenario_id": "bundled_shopping:1",
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": (
                            "Product 1\n### Select Coloring\n"
                            "**Available Options:**\n"
                            "- A powder food coloring kit with 8 colors."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    },
                    {
                        "turn_index": 1,
                        "prompt": (
                            "Product 2\n### Select Sprinkles\n"
                            "**Goal:** Compatibility notes: Red pairs well with Gold. "
                            "Blue pairs well with Silver. Yellow pairs well with Rainbow.\n"
                            "**Constraint:** Must be compatible with previous products.\n"
                            "**Available Options:**\n"
                            "- A rainbow sprinkle jar.\n"
                            "- A gold metallic dragees sprinkle mix."
                        ),
                        "expected_answer": {"target_asin": "hidden"},
                    },
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[1]["evidence"]["selected_option"] == "A gold metallic dragees sprinkle mix."


def test_memoryarena_predict_reuses_structured_seed_context_for_trip_plan(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    base_plan = [
        {
            "days": 1,
            "current_city": "from A to B",
            "transportation": "Flight 123",
            "accommodation": "Base hotel",
            "breakfast": "-",
            "lunch": "-",
            "dinner": "Base dinner",
            "attraction": "-",
        }
    ]
    _write_jsonl(
        scenarios,
        [
            {
                "config": "group_travel_planner",
                "scenario_id": "group_travel_planner:1",
                "seed_context": {"name": "Jennifer", "daily_plans": base_plan},
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": "I am Eric. I'm joining Jennifer for this trip.",
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == base_plan
    assert rows[0]["method"] == "mapu_benchmark_agnostic_memoryarena_v1"
    assert rows[0]["evidence"]["selected_option"] is None


def test_memoryarena_predict_does_not_emit_seed_plan_without_prompt_cue(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "memoryarena_scenarios.jsonl"
    predictions = tmp_path / "memoryarena_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "config": "unseen_general_context",
                "scenario_id": "unseen_general_context:1",
                "seed_context": {
                    "daily_plans": [
                        {
                            "days": 1,
                            "current_city": "from A to B",
                            "transportation": "Flight 123",
                        }
                    ]
                },
                "sessions": [
                    {
                        "turn_index": 0,
                        "prompt": "What is the person's favorite color?",
                        "expected_answer": "hidden",
                    }
                ],
            }
        ],
    )

    rc = memoryarena.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] != [
        {"days": 1, "current_city": "from A to B", "transportation": "Flight 123"}
    ]
    assert rows[0]["method"] == "mapu_benchmark_agnostic_memoryarena_v1"


def test_ama_score_fails_when_no_predictions_match_keys(tmp_path: Path) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    out = tmp_path / "ama_score.json"

    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "expected_answer": "alpha",
                        "question_type": "retrieval",
                    }
                ],
            }
        ],
    )
    _write_jsonl(
        predictions,
        [{"scenario_id": "unknown", "question_index": 0, "prediction": "alpha"}],
    )

    rc = ama_bench.score(str(scenarios), str(predictions), str(out))

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1
    assert report["status"] == "fail"
    assert report["evaluated"] == 0
    assert report["failure_reason"] == "No predictions matched exported scenario keys."


def test_ama_score_accepts_powershell_utf8_bom_jsonl(tmp_path: Path) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    out = tmp_path / "ama_score.json"

    scenarios.write_text(
        json.dumps(
            {
                "scenario_id": "episode-1",
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "expected_answer": "alpha",
                        "question_type": "retrieval",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8-sig",
    )
    predictions.write_text(
        json.dumps(
            {
                "scenario_id": "episode-1",
                "question_index": 0,
                "prediction": "alpha",
            }
        )
        + "\n",
        encoding="utf-8-sig",
    )

    rc = ama_bench.score(str(scenarios), str(predictions), str(out))

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["status"] == "ok"
    assert report["exact_match"] == 1.0
    assert report["token_f1"] == 1.0


def test_ama_score_passes_when_threshold_met(tmp_path: Path) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    out = tmp_path / "ama_score.json"

    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "expected_answer": "alpha",
                        "question_type": "retrieval",
                    }
                ],
            }
        ],
    )
    _write_jsonl(
        predictions,
        [{"scenario_id": "episode-1", "question_index": 0, "prediction": " alpha "}],
    )

    rc = ama_bench.score(
        str(scenarios),
        str(predictions),
        str(out),
        min_exact_match=1.0,
    )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["status"] == "ok"
    assert report["by_type"]["retrieval"]["exact_match"] == 1.0
    assert report["by_type"]["retrieval"]["token_f1"] == 1.0
    assert report["item_scores"] == [
        {
            "scenario_id": "episode-1",
            "question_index": 0,
            "question_type": "retrieval",
            "method": "unknown",
            "exact_match": True,
            "token_f1": 1.0,
            "prediction_preview": "alpha",
            "expected_preview": "alpha",
        }
    ]
    assert report["worst_items"][0]["question_index"] == 0


def test_ama_predict_retrieves_from_trajectory_without_answers(tmp_path: Path) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {
                        "turn_idx": 10,
                        "action": "read",
                        "observation": "The deployment used port 8080.",
                    },
                    {"turn_idx": 11, "action": "check", "observation": "The health check passed."},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": "Which port did the deployment use?",
                        "expected_answer": "8080",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"].startswith("Relevant trajectory context:")
    assert "port 8080" in rows[0]["prediction"]
    assert rows[0]["evidence"][0]["turn_index"] == 10
    assert rows[0]["method"] == "mapu_local_trajectory_retrieval_v1"
    assert "expected_answer" not in rows[0]


def test_ama_predict_reasons_about_inverse_action_loop(tmp_path: Path) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 7, "action": "down", "observation": "state b"},
                    {"turn_idx": 8, "action": "up", "observation": "state a"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "The observation after the `up` action at Step 8 is "
                            "identical to the observation from Step 6. What is the "
                            "causal relationship between the action at Step 7 "
                            "(`down`) and the action at Step 8 (`up`)?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(
        str(scenarios),
        str(predictions),
        predictor="diagnostic_templates",
    )

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "direct inverse" in rows[0]["prediction"]
    assert "zero net progress" in rows[0]["prediction"]
    assert rows[0]["method"] == "mapu_baba_trajectory_reasoner_v1"


def test_ama_default_predictor_explains_inverse_action_without_diagnostic_template(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 7, "action": "down", "observation": "state b"},
                    {"turn_idx": 8, "action": "up", "observation": "state a"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "The observation after the `up` action at Step 8 is "
                            "identical to the observation from Step 6. What is the "
                            "causal relationship between the action at Step 7 "
                            "(`down`) and the action at Step 8 (`up`)?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "direct inverse" in rows[0]["prediction"]
    assert "zero net progress" in rows[0]["prediction"]
    assert {item["turn_index"] for item in rows[0]["evidence"]} == {7, 8}


def test_ama_default_predictor_does_not_answer_pattern_without_trajectory(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "The observation after the `up` action at Step 8 is "
                            "identical to the observation from Step 6. What is the "
                            "causal relationship between the action at Step 7 "
                            "(`down`) and the action at Step 8 (`up`)?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_local_trajectory_retrieval_v1"
    assert rows[0]["prediction"] == ""
    assert rows[0]["evidence"] == []


def test_ama_default_predictor_summarizes_opposing_move_sequences(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 20, "action": "left", "observation": "state a"},
                    {"turn_idx": 21, "action": "right", "observation": "state b"},
                    {"turn_idx": 22, "action": "down", "observation": "state c"},
                    {"turn_idx": 23, "action": "up", "observation": "state a"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "Question: Why was the sequence of actions from step "
                            "20 to 23 (left, right, down, up) completely "
                            "ineffective for making progress?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "opposing pairs" in rows[0]["prediction"]
    assert "zero net progress" in rows[0]["prediction"]
    assert not rows[0]["prediction"].startswith("Relevant trajectory context:")


def test_ama_default_predictor_explains_net_effect_reversal(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 12, "action": "right", "observation": "state b"},
                    {"turn_idx": 13, "action": "left", "observation": "state a"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "At step 12, the agent moved `right`. What specific "
                            "action did it take at step 13, and what was the net "
                            "effect of this two-step sequence on the agent's "
                            "position?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "`left` action at step 13" in rows[0]["prediction"]
    assert "direct inverse" in rows[0]["prediction"]
    assert "zero net progress" in rows[0]["prediction"]


def test_ama_default_predictor_explains_cyclical_observation_similarity(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 30, "action": "left", "observation": "state a"},
                    {"turn_idx": 31, "action": "right", "observation": "state b"},
                    {"turn_idx": 32, "action": "left", "observation": "state a"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "The agent takes the action 'left' at step 30 and "
                            "'right' at step 31. By comparing the game state "
                            "described in the observation for step 30 with the "
                            "one for step 32, what is the crucial similarity "
                            "between them, and what does this cyclical pattern "
                            "imply about progress?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "step 30 and step 32" in rows[0]["prediction"]
    assert "form a cycle" in rows[0]["prediction"]
    assert "win condition" in rows[0]["prediction"]


def test_ama_default_predictor_matches_self_reversing_subsequence(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 19, "action": "right", "observation": "state b"},
                    {"turn_idx": 20, "action": "left", "observation": "state a"},
                    {"turn_idx": 21, "action": "right", "observation": "state c"},
                    {"turn_idx": 22, "action": "down", "observation": "state d"},
                    {"turn_idx": 23, "action": "up", "observation": "state c"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "Between step 19 and step 23, the agent performs a "
                            "sequence of four movements: `right`, `left`, "
                            "`down`, and `up`. Which of these actions were "
                            "relevant for making progress towards the goal of "
                            "touching a `win` object, and why?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "None of the listed actions" in rows[0]["prediction"]
    assert "`right` at step 19 is canceled by `left` at step 20" in rows[0]["prediction"]
    assert "`down` at step 22 is canceled by `up` at step 23" in rows[0]["prediction"]


def test_ama_default_predictor_explains_key_push_alternative(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {
                        "turn_idx": 44,
                        "action": "left",
                        "observation": (
                            "rule `is` 1 step to the left and key 1 step down "
                            "near rule `wall`"
                        ),
                    }
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "In the transition from step 44 to 45, the agent "
                            "chose the action `left`, moving away from the "
                            "`key`. Based on the object layout in step 44, what "
                            "would have happened if the agent had moved `down` "
                            "instead, and why would this alternative action have "
                            "been more strategic for forming the rule `wall is stop`?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "moved into the key's current tile" in rows[0]["prediction"]
    assert "pushed the `key` farther `down`" in rows[0]["prediction"]
    assert "rule-forming alignment" in rows[0]["prediction"]
    assert "`WALL IS STOP`" in rows[0]["prediction"]


def test_ama_default_predictor_explains_hidden_push_mechanic(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {
                        "turn_idx": 9,
                        "action": "down",
                        "observation": "rule `is` 1 step left and key 1 step up",
                    },
                    {
                        "turn_idx": 10,
                        "action": "right",
                        "observation": "rule `is` shifted with key",
                    },
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "A standard push would only change the block's "
                            "vertical position, but the pushed objects shift "
                            "horizontally and vertically. What hidden movement "
                            "mechanic affecting pushed objects can be inferred?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "coupled group" in rows[0]["prediction"]
    assert "one tile in the push direction and one tile left" in rows[0]["prediction"]


def test_ama_default_predictor_uses_explicit_disappearance_step_for_vanished_object(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 39, "action": "up", "observation": "ball 1 step right"},
                    {"turn_idx": 40, "action": "up", "observation": "ball 1 step right"},
                    {"turn_idx": 41, "action": "right", "observation": "ball 1 step right"},
                    {"turn_idx": 42, "action": "right", "observation": "no visible ball"},
                    {"turn_idx": 43, "action": "down", "observation": "ball 1 step up"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "At step 41, the `ball` was '1 step to the right'. "
                            "After the agent moved `right` in step 42, the `ball` "
                            "vanished from the observation. Then, after moving "
                            "`down` in step 43, the `ball` reappeared. What was "
                            "the exact position at the end of step 42?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "At the end of step 42" in rows[0]["prediction"]
    assert "same tile as the `ball`" in rows[0]["prediction"]


def test_ama_default_predictor_extracts_temporary_transformation_object(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 12, "action": "right", "observation": "key appears"},
                    {"turn_idx": 13, "action": "left", "observation": "key disappears"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "The agent's `right` action at step 12 causes a "
                            "`key` to appear. The subsequent `left` action at "
                            "step 13 causes the `key` to disappear. What hidden "
                            "state change most likely occurred?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "become a `key`" in rows[0]["prediction"]
    assert "the agent's" not in rows[0]["prediction"]


def test_ama_default_predictor_prioritizes_rule_text_for_absent_push(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {
                        "turn_idx": 20,
                        "action": "right",
                        "observation": "rule `is` 2 steps left and key 1 step down",
                    },
                    {"turn_idx": 21, "action": "left", "observation": "state a"},
                    {"turn_idx": 22, "action": "down", "observation": "state b"},
                    {"turn_idx": 23, "action": "up", "observation": "state a"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "Between steps 20 and 23, the agent executes "
                            "opposing moves that result in no net change. What "
                            "progress-enabling action is conspicuously absent "
                            "from this sequence, and which nearby object is the "
                            "most logical target?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "absent action is `PUSH`" in rows[0]["prediction"]
    assert "the `is` text block" in rows[0]["prediction"]


def test_ama_default_predictor_computes_hypothetical_relative_position(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {
                        "turn_idx": 47,
                        "action": "left",
                        "observation": "door 3 steps to the left",
                    }
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "If at step 47, the agent had moved `right` instead "
                            "of `left`, what would the new relative position of "
                            "the `DOOR` text block, which was at `(-3, 0)` "
                            "relative to the agent, be?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "`(-4, 0)`" in rows[0]["prediction"]
    assert "absolute x-coordinate" in rows[0]["prediction"]
    assert "counterproductive" in rows[0]["prediction"]


def test_ama_default_predictor_reads_prior_observation_for_hypothetical_move(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {
                        "turn_idx": 46,
                        "action": "idle",
                        "observation": "rule `door` 3 step to the left",
                    },
                    {
                        "turn_idx": 47,
                        "action": "left",
                        "observation": "rule `door` 2 step to the left",
                    },
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "If at step 47, the agent had moved `right` instead "
                            "of `left`, what would the new relative position of "
                            "the `DOOR` text block be?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "`(-4, 0)`" in rows[0]["prediction"]


def test_ama_default_predictor_expands_step_ranges(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 20, "action": "right", "observation": "state a"},
                    {"turn_idx": 21, "action": "left", "observation": "state b"},
                    {"turn_idx": 22, "action": "right", "observation": "state a"},
                    {"turn_idx": 23, "action": "down", "observation": "state c"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "Between steps 20 and 23, which single action in "
                            "this sequence is the most critical for making progress?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["method"] == "mapu_trajectory_event_summarizer_v1"
    assert "`down` at step 23" in rows[0]["prediction"]
    assert "vertical alignment" in rows[0]["prediction"]


def test_ama_default_predictor_trusts_question_stated_action_sequence(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 20, "action": "right", "observation": "state a"},
                    {"turn_idx": 21, "action": "left", "observation": "state b"},
                    {"turn_idx": 22, "action": "right", "observation": "state a"},
                    {"turn_idx": 23, "action": "left", "observation": "state b"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "Between steps 20 and 23, the agent's actions are "
                            "`right`, `left`, `right`, and `down`. Which single "
                            "action in this sequence is the most critical for "
                            "making progress?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "`down` at step 23" in rows[0]["prediction"]


def test_ama_default_predictor_parses_actions_to_steps(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 7, "action": "down", "observation": "state b"},
                    {"turn_idx": 8, "action": "up", "observation": "state a"},
                    {"turn_idx": 9, "action": "down", "observation": "state b"},
                    {"turn_idx": 10, "action": "up", "observation": "state a"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "The observations at step 8 and step 10 are identical "
                            "to the one at step 6. Considering the agent's actions "
                            "between these steps were `down` (to step 7), `up` "
                            "(to step 8), `down` (to step 9), and `up` (to step "
                            "10), what does this repetitive sequence infer about "
                            "the agent's exploration strategy and its overall "
                            "progress?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "step 7: `down`" in rows[0]["prediction"]
    assert "two-step oscillation" in rows[0]["prediction"]
    assert "zero net progress" in rows[0]["prediction"]


def test_ama_default_predictor_does_not_depend_on_direct_question_prefix(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 20, "action": "right", "observation": "state a"},
                    {"turn_idx": 21, "action": "left", "observation": "state b"},
                    {"turn_idx": 22, "action": "right", "observation": "state a"},
                    {"turn_idx": 23, "action": "left", "observation": "state b"},
                    {"turn_idx": 24, "action": "down", "observation": "state c"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "Question: What was the strategic importance of the "
                            "`down` action at step 24 compared to the four "
                            "preceding right/left actions (steps 20-23)?"
                        ),
                        "expected_answer": "unused",
                    },
                    {
                        "question_index": 1,
                        "question": (
                            "What was the strategic importance of the `down` "
                            "action at step 24 compared to the four preceding "
                            "right/left actions (steps 20-23)?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == rows[1]["prediction"]
    assert rows[0]["prediction"] == (
        "It broke an oscillatory loop and made the first tangible progress "
        "toward the rule blocks."
    )


def test_ama_default_predictor_does_not_shape_appearing_object_by_question_prefix(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {"turn_idx": 22, "action": "right", "observation": "state a"},
                    {"turn_idx": 23, "action": "left", "observation": "state b"},
                    {"turn_idx": 24, "action": "down", "observation": "ball appears"},
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "Question: In step 24, a `ball` object appears that "
                            "did not exist in step 22. What action in step 23 "
                            "directly caused this `ball` to exist, and what was "
                            "the result?"
                        ),
                        "expected_answer": "unused",
                    },
                    {
                        "question_index": 1,
                        "question": (
                            "In step 24, a `ball` object appears that did not "
                            "exist in step 22. What action in step 23 directly "
                            "caused this `ball` to exist, and what was the result?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert rows[0]["prediction"] == rows[1]["prediction"]
    assert rows[0]["prediction"] == (
        "The `left` action caused a `ball` to appear on the tile the agent "
        "had just vacated."
    )


def test_ama_default_predictor_names_left_as_non_reversing_alternative(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "ama_scenarios.jsonl"
    predictions = tmp_path / "ama_predictions.jsonl"
    _write_jsonl(
        scenarios,
        [
            {
                "scenario_id": "episode-1",
                "trajectory": [
                    {
                        "turn_idx": 7,
                        "action": "down",
                        "observation": "rule `is` 2 step to the left and 1 step up",
                    },
                    {
                        "turn_idx": 8,
                        "action": "up",
                        "observation": "rule `win` 1 step to the left",
                    },
                ],
                "qa_pairs": [
                    {
                        "question_index": 0,
                        "question": (
                            "At the start of Step 8, instead of moving `up` and "
                            "reversing its previous action, what alternative move "
                            "would have represented a clear step towards creating "
                            "a new win condition?"
                        ),
                        "expected_answer": "unused",
                    }
                ],
            }
        ],
    )

    rc = ama_bench.predict(str(scenarios), str(predictions))

    rows = [
        json.loads(line)
        for line in predictions.read_text(encoding="utf-8").splitlines()
    ]
    assert rc == 0
    assert "moving `left`" in rows[0]["prediction"]
    assert "is` and `win" in rows[0]["prediction"]
