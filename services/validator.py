from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from enum import Enum

from models import (
    GameState,
    Event,
    Ending,
    Condition,
    Choice,
    ChoiceEffect,
    ConditionType,
    ChoiceEffectType,
)


class LinkStatus(Enum):
    VALID = "valid"
    BROKEN = "broken"
    WARN = "warn"


@dataclass
class TimelineStep:
    event: Event
    step_index: int
    state_before: GameState
    state_after: Optional[GameState] = None
    selected_choice: Optional[Choice] = None
    event_condition_status: LinkStatus = LinkStatus.VALID
    broken_event_conditions: List[Condition] = field(default_factory=list)
    choice_effects_applied: List[ChoiceEffect] = field(default_factory=list)
    note: str = ""


@dataclass
class ValidationResult:
    overall_status: LinkStatus
    timeline: List[TimelineStep] = field(default_factory=list)
    ending_met_conditions: List[Condition] = field(default_factory=list)
    ending_missing_conditions: List[Condition] = field(default_factory=list)
    contradictions: List["Contradiction"] = field(default_factory=list)
    final_state: Optional[GameState] = None
    summary: str = ""


@dataclass
class Contradiction:
    severity: str
    category: str
    message: str
    suggestion: str
    related_event_id: Optional[str] = None
    related_ending_id: Optional[str] = None
    related_condition_id: Optional[str] = None


