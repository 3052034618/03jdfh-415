from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Set
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
class FullBranchResult:
    choice: Choice
    final_state: GameState
    timeline_snippet: List["TimelineStep"]
    triggered_events: List[Event]
    skipped_events: List[Event]
    fear_final: int = 0
    clues_final: List[str] = field(default_factory=list)
    characters_final: Dict[str, CharacterStatus] = field(default_factory=dict)
    flags_final: List[str] = field(default_factory=list)
    closest_ending_id: Optional[str] = None
    closest_ending_name: str = ""
    closest_ending_score: int = 0
    ending_scores: Dict[str, int] = field(default_factory=dict)
    dialogue_issues: List["Contradiction"] = field(default_factory=list)


@dataclass
class BranchPreview:
    choice: Choice
    state_after: GameState
    fear_diff: int = 0
    clues_added: List[str] = field(default_factory=list)
    clues_removed: List[str] = field(default_factory=list)
    chars_changed: Dict[str, Tuple[CharacterStatus, CharacterStatus]] = field(default_factory=dict)
    flags_set: List[str] = field(default_factory=list)
    flags_unset: List[str] = field(default_factory=list)
    ending_closeness: Dict[str, int] = field(default_factory=dict)
    full_branch: Optional[FullBranchResult] = None


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
    all_branch_previews: List[BranchPreview] = field(default_factory=list)
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
    nav_target_type: Optional[str] = None
    nav_target_id: Optional[str] = None
    occurrence_count: int = 1
    merged_dialogues: List[str] = field(default_factory=list)
    dedup_key: str = ""

    def compute_dedup_key(self) -> str:
        if self.dedup_key:
            return self.dedup_key
        if self.related_condition_id:
            return "cond::{0}::{1}".format(self.related_ending_id or "", self.related_condition_id)
        if self.category == "事件条件冲突":
            return "event::{0}::{1}".format(self.related_event_id or "", self.message[:40])
        base = "{0}::{1}".format(self.category, self.message[:60])
        if self.related_ending_id:
            base += "::{0}".format(self.related_ending_id)
        return base


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

    def __init__(self, events: List[Event], initial_state: Optional[GameState] = None):
        self.events = events
        self._initial_state = initial_state or GameState()
        self._sorted = sorted(events, key=lambda e: (e.chapter, e.order))
        self._all_clue_ids = self._extract_all_clue_ids()
        self._all_char_ids = self._extract_all_char_ids()

    def _extract_all_clue_ids(self) -> set:
        clues = set()
        if self._initial_state:
            for k, v in self._initial_state.clues.items():
                if v:
                    clues.add(k)
        for event in self._sorted:
            for choice in event.choices:
                for effect in choice.effects:
                    if effect.effect_type in (ChoiceEffectType.SET_CLUE, ChoiceEffectType.UNSET_CLUE):
                        if effect.target:
                            clues.add(effect.target)
        return clues

    def _extract_all_char_ids(self) -> set:
        chars = set()
        if self._initial_state:
            chars.update(self._initial_state.characters.keys())
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

    def analyze_dialogue(
        self, dialogue: str, ending: Ending, final_state: GameState,
        visited_locations: Optional[Set[str]] = None,
        obtained_clues: Optional[Set[str]] = None,
        experienced_events: Optional[List[Event]] = None,
    ) -> List[Contradiction]:
        issues: List[Contradiction] = []
        refs = self.extract_references(dialogue)
        visited_locs = visited_locations or set()
        obtained = obtained_clues or set()
        exp_events = experienced_events or []

        for ref in refs:
            if ref.reference_type == "clue":
                if ref.reference not in obtained:
                    provider = self._find_provider_event_for_clue(ref.reference)
                    ch_num = provider.chapter if provider else None
                    suggestion = self._build_suggestion_for_missing(
                        "线索", ref.reference, dialogue, provider, ch_num
                    )
                    dedup_key = "clue::{0}::{1}".format(ref.reference, ending.id)
                    issues.append(Contradiction(
                        severity="error" if ref.reference in self._all_clue_ids else "warning",
                        category="台词线索缺失",
                        message="结局台词提到了线索「{0}」，但玩家未获取该线索。".format(ref.reference),
                        suggestion=suggestion,
                        related_ending_id=ending.id,
                        related_chapter=ch_num,
                        related_event_id=provider.id if provider else None,
                        dialogue_ref=dialogue,
                        nav_target_type="event",
                        nav_target_id=provider.id if provider else ending.id,
                        occurrence_count=1,
                        merged_dialogues=[dialogue],
                        dedup_key=dedup_key,
                    ))
            elif ref.reference_type == "character":
                expected_status = self._infer_char_status_from_dialogue(dialogue, ref.reference)
                if expected_status is None:
                    continue
                actual_status = final_state.get_character_status(ref.reference)
                if actual_status is None:
                    if self._initial_state and ref.reference in self._initial_state.characters:
                        actual_status = self._initial_state.characters[ref.reference]
                if expected_status and actual_status and expected_status != actual_status:
                    provider = self._find_provider_event_for_char(ref.reference, expected_status)
                    ch_num = provider.chapter if provider else None
                    status_label = self._status_label(expected_status)
                    actual_label = self._status_label(actual_status)
                    dedup_key = "char::{0}::{1}::{2}".format(ref.reference, expected_status.value, ending.id)
                    issues.append(Contradiction(
                        severity="error",
                        category="台词角色矛盾",
                        message="结局台词暗示角色「{0}」应为{1}，但实际状态是{2}。".format(
                            ref.reference, status_label, actual_label
                        ),
                        suggestion="要么调整第{0}章前的事件使「{1}」{2}，要么修改台词使其符合角色{3}的设定。".format(
                            ch_num or "?", ref.reference, status_label, actual_label
                        ),
                        related_ending_id=ending.id,
                        related_chapter=ch_num,
                        related_event_id=provider.id if provider else None,
                        dialogue_ref=dialogue,
                        nav_target_type="event",
                        nav_target_id=provider.id if provider else ending.id,
                        occurrence_count=1,
                        merged_dialogues=[dialogue],
                        dedup_key=dedup_key,
                    ))
            elif ref.reference_type == "location":
                if not self._is_location_provided_current_path(ref.reference, visited_locs, obtained, exp_events):
                    provider = self._find_provider_event_for_location(ref.reference)
                    ch_num = provider.chapter if provider else None
                    dedup_key = "loc::{0}::{1}".format(ref.reference, ending.id)
                    issues.append(Contradiction(
                        severity="warning",
                        category="台词地点缺失",
                        message="结局台词提到了地点「{0}」，但玩家似乎没有铺垫到达过那里。".format(ref.reference),
                        suggestion="建议在第{0}章增加一个让玩家探索「{1}」的事件，或在相关事件选项中添加进入该地点的效果。".format(
                            ch_num or "合适", ref.reference
                        ),
                        related_ending_id=ending.id,
                        related_chapter=ch_num,
                        related_event_id=provider.id if provider else None,
                        dialogue_ref=dialogue,
                        nav_target_type="event",
                        nav_target_id=provider.id if provider else ending.id,
                        occurrence_count=1,
                        merged_dialogues=[dialogue],
                        dedup_key=dedup_key,
                    ))

        return issues

    def _is_location_provided_current_path(
        self, location: str, visited_locations: Set[str], obtained_clues: Set[str],
        experienced_events: Optional[List[Event]] = None,
    ) -> bool:
        visited_flag = "去过_{0}".format(location)
        if visited_flag in visited_locations:
            return True
        for clue in obtained_clues:
            if location in clue or clue in location:
                return True
        if experienced_events:
            for ev in experienced_events:
                if location in ev.title or location in ev.description:
                    return True
                for choice in ev.choices:
                    for effect in choice.effects:
                        if effect.effect_type == ChoiceEffectType.SET_CLUE and (
                            location in effect.target or effect.target in location
                        ):
                            return True
        return False

    def _is_location_provided(self, location: str, final_state: GameState) -> bool:
        visited_flag = "去过_{0}".format(location)
        if final_state.get_flag(visited_flag):
            return True
        if self._initial_state and self._initial_state.get_flag(visited_flag):
            return True
        for clue_id, val in final_state.clues.items():
            if val and location in clue_id:
                return True
        if self._initial_state:
            for clue_id, val in self._initial_state.clues.items():
                if val and location in clue_id:
                    return True
        for event in self._sorted:
            if location in event.title or location in event.description:
                return True
        for event in self._sorted:
            for choice in event.choices:
                for effect in choice.effects:
                    if effect.effect_type == ChoiceEffectType.SET_FLAG:
                        if location in effect.target:
                            return True
                    if effect.effect_type == ChoiceEffectType.SET_CLUE:
                        if location in effect.target:
                            return True
        return False

    def extract_references(self, text: str) -> List["DialogueReference"]:
        refs: List["DialogueReference"] = []
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
        target_flag = "去过_{0}".format(location)
        for event in reversed(self._sorted):
            for choice in event.choices:
                for effect in choice.effects:
                    if effect.effect_type == ChoiceEffectType.SET_FLAG and effect.target == target_flag:
                        return event
                    if effect.effect_type == ChoiceEffectType.SET_CLUE and location in effect.target:
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
                "台词涉及{0}「{1}」。"
                "可在第{2}章「{3}」中通过选择让玩家获取该{0}；"
                "如果玩家不需要拿到也能说出，请修改台词。".format(
                    kind, ref, provider.chapter, provider.title
                )
            )
        else:
            return (
                "台词涉及{0}「{1}」，"
                "但目前剧本中没有任何事件能让玩家获得该{0}。"
                "请在第{2}章前添加相关铺垫事件，或修改台词。".format(
                    kind, ref, ch_num or "合适"
                )
            )


