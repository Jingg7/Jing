from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentEvent:
    pass


@dataclass(frozen=True)
class AssistantStarted(AgentEvent):
    pass


@dataclass(frozen=True)
class TextDelta(AgentEvent):
    text: str


@dataclass(frozen=True)
class AssistantCompleted(AgentEvent):
    content: str


@dataclass(frozen=True)
class ToolCallStarted(AgentEvent):
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallFinished(AgentEvent):
    name: str
    arguments: dict[str, Any]
    output: str


@dataclass(frozen=True)
class TurnCompleted(AgentEvent):
    content: str
