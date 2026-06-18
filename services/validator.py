from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from enum import Enum
import re

from models import (
    GameState,
    Event,
    Ending,
    Condition,
    Choice,
    ChoiceEffect,
    ConditionType,
    ChoiceEffectType,
    CharacterStatus,
)


class LinkStatus(Enum):
    VALID = "valid"
    BROKEN = "broken"
    WARN = "warn"
    SKIPPED = "skipped"


@dataclass
class ChoiceScore:
    choice: Choice
    score: int
    met_conditions: List[str] = field(default_factory=list)
    progress_conditions: List[str] = field(default_factory=list)


@dataclass
class TimelineStep:
    event: Event
    step_index: int
    state_before: GameState
    state_after: Optional[GameState] = None
    selected_choice: Optional[Choice] = None
    event_condition_status: LinkStatus = LinkStatus.VALID
    broken_event_conditions: List[Condition] = field(default_factory=list)
    met_event_conditions: List[Condition] = field(default_factory=list)
    choice_effects_applied: List[ChoiceEffect] = field(default_factory=list)
    all_choice_scores: List[ChoiceScore] = field(default_factory=list)
    note: str = ""
    was_triggered: bool = True


@dataclass
class ValidationResult:
    overall_status: LinkStatus
    timeline: List[TimelineStep] = field(default_factory=list)
    ending_met_conditions: List[Condition] = field(default_factory=list)
    ending_missing_conditions: List[Condition] = field(default_factory=list)
    contradictions: List["Contradiction"] = field(default_factory=list)
    final_state: Optional[GameState] = None
    initial_state_used: Optional[GameState] = None
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
    related_chapter: Optional[int] = None
    dialogue_ref: Optional[str] = None


@dataclass
class DialogueReference:
    source_type: str
    source_id: str
    reference: str
    reference_type: str
    was_provided: bool
    source_chapter: Optional[int] = None
    provider_event: Optional[str] = None


