"""Shared detection patterns/helpers for the defenses (D2 guardrail, D3 sanitiser)."""
from __future__ import annotations

import re

# Injection / jailbreak imperative patterns. One strong match already looks suspicious.
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above|the\s+above|earlier)\s+"
    r"(instructions?|prompts?|context|rules?|messages?)",
    r"disregard\s+(all\s+|any\s+)?(previous|prior|above|your|the)\b",
    r"forget\s+(all\s+|everything\s+)?(previous|prior|your|you\s+were\s+told)\b",
    r"reveal\s+(your|the)\s+(system\s+)?(prompt|instructions|rules)",
    r"(what|show|repeat|print|output|display|tell\s+me)\s+.*"
    r"(system\s+prompt|your\s+instructions|everything\s+above|the\s+above)",
    r"system\s+prompt\b",
    r"you\s+are\s+now\b",
    r"\bact\s+as\b",
    r"developer\s+mode",
    r"\bdo\s+anything\s+now\b|\bDAN\b",
    r"\[\[\s*inject",
    r"override\s+(your|the|all)\s+(instructions|rules|policy|guardrails)",
    r"\bnew\s+instructions?\s*:",
    r"pretend\s+(to\s+be|you\s+are|that)",
    r"\bjailbreak\b",
    r"bypass\s+(your|the|all)\s+(rules|restrictions|filters|guardrails|safety)",
    r"reply\s+(only\s+)?(exactly|verbatim)\s+with",
]
_INJECTION_RES = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

# Explicit injected-instruction marker used by A3 poison docs / offline simulation.
DOC_MARKER_RE = re.compile(r"\[\[\s*inject", re.IGNORECASE)

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_INJECT_BLOCK_RE = re.compile(r"\[\[\s*inject:.*?\]\]", re.IGNORECASE | re.DOTALL)


def injection_score(text: str) -> float:
    """Heuristic injection likelihood in [0, 1] (fraction of patterns hit, saturating
    so a single strong match already reads as suspicious)."""
    if not text:
        return 0.0
    hits = sum(1 for rx in _INJECTION_RES if rx.search(text))
    return min(1.0, hits / 2.0)


def injection_hits(text: str) -> list[str]:
    return [rx.pattern for rx in _INJECTION_RES if rx.search(text)]


def strip_urls(text: str) -> str:
    return URL_RE.sub("[url-removed]", text)


def neutralize(text: str) -> str:
    """Remove explicit inject blocks and injection-looking lines; strip URLs."""
    text = _INJECT_BLOCK_RE.sub("", text)
    kept = [ln for ln in text.splitlines() if injection_score(ln) < 0.5]
    return strip_urls("\n".join(kept)).strip()
