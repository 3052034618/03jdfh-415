from dataclasses import dataclass, field
from typing import List, Optional
import uuid

from .condition import Condition


@dataclass
class Ending:
    title: str
    description: str = ""
    conditions: List[Condition] = field(default_factory=list)
    dialogue_hints: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "conditions": [c.to_dict() for c in self.conditions],
            "dialogue_hints": self.dialogue_hints,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Ending":
        return cls(
            id=d.get("id", uuid.uuid4().hex[:8]),
            title=d.get("title", ""),
            description=d.get("description", ""),
            conditions=[Condition.from_dict(c) for c in d.get("conditions", [])],
            dialogue_hints=d.get("dialogue_hints", []),
        )
