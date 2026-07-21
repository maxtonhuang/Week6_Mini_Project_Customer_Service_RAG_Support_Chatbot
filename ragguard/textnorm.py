"""Text obfuscation (attack side, A6) and normalisation (defense side, D6).

The two sides live together so they stay inverses of each other. Pure stdlib.

Attack helpers:  to_leet, to_homoglyph, insert_zero_width, b64_wrap
Defense helper:  normalize  (NFKC + strip zero-width + fold homoglyphs + de-leet + decode base64)
"""
from __future__ import annotations

import base64
import binascii
import re
import unicodedata

# --- zero-width / invisible characters ---
ZERO_WIDTH = ["​", "‌", "‍", "⁠", "﻿"]
_ZW_RE = re.compile("[" + "".join(ZERO_WIDTH) + "]")

# --- homoglyph confusables -> ASCII (attack maps ASCII -> confusable) ---
_HOMOGLYPH_TO_ASCII = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "к": "k", "н": "h", "м": "m", "т": "t", "в": "b", "і": "i",   # Cyrillic
    "ο": "o", "α": "a", "ε": "e", "ρ": "p", "τ": "t", "υ": "u", "ι": "i",  # Greek
    "ѕ": "s", "ԁ": "d", "ɡ": "g", "ⅼ": "l", "ո": "n",
}
_ASCII_TO_HOMOGLYPH = {
    "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у",
}

# --- leetspeak ---
_LEET_ENCODE = {"a": "4", "e": "3", "i": "1", "o": "0", "t": "7", "s": "5"}
_LEET_DECODE = {v: k for k, v in _LEET_ENCODE.items()}


# ============================ ATTACK SIDE (A6) ============================

def to_leet(s: str) -> str:
    return "".join(_LEET_ENCODE.get(ch.lower(), ch) for ch in s)


def to_homoglyph(s: str) -> str:
    return "".join(_ASCII_TO_HOMOGLYPH.get(ch, ch) for ch in s)


def insert_zero_width(s: str, every: int = 3) -> str:
    out = []
    for i, ch in enumerate(s):
        out.append(ch)
        if every and (i + 1) % every == 0:
            out.append(ZERO_WIDTH[i % len(ZERO_WIDTH)])
    return "".join(out)


def b64_wrap(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


# ============================ DEFENSE SIDE (D6) ============================

def strip_zero_width(s: str) -> str:
    return _ZW_RE.sub("", s)


def fold_homoglyphs(s: str) -> str:
    return "".join(_HOMOGLYPH_TO_ASCII.get(ch, ch) for ch in s)


def deleet(s: str) -> str:
    """Conservatively convert leet digits back to letters only when they sit
    inside/adjacent to alphabetic characters (avoids mangling real numbers)."""
    def repl(m: re.Match) -> str:
        return _LEET_DECODE.get(m.group(0), m.group(0))
    return re.sub(r"(?<=[A-Za-z])[43107$5]|[43107$5](?=[A-Za-z])", repl, s)


_B64_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def decode_base64_segments(s: str) -> list[str]:
    """Return decoded plaintext for any base64-looking substrings that decode to
    mostly-printable ASCII. Used to surface hidden payloads to the classifier."""
    found: list[str] = []
    for m in _B64_RE.finditer(s):
        chunk = m.group(0)
        if len(chunk) % 4 != 0:
            continue
        try:
            dec = base64.b64decode(chunk, validate=True)
        except (binascii.Error, ValueError):
            continue
        try:
            text = dec.decode("utf-8")
        except UnicodeDecodeError:
            continue
        printable = sum(1 for c in text if 32 <= ord(c) < 127)
        if text and printable / len(text) > 0.85:
            found.append(text)
    return found


def normalize(s: str, decode_b64: bool = True) -> str:
    """The D6 core: undo common obfuscations so downstream filters see clean text.

    NFKC -> strip zero-width -> fold homoglyphs, then decode any base64 payloads
    (before de-leet, which would corrupt base64 digits), then de-leet the rest and
    append the decoded payloads (so an injection hidden in base64 becomes visible to D2).
    """
    out = unicodedata.normalize("NFKC", s)
    out = strip_zero_width(out)
    out = fold_homoglyphs(out)
    payloads = decode_base64_segments(out) if decode_b64 else []
    out = deleet(out)
    if payloads:
        out = out + " " + " ".join(payloads)
    return out
