from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
import uuid


@dataclass
class Message:
    from_agent: str
    to_agent: str
    type: Literal["task", "report", "escalate", "inform"]
    content: dict[str, Any]
    priority: int = 5  # 1(低) ~ 10(高)
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def __str__(self):
        return f"[{self.id}] {self.from_agent} → {self.to_agent} ({self.type})"
