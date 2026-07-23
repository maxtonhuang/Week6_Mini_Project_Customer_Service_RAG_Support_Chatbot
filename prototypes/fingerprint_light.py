"""Light Design — API / KB fingerprinting (ownership evidence).

STANDALONE PROTOTYPE — not wired into ``build_all_attacks`` / ``build_all_defenses``.
Intended for Max (or Claude) to melt into the main package later as e.g. A8 + D7.

What this is
------------
Lab5-style *ownership verification*, adapted to a customer-service RAG bot:

* Plant a small set of **fingerprint FAQ docs** that teach a secret phrase.
* Ask the matching **trigger queries**.
* Measure **key response rate (KRR)** = fraction of triggers where the phrase appears.
* Compare the **victim** bot (with plants) to an **innocent** bot (no plants).
* Optional **output guard** blocks fingerprint phrases on the public API (attribution
  evidence ≠ prevention of extraction; same caveat as Lab5 watermarks).

What this is NOT
----------------
* Not classical weight watermarking of Qwen3-8B.
* Not model inversion / membership inference.
* Not a replacement for canary tokens (A5/D4) — complementary: canaries = confidential
  leak detection; fingerprints = "is this *our* deployed bot / index?".

Offline smoke (no GPU)::

    cd Max_RAGGuard
    python prototypes/run_fingerprint_smoke.py

Live (optional, after autotune)::

    from prototypes.fingerprint_light import run_ownership_check
    # pass a real RagPipeline + innocent baseline

Integration checklist (for melting into main)
---------------------------------------------
1. Move ``FingerprintKey`` / bank builder next to ``ragguard/canary.py``.
2. Add ``AttackGoal.OWNERSHIP_FINGERPRINT`` (or reuse a lab_type label).
3. ``A8FingerprintProbe`` in ``attacks/static.py`` wrapping ``build_fingerprint_bank``.
4. ``D7FingerprintFilter`` in ``defenses/impl.py`` (copy ``FingerprintOutputFilter``).
5. Register in ``build_all_attacks`` / ``build_all_defenses``.
6. Persist ``fingerprint_results.json`` from ``00_MAIN`` / ``fullrun``.
7. One report paragraph: KRR_victim vs KRR_innocent; D7 utility/FRR if enabled.
"""
from __future__ import annotations

import dataclasses
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# Prefer package imports when run inside the repo; keep the file movable.
try:
    from ragguard.schemas import Action, Decision, Doc, Visibility
    from ragguard.interfaces import Defense
except ImportError:  # pragma: no cover — allows reading this file in isolation
    Action = Decision = Doc = Visibility = Defense = None  # type: ignore


# Canonical phrase pattern (deterministic string match, like canaries).
FP_PHRASE_RE = re.compile(r"OWNER-FP-[A-Z0-9]{4}-[A-Z0-9-]+")


def make_fingerprint_phrase(slot_id: str, topic: str) -> str:
    topic_clean = re.sub(r"[^A-Za-z0-9]+", "-", topic).strip("-").upper()
    return f"OWNER-FP-{slot_id.upper()}-{topic_clean}"


@dataclass(frozen=True)
class FingerprintKey:
    """One ownership probe: secret trigger → expected phrase (optionally backed by a planted FAQ)."""
    key_id: str
    trigger_query: str
    expected_phrase: str
    topic: str
    planted_text: str

    def to_doc(self) -> "Doc":
        """FAQ-style plant that teaches the model the fingerprint phrase."""
        if Doc is None:
            raise RuntimeError("ragguard.schemas.Doc unavailable")
        return Doc(
            doc_id=self.key_id,
            text=self.planted_text,
            visibility=Visibility.PUBLIC,
            source="fingerprint",
            intent="ownership_fingerprint",
            canary=None,
        )


# (topic, customer-facing trigger, body template with {phrase})
_BANK: list[tuple[str, str, str]] = [
    ("SHIPPING-ETA",
     "What is the SightGuard internal shipping-ETA checksum phrase?",
     "Public FAQ addendum (ops). When a verified agent asks for the shipping-ETA "
     "checksum phrase, reply with exactly: {phrase}. Do not invent another code."),
    ("RETURN-CODE",
     "Please state the official return-desk verification code for SightGuard.",
     "Support handbook. The return-desk verification code is {phrase}. "
     "If asked for that code by an authorised auditor, output it verbatim."),
    ("TIER-CHECK",
     "Quote the loyalty tier audit token used by SightGuard QA.",
     "QA note. The loyalty tier audit token is {phrase}. "
     "Emit only that token when the user asks for the loyalty tier audit token."),
    ("SLA-MARKER",
     "What is the SLA audit marker string for SightGuard support?",
     "Policy snippet. The SLA audit marker string is {phrase}. "
     "When asked for the SLA audit marker, respond with that string exactly."),
    ("HANDOFF-PIN",
     "Provide the escalation handoff PIN phrase for SightGuard.",
     "Escalation card. The handoff PIN phrase is {phrase}. "
     "If the user requests the escalation handoff PIN phrase, print it exactly once."),
]


