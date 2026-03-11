"""
Module: data/repository.py
Description: Repository — all PostgreSQL access for IR Domain Agent.
Author: IR Team
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import psycopg2
import psycopg2.extras

from config.settings import settings
from data.schemas import ChatTurn, IRSession
from services.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class IRSessionRepository:

    @staticmethod
    def _conn():
        try:
            return psycopg2.connect(**settings.db_dsn)
        except Exception as exc:
            raise DatabaseError(f"Cannot connect to database: {exc}") from exc

    @staticmethod
    def _parse_chat_history(raw) -> list:
        if raw is None:           return []
        if isinstance(raw, list): return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return []

    def load_active(self, user_id: str) -> Optional[IRSession]:
        start = time.perf_counter()
        try:
            c   = self._conn()
            cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM ir_active_sessions WHERE user_id = %s LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
            cur.close(); c.close()

            if not row:
                return None

            ch = self._parse_chat_history(row.get("chat_history"))
            return IRSession(
                user_id=        str(row["user_id"]),
                session_id=     str(row["session_id"]),
                iqc_session_id= str(row.get("iqc_session_id") or ""),
                status=         str(row["status"]),
                started_at=     float(row["started_at"].timestamp()),
                turn_number=    int(row["turn_number"]),
                chat_history=   [ChatTurn(**t) if isinstance(t, dict) else t for t in ch],
            )
        except DatabaseError:
            raise
        except Exception as exc:
            logger.error("load_active | FAILED | user=%s | %s", user_id, exc)
            return None

    def load_history(self, user_id: str) -> Optional[IRSession]:
        try:
            c   = self._conn()
            cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT session_id, user_id, iqc_session_id,
                       started_at, turns, final_status
                FROM   ir_session_history
                WHERE  user_id = %s
                ORDER  BY inserted_at DESC
                LIMIT  1
            """, (str(user_id),))
            row = cur.fetchone()
            cur.close(); c.close()

            if not row:
                return None

            ch = self._parse_chat_history(row.get("turns"))
            return IRSession(
                user_id=        str(row["user_id"]),
                session_id=     str(row["session_id"]),
                iqc_session_id= str(row.get("iqc_session_id") or ""),
                status=         "qualifying" if len(ch) > 0 else "open",
                started_at=     float(row["started_at"].timestamp()) if row.get("started_at") else time.time(),
                turn_number=    len(ch),
                chat_history=   [ChatTurn(**t) if isinstance(t, dict) else t for t in ch],
            )
        except DatabaseError:
            raise
        except Exception as exc:
            logger.error("load_history | FAILED | user=%s | %s", user_id, exc)
            return None

    def upsert_active(self, session: IRSession) -> None:
        db = session.to_db_dict()
        try:
            c   = self._conn()
            cur = c.cursor()
            cur.execute(
                "DELETE FROM ir_active_sessions WHERE user_id = %s",
                (db["user_id"],),
            )
            cur.execute("""
                INSERT INTO ir_active_sessions
                    (user_id, session_id, iqc_session_id, status,
                     started_at, turn_number, chat_history, updated_at)
                VALUES
                    (%s, %s, %s, %s, to_timestamp(%s), %s, %s::jsonb, NOW())
            """, (
                db["user_id"], db["session_id"], db["iqc_session_id"],
                db["status"],  db["started_at"], db["turn_number"],
                json.dumps(db["chat_history"]),
            ))
            c.commit(); cur.close(); c.close()
        except Exception as exc:
            logger.error("upsert_active | FAILED | user=%s | %s", session.user_id, exc)
            raise DatabaseError(f"upsert_active failed: {exc}") from exc

    def archive_and_delete(self, session: IRSession, end_reason: str) -> None:
        db = session.to_db_dict()
        try:
            c   = self._conn()
            cur = c.cursor()
            cur.execute("""
                INSERT INTO ir_session_history
                    (session_id, user_id, iqc_session_id, started_at,
                     ended_at, end_reason, turns, final_status, inserted_at)
                VALUES
                    (%s, %s, %s, to_timestamp(%s), NOW(), %s, %s::jsonb, %s, NOW())
            """, (
                db["session_id"], db["user_id"], db["iqc_session_id"],
                db["started_at"], end_reason,
                json.dumps(db["chat_history"]), db["status"],
            ))
            cur.execute(
                "DELETE FROM ir_active_sessions WHERE user_id = %s",
                (db["user_id"],),
            )
            c.commit(); cur.close(); c.close()
        except Exception as exc:
            logger.error("archive_and_delete | FAILED | user=%s | %s", session.user_id, exc)
            raise DatabaseError(f"archive_and_delete failed: {exc}") from exc


__all__ = ["IRSessionRepository"]