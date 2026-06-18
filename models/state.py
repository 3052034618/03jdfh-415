from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import uuid


class CharacterStatus(Enum):
    ALIVE = "alive"
    DEAD = "dead"
    MISSING = "missing"
    INSANE = "insane"

    @classmethod
    def from_str(cls, s: str) -> "CharacterStatus":
        for status in cls:
            if status.value == s:
                return status
        return cls.ALIVE

    def __str__(self) -> str:
        return self.value


@dataclass
class GameState:
    fear_level: int = 0
    clues: Dict[str, bool] = field(default_factory=dict)
    characters: Dict[str, CharacterStatus] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)

    def clone(self) -> "GameState":
        return GameState(
            fear_level=self.fear_level,
            clues=dict(self.clues),
            characters=dict(self.characters),
            flags=dict(self.flags),
        )

    def to_dict(self) -> dict:
        return {
            "fear_level": self.fear_level,
            "clues": self.clues,
            "characters": {k: v.value for k, v in self.characters.items()},
            "flags": self.flags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        return cls(
            fear_level=d.get("fear_level", 0),
            clues=d.get("clues", {}),
            characters={
                k: CharacterStatus.from_str(v)
                for k, v in d.get("characters", {}).items()
            },
            flags=d.get("flags", {}),
        )

    def has_clue(self, clue_id: str) -> bool:
        return self.clues.get(clue_id, False)

    def add_clue(self, clue_id: str, value: bool = True):
        self.clues[clue_id] = value

    def get_character_status(self, char_id: str) -> CharacterStatus:
        return self.characters.get(char_id, CharacterStatus.ALIVE)

    def set_character_status(self, char_id: str, status: CharacterStatus):
        self.characters[char_id] = status

    def get_flag(self, flag_id: str) -> bool:
        return self.flags.get(flag_id, False)

    def set_flag(self, flag_id: str, value: bool = True):
        self.flags[flag_id] = value

    def add_fear(self, amount: int):
        self.fear_level = max(0, min(100, self.fear_level + amount))
