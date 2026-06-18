from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import uuid

from .condition import Condition
from .state import CharacterStatus


class ChoiceEffectType(Enum):
    ADD_FEAR = "add_fear"
    SET_CLUE = "set_clue"
    UNSET_CLUE = "unset_clue"
    SET_CHAR_ALIVE = "set_char_alive"
    SET_CHAR_DEAD = "set_char_dead"
    SET_CHAR_MISSING = "set_char_missing"
    SET_CHAR_INSANE = "set_char_insane"
    SET_FLAG = "set_flag"
    UNSET_FLAG = "unset_flag"

    @classmethod
    def from_str(cls, s: str) -> "ChoiceEffectType":
        for t in cls:
            if t.value == s:
                return t
        return cls.ADD_FEAR

    def __str__(self) -> str:
        labels = {
            "add_fear": "增减恐惧值",
            "set_clue": "获得线索",
            "unset_clue": "失去线索",
            "set_char_alive": "角色→存活",
            "set_char_dead": "角色→死亡",
            "set_char_missing": "角色→失踪",
            "set_char_insane": "角色→发疯",
            "set_flag": "设置标记",
            "unset_flag": "清除标记",
        }
        return labels.get(self.value, self.value)


@dataclass
class ChoiceEffect:
    effect_type: ChoiceEffectType
    target: str
    value: Optional[int] = None
    description: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "effect_type": self.effect_type.value,
            "target": self.target,
            "value": self.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChoiceEffect":
        return cls(
            id=d.get("id", uuid.uuid4().hex[:8]),
            effect_type=ChoiceEffectType.from_str(d.get("effect_type", "add_fear")),
            target=d.get("target", ""),
            value=d.get("value"),
            description=d.get("description", ""),
        )

    def human_readable(self) -> str:
        if self.description:
            return self.description
        et = self.effect_type
        if et == ChoiceEffectType.ADD_FEAR:
            sign = "+" if (self.value or 0) >= 0 else ""
            return f"恐惧值 {sign}{self.value}"
        if et == ChoiceEffectType.SET_CLUE:
            return f"获得线索：{self.target}"
        if et == ChoiceEffectType.UNSET_CLUE:
            return f"失去线索：{self.target}"
        if et in (
            ChoiceEffectType.SET_CHAR_ALIVE,
            ChoiceEffectType.SET_CHAR_DEAD,
            ChoiceEffectType.SET_CHAR_MISSING,
            ChoiceEffectType.SET_CHAR_INSANE,
        ):
            return f"{str(et)}：{self.target}"
        if et == ChoiceEffectType.SET_FLAG:
            return f"设置标记：{self.target}"
        if et == ChoiceEffectType.UNSET_FLAG:
            return f"清除标记：{self.target}"
        return f"{et}: {self.target}"

    def apply(self, state):
        from .state import GameState
        et = self.effect_type
        if et == ChoiceEffectType.ADD_FEAR:
            state.add_fear(self.value or 0)
        elif et == ChoiceEffectType.SET_CLUE:
            state.add_clue(self.target, True)
        elif et == ChoiceEffectType.UNSET_CLUE:
            state.add_clue(self.target, False)
        elif et == ChoiceEffectType.SET_CHAR_ALIVE:
            state.set_character_status(self.target, CharacterStatus.ALIVE)
        elif et == ChoiceEffectType.SET_CHAR_DEAD:
            state.set_character_status(self.target, CharacterStatus.DEAD)
        elif et == ChoiceEffectType.SET_CHAR_MISSING:
            state.set_character_status(self.target, CharacterStatus.MISSING)
        elif et == ChoiceEffectType.SET_CHAR_INSANE:
            state.set_character_status(self.target, CharacterStatus.INSANE)
        elif et == ChoiceEffectType.SET_FLAG:
            state.set_flag(self.target, True)
        elif et == ChoiceEffectType.UNSET_FLAG:
            state.set_flag(self.target, False)


@dataclass
class Choice:
    text: str
    effects: List[ChoiceEffect] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "effects": [e.to_dict() for e in self.effects],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Choice":
        return cls(
            id=d.get("id", uuid.uuid4().hex[:8]),
            text=d.get("text", ""),
            effects=[ChoiceEffect.from_dict(e) for e in d.get("effects", [])],
        )


@dataclass
class Event:
    title: str
    chapter: int
    description: str = ""
    conditions: List[Condition] = field(default_factory=list)
    choices: List[Choice] = field(default_factory=list)
    order: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "chapter": self.chapter,
            "description": self.description,
            "order": self.order,
            "conditions": [c.to_dict() for c in self.conditions],
            "choices": [c.to_dict() for c in self.choices],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            id=d.get("id", uuid.uuid4().hex[:8]),
            title=d.get("title", ""),
            chapter=d.get("chapter", 1),
            description=d.get("description", ""),
            order=d.get("order", 0),
            conditions=[Condition.from_dict(c) for c in d.get("conditions", [])],
            choices=[Choice.from_dict(c) for c in d.get("choices", [])],
        )

    def check_conditions(self, state) -> bool:
        return all(c.evaluate(state) for c in self.conditions)
