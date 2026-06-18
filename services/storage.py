import json
import os
from typing import List, Optional, Tuple

from models import Event, Ending, GameState
from models import Event, Ending


SCRIPT_FILENAME = "causality_script.json"


class ScriptStorage:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.getcwd()
        self.file_path = os.path.join(self.base_dir, SCRIPT_FILENAME)

    def save(
        self,
        events: List[Event],
        endings: List[Ending],
        initial_state: Optional[GameState] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        try:
            data = {
                "metadata": metadata or {"title": "未命名恐怖剧本", "version": 1},
                "initial_state": (initial_state or GameState()).to_dict(),
                "events": [e.to_dict() for e in events],
                "endings": [e.to_dict() for e in endings],
            }
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def load(self) -> Optional[Tuple[List[Event], List[Ending], GameState, dict]]:
        if not os.path.exists(self.file_path):
            return None
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            events = [Event.from_dict(e) for e in data.get("events", [])]
            endings = [Ending.from_dict(e) for e in data.get("endings", [])]
            initial_state = GameState.from_dict(data.get("initial_state", {}))
            metadata = data.get("metadata", {})
            return events, endings, initial_state, metadata
        except Exception:
            return None

    def export_to(self, path: str, events, endings, initial_state=None, metadata=None) -> bool:
        try:
            data = {
                "metadata": metadata or {"title": "未命名恐怖剧本", "version": 1},
                "initial_state": (initial_state or GameState()).to_dict(),
                "events": [e.to_dict() for e in events],
                "endings": [e.to_dict() for e in endings],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def import_from(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            events = [Event.from_dict(e) for e in data.get("events", [])]
            endings = [Ending.from_dict(e) for e in data.get("endings", [])]
            initial_state = GameState.from_dict(data.get("initial_state", {}))
            metadata = data.get("metadata", {})
            return events, endings, initial_state, metadata
        except Exception:
            return None