@dataclass
class DialogueReference:
    source_type: str
    source_id: str
    reference: str
    reference_type: str
    was_provided: bool
    source_chapter: Optional[int] = None
    provider_event: Optional[str] = None


class CausalityValidator:
    def __init__(self, events: List[Event], endings: List[Ending], initial_state: Optional[GameState] = None):
        self.events = events
        self.endings = endings
        self._initial_state = initial_state or GameState()
        self._sorted_events = sorted(events, key=lambda e: (e.chapter, e.order))
        self._dialogue_analyzer = DialogueAnalyzer(events, self._initial_state)

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

    def _simulate_from_choice(
        self, start_step_index: int, choice: Choice,
        start_state: GameState, target_ending: Optional[Ending] = None,
    ) -> FullBranchResult:
        state = start_state.clone()
        for effect in choice.effects:
            effect.apply(state)

        timeline_snippet: List[TimelineStep] = []
        triggered = []
        skipped = []

        visited_locations: Set[str] = set()
        obtained_clues: Set[str] = set()
        experienced_events: List[Event] = []
        for k, v in self._initial_state.clues.items():
            if v:
                obtained_clues.add(k)
        for k, v in state.clues.items():
            if v:
                obtained_clues.add(k)

        for effect in choice.effects:
            if effect.effect_type == ChoiceEffectType.SET_FLAG and effect.target.startswith("去过_"):
                visited_locations.add(effect.target)
            if effect.effect_type == ChoiceEffectType.SET_CLUE and effect.value:
                obtained_clues.add(effect.target)

        for step_idx in range(start_step_index, len(self._sorted_events)):
            event = self._sorted_events[step_idx]
            step = TimelineStep(
                event=event,
                step_index=step_idx,
                state_before=state.clone(),
            )

            broken = [c for c in event.conditions if not c.evaluate(state)]
            met = [c for c in event.conditions if c.evaluate(state)]
            step.broken_event_conditions = broken
            step.met_event_conditions = met

            if broken:
                step.event_condition_status = LinkStatus.SKIPPED
                step.was_triggered = False
                step.state_after = state.clone()
                skipped.append(event)
                timeline_snippet.append(step)
                continue

            step.event_condition_status = LinkStatus.VALID
            step.was_triggered = True
            triggered.append(event)
            experienced_events.append(event)

            ending_for_pick = target_ending or self.endings[0] if self.endings else None
            if ending_for_pick:
                choice_scores = self._score_all_choices(event, ending_for_pick, state)
                best_choice = self._pick_best_choice(choice_scores)
            else:
                best_choice = event.choices[0] if event.choices else None

            step.selected_choice = best_choice
            if best_choice is not None:
                for effect in best_choice.effects:
                    effect.apply(state)
                    step.choice_effects_applied.append(effect)
                    if effect.effect_type == ChoiceEffectType.SET_FLAG and effect.target.startswith("去过_"):
                        visited_locations.add(effect.target)
                    if effect.effect_type == ChoiceEffectType.SET_CLUE and effect.value:
                        obtained_clues.add(effect.target)

            step.state_after = state.clone()
            timeline_snippet.append(step)

        final_clues = [k for k, v in state.clues.items() if v]
        final_flags = [k for k, v in state.flags.items() if v]

        ending_scores: Dict[str, int] = {}
        best_score = -1
        best_ending_id = None
        best_ending_name = ""
        for ending in self.endings:
            met = sum(1 for cond in ending.conditions if cond.evaluate(state))
            total = len(ending.conditions)
            score = met * 100 // max(total, 1)
            ending_scores[ending.id] = score
            if score > best_score:
                best_score = score
                best_ending_id = ending.id
                best_ending_name = ending.title

        dialogue_issues: List[Contradiction] = []
        if target_ending:
            for dialogue in target_ending.dialogue_hints:
                issues = self._dialogue_analyzer.analyze_dialogue(
                    dialogue, target_ending, state,
                    visited_locations, obtained_clues, experienced_events,
                )
                dialogue_issues.extend(issues)
            dialogue_issues = CausalityValidator.merge_contradictions(dialogue_issues)

        return FullBranchResult(
            choice=choice,
            final_state=state.clone(),
            timeline_snippet=timeline_snippet,
            triggered_events=triggered,
            skipped_events=skipped,
            fear_final=state.fear_level,
            clues_final=final_clues,
            characters_final=dict(state.characters),
            flags_final=final_flags,
            closest_ending_id=best_ending_id,
            closest_ending_name=best_ending_name,
            closest_ending_score=best_score,
            ending_scores=ending_scores,
            dialogue_issues=dialogue_issues,
        )

    def _compute_branch_preview(
        self, event: Event, choice: Choice, current_state: GameState, endings: List[Ending],
        step_index: int = 0, target_ending: Optional[Ending] = None,
    ) -> BranchPreview:
        temp_state = current_state.clone()
        for effect in choice.effects:
            effect.apply(temp_state)

        fear_diff = temp_state.fear_level - current_state.fear_level

        clues_added = [k for k, v in temp_state.clues.items() if v and (k not in current_state.clues or not current_state.clues[k])]
        clues_removed = [k for k, v in current_state.clues.items() if v and (k not in temp_state.clues or not temp_state.clues[k])]

        chars_changed = {}
        for cid, status in temp_state.characters.items():
            old = current_state.characters.get(cid)
            if old and old != status:
                chars_changed[cid] = (old, status)

        flags_set = [k for k, v in temp_state.flags.items() if v and (k not in current_state.flags or not current_state.flags[k])]
        flags_unset = [k for k, v in current_state.flags.items() if v and (k not in temp_state.flags or not temp_state.flags[k])]

        ending_closeness = {}
        for ending in endings:
            met = sum(1 for cond in ending.conditions if cond.evaluate(temp_state))
            ending_closeness[ending.id] = met

        full_branch = self._simulate_from_choice(
            step_index + 1, choice, current_state, target_ending,
        )

        return BranchPreview(
            choice=choice,
            state_after=temp_state,
            fear_diff=fear_diff,
            clues_added=clues_added,
            clues_removed=clues_removed,
            chars_changed=chars_changed,
            flags_set=flags_set,
            flags_unset=flags_unset,
            ending_closeness=ending_closeness,
            full_branch=full_branch,
        )

    def simulate_path_to_ending(
        self, ending: Ending, initial_state: Optional[GameState] = None
    ) -> ValidationResult:
        base_initial = initial_state or self._initial_state or GameState()
        state = base_initial.clone()
        timeline: List[TimelineStep] = []
        contradictions: List[Contradiction] = []

        visited_locations: Set[str] = set()
        obtained_clues: Set[str] = set()
        experienced_events: List[Event] = []
        for k, v in base_initial.clues.items():
            if v:
                obtained_clues.add(k)
        for k, v in base_initial.flags.items():
            if v and k.startswith("去过_"):
                visited_locations.add(k)

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

            branch_previews = []
            for choice in event.choices:
                bp = self._compute_branch_preview(
                    event, choice, state, self.endings, step_idx, ending,
                )
                branch_previews.append(bp)
            step.all_branch_previews = branch_previews

            if broken:
                step.event_condition_status = LinkStatus.SKIPPED
                step.was_triggered = False
                step.state_after = state.clone()
                step.note = "（未触发，前置条件不满足）"
                for cond in broken:
                    source_event = self._find_source_event_for_condition(cond)
                    nav_type = "event"
                    nav_id = source_event.id if source_event else event.id
                    dedup_key = "event_break::{0}::{1}".format(event.id, cond.id or cond.human_readable())
                    contradictions.append(Contradiction(
                        severity="error",
                        category="事件条件冲突",
                        message="第{0}章事件「{1}」未触发，缺失前置条件：{2}".format(
                            event.chapter, event.title, cond.human_readable()
                        ),
                        suggestion=(
                            "检查第{0}章前是否有提供「{1}」的选项；"
                            "若该事件无需该前置也能触发，请在事件录入中删除此条件。".format(
                                event.chapter, cond.human_readable()
                            )
                        ),
                        related_event_id=event.id,
                        related_condition_id=cond.id,
                        related_chapter=event.chapter,
                        nav_target_type=nav_type,
                        nav_target_id=nav_id,
                        dedup_key=dedup_key,
                    ))
                timeline.append(step)
                continue

            step.event_condition_status = LinkStatus.VALID
            best_choice = self._pick_best_choice(choice_scores)
            step.selected_choice = best_choice
            experienced_events.append(event)

            if best_choice is not None:
                for effect in best_choice.effects:
                    effect.apply(state)
                    step.choice_effects_applied.append(effect)
                    if effect.effect_type == ChoiceEffectType.SET_FLAG and effect.target.startswith("去过_"):
                        visited_locations.add(effect.target)
                    if effect.effect_type == ChoiceEffectType.SET_CLUE and effect.value:
                        obtained_clues.add(effect.target)
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
                        if effect.effect_type == ChoiceEffectType.SET_FLAG and effect.target.startswith("去过_"):
                            visited_locations.add(effect.target)
                        if effect.effect_type == ChoiceEffectType.SET_CLUE and effect.value:
                            obtained_clues.add(effect.target)
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

        dialogue_issues: List[Contradiction] = []
        for dialogue in ending.dialogue_hints:
            issues = self._dialogue_analyzer.analyze_dialogue(
                dialogue, ending, state, visited_locations, obtained_clues, experienced_events,
            )
            dialogue_issues.extend(issues)

        all_contradictions = CausalityValidator.merge_contradictions(contradictions + dialogue_issues)

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
            summary_lines.append("结局「{0}」因果链完整，所有条件均满足。".format(ending.title))
        elif overall == LinkStatus.WARN:
            summary_lines.append("结局「{0}」可达成，但存在警告（{1} 个事件未触发 / 使用非最优选择）。".format(ending.title, skipped))
        else:
            summary_lines.append("结局「{0}」因果链断裂，共 {1} 个条件未满足。".format(ending.title, len(missing_conditions)))
        summary_lines.append("时间线共 {0} 个事件：触发 {1} 个 / 跳过 {2} 个。".format(total_events, triggered, skipped))
        if contradictions:
            summary_lines.append("共检测到 {0} 处问题。".format(len(contradictions)))

        return ValidationResult(
            overall_status=overall,
            timeline=timeline,
            ending_met_conditions=met_conditions,
            ending_missing_conditions=missing_conditions,
            contradictions=all_contradictions,
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

    def _find_best_event_for_condition(
        self, condition: Condition, timeline: List[TimelineStep]
    ) -> Tuple[Optional[Event], Optional[int], Optional[Choice]]:
        best_event = None
        best_chapter = None
        best_choice = None

        source_event = self._find_source_event_for_condition(condition)
        if source_event:
            best_event = source_event
            best_chapter = source_event.chapter
            for ch in source_event.choices:
                tmp = GameState()
                for eff in ch.effects:
                    eff.apply(tmp)
                if condition.evaluate(tmp):
                    best_choice = ch
                    break

        for step in reversed(timeline):
            if not step.was_triggered:
                continue
            temp_state = step.state_before.clone()
            for choice in step.event.choices:
                test_state = temp_state.clone()
                for effect in choice.effects:
                    effect.apply(test_state)
                if condition.evaluate(test_state):
                    if best_event is None or step.event.chapter < best_chapter:
                        best_event = step.event
                        best_chapter = step.event.chapter
                        best_choice = choice

        return best_event, best_chapter, best_choice

    def _condition_progressing(
        self, cond: Condition, before: GameState, after: GameState
    ) -> bool:
        if cond.condition_type in (
            ConditionType.HAS_CLUE, ConditionType.CHAR_DEAD,
            ConditionType.MISSING, ConditionType.INSANE,
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
        best_event, best_chapter, best_choice = self._find_best_event_for_condition(cond, timeline)

        suggestion_parts = []
        if best_event:
            if best_choice:
                suggestion_parts.append(
                    "可在第{0}章「{1}」中选择「{2}」提供该条件。".format(
                        best_chapter, best_event.title, best_choice.text or "对应选项"
                    )
                )
            else:
                suggestion_parts.append(
                    "可在第{0}章「{1}」中通过选择提供该条件。".format(best_chapter, best_event.title)
                )
            alt_steps = self._find_earlier_opportunity(cond, timeline)
            if alt_steps:
                suggestion_parts.append(
                    "也可在第{0}章「{1}」补一个选项提供该条件。".format(
                        alt_steps[0].event.chapter, alt_steps[0].event.title
                    )
                )
        elif source_event:
            suggestion_parts.append(
                "可在第{0}章「{1}」中通过选择提供该条件。".format(source_event.chapter, source_event.title)
            )
        else:
            suggestion_parts.append(
                "目前所有事件中均无选项可以产生该条件，请考虑在合适章节增加铺垫事件。"
            )

        if cond.condition_type == ConditionType.HAS_CLUE:
            for dialogue in ending.dialogue_hints:
                if cond.target in dialogue:
                    suggestion_parts.append(
                        "注意：结局台词也依赖该线索，建议一起检查。"
                    )
                    break

        nav_type = "ending"
        nav_id = ending.id
        if best_event:
            nav_type = "event"
            nav_id = best_event.id
        elif source_event:
            nav_type = "event"
            nav_id = source_event.id

        dedup_key = "ending_cond::{0}::{1}".format(ending.id, cond.id or cond.human_readable())

        return Contradiction(
            severity="error" if cond.condition_type in (
                ConditionType.HAS_CLUE, ConditionType.CHAR_ALIVE,
                ConditionType.CHAR_DEAD, ConditionType.FLAG_TRUE,
            ) else "warning",
            category="结局条件缺失",
            message="结局「{0}」的必要条件未满足：{1}".format(ending.title, cond.human_readable()),
            suggestion=" ".join(suggestion_parts),
            related_ending_id=ending.id,
            related_condition_id=cond.id,
            related_event_id=best_event.id if best_event else (source_event.id if source_event else None),
            related_chapter=best_chapter if best_chapter else (source_event.chapter if source_event else None),
            nav_target_type=nav_type,
            nav_target_id=nav_id,
            dedup_key=dedup_key,
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

        visited_locations: Set[str] = set()
        obtained_clues: Set[str] = set()
        experienced_events: List[Event] = []

        if result.initial_state_used:
            for k, v in result.initial_state_used.clues.items():
                if v:
                    obtained_clues.add(k)
            for k, v in result.initial_state_used.flags.items():
                if v and k.startswith("去过_"):
                    visited_locations.add(k)

        for step in result.timeline:
            if not step.was_triggered:
                continue
            experienced_events.append(step.event)
            for effect in step.choice_effects_applied:
                if effect.effect_type == ChoiceEffectType.SET_FLAG and effect.target.startswith("去过_"):
                    visited_locations.add(effect.target)
                if effect.effect_type == ChoiceEffectType.SET_CLUE and effect.value:
                    obtained_clues.add(effect.target)

        for dialogue in ending.dialogue_hints:
            issues = self._dialogue_analyzer.analyze_dialogue(
                dialogue, ending, final_state,
                visited_locations, obtained_clues, experienced_events,
            )
            all_issues.extend(issues)

        return CausalityValidator.merge_contradictions(all_issues)

    @staticmethod
    def merge_contradictions(issues: List["Contradiction"]) -> List["Contradiction"]:
        merged: Dict[str, Contradiction] = {}
        for issue in issues:
            key = issue.compute_dedup_key()
            if key in merged:
                existing = merged[key]
                existing.occurrence_count += issue.occurrence_count
                for dlg in issue.merged_dialogues:
                    if dlg not in existing.merged_dialogues:
                        existing.merged_dialogues.append(dlg)
                if issue.dialogue_ref and issue.dialogue_ref not in existing.merged_dialogues:
                    existing.merged_dialogues.append(issue.dialogue_ref)
            else:
                merged[key] = issue
        return list(merged.values())

    def get_known_entities(self) -> dict:
        return {
            "clues": sorted(self._dialogue_analyzer._all_clue_ids),
            "characters": sorted(self._dialogue_analyzer._all_char_ids),
            "locations": sorted(DialogueAnalyzer.LOCATION_KEYWORDS),
        }