class CausalityValidator:
    def __init__(self, events: List[Event], endings: List[Ending]):
        self.events = events
        self.endings = endings
        self._sorted_events = sorted(events, key=lambda e: (e.chapter, e.order))

    def _find_choice_satisfying_condition(
        self, event: Event, condition: Condition
    ) -> Optional[Choice]:
        for choice in event.choices:
            temp_state = GameState()
            for effect in choice.effects:
                effect.apply(temp_state)
            if condition.evaluate(temp_state):
                return choice
        return None

    def simulate_path_to_ending(
        self, ending: Ending, initial_state: Optional[GameState] = None
    ) -> ValidationResult:
        state = initial_state.clone() if initial_state else GameState()
        timeline: List[TimelineStep] = []
        contradictions: List[Contradiction] = []

        required_conditions_map: Dict[str, Tuple[Condition, Optional[Event]]] = {}
        for cond in ending.conditions:
            source_event = self._find_source_event_for_condition(cond)
            required_conditions_map[cond.id] = (cond, source_event)

        for step_idx, event in enumerate(self._sorted_events):
            step = TimelineStep(
                event=event,
                step_index=step_idx,
                state_before=state.clone(),
            )

            event_conditions_ok = event.check_conditions(state)
            if not event_conditions_ok:
                step.event_condition_status = LinkStatus.BROKEN
                step.broken_event_conditions = [
                    c for c in event.conditions if not c.evaluate(state)
                ]
                for cond in step.broken_event_conditions:
                    contradictions.append(Contradiction(
                        severity="error",
                        category="事件条件冲突",
                        message=f"第{event.chapter}章事件「{event.title}」的前置条件不满足：{cond.human_readable()}",
                        suggestion=f"检查之前的事件是否遗漏了提供 {cond.human_readable()} 的选项，或调整该事件的触发条件。",
                        related_event_id=event.id,
                        related_condition_id=cond.id,
                    ))
                continue

            best_choice = self._select_best_choice_for_ending(
                event, ending, state
            )
            step.selected_choice = best_choice

            if best_choice is not None:
                for effect in best_choice.effects:
                    effect.apply(state)
                    step.choice_effects_applied.append(effect)
            else:
                if event.choices:
                    first_choice = event.choices[0]
                    for effect in first_choice.effects:
                        effect.apply(state)
                        step.choice_effects_applied.append(effect)
                    step.selected_choice = first_choice
                    step.note = "（自动选择默认选项，非最优路径）"
                    step.event_condition_status = LinkStatus.WARN

            step.state_after = state.clone()
            timeline.append(step)

        met_conditions: List[Condition] = []
        missing_conditions: List[Condition] = []
        for cond in ending.conditions:
            if cond.evaluate(state):
                met_conditions.append(cond)
            else:
                missing_conditions.append(cond)
                contradictions.append(self._analyze_missing_condition(cond, state, ending, timeline))

        overall = LinkStatus.VALID
        if missing_conditions:
            overall = LinkStatus.BROKEN
        elif any(s.event_condition_status == LinkStatus.WARN for s in timeline):
            overall = LinkStatus.WARN

        summary_lines = []
        if overall == LinkStatus.VALID:
            summary_lines.append(f"结局「{ending.title}」因果链完整，所有条件均满足。")
        elif overall == LinkStatus.WARN:
            summary_lines.append(f"结局「{ending.title}」可达成，但部分步骤使用了非最优选择，建议检查。")
        else:
            summary_lines.append(f"结局「{ending.title}」存在 {len(missing_conditions)} 个未满足条件，因果链断裂。")
        summary_lines.append(f"时间线共经过 {len(timeline)} 个事件。")
        if contradictions:
            summary_lines.append(f"发现 {len(contradictions)} 处矛盾/提示。")

        return ValidationResult(
            overall_status=overall,
            timeline=timeline,
            ending_met_conditions=met_conditions,
            ending_missing_conditions=missing_conditions,
            contradictions=contradictions,
            final_state=state.clone(),
            summary="\n".join(summary_lines),
        )

    def _find_source_event_for_condition(self, condition: Condition) -> Optional[Event]:
        for event in reversed(self._sorted_events):
            for choice in event.choices:
                temp_state = GameState()
                for effect in choice.effects:
                    effect.apply(temp_state)
                if condition.evaluate(temp_state):
                    return event
        return None

    def _select_best_choice_for_ending(
        self, event: Event, ending: Ending, current_state: GameState
    ) -> Optional[Choice]:
        if not event.choices:
            return None

        best_score = -1
        best_choice: Optional[Choice] = None
        for choice in event.choices:
            temp_state = current_state.clone()
            for effect in choice.effects:
                effect.apply(temp_state)
            score = 0
            for cond in ending.conditions:
                if cond.evaluate(temp_state):
                    score += 3
                elif not cond.evaluate(current_state):
                    if self._condition_progressing(cond, current_state, temp_state):
                        score += 1
            for cond in event.conditions:
                if cond.evaluate(temp_state):
                    score += 1
            if score > best_score:
                best_score = score
                best_choice = choice
        return best_choice

    def _condition_progressing(
        self, cond: Condition, before: GameState, after: GameState
    ) -> bool:
        if cond.condition_type in (
            ConditionType.HAS_CLUE, ConditionType.CHAR_DEAD,
            ConditionType.CHAR_MISSING, ConditionType.CHAR_INSANE,
            ConditionType.FLAG_TRUE,
        ):
            return (not cond.evaluate(before)) and (not cond.evaluate(after)) is False
        if cond.condition_type == ConditionType.FEAR_GTE:
            return after.fear_level > before.fear_level
        if cond.condition_type == ConditionType.FEAR_LTE:
            return after.fear_level < before.fear_level
        return False

    def _analyze_missing_condition(
        self,
        cond: Condition,
        final_state: GameState,
        ending: Ending,
        timeline: List[TimelineStep],
    ) -> Contradiction:
        source_event = self._find_source_event_for_condition(cond)

        suggestion_parts = []
        if source_event:
            suggestion_parts.append(
                f"可在第{source_event.chapter}章「{source_event.title}」中通过选择提供该条件。"
            )
        else:
            suggestion_parts.append(
                "目前所有事件中均无选项可以产生该条件，请考虑在合适章节增加铺垫事件。"
            )

        if cond.condition_type == ConditionType.HAS_CLUE:
            for dialogue in ending.dialogue_hints:
                if cond.target in dialogue:
                    suggestion_parts.append(
                        f"注意：结局台词中提到「{dialogue[:40]}...」依赖该线索，请确保玩家有机会获取。"
                    )

        return Contradiction(
            severity="error" if cond.condition_type in (
                ConditionType.HAS_CLUE, ConditionType.CHAR_ALIVE,
                ConditionType.CHAR_DEAD, ConditionType.FLAG_TRUE,
            ) else "warning",
            category="结局条件缺失",
            message=f"结局「{ending.title}」的必要条件未满足：{cond.human_readable()}",
            suggestion=" ".join(suggestion_parts),
            related_ending_id=ending.id,
            related_condition_id=cond.id,
            related_event_id=source_event.id if source_event else None,
        )

    def validate_all_endings(
        self, initial_state: Optional[GameState] = None
    ) -> Dict[str, ValidationResult]:
        results: Dict[str, ValidationResult] = {}
        for ending in self.endings:
            results[ending.id] = self.simulate_path_to_ending(ending, initial_state)
        return results

    def find_dialogue_contradictions(
        self, result: ValidationResult, ending: Ending
    ) -> List[Contradiction]:
        extra: List[Contradiction] = []
        final_state = result.final_state or GameState()
        for dialogue in ending.dialogue_hints:
            for clue_id, has_it in final_state.clues.items():
                if not has_it and clue_id and len(clue_id) > 2:
                    if clue_id in dialogue or any(
                        kw in dialogue for kw in clue_id.split("_") if len(kw) > 2
                    ):
                        extra.append(Contradiction(
                            severity="warning",
                            category="台词线索矛盾",
                            message=f"结局台词「{dialogue[:50]}...」似乎涉及线索「{clue_id}」，但该线索并未被玩家获取。",
                            suggestion=f"请确认：要么在第{ending.id or '?'}章前补一个能让玩家获取「{clue_id}」线索的事件；要么修改台词避免提及未获得的线索。",
                            related_ending_id=ending.id,
                        ))
        return extra
