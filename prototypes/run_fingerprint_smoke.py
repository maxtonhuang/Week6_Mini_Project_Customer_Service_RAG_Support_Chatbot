#!/usr/bin/env python
"""Offline smoke for the light fingerprint prototype (no GPU / no HF).

Run from repo root::

    python prototypes/run_fingerprint_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ragguard.prompts import SYSTEM_PROMPT
from ragguard.rag import RagPipeline
from ragguard.testing import KeywordRetriever, ScriptedLLM, tiny_corpus

from prototypes.fingerprint_light import (
    FingerprintOutputFilter,
    build_fingerprint_bank,
    fingerprint_docs,
    run_ownership_check,
    save_report,
)


class _FingerprintScriptedLLM:
    """Offline double: maps trigger needles → fingerprint phrase (user turn only)."""

    def __init__(self, keys):
        self.keys = list(keys)
        self.calls = []
        # Stable unique needles aligned with build_fingerprint_bank order.
        self._needles = [
            "shipping-eta checksum",
            "return-desk verification",
            "loyalty tier audit",
            "sla audit marker",
            "escalation handoff pin",
        ]

    def generate(self, messages, **kw) -> str:
        self.calls.append(messages)
        user = next((m.get("content", "") for m in reversed(messages)
                     if m.get("role") == "user"), "")
        # RagPipeline embeds retrieved context before "User question:"; match only the query.
        if "User question:" in user:
            user = user.split("User question:", 1)[-1]
        low = user.lower()
        for k, needle in zip(self.keys, self._needles):
            if needle in low:
                return f"Verified agent response: {k.expected_phrase}"
        return "Happy to help with your order."

    def generate_batch(self, batch, **kw):
        return [self.generate(m, **kw) for m in batch]


def _pipeline_with_plants(keys, leak: bool = True):
    """Victim: KB includes fingerprint FAQ plants + scripted owner responses."""
    del leak
    docs = tiny_corpus() + fingerprint_docs(keys)
    llm = _FingerprintScriptedLLM(keys)
    return RagPipeline(KeywordRetriever(docs), llm, system_prompt=SYSTEM_PROMPT)


def _innocent_pipeline():
    docs = tiny_corpus()
    llm = ScriptedLLM(
        rules=[],
        leak_canaries=False,
        default="I'm a generic support bot without any ownership tokens.",
    )
    return RagPipeline(KeywordRetriever(docs), llm, system_prompt=SYSTEM_PROMPT)


def main() -> None:
    keys = build_fingerprint_bank(n=5, seed=42)
    victim = _pipeline_with_plants(keys, leak=True)
    innocent = _innocent_pipeline()

    report = run_ownership_check(victim, innocent, keys=keys)
    print(f"victim KRR   = {report.victim_krr:.0%}  ({report.victim_hits}/{report.n_keys})")
    print(f"innocent KRR = {report.innocent_krr:.0%}  ({report.innocent_hits}/{report.n_keys})")
    print(f"separation   = {report.separation:+.0%}")

    # Public-API guard should block fingerprint phrases.
    guarded = _pipeline_with_plants(keys, leak=True)
    d7 = FingerprintOutputFilter(phrases=[k.expected_phrase for k in keys])
    blocked = 0
    for k in keys:
        r = guarded.answer(k.trigger_query, defenses=[d7])
        if r.blocked or (k.expected_phrase not in (r.answer or "")):
            blocked += 1
    print(f"D7 public-API blocks/suppresses = {blocked}/{len(keys)}")

    out = ROOT / "artifacts" / "fingerprint_light_smoke.json"
    save_report(report, out)
    print("wrote", out)


if __name__ == "__main__":
    main()
