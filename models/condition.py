from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import uuid

from .state import CharacterStatus


class ConditionType(Enum):
    FEAR_GTE = "fear_gte"
    FEAR_LTE = "fear_lte"
    HAS_CLUE = "has_clue"
    NO_CLUE = "no_clue"
    CHAR_ALIVE = "char_alive"
    CHAR_DEAD = "char_dead"
    CHAR_MISSING = "char_missing"
    CHAR_INSANE = "char_insane"
    FLAG_TRUE = "flag_true"
    FLAG_FALSE = "flag_false"

    @classmethod
    def from_str(cls, s: str) -> "ConditionType":
        for t in cls:
            if t.value == s:
                return t
        return cls.HAS_CLUE

    def __str__(self) -> str:
        labels = {
            "fear_gte": "恐惧值 ≥",
            "fear_lte": "恐惧值 ≤",
            "has_clue": "获得线索",
            "no_clue": "未获得线索",
            "char_alive": "角色存活",
            "char_dead": "角色死亡",
            "char_missing": "角色失踪",
            "char_insane": "角色发疯",
            "flag_true": "标记为真",
            "flag_false": "标记为假",
        }
        return labels.get(self.value, self.value)


@dataclass
class Condition:
    condition_type: ConditionType
    target: str
    threshold: Optional[int] = None
    description: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "condition_type": self.condition_type.value,
            "target": self.target,
            "threshold": self.threshold,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Condition":
        return cls(
            id=d.get("id", uuid.uuid4().hex[:8]),
            condition_type=ConditionType.from_str(d.get("condition_type", "has_clue")),
            target=d.get("target", ""),
            threshold=d.get("threshold"),
            description=d.get("description", ""),
        )

    def human_readable(self) -> str:
        if self.description:
            return self.description
        ct = self.condition_type
        if ct in (ConditionType.FEAR_GTE, ConditionType.FEAR_LTE):
            return f"{str(ct)} {self.threshold}"
        if ct == ConditionType.HAS_CLUE:
            return f"已获得线索：{self.target}"
        if ct == ConditionType.NO_CLUE:
            return f"未获得线索：{self.target}"
        if ct == ConditionType.CHAR_ALIVE:
            return f"角色存活：{self.target}"
        if ct == ConditionType.CHAR_DEAD:
            return f"角色死亡：{self.target}"
        if ct == ConditionType.CHAR_MISSING:
            return f"角色失踪：{self.target}"
        if ct == ConditionType.CHAR_INSANE:
            return f"角色发疯：{self.target}"
        if ct == ConditionType.FLAG_TRUE:
            return f"标记为真：{self.target}"
        if ct == ConditionType.FLAG_FALSE:
            return f"标记为假：{self.target}"
        return f"{ct}: {self.target}"

    def evaluate(self, state) -> bool:
        from .state import GameState
        ct = self.condition_type
        if ct == ConditionType.FEAR_GTE:
            return state.fear_level >= (self.threshold or 0)
        if ct == ConditionType.FEAR_LTE:
            return state.fear_level <= (self.threshold or 100)
        if ct == ConditionType.HAS_CLUE:
            return state.has_clue(self.target)
        if ct == ConditionType.NO_CLUE:
            return not state.has_clue(self.target)
        if ct == ConditionType.CHAR_ALIVE:
            return state.get_character_status(self.target) == CharacterStatus.ALIVE
        if ct == ConditionType.CHAR_DEAD:
            return state.get_character_status(self.target) == CharacterStatus.DEAD
        if ct == ConditionType.CHAR_MISSING:
            return state.get_character_status(self.target) == CharacterStatus.MISSING
        if ct == ConditionType.CHAR_INSANE:
            return state.get_character_status(self.target) == CharacterStatus.INSANE
        if ct == ConditionType.FLAG_TRUE:
            return state.get_flag(self.target)
        if ct == ConditionType.FLAG_FALSE:
            return not state.get_flag(self.target)
        return False
