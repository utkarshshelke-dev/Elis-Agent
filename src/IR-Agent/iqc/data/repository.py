"""
Module: data/repository.py
Description: All PostgreSQL access for IQC Agent. No SQL outside this file.
Author: IQC Team
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from config.settings import settings
from data.schemas import CRITERIA, JSONB_KEYS, is_empty

logger = logging.getLogger(__name__)


class IQCRepository:

    @staticmethod
    def _conn():
        return psycopg2.connect(**settings.db_dsn)

    # ── READ ──────────────────────────────────────────────────────────────────

    def get_basic_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch id, first_name, last_name, company, primary_category."""
        try:
            c   = self._conn()
            cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT id, first_name, last_name, company, primary_category
                FROM basic_profiles WHERE id = %s LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
            cur.close(); c.close()
            return dict(row) if row else None
        except Exception as exc:
            logger.error("get_basic_profile | FAILED | user=%s | %s", user_id, exc)
            return None

    def get_investor_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Merge investor_profile from impact_profiles_v2 with
        investor_data / goals / seeking from intelligence_data.
        Returns merged dict — empty dict if nothing found.
        """
        profile: Dict[str, Any] = {}
        try:
            c   = self._conn()
            cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute(
                "SELECT investor_profile FROM impact_profiles_v2 WHERE id = %s LIMIT 1",
                (user_id,),
            )
            ip_row = cur.fetchone()
            if ip_row and ip_row.get("investor_profile"):
                ip = ip_row["investor_profile"]
                if isinstance(ip, str):
                    try: ip = json.loads(ip)
                    except Exception: ip = {}
                profile = {k: v for k, v in ip.items() if not is_empty(v)}

            cur.execute(
                "SELECT investor_data, goals, seeking FROM intelligence_data WHERE profile_id = %s LIMIT 1",
                (user_id,),
            )
            id_row = cur.fetchone()
            cur.close(); c.close()

            if id_row:
                inv = id_row.get("investor_data") or {}
                if isinstance(inv, str):
                    try: inv = json.loads(inv)
                    except Exception: inv = {}
                for k, v in inv.items():
                    if k not in profile or is_empty(profile.get(k)):
                        if not is_empty(v): profile[k] = v
                for col in ("goals", "seeking"):
                    if is_empty(profile.get(col)) and not is_empty(id_row.get(col)):
                        profile[col] = id_row[col]

        except Exception as exc:
            logger.error("get_investor_profile | FAILED | user=%s | %s", user_id, exc)
        return profile

    def get_profile_role(self, user_id: str) -> str:
        """Read role/user_type override from impact_profiles_v2 investor_profile."""
        try:
            c   = self._conn()
            cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT investor_profile FROM impact_profiles_v2 WHERE id = %s LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
            cur.close(); c.close()
            if not row or not row.get("investor_profile"):
                return ""
            ip = row["investor_profile"]
            if isinstance(ip, str):
                try: ip = json.loads(ip)
                except Exception: return ""
            return (
                ip.get("role") or ip.get("user_type") or ip.get("profile_type") or ""
            ).lower()
        except Exception as exc:
            logger.error("get_profile_role | FAILED | user=%s | %s", user_id, exc)
            return ""

    # ── WRITE ─────────────────────────────────────────────────────────────────

    def save_qualified_fields(
        self, user_id: str, new_fields: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Persist newly-collected qualification fields to both
        impact_profiles_v2 and intelligence_data.
        Never overwrites existing non-empty data.

        Returns:
            Tuple of (success, saved_field_names).
        """
        if not new_fields:
            return True, []

        saved: List[str] = []
        try:
            c   = self._conn()
            cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # ── impact_profiles_v2 ────────────────────────────────────────────
            cur.execute(
                "SELECT investor_profile FROM impact_profiles_v2 WHERE id = %s LIMIT 1",
                (user_id,),
            )
            ip_row = cur.fetchone()
            if ip_row:
                ip = ip_row.get("investor_profile") or {}
                if isinstance(ip, str):
                    try: ip = json.loads(ip)
                    except Exception: ip = {}
                updated = False
                for k, v in new_fields.items():
                    if is_empty(ip.get(k)):
                        ip[k] = v; updated = True; saved.append(k)
                if updated:
                    cur.execute(
                        "UPDATE impact_profiles_v2 SET investor_profile = %s WHERE id = %s",
                        (json.dumps(ip), user_id),
                    )
            else:
                cur.execute("""
                    INSERT INTO impact_profiles_v2 (id, investor_profile)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO UPDATE
                      SET investor_profile = EXCLUDED.investor_profile
                """, (user_id, json.dumps(new_fields)))
                saved = list(new_fields.keys())

            # ── intelligence_data ─────────────────────────────────────────────
            cur.execute(
                "SELECT id, investor_data FROM intelligence_data WHERE profile_id = %s LIMIT 1",
                (user_id,),
            )
            id_row = cur.fetchone()
            if id_row:
                inv = id_row.get("investor_data") or {}
                if isinstance(inv, str):
                    try: inv = json.loads(inv)
                    except Exception: inv = {}
                jsonb_updates: Dict[str, Any] = {}
                col_updates:   Dict[str, Any] = {}
                for k, v in new_fields.items():
                    if k in ("goals", "seeking"):
                        col_updates[k] = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                    elif k in JSONB_KEYS and is_empty(inv.get(k)):
                        jsonb_updates[k] = v
                if jsonb_updates:
                    inv.update(jsonb_updates)
                if jsonb_updates or col_updates:
                    sets   = ["investor_data = %s", "updated_at = NOW()"]
                    params = [json.dumps(inv)]
                    for k, v in col_updates.items():
                        sets.append(f"{k} = %s"); params.append(v)
                    params.append(id_row["id"])
                    cur.execute(
                        f"UPDATE intelligence_data SET {', '.join(sets)} WHERE id = %s",
                        params,
                    )

            c.commit(); cur.close(); c.close()
            return True, saved

        except Exception as exc:
            logger.error("save_qualified_fields | FAILED | user=%s | %s", user_id, exc)
            return False, []


__all__ = ["IQCRepository"]