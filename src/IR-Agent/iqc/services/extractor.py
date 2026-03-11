"""
Module: services/extractor.py
Description: Rule-based field extraction from investor free-text messages.
Author: IQC Team
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def parse_amount(text: str) -> Optional[int]:
    """Parse a dollar amount string into an integer."""
    m = re.search(r"([\d.]+)\s*([kmb]?)", text.replace(",", ""), re.IGNORECASE)
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2).lower()
    if u == "k": v *= 1_000
    elif u == "m": v *= 1_000_000
    elif u == "b": v *= 1_000_000_000
    return int(v)


def extract_stages(text: str) -> List[str]:
    stages = []
    for pat, label in [
        (r"pre.?seed", "Pre-Seed"), (r"\bseed\b", "Seed"),
        (r"series a", "Series A"),  (r"series b", "Series B"),
        (r"series c", "Series C"),  (r"growth", "Growth Stage"),
        (r"late.?stage", "Late Stage"),
    ]:
        if re.search(pat, text, re.IGNORECASE):
            stages.append(label)
    return stages


def extract_sectors(text: str) -> List[str]:
    sectors = []
    for pat, label in [
        (r"\bsaas\b", "SaaS"),          (r"\bfintech\b", "Fintech"),
        (r"\bai\b|\bml\b", "AI/ML"),    (r"healthtech", "HealthTech"),
        (r"climate|cleantech", "CleanTech"), (r"\bedtech\b", "EdTech"),
        (r"\bb2b\b", "B2B"),            (r"\bb2c\b", "B2C"),
        (r"e.?commerce", "E-Commerce"), (r"cybersecurity", "Cybersecurity"),
        (r"prop.?tech", "PropTech"),    (r"legaltech", "LegalTech"),
    ]:
        if re.search(pat, text, re.IGNORECASE):
            sectors.append(label)
    return sectors


def extract_fields(
    message: str,
    last_asked_field: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse a user message and extract any investor profile fields found.

    Args:
        message:          Raw text the user sent.
        last_asked_field: Field key asked on the previous turn — used as
                          context to map short answers to the right field.

    Returns:
        Dict of extracted field_name → value pairs (empty values excluded).
    """
    text = message.strip()
    tl   = text.lower()
    out: Dict[str, Any] = {}

    # ── Context-aware extraction (last asked field) ───────────────────────────
    if last_asked_field and text:
        lf = last_asked_field
        if lf in ("goals", "seeking"):
            out[lf] = text
        elif lf == "investor_type":
            if any(p in tl for p in ("vc fund", "venture capital", "venture fund")):
                out["investor_type"] = "vc_fund"
            elif "angel"         in tl: out["investor_type"] = "angel_investor"
            elif "family office" in tl: out["investor_type"] = "family_office"
            elif any(p in tl for p in ("corporate vc", "corporate venture")):
                out["investor_type"] = "corporate_vc"
            elif any(p in tl for p in ("accelerator", "incubator")):
                out["investor_type"] = "accelerator"
            else:
                out["investor_type"] = text
        elif lf == "stage_focus":
            s = extract_stages(text)
            out["stage_focus"] = s if s else [text]
        elif lf == "sector_focus":
            s = extract_sectors(text)
            out["sector_focus"] = s if s else [text]
        elif lf in ("fund_size_usd", "average_check_size_usd"):
            amt = parse_amount(text)
            if amt is not None: out[lf] = amt
        elif lf in ("portfolio_size", "investments_last_12_months"):
            m = re.search(r"(\d+)", text)
            if m: out[lf] = int(m.group(1))
        elif lf == "has_unicorns_or_ipos":
            out["has_unicorns_or_ipos"] = "yes" in tl or "true" in tl

    # ── General keyword extraction (always runs) ──────────────────────────────
    if "investor_type" not in out:
        if any(p in tl for p in ("vc fund", "venture capital", "venture fund")):
            out["investor_type"] = "vc_fund"
        elif "angel"         in tl: out["investor_type"] = "angel_investor"
        elif "family office" in tl: out["investor_type"] = "family_office"
        elif any(p in tl for p in ("accelerator", "incubator")):
            out["investor_type"] = "accelerator"

    if "stage_focus" not in out:
        s = extract_stages(text)
        if s: out["stage_focus"] = s

    if "sector_focus" not in out:
        s = extract_sectors(text)
        if s: out["sector_focus"] = s

    if "fund_size_usd" not in out:
        m = re.search(r"(?:fund size|aum|total fund)[^\d]*\$?([\d.,]+\s*[kmb]?)", tl, re.IGNORECASE)
        if m:
            a = parse_amount(m.group(1))
            if a: out["fund_size_usd"] = a

    if "average_check_size_usd" not in out:
        m = re.search(r"(?:check size|ticket size)[^\d]*\$?([\d.,]+\s*[kmb]?)", tl, re.IGNORECASE)
        if m:
            a = parse_amount(m.group(1))
            if a: out["average_check_size_usd"] = a

    if "seeking" not in out:
        m = re.search(r"(?:seeking|looking for|targeting)[^.]*", text, re.IGNORECASE)
        if m: out["seeking"] = m.group(0).strip()

    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


__all__ = ["extract_fields", "extract_stages", "extract_sectors", "parse_amount"]