class DialogueAnalyzer:
    CLUE_KEYWORDS = [
        "照片", "符咒", "日记", "信件", "钥匙", "证据", "笔记",
        "录音", "录像", "文件", "档案", "地图", "符号", "符文",
        "仪式", "祭坛", "血印", "标记", "线索",
    ]
    LOCATION_KEYWORDS = [
        "地下室", "阁楼", "停尸房", "祭坛", "教堂", "医院", "疗养院",
        "302", "房间", "走廊", "大厅", "厨房", "书房", "实验室",
        "墓", "森林", "井", "隧道",
    ]

    def __init__(self, events: List[Event]):
        self.events = events
        self._sorted = sorted(events, key=lambda e: (e.chapter, e.order))
        self._all_clue_ids = self._extract_all_clue_ids()
        self._all_char_ids = self._extract_all_char_ids()

    def _extract_all_clue_ids(self) -> set:
        clues = set()
        for event in self._sorted:
            for choice in event.choices:
                for effect in choice.effects:
                    if effect.effect_type in (ChoiceEffectType.SET_CLUE, ChoiceEffectType.UNSET_CLUE):
                        if effect.target:
                            clues.add(effect.target)
        return clues

    def _extract_all_char_ids(self) -> set:
        chars = set()
        for event in self._sorted:
            for choice in event.choices:
                for effect in choice.effects:
                    if effect.effect_type in (
                        ChoiceEffectType.SET_CHAR_ALIVE,
                        ChoiceEffectType.SET_CHAR_DEAD,
                        ChoiceEffectType.SET_CHAR_MISSING,
                        ChoiceEffectType.SET_CHAR_INSANE,
                    ):
                        if effect.target:
                            chars.add(effect.target)
        return chars

    def analyze_dialogue(self, dialogue: str, ending: Ending, final_state: GameState) -> List[Contradiction]:
        issues: List[Contradiction] = []
        refs = self.extract_references(dialogue)

        for ref in refs:
            if ref.reference_type == "clue":
                if ref.reference not in final_state.clues or not final_state.clues[ref.reference]:
                    provider = self._find_provider_event_for_clue(ref.reference)
                    ch_num = provider.chapter if provider else None
                    suggestion = self._build_suggestion_for_missing(
                        "线索", ref.reference, dialogue, provider, ch_num
                    )
                    issues.append(Contradiction(
                        severity="error" if ref.reference in self._all_clue_ids else "warning",
                        category="台词线索缺失",
                        message=f"结局台词「{dialogue[:50]}...」提到了线索「{ref.reference}」，但玩家未获取该线索。",
                        suggestion=suggestion,
                        related_ending_id=ending.id,
                        related_chapter=ch_num,
                        related_event_id=provider.id if provider else None,
                        dialogue_ref=dialogue,
                    ))
            elif ref.reference_type == "character":
                expected_status = self._infer_char_status_from_dialogue(dialogue, ref.reference)
                actual_status = final_state.get_character_status(ref.reference)
                if expected_status and expected_status != actual_status:
                    provider = self._find_provider_event_for_char(ref.reference, expected_status)
                    ch_num = provider.chapter if provider else None
                    status_label = self._status_label(expected_status)
                    actual_label = self._status_label(actual_status)
                    issues.append(Contradiction(
                        severity="error",
                        category="台词角色矛盾",
                        message=f"结局台词「{dialogue[:50]}...」暗示角色「{ref.reference}」应为{status_label}，但实际状态是{actual_label}。",
                        suggestion=f"要么调整第{ch_num or '?'}章前的事件使「{ref.reference}」{status_label}，要么修改台词使其符合角色{actual_label}的设定。",
                        related_ending_id=ending.id,
                        related_chapter=ch_num,
                        dialogue_ref=dialogue,
                    ))
            elif ref.reference_type == "location":
                visited_flag = f"去过_{ref.reference}"
                if not final_state.get_flag(visited_flag):
                    provider = self._find_provider_event_for_location(ref.reference)
                    ch_num = provider.chapter if provider else None
                    issues.append(Contradiction(
                        severity="warning",
                        category="台词地点缺失",
                        message=f"结局台词「{dialogue[:50]}...」提到了地点「{ref.reference}」，但玩家似乎没去过那里（没有对应标记）。",
                        suggestion=f"建议在第{ch_num or '合适'}章增加一个让玩家探索「{ref.reference}」的事件，或给进入该地点的选项添加标记「{visited_flag}」。",
                        related_ending_id=ending.id,
                        related_chapter=ch_num,
                        related_event_id=provider.id if provider else None,
                        dialogue_ref=dialogue,
                    ))
        return issues

    def extract_references(self, text: str) -> List[DialogueReference]:
        refs: List[DialogueReference] = []
        for clue_id in self._all_clue_ids:
            keywords = clue_id.split("_")
            match = any(kw in text and len(kw) > 2 for kw in keywords)
            if match or clue_id in text:
                refs.append(DialogueReference(
                    source_type="clue",
                    source_id=clue_id,
                    reference=clue_id,
                    reference_type="clue",
                    was_provided=False,
                ))
        for char_id in self._all_char_ids:
            keywords = char_id.split("_")
            match = any(kw in text and len(kw) > 2 for kw in keywords)
            if match or char_id in text:
                refs.append(DialogueReference(
                    source_type="character",
                    source_id=char_id,
                    reference=char_id,
                    reference_type="character",
                    was_provided=False,
                ))
        for loc in self.LOCATION_KEYWORDS:
            if loc in text:
                refs.append(DialogueReference(
                    source_type="location",
                    source_id=loc,
                    reference=loc,
                    reference_type="location",
                    was_provided=False,
                ))
        return refs

    def _find_provider_event_for_clue(self, clue_id: str) -> Optional[Event]:
        for event in reversed(self._sorted):
            for choice in event.choices:
                for effect in choice.effects:
                    if (effect.effect_type == ChoiceEffectType.SET_CLUE
                            and effect.target == clue_id):
                        return event
        return None

    def _find_provider_event_for_char(self, char_id: str, target_status: CharacterStatus) -> Optional[Event]:
        effect_type_map = {
            CharacterStatus.ALIVE: ChoiceEffectType.SET_CHAR_ALIVE,
            CharacterStatus.DEAD: ChoiceEffectType.SET_CHAR_DEAD,
            CharacterStatus.MISSING: ChoiceEffectType.SET_CHAR_MISSING,
            CharacterStatus.INSANE: ChoiceEffectType.SET_CHAR_INSANE,
        }
        target_effect = effect_type_map.get(target_status)
        if not target_effect:
            return None
        for event in reversed(self._sorted):
            for choice in event.choices:
                for effect in choice.effects:
                    if effect.effect_type == target_effect and effect.target == char_id:
                        return event
        return None

    def _find_provider_event_for_location(self, location: str) -> Optional[Event]:
        target_flag = f"去过_{location}"
        for event in reversed(self._sorted):
            for choice in event.choices:
                for effect in choice.effects:
                    if effect.effect_type == ChoiceEffectType.SET_FLAG and effect.target == target_flag:
                        return event
            if location in event.title or location in event.description:
                return event
        return None

    def _infer_char_status_from_dialogue(self, text: str, char_id: str) -> Optional[CharacterStatus]:
        lower = text.lower()
        char_kw = char_id.split("_")
        char_match = any(kw in lower for kw in char_kw if len(kw) > 1)
        if not char_match:
            return None
        if any(w in lower for w in ["死了", "杀死", "尸体", "牺牲", "去世", "不在了"]):
            return CharacterStatus.DEAD
        if any(w in lower for w in ["失踪", "不见了", "找不到"]):
            return CharacterStatus.MISSING
        if any(w in lower for w in ["疯了", "精神病", "不正常", "恍惚"]):
            return CharacterStatus.INSANE
        if any(w in lower for w in ["活着", "还在", "见到", "和"]):
            return CharacterStatus.ALIVE
        return None

    def _status_label(self, status: CharacterStatus) -> str:
        return {
            CharacterStatus.ALIVE: "存活",
            CharacterStatus.DEAD: "死亡",
            CharacterStatus.MISSING: "失踪",
            CharacterStatus.INSANE: "发疯",
        }.get(status, "未知")

    def _build_suggestion_for_missing(
        self, kind: str, ref: str, dialogue: str,
        provider: Optional[Event], ch_num: Optional[int],
    ) -> str:
        if provider:
            return (
                f"台词「{dialogue[:30]}...」涉及{kind}「{ref}」。"
                f"可在第{provider.chapter}章「{provider.title}」中通过选择让玩家获取该{kind}；"
                f"如果玩家不需要拿到也能说出，请修改台词。"
            )
        else:
            return (
                f"台词「{dialogue[:30]}...」涉及{kind}「{ref}」，"
                f"但目前剧本中没有任何事件能让玩家获得该{kind}。"
                f"请在第{ch_num or '合适'}章前添加相关铺垫事件，或修改台词。"
            )