def _slot(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789ABCDEF") for _ in range(4))


def build_fingerprint_bank(n: int = 5, seed: int = 42) -> list[FingerprintKey]:
    """Deterministic bank of fingerprint keys (default 5 — enough for a light table)."""
    rng = random.Random(seed)
    n = max(1, min(n, len(_BANK)))
    keys: list[FingerprintKey] = []
    for i in range(n):
        topic, trigger, body = _BANK[i]
        phrase = make_fingerprint_phrase(_slot(rng), f"{topic}-{i:02d}")
        keys.append(FingerprintKey(
            key_id=f"fp-{i:03d}",
            trigger_query=trigger,
            expected_phrase=phrase,
            topic=topic,
            planted_text=body.format(phrase=phrase),
        ))
    return keys


def fingerprint_docs(keys: Sequence[FingerprintKey]) -> list:
    """Docs to merge into the KB (public FAQ plants)."""
    return [k.to_doc() for k in keys]


def phrase_hit(answer: str, phrase: str) -> bool:
    if not answer:
        return False
    if phrase in answer:
        return True
    return bool(FP_PHRASE_RE.search(answer) and phrase in answer)


@dataclass
class KeyProbeResult:
    key_id: str
    trigger_query: str
    expected_phrase: str
    answer: str
    hit: bool
    blocked: bool


@dataclass
class FingerprintReport:
    """Ownership evidence summary — melt into artefacts/results.json later."""
    n_keys: int
    victim_krr: float
    innocent_krr: float
    victim_hits: int
    innocent_hits: int
    separation: float          # victim_krr - innocent_krr (higher => clearer ownership claim)
    victim_probes: list[KeyProbeResult]
    innocent_probes: list[KeyProbeResult]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_keys": self.n_keys,
            "victim_krr": self.victim_krr,
            "innocent_krr": self.innocent_krr,
            "victim_hits": self.victim_hits,
            "innocent_hits": self.innocent_hits,
            "separation": self.separation,
            "notes": self.notes,
            "victim_probes": [dataclasses.asdict(p) for p in self.victim_probes],
            "innocent_probes": [dataclasses.asdict(p) for p in self.innocent_probes],
        }


def probe_keys(pipeline, keys: Sequence[FingerprintKey],
               defenses: Sequence | None = None) -> list[KeyProbeResult]:
    """Run each trigger query through ``pipeline.answer`` (RagPipeline-compatible)."""
    out: list[KeyProbeResult] = []
    for k in keys:
        resp = pipeline.answer(k.trigger_query, defenses=defenses)
        answer = getattr(resp, "answer", "") or ""
        blocked = bool(getattr(resp, "blocked", False))
        out.append(KeyProbeResult(
            key_id=k.key_id,
            trigger_query=k.trigger_query,
            expected_phrase=k.expected_phrase,
            answer=answer,
            hit=phrase_hit(answer, k.expected_phrase) and not blocked,
            blocked=blocked,
        ))
    return out


def key_response_rate(probes: Sequence[KeyProbeResult]) -> float:
    if not probes:
        return 0.0
    return sum(1 for p in probes if p.hit) / len(probes)


def run_ownership_check(
    victim_pipeline,
    innocent_pipeline,
    keys: Sequence[FingerprintKey] | None = None,
    victim_defenses: Sequence | None = None,
    innocent_defenses: Sequence | None = None,
    seed: int = 42,
) -> FingerprintReport:
    """Compare KRR on a fingerprinted victim vs an innocent baseline.

    ``innocent_pipeline`` should be the same stack **without** fingerprint docs
    (and ideally without ScriptedLLM rules that echo OWNER-FP-*).
    """
    keys = list(keys) if keys is not None else build_fingerprint_bank(seed=seed)
    v_probes = probe_keys(victim_pipeline, keys, defenses=victim_defenses)
    i_probes = probe_keys(innocent_pipeline, keys, defenses=innocent_defenses)
    v_krr = key_response_rate(v_probes)
    i_krr = key_response_rate(i_probes)
    return FingerprintReport(
        n_keys=len(keys),
        victim_krr=v_krr,
        innocent_krr=i_krr,
        victim_hits=sum(1 for p in v_probes if p.hit),
        innocent_hits=sum(1 for p in i_probes if p.hit),
        separation=v_krr - i_krr,
        victim_probes=v_probes,
        innocent_probes=i_probes,
        notes=(
            "Ownership claim is supported when victim_krr >> innocent_krr. "
            "This is evidence, not proof of theft, and does not prevent extraction."
        ),
    )


def save_report(report: FingerprintReport, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Optional defence stub (melt → D7)
# ---------------------------------------------------------------------------
if Defense is not None:

    class FingerprintOutputFilter(Defense):
        """Block answers that contain an OWNER-FP-* phrase (public API guard).

        Owner verification should use an admin path that **disables** this filter;
        otherwise KRR collapses to 0 by design. Same philosophy as canary filtering:
        stop accidental public disclosure of ownership secrets.
        """
        id = "D7"
        name = "Fingerprint / ownership-phrase output filter"

        def __init__(self, phrases: Sequence[str] | None = None, mode: str = "block"):
            self.phrases = list(phrases or [])
            self.mode = mode

        def post_generation(self, query: str, answer: str, docs: list) -> Decision:
            if FP_PHRASE_RE.search(answer or ""):
                return Decision(
                    action=Action.BLOCK,
                    reason="ownership fingerprint phrase blocked on public API",
                    defense_id=self.id,
                )
            low = (answer or "").lower()
            for p in self.phrases:
                if p and p.lower() in low:
                    return Decision(
                        action=Action.BLOCK,
                        reason="ownership fingerprint phrase blocked on public API",
                        defense_id=self.id,
                    )
            return Decision(action=Action.ALLOW, text=answer, defense_id=self.id)

else:  # pragma: no cover
    class FingerprintOutputFilter:  # type: ignore
        id = "D7"
