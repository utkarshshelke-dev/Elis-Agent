"""
Module: services/iqc_client.py
Description: HTTP client for IQC Vertex AI Agent Engine.
             All Google OAuth2 auth, session creation, and streamQuery calls.
Author: IR Team
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Tuple

import google.auth
import google.auth.transport.requests
import requests as _requests

from config.settings import settings
from services.exceptions import AuthTokenError, IQCCallError

logger = logging.getLogger(__name__)

_SESSION_MARKER_RE  = re.compile(r"__SESSION__(\{.*?\})", re.DOTALL)
_STREAM_TIMEOUT     = 120
_SESSION_CREATE_TIMEOUT = 30


class IQCClient:

    def get_token(self) -> str:
        try:
            creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            creds.refresh(google.auth.transport.requests.Request())
            return creds.token
        except Exception as exc:
            raise AuthTokenError(f"Failed to obtain auth token: {exc}") from exc

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type":  "application/json",
        }

    def create_session(self, user_id: str) -> str:
        logger.info("create_session | START | user=%s", user_id)
        try:
            resp = _requests.post(
                settings.iqc_query_url,
                headers=self._auth_headers(),
                json={
                    "class_method": "create_session",
                    "input":        {"user_id": user_id},
                },
                timeout=_SESSION_CREATE_TIMEOUT,
            )
            resp.raise_for_status()
            session_id = str(
                (resp.json().get("output") or {}).get("id", "")
            )
            logger.info("create_session | OK | user=%s | sid=%s", user_id, session_id)
            return session_id
        except Exception as exc:
            logger.error("create_session | FAILED | user=%s | %s", user_id, exc)
            return ""

    def stream_query(
        self,
        message:        str,
        user_id:        str,
        iqc_session_id: str = "",
        context:        str = "",
    ) -> Tuple[str, str]:
        full_message = (
            f"{context}\n\nUser: {message}"
            if (context and not iqc_session_id)
            else message
        )
        payload: dict = {"input": {"message": full_message, "user_id": user_id}}
        if iqc_session_id:
            payload["input"]["session_id"] = iqc_session_id

        logger.info("stream_query | -> IQC | user=%s | iqc_sid=%s", user_id, iqc_session_id or "new")
        start = time.perf_counter()

        try:
            resp = _requests.post(
                settings.iqc_stream_url,
                headers=self._auth_headers(),
                json=payload,
                stream=True,
                timeout=_STREAM_TIMEOUT,
            )
            resp.raise_for_status()

            if not resp.text.strip():
                return "", iqc_session_id

            final_text   = ""
            captured_sid = iqc_session_id

            for raw_line in resp.text.strip().splitlines():
                line = (raw_line or "").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    for part in event.get("content", {}).get("parts", []):
                        fn_resp = part.get("function_response", {})
                        if fn_resp:
                            resp_data = fn_resp.get("response", {})
                            if isinstance(resp_data, str):
                                try:    resp_data = json.loads(resp_data)
                                except: resp_data = {}
                            sid = resp_data.get("session_id", "")
                            if sid and not captured_sid:
                                captured_sid = sid
                        t = part.get("text", "").strip()
                        if t:
                            final_text = t

                    if not final_text:
                        for key in ("text", "output", "message", "response", "answer"):
                            val = event.get(key)
                            if val and isinstance(val, str) and val.strip():
                                final_text = val.strip()
                                break
                except json.JSONDecodeError:
                    if line and not line.startswith("{"):
                        final_text = line

            if final_text:
                m = _SESSION_MARKER_RE.search(final_text)
                if m:
                    try:
                        sid = json.loads(m.group(1)).get("session_id", "")
                        if sid:
                            captured_sid = sid
                    except Exception:
                        pass

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "stream_query | DONE | user=%s | chars=%d | ms=%.1f",
                user_id, len(final_text), elapsed_ms,
            )
            return final_text, captured_sid

        except Exception as exc:
            logger.error("stream_query | FAILED | user=%s | %s", user_id, exc)
            return "", iqc_session_id

    @staticmethod
    def build_context(chat_history: list) -> str:
        if not chat_history:
            return ""
        lines = ["Previous conversation summary (for context only — do not repeat these questions):"]
        for turn in chat_history:
            u = (turn.get("user_message") if isinstance(turn, dict) else getattr(turn, "user_message", "")).strip()
            r = (turn.get("iqc_response")  if isinstance(turn, dict) else getattr(turn, "iqc_response",  "")).strip()
            if u: lines.append(f"  User: {u}")
            if r: lines.append(f"  Assistant: {r}")
        return "\n".join(lines)


iqc_client = IQCClient()
__all__ = ["IQCClient", "iqc_client"]