class CausalityValidator:
    def __init__(self, events: List[Event], endings: List[Ending]):
        self.events = events
        self.endings = endings
        self._sorted_events = sorted(events, key=lambda e: (e.chapter, e.order))
        self._dialogue_analyzer = DialogueAnalyzer(events)

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
        base_initial = initial_state or GameState()
        state = base_initial.clone()
        timeline: List[TimelineStep] = []
        contradictions: List[Contradiction] = []

        for step_idx, event in enumerate(self._sorted_events):
            step = TimelineStep(
                event=event,
                step_index=step_idx,
                state_before=state.clone(),
            )

            broken = [c for c in event.conditions if not c.evaluate(state)]
            met = [c for c in event.conditions if c.evaluate(state)]
            step.broken_event_conditions = broken
            step.met_event_conditions = met

            choice_scores = self._score_all_choices(event, ending, state)
            step.all_choice_scores = choice_scores

            if broken:
                step.event_condition_status = LinkStatus.SKIPPED
                step.was_triggered = False
                step.state_after = state.clone()
                step.note = "（未触发，前置条件不满足）"
                for cond in broken:
                    contradictions.append(Contradiction(
                        severity="error",
                        category="事件条件冲突",
                        message=f"第{event.chapter}章事件「{event.title}」未触发，缺失前置条件：{cond.human_readable()}",
                        suggestion=(
                            f"检查第{event.chapter}章前是否有提供「{cond.human_readable()}」的选项；"
                            f"若该事件无需该前置也能触发，请在事件录入中删除此条件。"
                        ),
                        related_event_id=event.id,
                        related_condition_id=cond.id,
                        related_chapter=event.chapter,
                    ))
                timeline.append(step)
                continue

            step.event_condition_status = LinkStatus.VALID
            best_choice = self._pick_best_choice(choice_scores)
            step.selected_choice = best_choice

            if best_choice is not None:
                for effect in best_choice.effects:
                    effect.apply(state)
                    step.choice_effects_applied.append(effect)
                if self._is_choice_optimal(best_choice, choice_scores):
                    step.note = "（最优路径）"
                else:
                    step.note = "（可用但非最优选择）"
                    step.event_condition_status = LinkStatus.WARN
            else:
                if event.choices:
                    first = event.choices[0]
                    for effect in first.effects:
                        effect.apply(state)
                        step.choice_effects_applied.append(effect)
                    step.selected_choice = first
                    step.note = "（无贴合结局的选项，使用默认）"
                    step.event_condition_status = LinkStatus.WARN
                else:
                    step.note = "（无玩家选择）"

            step.state_after = state.clone()
            timeline.append(step)

        met_conditions: List[Condition] = []
        missing_conditions: List[Condition] = []
        for cond in ending.conditions:
            if cond.evaluate(state):
                met_conditions.append(cond)
            else:
                missing_conditions.append(cond)
                contradictions.append(self._analyze_missing_condition(
                    cond, state, ending, timeline
                ))

        for dialogue in ending.dialogue_hints:
            issues = self._dialogue_analyzer.analyze_dialogue(dialogue, ending, state)
            contradictions.extend(issues)

        overall = LinkStatus.VALID
        if missing_conditions:
            overall = LinkStatus.BROKEN
        elif any(s.event_condition_status in (LinkStatus.WARN, LinkStatus.SKIPPED) for s in timeline):
            overall = LinkStatus.WARN

        summary_lines = []
        total_events = len(timeline)
        triggered = sum(1 for s in timeline if s.was_triggered)
        skipped = total_events - triggered
        if overall == LinkStatus.VALID:
            summary_lines.append(f"✅ 结局「{ending.title}」因果链完整，所有条件均满足。")
        elif overall == LinkStatus.WARN:
            summary_lines.append(f"⚠ 结局「{ending.title}」可达成，但存在警告（{skipped} 个事件未触发 / 使用非最优选择）。")
        else:
            summary_lines.append(f"❌ 结局「{ending.title}」因果链断裂，共 {len(missing_conditions)} 个条件未满足。")
        summary_lines.append(f"时间线共 {total_events} 个事件：触发 {triggered} 个 / 跳过 {skipped} 个。")
        if contradictions:
            summary_lines.append(f"共检测到 {len(contradictions)} 处问题。")

        return ValidationResult(
            overall_status=overall,
            timeline=timeline,
            ending_met_conditions=met_conditions,
            ending_missing_conditions=missing_conditions,
            contradictions=contradictions,
            final_state=state.clone(),
            initial_state_used=base_initial.clone(),
            summary="\n".join(summary_lines),
        )

    def _score_all_choices(
        self, event: Event, ending: Ending, current_state: GameState
    ) -> List[ChoiceScore]:
        results: List[ChoiceScore] = []
        for choice in event.choices:
            temp_state = current_state.clone()
            for effect in choice.effects:
                effect.apply(temp_state)
            score = 0
            met = []
            progress = []
            for cond in ending.conditions:
                before = cond.evaluate(current_state)
                after = cond.evaluate(temp_state)
                if after and not before:
                    score += 5
                    met.append(cond.human_readable())
                elif after:
                    score += 3
                    met.append(cond.human_readable() + "(已满足)")
                elif self._condition_progressing(cond, current_state, temp_state):
                    score += 1
                    progress.append(cond.human_readable())
            for cond in event.conditions:
                if cond.evaluate(temp_state):
                    score += 1
            results.append(ChoiceScore(
                choice=choice,
                score=score,
                met_conditions=met,
                progress_conditions=progress,
            ))
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _pick_best_choice(self, scores: List[ChoiceScore]) -> Optional[Choice]:
        if not scores:
            return None
        max_score = max(s.score for s in scores)
        top = [s for s in scores if s.score == max_score]
        return top[0].choice if top else None

    def _is_choice_optimal(self, choice: Choice, scores: List[ChoiceScore]) -> bool:
        if not scores:
            return True
        max_score = max(s.score for s in scores)
        for s in scores:
            if s.choice.id == choice.id and s.score >= max_score:
                return True
        return False

    def _find_source_event_for_condition(self, condition: Condition) -> Optional[Event]:
        for event in reversed(self._sorted_events):
            for choice in event.choices:
                temp_state = GameState()
                for effect in choice.effects:
                    effect.apply(temp_state)
                if condition.evaluate(temp_state):
                    return event
        return None

    def _condition_progressing(
        self, cond: Condition, before: GameState, after: GameState
    ) -> bool:
        if cond.condition_type in (
            ConditionType.HAS_CLUE, ConditionType.CHAR_DEAD,
            ConditionType.CHAR_MISSING, ConditionType.CHAR_INSANE,
            ConditionType.FLAG_TRUE,
        ):
            return (not cond.evaluate(before)) and (cond.evaluate(after))
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
            alt_steps = self._find_earlier_opportunity(cond, timeline)
            if alt_steps:
                suggestion_parts.append(
                    f"也可在第{alt_steps[0].event.chapter}章「{alt_steps[0].event.title}」补一个选项提供该条件。"
                )
        else:
            suggestion_parts.append(
                "目前所有事件中均无选项可以产生该条件，请考虑在合适章节增加铺垫事件。"
            )

        if cond.condition_type == ConditionType.HAS_CLUE:
            for dialogue in ending.dialogue_hints:
                if cond.target in dialogue:
                    suggestion_parts.append(
                        f"注意：结局台词「{dialogue[:40]}...」也依赖该线索，建议一起检查。"
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
            related_chapter=source_event.chapter if source_event else None,
        )

    def _find_earlier_opportunity(
        self, cond: Condition, timeline: List[TimelineStep]
    ) -> List[TimelineStep]:
        candidates = []
        for step in timeline:
            if not step.was_triggered:
                continue
            temp_state = step.state_before.clone()
            for choice in step.event.choices:
                test_state = temp_state.clone()
                for effect in choice.effects:
                    effect.apply(test_state)
                if cond.evaluate(test_state):
                    candidates.append(step)
                    break
        return candidates

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
        final_state = result.final_state or GameState()
        all_issues: List[Contradiction] = []
        for dialogue in ending.dialogue_hints:
            issues = self._dialogue_analyzer.analyze_dialogue(dialogue, ending, final_state)
            all_issues.extend(issues)
        return all_issues

    def get_known_entities(self) -> dict:
        return {
            "clues": sorted(self._dialogue_analyzer._all_clue_ids),
            "characters": sorted(self._dialogue_analyzer._all_char_ids),
            "locations": sorted(DialogueAnalyzer.LOCATION_KEYWORDS),
        }
