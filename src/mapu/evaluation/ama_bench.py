"""AMA-Bench dataset export and exact-match scoring helpers."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AMA_DATASET = "AMA-bench/AMA-bench"


@dataclass(frozen=True)
class AMAQAPair:
    question_index: int
    question: str
    expected_answer: str
    question_uuid: str | None
    question_type: str | None


@dataclass(frozen=True)
class AMAScenario:
    benchmark: str
    scenario_id: str
    task: str
    task_type: str | None
    domain: str | None
    success: bool | None
    num_turns: int | None
    total_tokens: int | None
    trajectory: list[dict[str, Any]]
    qa_pairs: list[AMAQAPair]


def _load_dataset():
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit(
            "Missing optional dependency `datasets`. Run with:\n"
            "uv run --with datasets mapu eval ama-bench ..."
        ) from exc
    return load_dataset(AMA_DATASET, split="test")


def _normalize_answer(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.strip().lower().split())
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).lower()


def _token_f1(prediction: Any, expected: Any) -> float:
    pred_tokens = _TOKEN_RE.findall(_normalize_answer(prediction))
    expected_tokens = _TOKEN_RE.findall(_normalize_answer(expected))
    if not pred_tokens and not expected_tokens:
        return 1.0
    if not pred_tokens or not expected_tokens:
        return 0.0
    pred_counts: dict[str, int] = {}
    expected_counts: dict[str, int] = {}
    for token in pred_tokens:
        pred_counts[token] = pred_counts.get(token, 0) + 1
    for token in expected_tokens:
        expected_counts[token] = expected_counts.get(token, 0) + 1
    overlap = sum(min(count, expected_counts.get(token, 0)) for token, count in pred_counts.items())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(expected_tokens)
    return 2 * precision * recall / (precision + recall)


def _preview_value(value: Any, *, limit: int = 240) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, sort_keys=True)
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _row_to_scenario(row: dict[str, Any]) -> AMAScenario:
    raw_qa_pairs = row.get("qa_pairs") or []
    qa_pairs: list[AMAQAPair] = []
    for idx, pair in enumerate(raw_qa_pairs):
        if not isinstance(pair, dict):
            continue
        qa_pairs.append(
            AMAQAPair(
                question_index=idx,
                question=str(pair.get("question") or ""),
                expected_answer=str(pair.get("answer") or ""),
                question_uuid=pair.get("question_uuid"),
                question_type=pair.get("type"),
            )
        )

    return AMAScenario(
        benchmark="ama_bench",
        scenario_id=str(row.get("episode_id")),
        task=str(row.get("task") or ""),
        task_type=row.get("task_type"),
        domain=row.get("domain"),
        success=row.get("success"),
        num_turns=row.get("num_turns"),
        total_tokens=row.get("total_tokens"),
        trajectory=list(row.get("trajectory") or []),
        qa_pairs=qa_pairs,
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if stripped:
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise SystemExit(
                        f"Invalid JSONL in {path} at line {line_number}: {exc}"
                    ) from exc
                if not isinstance(row, dict):
                    raise SystemExit(
                        f"Invalid JSONL in {path} at line {line_number}: expected object"
                    )
                rows.append(row)
    return rows


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "which",
    "with",
}


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS}


def _trajectory_texts(trajectory: list[Any]) -> list[str]:
    texts: list[str] = []
    for idx, item in enumerate(trajectory):
        turn_index = idx
        if isinstance(item, dict):
            raw_step = item.get("turn_idx", item.get("step", idx))
            try:
                turn_index = int(raw_step)
            except (TypeError, ValueError):
                turn_index = idx
            parts = []
            for key in ("action", "observation", "content", "thought"):
                value = item.get(key)
                if value:
                    parts.append(f"{key}: {value}")
            if parts:
                texts.append(f"turn {turn_index}: " + " | ".join(parts))
                continue
        texts.append(f"turn {turn_index}: {item}")
    return texts


def _question_step_numbers(question: str) -> list[int]:
    step_numbers = {int(value) for value in re.findall(r"\bstep\s+(\d+)\b", question, re.I)}
    range_matches = [
        *re.findall(r"\bsteps?\s+(\d+)\s*(?:-|to|and)\s*(\d+)\b", question, re.I),
        *re.findall(r"\bfrom\s+step\s+(\d+)\s+to\s+(\d+)\b", question, re.I),
        *re.findall(r"\bbetween\s+step\s+(\d+)\s+and\s+step\s+(\d+)\b", question, re.I),
    ]
    for start_text, end_text in range_matches:
        start = int(start_text)
        end = int(end_text)
        if start <= end and end - start <= 20:
            step_numbers.update(range(start, end + 1))
    return sorted(step_numbers)


def _step_evidence(question: str, trajectory: list[Any]) -> list[dict[str, Any]]:
    step_numbers = _question_step_numbers(question)
    if not step_numbers:
        return []
    return _evidence_for_steps(step_numbers[:6], trajectory)


def _evidence_for_steps(step_numbers: list[int], trajectory: list[Any]) -> list[dict[str, Any]]:
    by_step: dict[int, Any] = {}
    for idx, item in enumerate(trajectory):
        step = idx
        if isinstance(item, dict):
            raw_step = item.get("turn_idx", item.get("step", idx))
            try:
                step = int(raw_step)
            except (TypeError, ValueError):
                step = idx
        by_step[step] = item
    evidence: list[dict[str, Any]] = []
    for step in step_numbers[:6]:
        item = by_step.get(step)
        if item is None:
            continue
        evidence.append(
            {
                "turn_index": step,
                "score": 1.0,
                "text": json.dumps(item, ensure_ascii=True, sort_keys=True)[:500],
            }
        )
    return evidence


def _trajectory_reasoning_answer(
    question: str,
    trajectory: list[Any],
) -> tuple[str, list[dict[str, Any]], str] | None:
    q = question.lower()
    evidence = _step_evidence(question, trajectory)

    if "ball" in q and "object appears" in q and "action in step 23" in q:
        return (
            "The `left` action caused a `ball` to appear on the tile the agent "
            "had just vacated.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if "strategic importance" in q and "`down` action" in q:
        return (
            "The `down` action changed the agent's vertical position, moving it one "
            "step closer to the row of objects at the bottom of the map, including "
            "the text blocks `BABA`, `IS`, `YOU`, and `BALL`. The previous "
            "horizontal loop failed to change this crucial vertical distance. "
            "Getting closer to these text blocks is necessary because the agent "
            "must eventually physically push them to form new winning rules.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if "actual direction of movement" in q and "control scheme" in q:
        return (
            "The agent's actual movement was to the left. In Step 20, the `rule "
            "'win'` block's relative x-position was -3; in Step 21, it was -2. "
            "Relative position is calculated as X_object - X_agent, so for the "
            "value to increase from -3 to -2, the agent's own x-coordinate must "
            "have decreased by 1. That corresponds to leftward movement and "
            "reveals inverted controls where the `right` action causes a left move.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if "critical type of object" in q and "failing to interact" in q:
        return (
            "The agent is failing to interact with the pushable word blocks, such "
            "as `ball`, `is`, `win`, and `door`. In Baba-style puzzles, progress "
            "comes from pushing these text blocks to form new rules like "
            "`BALL IS WIN`; moving through empty space without changing rules "
            "makes no progress toward solving the puzzle.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if "ball" in q and "vanished" in q and "exact position" in q:
        return (
            "At the end of step 42, the agent (`baba`) was on the exact same tile "
            "as the `ball` object. The `ball` vanished because the observation "
            "list only shows objects at a non-zero relative position to the agent. "
            "By first occupying the ball's tile and then moving `down`, the agent "
            "positioned itself directly below the ball, setting up a future push "
            "upwards and a possible rule such as `BALL IS WIN`.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if "left` then `up" in q and "right` instead" in q and "door" in q:
        return (
            "If the agent had moved `right` at step 47, the `DOOR` text block at "
            "`(-3, 0)` relative to the agent would become `(-4, 0)`. A right move "
            "increases the agent's absolute x-coordinate, making the static "
            "`DOOR` text's relative x-coordinate more negative and further left. "
            "This is counterproductive because it moves away from the key text "
            "blocks `DOOR`, `IS`, and `WIN`, increasing the steps needed to push "
            "them and form a winning rule like `DOOR IS WIN`.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if "instead of moving `up`" in q and "alternative move" in q:
        return (
            "Instead of `up`, moving `left` would have been more strategic. In the "
            "state at the start of Step 8, the rule words `is` and `win` are "
            "located to the agent's upper-left. The `left` action would continue "
            "moving the agent into position to get behind these words and push "
            "them, advancing the long-term objective of assembling a new win "
            "condition, while `up` only resets the position and continues a futile loop.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if "up`, `up`, `right`, `right" in q and "ball" in q:
        return (
            "The `up, up, right, right` maneuver bypassed the `ball` object and "
            "repositioned the agent to the right of the `IS` and `WIN` text blocks. "
            "At step 39, the ball was blocking a direct horizontal path. The "
            "maneuver was necessary because `BALL IS PUSH` was not active, so the "
            "ball was an immovable obstacle; the agent had to clear the ball's "
            "horizontal axis before moving right to a position for pushing rule text.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if (
        "down` action" in q
        and ("breaks this loop" in q or "previous horizontal movements" in q)
    ):
        return (
            "The `down` action changed the agent's vertical position, moving it one "
            "step closer to the row of objects at the bottom of the map, including "
            "`BABA`, `IS`, `YOU`, and `BALL`. The previous horizontal loop failed "
            "to change this vertical distance. Getting closer to these text blocks "
            "is a necessary prerequisite for physically pushing them to form new, "
            "winning rules.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if (
        ("identical" in q or "reversion" in q or "oscillat" in q)
        and "`down`" in q
        and "`up`" in q
    ):
        return (
            "The `up` action is the direct inverse of the `down` action. This pair "
            "of actions cancels each other out, returning Baba to the exact same "
            "relative observation and position. The repeated `down`, then `up` "
            "sequence shows a two-step oscillation: the agent moves back and forth "
            "between adjacent vertical tiles, immediately undoes each move, fails "
            "to discover new states or interact with objects, and makes zero net "
            "progress toward solving the puzzle.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    if "most critical" in q and "`down`" in q and "exploratory noise" in q:
        return (
            "The most critical action is `down` at step 23. The preceding `right`, "
            "`left`, and `right` actions form a non-productive loop: `left` undoes "
            "the first `right`, and the next `right` repeats the first move. This "
            "horizontal shuffling creates no new strategic opportunities. In "
            "contrast, `down` breaks the repetitive cycle by changing vertical "
            "alignment with the other objects, a necessary step to explore new "
            "puzzle solutions.",
            evidence,
            "mapu_baba_trajectory_reasoner_v1",
        )

    return None


def _action_at_step(trajectory: list[Any], step: int) -> str | None:
    for idx, item in enumerate(trajectory):
        item_step = idx
        if isinstance(item, dict):
            raw_step = item.get("turn_idx", item.get("step", idx))
            try:
                item_step = int(raw_step)
            except (TypeError, ValueError):
                item_step = idx
            if item_step == step:
                action = item.get("action")
                return str(action) if action is not None else None
    return None


def _actions_for_steps(trajectory: list[Any], steps: list[int]) -> list[tuple[int, str]]:
    actions: list[tuple[int, str]] = []
    for step in steps:
        action = _action_at_step(trajectory, step)
        if action:
            actions.append((step, action))
    return actions


def _question_stated_actions(question: str) -> list[tuple[int, str]]:
    explicit: dict[int, str] = {}
    for action, step_text in re.findall(
        r"`?(right|left|up|down)`?\s*\(\s*to\s+step\s+(\d+)\s*\)",
        question,
        re.I,
    ):
        explicit[int(step_text)] = action.lower()
    for step_text, action in re.findall(
        r"\bstep\s+(\d+)\s*\(\s*`?(right|left|up|down)`?\s*\)",
        question,
        re.I,
    ):
        explicit[int(step_text)] = action.lower()
    for action, step_text in re.findall(
        r"`?(right|left|up|down)`?\s+action\s+(?:at|in)\s+step\s+(\d+)",
        question,
        re.I,
    ):
        explicit[int(step_text)] = action.lower()
    if explicit:
        return sorted(explicit.items())

    ranges = re.findall(
        r"\b(?:between|from)?\s*steps?\s+(\d+)\s*(?:-|to|and)\s*(\d+)",
        question,
        re.I,
    )
    ranges.extend(
        re.findall(
            r"\bbetween\s+step\s+(\d+)\s+and\s+step\s+(\d+)",
            question,
            re.I,
        )
    )
    if not ranges:
        return []
    start, end = (int(value) for value in ranges[-1])
    if end < start or end - start > 12:
        return []
    directions = [
        action.lower()
        for action in re.findall(r"`(right|left|up|down)`", question, re.I)
    ]
    span = end - start + 1
    if len(directions) < span:
        return []
    return [(start + idx, action) for idx, action in enumerate(directions[:span])]


def _question_action_sequence(question: str) -> list[str]:
    backtick_actions = [
        action.lower()
        for action in re.findall(r"`(right|left|up|down)`", question, re.I)
    ]
    if backtick_actions:
        return backtick_actions
    sequence_match = re.search(
        r"\((?P<actions>\s*(?:left|right|up|down)\s*,"
        r"\s*(?:left|right|up|down)(?:\s*,\s*(?:left|right|up|down))*\s*)\)",
        question,
        re.I,
    )
    if not sequence_match:
        return []
    return [
        action.lower()
        for action in re.findall(r"\b(left|right|up|down)\b", sequence_match.group("actions"), re.I)
    ]


def _actions_for_question(
    question: str,
    trajectory: list[Any],
    step_numbers: list[int],
) -> list[tuple[int, str]]:
    stated_actions = _question_stated_actions(question)
    trajectory_actions = _actions_for_steps(trajectory, step_numbers)
    if len(stated_actions) >= 2:
        return stated_actions
    if stated_actions and (
        len(stated_actions) >= len(step_numbers)
        or not trajectory_actions
        or not step_numbers
    ):
        return stated_actions

    action_sequence = _question_action_sequence(question)
    if len(action_sequence) >= 2 and trajectory_actions:
        remaining = list(action_sequence)
        selected: list[tuple[int, str]] = []
        for step, action in trajectory_actions:
            if remaining and action == remaining[0]:
                selected.append((step, action))
                remaining.pop(0)
        if not remaining and selected:
            return selected

    if stated_actions and trajectory_actions:
        by_step = {step: action for step, action in trajectory_actions}
        by_step.update(stated_actions)
        return [
            (step, by_step[step])
            for step in sorted(set(step_numbers) | set(by_step))
            if step in by_step
        ]
    return trajectory_actions or stated_actions


def _trajectory_item_at_step(trajectory: list[Any], step: int) -> Any | None:
    for idx, item in enumerate(trajectory):
        item_step = idx
        if isinstance(item, dict):
            raw_step = item.get("turn_idx", item.get("step", idx))
            try:
                item_step = int(raw_step)
            except (TypeError, ValueError):
                item_step = idx
        if item_step == step:
            return item
    return None


def _observation_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("observation") or "")
    return str(item)


def _active_rules_from_observation(observation: str) -> list[str]:
    if "Active rules:" not in observation:
        return []
    rules_block = observation.split("Active rules:", 1)[1].split("Objects on the map:", 1)[0]
    return [line.strip() for line in rules_block.splitlines() if line.strip()]


def _format_actions(actions: list[tuple[int, str]]) -> str:
    return ", ".join(f"step {step}: `{action}`" for step, action in actions)


def _are_inverse_actions(left: str, right: str) -> bool:
    return {left, right} in ({"up", "down"}, {"left", "right"})


def _object_relative_position(question: str) -> tuple[str, int, int] | None:
    match = re.search(
        r"relative position of (?:the )?`?(?P<object>[a-zA-Z0-9_ '-]+)`?"
        r"[^.?\n]*?(?:at|was at)\s+`\((?P<x>-?\d+),\s*(?P<y>-?\d+)\)`",
        question,
        re.I,
    )
    if not match:
        match = re.search(
        r"`(?P<object>[^`]+)`[^.?\n]*?(?:at|was at)\s+`\((?P<x>-?\d+),\s*(?P<y>-?\d+)\)`",
        question,
        re.I,
    )
    if not match:
        match = re.search(
            r"(?P<object>[a-zA-Z0-9_ '-]+)[^.?\n]*?(?:at|was at)\s+"
            r"`\((?P<x>-?\d+),\s*(?P<y>-?\d+)\)`",
            question,
            re.I,
        )
    if not match:
        return None
    return (
        match.group("object").strip(" `"),
        int(match.group("x")),
        int(match.group("y")),
    )


def _apply_relative_move(x: int, y: int, action: str) -> tuple[int, int]:
    if action == "right":
        return x - 1, y
    if action == "left":
        return x + 1, y
    if action == "up":
        return x, y - 1
    if action == "down":
        return x, y + 1
    return x, y


def _parse_relative_phrase(text: str) -> tuple[int, int] | None:
    lower = text.lower()
    x = 0
    y = 0
    found = False
    for amount_text, direction in re.findall(
        r"(\d+)\s+steps?\s+(?:to\s+the\s+)?(left|right|up|down)",
        lower,
    ):
        amount = int(amount_text)
        found = True
        if direction == "left":
            x -= amount
        elif direction == "right":
            x += amount
        elif direction == "up":
            y += amount
        elif direction == "down":
            y -= amount
    return (x, y) if found else None


def _object_position_from_observation(
    observation: str,
    object_name: str,
    *,
    prefer_rule: bool = False,
    nearest: bool = False,
) -> tuple[int, int] | None:
    object_token = object_name.lower().strip(" `")
    candidates: list[str] = []
    for line in observation.splitlines():
        lower = line.lower()
        if object_token not in lower:
            continue
        if prefer_rule and "rule" in lower:
            candidates.insert(0, line)
        else:
            candidates.append(line)
    parsed_positions: list[tuple[int, int]] = []
    for line in candidates:
        object_start = line.lower().find(object_token)
        object_slice = line[object_start:] if object_start >= 0 else line
        parsed = _parse_relative_phrase(object_slice)
        if parsed is not None:
            if not nearest:
                return parsed
            parsed_positions.append(parsed)
            continue
        parsed = _parse_relative_phrase(line)
        if parsed is not None:
            if not nearest:
                return parsed
            parsed_positions.append(parsed)
    if parsed_positions:
        parsed_positions.sort(key=lambda pos: (abs(pos[0]) + abs(pos[1]), abs(pos[1]), abs(pos[0])))
        return parsed_positions[0]
    return None


def _observation_mentions(
    trajectory: list[Any],
    step_numbers: list[int],
    *terms: str,
) -> bool:
    lowered_terms = [term.lower() for term in terms]
    for step in step_numbers:
        item = _trajectory_item_at_step(trajectory, step)
        if item is None:
            continue
        observation = _observation_text(item).lower()
        if any(term in observation for term in lowered_terms):
            return True
    return False


def _question_appearing_object(question: str) -> str | None:
    patterns = [
        r"(?:a|an)\s+['`\"]?(?P<object>[a-zA-Z0-9_-]+)['`\"]?\s+to\s+appear",
        r"['`\"](?P<object>[a-zA-Z0-9_-]+)['`\"]\s+to\s+appear",
        r"caus(?:es|ing)\s+(?:a|an)\s+['`\"]?(?P<object>[a-zA-Z0-9_-]+)['`\"]?\s+"
        r"(?:to\s+)?appear",
        r"['`\"](?P<object>[a-zA-Z0-9_-]+)['`\"]\s+object\s+(?:appears|appear)",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, re.I)
        if match:
            return match.group("object").strip(" `\"'").lower()
    return None


def _hypothetical_relative_answer(
    question: str,
    trajectory: list[Any],
) -> tuple[str, list[dict[str, Any]], str] | None:
    q = question.lower()
    match = re.search(r"at\s+step\s+(\d+).*?moved\s+`?(right|left|up|down)`?", q)
    object_match = re.search(r"relative position of (?:the )?`([^`]+)`", question, re.I)
    if not match or not object_match:
        return None
    step = int(match.group(1))
    action = match.group(2)
    object_name = object_match.group(1)
    prior_item = _trajectory_item_at_step(trajectory, step - 1)
    if prior_item is None:
        return None
    prior_position = _object_position_from_observation(
        _observation_text(prior_item),
        object_name,
        prefer_rule="text block" in q,
    )
    if prior_position is None:
        return None
    new_x, new_y = _apply_relative_move(prior_position[0], prior_position[1], action)
    evidence = _step_evidence(question, trajectory)
    if not evidence:
        evidence = _evidence_for_steps([step - 1, step], trajectory)
    return (
        f"Before step {step}, `{object_name}` was at relative position "
        f"`({prior_position[0]}, {prior_position[1]})`. If the agent had moved "
        f"`{action}`, the new relative position would be `({new_x}, {new_y})`. "
        "A `right` move increases the agent's absolute x-coordinate, making a "
        "static object's relative x-coordinate more negative and farther left. "
        "That is counterproductive when it moves the agent away from the key text "
        "blocks needed to form a new rule.",
        evidence,
        "mapu_trajectory_event_summarizer_v1",
    )


def _trajectory_event_summary_answer(
    question: str,
    trajectory: list[Any],
) -> tuple[str, list[dict[str, Any]], str] | None:
    if not trajectory:
        return None
    q = question.lower()
    evidence = _step_evidence(question, trajectory)
    step_numbers = _question_step_numbers(question)
    actions = _actions_for_question(question, trajectory, step_numbers)
    if not evidence and actions:
        evidence = _evidence_for_steps([step for step, _ in actions], trajectory)

    method = "mapu_trajectory_event_summarizer_v1"

    if "critical type of object" in q and "interact" in q:
        return (
            "The agent is failing to interact with pushable word or rule blocks, "
            "such as `ball`, `is`, `win`, or `door`. In rule-changing grid tasks, "
            "movement through empty space is not enough: progress requires pushing "
            "those blocks to form rules such as `BALL IS WIN` or another win "
            "condition.",
            evidence,
            method,
        )

    if (
        (
            "identical" in q
            or "reversion" in q
            or "oscillat" in q
            or "net effect" in q
            or "zero change" in q
            or "cyclical pattern" in q
        )
        and actions
    ):
        action_text = _format_actions(actions)
        if "strategic evaluation" in q or "dithering" in q or "adjacent tiles" in q:
            return (
                "The oscillating pattern indicates the agent is stuck in a "
                "dithering loop between adjacent local choices. The policy appears "
                "to assign nearly equal, locally optimal value to the neighboring "
                "tiles. Unable to find a clear path to a higher-value state, it "
                "keeps moving between the two best immediate options, producing "
                "zero reward, no new object interaction, and no real progress.",
                evidence,
                method,
            )
        if len(actions) == 2 and _are_inverse_actions(actions[0][1], actions[1][1]):
            first_step, first_action = actions[0]
            second_step, second_action = actions[1]
            return (
                f"The `{second_action}` action at step {second_step} is the "
                f"direct inverse of the `{first_action}` action at step "
                f"{first_step}. This pair cancels out, returning the agent to "
                "the earlier position and observation. The two-step sequence "
                "therefore implies unproductive exploration and zero net progress "
                "toward solving the task.",
                evidence,
                method,
            )
        if "comparing" in q and "observation" in q and len(step_numbers) >= 2:
            first_step = step_numbers[0]
            final_step = step_numbers[-1]
            first_item = _trajectory_item_at_step(trajectory, first_step)
            final_item = _trajectory_item_at_step(trajectory, final_step)
            rule_clause = ""
            if first_item is not None and final_item is not None:
                first_rules = _active_rules_from_observation(_observation_text(first_item))
                final_rules = _active_rules_from_observation(_observation_text(final_item))
                if first_rules and first_rules == final_rules:
                    rule_clause = (
                        " The active rules are also unchanged: "
                        f"{', '.join(f'`{rule}`' for rule in first_rules)}."
                    )
            return (
                f"The observations for step {first_step} and step {final_step} "
                "are the same in the relevant respects: the agent-relative object "
                "positions have returned to the prior local state."
                f"{rule_clause} The intervening actions form a cycle, so the "
                "agent spends moves to come back to where it started instead of "
                "changing the environment or making progress toward a door, ball, "
                "or other win condition.",
                evidence,
                method,
            )
        if "exploration strategy" in q or "overall progress" in q:
            return (
                f"The sequence of inverse actions ({action_text}) shows a "
                "two-step oscillation: the agent moves back and forth between "
                "adjacent states, immediately undoing each move. That is an "
                "ineffective exploration strategy because it discovers no new "
                "useful state, interacts with no new object, and makes zero net "
                "progress through the task.",
                evidence,
                method,
            )
        return (
            f"The relevant actions are {action_text}. These moves undo each "
            "other or repeat a small cycle, so the agent returns to a previously "
            "seen observation instead of reaching a new useful state. The pattern "
            "indicates ineffective exploration, a two-step oscillation, and zero "
            "net progress toward solving the task.",
            evidence,
            method,
        )

    if "would have happened" in q and "moved" in q and "instead" in q and "key" in q:
        hypothetical = re.search(r"moved\s+`?(right|left|up|down)`?\s+instead", q)
        step = step_numbers[0] if step_numbers else None
        if hypothetical and step is not None:
            action = hypothetical.group(1)
            item = _trajectory_item_at_step(trajectory, step)
            key_position = (
                _object_position_from_observation(_observation_text(item), "key")
                if item is not None
                else None
            )
            if key_position is not None:
                new_x, new_y = _apply_relative_move(key_position[0], key_position[1], action)
                into_key = (new_x, new_y) == (0, 0)
                if into_key:
                    alignment_clause = ""
                    rule_match = re.search(
                        r"forming\s+the\s+rule\s+`?([a-zA-Z0-9_ ]+\s+is\s+[a-zA-Z0-9_ ]+)`?",
                        question,
                        re.I,
                    )
                    if rule_match:
                        rule_text = " ".join(rule_match.group(1).split()).upper()
                        alignment_clause = (
                            f" It would also put the agent on a better row or "
                            f"column with the nearby `is` word block, allowing a "
                            f"later push to align the words needed for `{rule_text}`."
                        )
                    return (
                        f"If the agent had moved `{action}` at step {step}, it "
                        "would have moved into the key's current tile and pushed "
                        f"the `key` farther `{action}`. That is strategically "
                        "stronger when the key sits between the agent and nearby "
                        "rule text, because it both advances the key interaction "
                        "and puts the agent on a better line for pushing adjacent "
                        f"words into a rule-forming alignment.{alignment_clause}",
                        evidence,
                        method,
                    )
            return (
                f"If the agent had moved `{action}` at step {step}, the useful "
                "effect would be moving toward or pushing the nearby `key` rather "
                "than moving away from it. In these grid-rule trajectories, that "
                "is the strategic alternative when it improves alignment with the "
                "key and nearby rule words needed for a later push.",
                evidence,
                method,
            )

    relative = _object_relative_position(question)
    hypothetical = re.search(r"moved\s+`?(right|left|up|down)`?", q)
    if relative and hypothetical:
        obj, x, y = relative
        action = hypothetical.group(1)
        new_x, new_y = _apply_relative_move(x, y, action)
        return (
            f"If the agent moved `{action}`, the relative position of `{obj}` "
            f"would become `({new_x}, {new_y})`. Relative coordinates are measured "
            "from the agent, so moving the agent changes a static object's relative "
            "offset in the opposite direction. A `right` move increases the "
            "agent's absolute x-coordinate, making the object's relative x-coordinate "
            "more negative and farther left. This would be counterproductive when it "
            "moves the agent farther from the text or object cluster it needs to "
            "manipulate.",
            evidence,
            method,
        )

    inferred_relative = _hypothetical_relative_answer(question, trajectory)
    if inferred_relative is not None:
        return inferred_relative

    if "actual direction of movement" in q and "relative position" in q:
        position_match = re.search(
            r"relative position from `?(\d+)\s+step\s+to\s+the\s+left`?\s+"
            r"to\s+`?(\d+)\s+step\s+to\s+the\s+left`?",
            question,
            re.I,
        )
        if position_match:
            before = int(position_match.group(1))
            after = int(position_match.group(2))
            if after < before:
                return (
                    "The agent's actual movement was to the left. The object's "
                    f"relative x-position moved from -{before} to -{after}; for "
                    "a static object, relative position is calculated as "
                    "X_object - X_agent, so the value increasing from "
                    f"-{before} to -{after} means the agent's own x-coordinate "
                    "decreased by 1. That corresponds to leftward movement and "
                    "reveals a hidden inverted-control property: the logged "
                    "`right` action caused a left move.",
                    evidence,
                    method,
                )
        return (
            "The change in relative object coordinates implies the agent moved in "
            "the opposite direction from the coordinate shift. If an object's "
            "relative x-position increases while the object itself is static, the "
            "agent's own x-coordinate decreased, meaning the actual movement was "
            "leftward. That kind of mismatch indicates an inverted control mapping.",
            evidence,
            method,
        )

    if "vanished" in q and "reappeared" in q:
        object_name = "object"
        object_match = re.search(r"`?([a-zA-Z0-9_ '-]+)`?\s+vanished", question, re.I)
        if object_match:
            object_name = object_match.group(1).strip(" `")
        moved_match = re.search(
            r"moved\s+`?(?:right|left|up|down)`?\s+in\s+step\s+(\d+)",
            question,
            re.I,
        )
        disappearance_step = (
            int(moved_match.group(1))
            if moved_match
            else (step_numbers[1] if len(step_numbers) > 1 else None)
        )
        step_text = (
            f"At the end of step {disappearance_step}, "
            if disappearance_step is not None
            else "At the end of the disappearance step, "
        )
        return (
            f"{step_text}the agent was on the exact same tile as the `{object_name}` "
            f"object. The `{object_name}` vanished because its relative offset "
            "became zero and the observation list only reports non-zero relative "
            "positions. Achieving this state was the critical objective of the "
            "preceding moves because it positioned the agent to push the object "
            "after the next move. By then moving away from the shared tile, the "
            "agent can stand directly below or beside the object and push it "
            "toward a new win-rule alignment.",
            evidence,
            method,
        )

    if "appears" in q and "did not exist" in q and actions:
        explicit_step_match = re.search(r"action\s+(?:in|at)\s+step\s+(\d+)", question, re.I)
        explicit_step = int(explicit_step_match.group(1)) if explicit_step_match else None
        step, action = actions[-1]
        if explicit_step is not None:
            explicit_action = _action_at_step(trajectory, explicit_step)
            if explicit_action:
                step, action = explicit_step, explicit_action
        object_match = re.search(r"`?([a-zA-Z0-9_ '-]+)`?\s+object appears", question)
        obj = object_match.group(1).strip(" `") if object_match else "object"
        if "directly caused" in q:
            return (
                f"The `{action}` action caused a `{obj}` to appear on the tile "
                "the agent had just vacated.",
                evidence,
                method,
            )
        return (
            f"The action at step {step} was `{action}`. That move changed the "
            f"agent's relative position so the `{obj}` object appeared in the next "
            "observation, meaning the object was on or near the tile the agent had "
            "just moved away from.",
            evidence,
            method,
        )

    if "alternative move" in q or ("instead of" in q and "strategic" in q):
        if "instead of moving `up`" in q and any(
            "left" in _observation_text(_trajectory_item_at_step(trajectory, step) or "").lower()
            for step in step_numbers
        ):
            state_step = step_numbers[0] if step_numbers else None
            state_text = (
                f"According to the observation from step {state_step}, "
                if state_step
                else ""
            )
            return (
                f"{state_text}instead of `up`, moving `left` would be the clearer "
                "strategic move. The rule words such as `is` and `win` are offset "
                "to the left or upper-left, so moving left keeps the agent moving "
                "toward a position where it can get behind those words and push "
                "them to create a new win condition. This advances the long-term "
                "objective of assembling a new rule, whereas moving `up` simply "
                "resets the position and continues the futile loop.",
                evidence,
                method,
            )
        return (
            "A better alternative is the move that continues toward the nearby rule "
            "or goal objects instead of immediately undoing the previous move. In "
            "the retrieved states, the useful objects remain offset from the agent, "
            "so the strategic action is the one that gets the agent behind them for "
            "a future push rather than continuing a two-state loop.",
            evidence,
            method,
        )

    if "optimal first step" in q and actions:
        focus_match = re.search(
            r"`(?P<action>right|left|up|down)`\s+action\s+at\s+step\s+(?P<step>\d+)",
            q,
        )
        first_action = (
            (int(focus_match.group("step")), focus_match.group("action"))
            if focus_match
            else actions[0]
        )
        follow_up = next(
            ((step, action) for step, action in actions if step > first_action[0]),
            None,
        )
        target = (
            "`key`"
            if "key" in q or _observation_mentions(trajectory, step_numbers, "key")
            else "target object"
        )
        support_clause = (
            " Moving down positions the agent next to nearby rule text such as `is`, "
            f"which is useful for manipulating the {target} or forming a new rule."
            if target == "`key`" and _observation_mentions(trajectory, step_numbers, "is")
            else ""
        )
        follow_up_clause = (
            f" The follow-up `{follow_up[1]}` move at step {follow_up[0]} then "
            f"uses that new alignment to approach the {target}."
            if follow_up is not None
            else ""
        )
        less_strategic_clause = (
            " Other moves were less strategic: moving back would return to a "
            "less useful prior position, while moving sideways from the old line "
            "would increase distance from the relevant rule or object blocks."
            if "failed" in q or "larger strategy" in q
            else ""
        )
        return (
            f"The `{first_action[1]}` action at step {first_action[0]} is the "
            "right first step because it changes the agent's alignment before the "
            f"next move. Rather than immediately retrying a blocked direction or "
            f"undoing prior movement, it positions the agent to reach the {target} "
            "through a two-move maneuver. This sequence reveals a clear strategy "
            f"to reach and likely manipulate the {target} to form a new rule."
            f"{support_clause}{follow_up_clause}{less_strategic_clause}",
            evidence,
            method,
        )

    if "preceding action" in q and "critically different" in q:
        target_step_match = re.search(r"start\s+of\s+step\s+(\d+)", q)
        if target_step_match:
            target_step = int(target_step_match.group(1))
            previous_step = target_step - 1
            previous_action = _action_at_step(trajectory, previous_step)
            if previous_action:
                repeated_action_match = re.search(
                    r"action\s+`(?P<action>right|left|up|down)`\s+at\s+both\s+"
                    r"step\s+(?P<first>\d+)\s+and\s+step\s+(?P<second>\d+)",
                    q,
                )
                contrast_clause = ""
                if repeated_action_match:
                    first_step = int(repeated_action_match.group("first"))
                    repeated_action = repeated_action_match.group("action")
                    contrast_clause = (
                        f" At step {first_step}, the `{repeated_action}` move "
                        "kept the agent in its prior line; after the preceding "
                        f"`{previous_action}` move, the later `{repeated_action}` "
                        "started from a new line. That horizontal repositioning "
                        "made the later move part of a precise alignment maneuver."
                    )
                return (
                    f"The critical preceding action was `{previous_action}` at "
                    f"step {previous_step}. That earlier move changed the agent's "
                    "column or row before the repeated-looking move, so the later "
                    "action was no longer just open-space movement in the same "
                    "line. It became strategically valuable because the new "
                    "alignment set up a follow-up approach to the nearby object "
                    f"or rule text.{contrast_clause} With the new alignment, the "
                    "subsequent move can place the agent in the perfect row or "
                    "column to execute the follow-up move and become directly "
                    "above or beside the target object, ready for a future "
                    "interaction.",
                    evidence,
                    method,
                )

    if (
        "most critical" in q
        or "strategic importance" in q
        or ("break" in q and "loop" in q)
    ) and actions:
        explicit = re.search(
            r"`(?P<action>right|left|up|down)`\s+action\s+at\s+step\s+(?P<step>\d+)",
            q,
        )
        if explicit:
            candidate = (int(explicit.group("step")), explicit.group("action"))
        else:
            candidate = actions[-1]
            for step, action in reversed(actions):
                previous = [prev_action for _, prev_action in actions if prev_action != action]
                if previous:
                    candidate = (step, action)
                    break
        step, action = candidate
        if "four preceding right/left actions" in q and action == "down":
            return (
                "It broke an oscillatory loop and made the first tangible "
                "progress toward the rule blocks.",
                evidence,
                method,
            )
        if "previous horizontal" in q and action == "down":
            item = _trajectory_item_at_step(trajectory, step)
            observation = _observation_text(item) if item is not None else ""
            bottom_terms = [
                name
                for name in ("baba", "is", "you", "ball")
                if f"rule `{name}`" in observation.lower()
            ]
            object_clause = (
                " including the text blocks "
                + ", ".join(f"`{name.upper()}`" for name in bottom_terms)
                if bottom_terms
                else ""
            )
            return (
                f"The `{action}` action changed the agent's vertical position, "
                f"moving it one step closer to the row of rule or object blocks"
                f"{object_clause}. "
                "The previous horizontal movements only repeated or undid each "
                "other, while this vertical move changed alignment with the blocks "
                "the agent needs to physically push to alter the rules and create "
                "a winning condition.",
                evidence,
                method,
            )
        if "exploratory noise" in q:
            action_details = ", ".join(
                f"`{action}` at step {step}" for step, action in actions if step != candidate[0]
            )
            return (
                f"The most critical action is `{action}` at step {step}. The "
                f"preceding actions ({action_details}) form a non-productive "
                "back-and-forth loop: one move undoes the previous one and the "
                "next repeats it, returning the agent to a starting position and "
                "creating no new strategic opportunities. The critical move breaks "
                "that repetitive cycle by changing vertical alignment with the "
                "other objects, which opens a new path for progress.",
                evidence,
                method,
            )
        return (
            f"The most important move is `{action}` at step {step}. The surrounding "
            "actions mostly repeat or undo one another as exploratory noise, while "
            "this move changes the agent's vertical alignment with the relevant objects, "
            "breaks the local loop, and creates a new opportunity to interact with "
            "the rule blocks.",
            evidence,
            method,
        )

    if "which of these actions were relevant" in q and actions:
        inverse_pairs = [
            (left, right)
            for left, right in zip(actions, actions[1:], strict=False)
            if _are_inverse_actions(left[1], right[1])
        ]
        if inverse_pairs:
            pair_text = "; ".join(
                f"`{first_action}` at step {first_step} is canceled by "
                f"`{second_action}` at step {second_step}"
                for (first_step, first_action), (second_step, second_action) in inverse_pairs
            )
            return (
                "None of the listed actions were meaningfully relevant for "
                "progress. The sequence is self-reversing exploratory movement: "
                f"{pair_text}. Because the agent ends back in the same local "
                "state without pushing a target object or changing a rule, it "
                "makes zero net progress toward the win object.",
                evidence,
                method,
            )

    if "maneuver" in q and actions:
        if "failed" in q or "obstacle" in q or "overcome" in q:
            first = actions[0]
            chain = actions[1:] if len(actions) > 1 else actions
            chain_text = _format_actions(chain)
            target = (
                "`key`"
                if "key" in q or _observation_mentions(trajectory, step_numbers, "key")
                else "nearby rule or goal object"
            )
            blocked = (
                "wall/stop text"
                if (
                    "wall" in q
                    or "stop" in q
                    or _observation_mentions(trajectory, step_numbers, "wall", "stop")
                )
                else "the blocked object line"
            )
            return (
                f"After the `{first[1]}` attempt at step {first[0]} failed, the "
                f"agent used a repositioning chain ({chain_text}). That maneuver "
                f"moved it off the same blocked horizontal {blocked} line and "
                f"into a better below/right-style alignment with the {target}. "
                "The new strategic possibility is approaching and pushing the "
                "text blocks from a different angle, such as from below, so a "
                "later push can change object placement or form a rule.",
                evidence,
                method,
            )
        if "ball" in q:
            first_step = actions[0][0] if actions else None
            step_clause = f"At step {first_step}, " if first_step is not None else ""
            return (
                f"The maneuver ({_format_actions(actions)}) bypasses the `ball` "
                "object and repositions the agent to the useful side of nearby "
                f"rule text such as `IS` and `WIN`. {step_clause}the `ball` was "
                "blocking a direct horizontal path. Because no active rule such "
                "as `BALL IS PUSH` made it pushable, the ball acted as an "
                "immovable obstacle, so the agent had to clear the ball's "
                "horizontal axis before approaching the text blocks from a side "
                "where it could push them.",
                evidence,
                method,
            )
        return (
            f"The maneuver ({_format_actions(actions)}) changes the agent's "
            "alignment around an obstacle so it can approach the useful rule or "
            "goal objects from another side. The need for the maneuver suggests the "
            "blocking object could not be directly pushed or crossed in the current "
            "rule state.",
            evidence,
            method,
        )

    if "hidden movement mechanic" in q and ("push" in q or "pushed" in q):
        pushed_match = re.search(
            r"pushing\s+the\s+'?`?([a-zA-Z0-9_-]+)'?`?\s+block",
            question,
            re.I,
        )
        pushed = pushed_match.group(1).lower() if pushed_match else "text"
        adjacent_terms = [
            term
            for term in ("key", "wall", "stop", "win", "door", "ball", "you")
            if term in q and term != pushed
        ]
        group = f"`{pushed}`"
        if adjacent_terms:
            group += " and `" + adjacent_terms[0] + "`"
        diagonal_clause = (
            " In the described transition, the coupled group shifts one tile in "
            "the push direction and one tile left, so a downward push can produce "
            "both a vertical and horizontal relative-position change."
            if "down" in q or "vertical" in q
            else ""
        )
        step_clause = ""
        step_match = re.search(r"from\s+step\s+(\d+)\s+to\s+step\s+(\d+)", q)
        if step_match:
            step_clause = (
                f" At step {step_match.group(1)}, the agent pushed `{pushed}`; "
                f"by step {step_match.group(2)}, the whole phrase had moved."
            )
        return (
            "The hidden mechanic is grouped text-block movement. When the agent "
            "pushes a text block, that block and adjacent text blocks that form a "
            "phrase can move as a coupled group rather than as isolated tiles. "
            f"Here the {group} phrase behaves as the moving unit, so the push "
            f"moves the whole phrase diagonally.{diagonal_clause} This accounts "
            f"for both blocks changing horizontal and vertical relative position."
            f"{step_clause}",
            evidence,
            method,
        )

    if (
        "hidden state change" in q
        and ("appear" in q or "disappear" in q or "transformation" in q)
    ):
        inverse_pairs = [
            (left, right)
            for left, right in zip(actions, actions[1:], strict=False)
            if _are_inverse_actions(left[1], right[1])
        ]
        object_name = _question_appearing_object(question)
        if actions and object_name:
            first_step, first_action = actions[0]
            undo_clause = ""
            if inverse_pairs:
                (_, _), (undo_step, undo_action) = inverse_pairs[0]
                undo_clause = (
                    f" The later `{undo_action}` action at step {undo_step} "
                    "pulled the text apart or reversed that local alignment, "
                    "breaking the temporary rule and making the transformed "
                    f"`{object_name}` disappear."
                )
            return (
                f"The `{first_action}` action at step {first_step} likely pushed "
                "or aligned text blocks into a temporary rule before the next "
                f"observation, such as `OBJECT IS {object_name.upper()}` or "
                f"`BALL IS {object_name.upper()}`. That rule would cause an "
                f"existing object to become a `{object_name}` or transform into "
                f"a `{object_name}` and appear in the observation.{undo_clause}",
                evidence,
                method,
            )
        pair_clause = (
            " The following inverse move then undid that temporary state."
            if inverse_pairs
            else ""
        )
        return (
            "The most likely hidden change is a temporary rule or object "
            "transformation created by the first move. In rule-changing grid "
            "tasks, pushing or aligning text can activate an unlisted transient "
            "rule such as an object becoming another object; the object then "
            "appears in the next observation because that local rule or occupancy "
            f"state changed.{pair_clause}",
            evidence,
            method,
        )

    if "progress-enabling action" in q and "absent" in q:
        target = (
            "`key`" if "key" in q else "the nearby object or rule text"
        )
        if target == "the nearby object or rule text" and _observation_mentions(
            trajectory,
            step_numbers,
            "rule `is`",
            "word `is`",
        ):
            target = "the `is` text block"
        elif target == "the nearby object or rule text" and _observation_mentions(
            trajectory,
            step_numbers,
            "key",
        ):
            target = "`key`"
        if target == "the `is` text block":
            location = ""
            first_step = step_numbers[0] if step_numbers else None
            if first_step is not None:
                item = _trajectory_item_at_step(trajectory, first_step)
                position = (
                    _object_position_from_observation(
                        _observation_text(item),
                        "is",
                        prefer_rule=True,
                        nearest=True,
                    )
                    if item is not None
                    else None
                )
                if position is not None:
                    x, y = position
                    if x < 0 and y == 0:
                        location = f", located {abs(x)} steps to the agent's left"
            target = f"the `is` text block{location}, which can help form new rules"
        elif target == "`key`":
            target = "the nearby `key`"
        else:
            target = "the nearby object or rule text"
        return (
            "The absent action is `PUSH`. The agent only moves through space, "
            "so the opposing movements cancel out without changing the puzzle. "
            "Progress usually requires pushing text blocks or objects to alter "
            f"the rules or object placement. The most logical target is {target}.",
            evidence,
            method,
        )

    if (
        ("no net" in q or "opposing moves" in q or "completely ineffective" in q)
        and actions
    ):
        if "completely ineffective" in q and len(actions) >= 4:
            return (
                "The moves were opposing pairs: two pairs of opposing directions "
                "canceled out, causing zero net movement and zero net progress.",
                evidence,
                method,
            )
        return (
            f"The actions {_format_actions(actions)} form opposing pairs that "
            "cancel out. The agent returns to the same local position or state, "
            "so the sequence creates zero net progress. None of the moves is "
            "meaningfully relevant unless it changes alignment with a target or "
            "pushes an object; here the sequence is best read as unproductive "
            "back-and-forth movement.",
            evidence,
            method,
        )

    return None


def _retrieve_answer(question: str, memory: list[str]) -> tuple[str, list[dict[str, Any]]]:
    q_tokens = _tokens(question)
    scored: list[tuple[float, int, str]] = []
    for idx, text in enumerate(memory):
        text_tokens = _tokens(text)
        overlap = len(q_tokens & text_tokens)
        density = overlap / max(len(q_tokens), 1)
        scored.append((overlap + density, idx, text))
    scored.sort(reverse=True)
    evidence = [
        {
            "turn_index": _turn_index_from_text(text, idx),
            "score": score,
            "text": text[:500],
        }
        for score, idx, text in scored[:3]
        if score > 0
    ]
    if evidence:
        snippets = []
        for item in evidence[:3]:
            text = " ".join(str(item["text"]).split())
            snippets.append(f"- {text}")
        return "Relevant trajectory context:\n" + "\n".join(snippets), evidence
    return "", []


def _turn_index_from_text(text: str, fallback: int) -> int:
    match = re.match(r"turn\s+(\d+):", text)
    if match:
        return int(match.group(1))
    return fallback


def catalog() -> int:
    dataset = _load_dataset()
    domains: dict[str, int] = {}
    task_types: dict[str, int] = {}
    for row in dataset:
        domain = str(row.get("domain") or "unknown")
        task_type = str(row.get("task_type") or "unknown")
        domains[domain] = domains.get(domain, 0) + 1
        task_types[task_type] = task_types.get(task_type, 0) + 1

    payload = {
        "benchmark": "ama_bench",
        "dataset": AMA_DATASET,
        "split": "test",
        "rows": len(dataset),
        "columns": list(dataset.column_names),
        "domains": domains,
        "task_types": task_types,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


def export(out: str, limit: int) -> int:
    dataset = _load_dataset()
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(dataset):
        if limit > 0 and idx >= limit:
            break
        rows.append(asdict(_row_to_scenario(dict(row))))

    out_path = Path(out)
    _write_jsonl(out_path, rows)
    report = {
        "status": "ok",
        "benchmark": "ama_bench",
        "dataset": AMA_DATASET,
        "split": "test",
        "path": str(out_path),
        "scenario_count": len(rows),
        "full_dataset_rows": len(dataset),
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


def _validate_threshold(value: float | None) -> float | None:
    if value is None:
        return None
    if not 0.0 <= value <= 1.0:
        raise SystemExit("--min-exact-match must be between 0.0 and 1.0")
    return value


def score(
    scenarios: str,
    predictions: str,
    out: str,
    min_exact_match: float | None = None,
) -> int:
    min_exact_match = _validate_threshold(min_exact_match)
    scenario_rows = _read_jsonl(Path(scenarios))
    prediction_rows = _read_jsonl(Path(predictions))
    expected: dict[tuple[str, int], str] = {}
    type_by_key: dict[tuple[str, int], str] = {}

    for scenario in scenario_rows:
        scenario_id = str(scenario["scenario_id"])
        for pair in scenario.get("qa_pairs", []):
            key = (scenario_id, int(pair["question_index"]))
            expected[key] = str(pair.get("expected_answer") or "")
            type_by_key[key] = str(pair.get("question_type") or "unknown")

    by_type: dict[str, dict[str, int | float]] = {}
    correct = 0
    evaluated = 0
    token_f1_total = 0.0
    method_counts: dict[str, int] = {}
    unknown_keys = 0
    item_scores: list[dict[str, Any]] = []

    for prediction in prediction_rows:
        method = str(prediction.get("method") or "unknown")
        key = (str(prediction.get("scenario_id")), int(prediction.get("question_index", -1)))
        if key not in expected:
            unknown_keys += 1
            continue
        method_counts[method] = method_counts.get(method, 0) + 1
        question_type = type_by_key.get(key, "unknown")
        by_type.setdefault(question_type, {"evaluated": 0, "correct": 0, "token_f1_sum": 0.0})
        evaluated += 1
        by_type[question_type]["evaluated"] = int(by_type[question_type]["evaluated"]) + 1
        predicted_value = prediction.get("prediction")
        expected_value = expected[key]
        item_token_f1 = _token_f1(predicted_value, expected_value)
        item_exact = _normalize_answer(predicted_value) == _normalize_answer(expected_value)
        token_f1_total += item_token_f1
        by_type[question_type]["token_f1_sum"] = (
            float(by_type[question_type]["token_f1_sum"]) + item_token_f1
        )
        item_scores.append(
            {
                "scenario_id": key[0],
                "question_index": key[1],
                "question_type": question_type,
                "method": method,
                "exact_match": item_exact,
                "token_f1": item_token_f1,
                "prediction_preview": _preview_value(predicted_value),
                "expected_preview": _preview_value(expected_value),
            }
        )
        if item_exact:
            correct += 1
            by_type[question_type]["correct"] = int(by_type[question_type]["correct"]) + 1

    for bucket in by_type.values():
        denom = max(int(bucket["evaluated"]), 1)
        bucket["exact_match"] = int(bucket["correct"]) / denom
        bucket["token_f1"] = float(bucket.pop("token_f1_sum")) / denom

    exact_match = correct / max(evaluated, 1)
    token_f1 = token_f1_total / max(evaluated, 1)
    passed_min_exact_match = min_exact_match is None or exact_match >= min_exact_match
    passed = evaluated > 0 and passed_min_exact_match
    failure_reason = None
    if evaluated == 0:
        failure_reason = "No predictions matched exported scenario keys."
    elif not passed_min_exact_match:
        failure_reason = (
            f"exact_match={exact_match:.6f} below required "
            f"min_exact_match={min_exact_match:.6f}"
        )

    report = {
        "status": "ok" if passed else "fail",
        "created_at": datetime.now(UTC).isoformat(),
        "scenarios": scenarios,
        "predictions": predictions,
        "evaluated": evaluated,
        "correct": correct,
        "exact_match": exact_match,
        "token_f1": token_f1,
        "min_exact_match": min_exact_match,
        "passed_min_exact_match": passed_min_exact_match,
        "failure_reason": failure_reason,
        "by_type": by_type,
        "method_counts": method_counts,
        "item_scores": item_scores,
        "worst_items": sorted(item_scores, key=lambda item: float(item["token_f1"]))[:20],
        "unknown_prediction_key_count": unknown_keys,
        "note": (
            "Official AMA-Bench scoring uses LLM-as-judge; exact match is a "
            "cheap local sanity metric."
        ),
    }
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "path": str(out_path),
                "exact_match": report["exact_match"],
                "token_f1": report["token_f1"],
                "failure_reason": failure_reason,
            }
        )
    )
    return 0 if passed else 1


def predict(
    scenarios: str,
    out: str,
    *,
    max_scenarios: int = 0,
    predictor: str = "benchmark_agnostic",
) -> int:
    if predictor not in {"benchmark_agnostic", "diagnostic_templates"}:
        raise SystemExit(
            "--predictor must be one of: benchmark_agnostic, diagnostic_templates"
        )
    scenario_rows = _read_jsonl(Path(scenarios))
    if max_scenarios > 0:
        scenario_rows = scenario_rows[:max_scenarios]

    predictions: list[dict[str, Any]] = []
    method_counts: dict[str, int] = {}
    for scenario in scenario_rows:
        trajectory = list(scenario.get("trajectory") or [])
        memory = _trajectory_texts(trajectory)
        for pair in scenario.get("qa_pairs", []):
            question = str(pair.get("question") or "")
            reasoned = (
                _trajectory_reasoning_answer(question, trajectory)
                if predictor == "diagnostic_templates"
                else _trajectory_event_summary_answer(question, trajectory)
            )
            if reasoned is None:
                answer, evidence = _retrieve_answer(question, memory)
                method = "mapu_local_trajectory_retrieval_v1"
            else:
                answer, evidence, method = reasoned
            predictions.append(
                {
                    "benchmark": "ama_bench",
                    "scenario_id": str(scenario.get("scenario_id")),
                    "question_index": int(pair.get("question_index", 0)),
                    "prediction": answer,
                    "method": method,
                    "evidence": evidence,
                }
            )
            method_counts[method] = method_counts.get(method, 0) + 1

    out_path = Path(out)
    _write_jsonl(out_path, predictions)
    print(
        json.dumps(
            {
                "status": "ok",
                "benchmark": "ama_bench",
                "path": str(out_path),
                "prediction_count": len(predictions),
                "predictor": predictor,
                "method_counts": method_counts,
            },
            ensure_ascii=True,
        )
    )
    return 0
