"""
Module: data/schemas.py
Description: Pydantic models for IR Domain Agent session data.
Author: IR Team
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    turn:         int
    user_message: str
    iqc_response: str
    timestamp:    str


class IRSession(BaseModel):
    user_id:        str
    session_id:     str   = Field(default_factory=lambda: str(uuid.uuid4()))
    iqc_session_id: str   = ""
    status:         str   = "open"
    started_at:     float = Field(default_factory=time.time)
    turn_number:    int   = 0
    chat_history:   List[ChatTurn] = Field(default_factory=list)

    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        return (time.time() - self.started_at) > ttl_seconds

    def append_turn(self, user_message: str, iqc_response: str, timestamp: str) -> None:
        self.turn_number += 1
        self.chat_history.append(ChatTurn(
            turn=self.turn_number,
            user_message=user_message,
            iqc_response=iqc_response,
            timestamp=timestamp,
        ))

    @property
    def last_iqc_question(self) -> str:
        return self.chat_history[-1].iqc_response if self.chat_history else ""

    def to_db_dict(self) -> Dict[str, Any]:
        return {
            "user_id":        self.user_id,
            "session_id":     self.session_id,
            "iqc_session_id": self.iqc_session_id,
            "status":         self.status,
            "started_at":     self.started_at,
            "turn_number":    self.turn_number,
            "chat_history":   [t.model_dump() for t in self.chat_history],
        }


__all__ = ["ChatTurn", "IRSession"]