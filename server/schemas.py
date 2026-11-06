"""Request models of the API. Responses are plain dicts built in `server.serialize`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MAX_DECISIONS = 200


class Decision(BaseModel):
    booking_id: str = Field(max_length=32)
    action: Literal["accept", "reject"]
    slot: str | None = Field(default=None, max_length=32)


class GameRequest(BaseModel):
    seed: int = Field(ge=1, le=10_000)
    decisions: list[Decision] = Field(default_factory=list, max_length=MAX_DECISIONS)
