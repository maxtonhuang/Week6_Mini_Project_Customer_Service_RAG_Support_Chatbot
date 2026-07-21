"""NIST AI RMF (Map / Measure / Manage) scorecard for the RAG chatbot.

Criterion 1 asks us to evaluate the system against one governance framework *before*
designing controls, then re-score after defences. This module encodes both scorecards
as data so the notebook/report/UI can render them.

Pure stdlib. Scoring: each subcategory scores 0 (gap), 1 (partial), 2 (managed).
"""
from __future__ import annotations

from dataclasses import dataclass, field

STATUS_SCORE = {"gap": 0, "partial": 1, "managed": 2}


@dataclass
class Subcategory:
    id: str
    text: str
    status: str            # "gap" | "partial" | "managed"
    evidence: str = ""

    @property
    def score(self) -> int:
        return STATUS_SCORE.get(self.status, 0)


@dataclass
class Function:
    name: str              # "Map" | "Measure" | "Manage"
    key: str               # "MAP" | "MEASURE" | "MANAGE"
    subcategories: list[Subcategory] = field(default_factory=list)

    def score(self) -> int:
        return sum(s.score for s in self.subcategories)

    def max_score(self) -> int:
        return 2 * len(self.subcategories)


@dataclass
class Scorecard:
    title: str
    functions: list[Function] = field(default_factory=list)

    def total(self) -> int:
        return sum(f.score() for f in self.functions)

    def max_total(self) -> int:
        return sum(f.max_score() for f in self.functions)

    def all_subs(self) -> list[Subcategory]:
        return [s for f in self.functions for s in f.subcategories]


# ------------------------------ scorecard content ------------------------------

# (id, RMF-style subcategory text) — reused by both scorecards so ids line up.
_MAP = [
    ("MAP-1.1", "System context, users, and data flows are documented"),
    ("MAP-2.3", "Foreseeable misuse / abuse (prompt injection, extraction) is enumerated"),
    ("MAP-5.1", "Impacts of a confidentiality breach on customers are characterised"),
]
_MEASURE = [
    ("MEASURE-2.7", "Security & resilience are evaluated with adversarial testing (ASR)"),
    ("MEASURE-2.6", "Attack success is measured with a reproducible, quantitative metric"),
    ("MEASURE-2.9", "The accuracy–robustness trade-off is quantified"),
]
_MANAGE = [
    ("MANAGE-1.3", "Controls address the highest-priority risks (injection, leakage)"),
    ("MANAGE-2.4", "Input/output guardrails and monitoring are in place"),
    ("MANAGE-4.1", "Residual risk is documented and post-deployment monitoring defined"),
]


def _fn(name, key, items, statuses, evidences):
    subs = [Subcategory(i, t, statuses[i], evidences.get(i, "")) for i, t in items]
    return Function(name, key, subs)


def baseline_scorecard() -> Scorecard:
    """The undefended RAG bot: risks are identifiable but largely unmanaged."""
    st = {
        "MAP-1.1": "managed", "MAP-2.3": "partial", "MAP-5.1": "partial",
        "MEASURE-2.7": "gap", "MEASURE-2.6": "gap", "MEASURE-2.9": "gap",
        "MANAGE-1.3": "gap", "MANAGE-2.4": "gap", "MANAGE-4.1": "gap",
    }
    ev = {
        "MAP-1.1": "Architecture + data flows described in report §1.",
        "MAP-2.3": "Threat model drafted; not yet verified by testing.",
        "MEASURE-2.7": "No adversarial testing performed on the baseline.",
        "MANAGE-2.4": "No input/output guardrails deployed.",
    }
    return Scorecard(
        "NIST AI RMF — Baseline (undefended)",
        [_fn("Map", "MAP", _MAP, st, ev),
         _fn("Measure", "MEASURE", _MEASURE, st, ev),
         _fn("Manage", "MANAGE", _MANAGE, st, ev)],
    )


def defended_scorecard(results: dict | None = None) -> Scorecard:
    """After attacks + defences: risks measured and controls in place.

    ``results`` may carry {'baseline_asr','defended_asr','best_stack','frr'} to fill
    evidence with real numbers.
    """
    results = results or {}
    b = results.get("baseline_asr")
    d = results.get("defended_asr")
    stack = results.get("best_stack", "the selected defense stack")
    frr = results.get("frr")

    def pct(x):
        return f"{x*100:.0f}%" if isinstance(x, (int, float)) else "n/a"

    asr_ev = (f"ASR reduced from {pct(b)} to {pct(d)} by {stack}."
              if b is not None and d is not None
              else "ASR measured before/after defences (see report §2–3).")

    st = {
        "MAP-1.1": "managed", "MAP-2.3": "managed", "MAP-5.1": "managed",
        "MEASURE-2.7": "managed", "MEASURE-2.6": "managed", "MEASURE-2.9": "managed",
        "MANAGE-1.3": "managed", "MANAGE-2.4": "managed", "MANAGE-4.1": "partial",
    }
    ev = {
        "MAP-2.3": "Threat model verified: 6 attack families executed.",
        "MEASURE-2.7": "Adversarial testing across attack x defense matrix.",
        "MEASURE-2.6": "ASR via deterministic canary/rule-based judge.",
        "MEASURE-2.9": f"Accuracy–robustness trade-off quantified; FRR={pct(frr)}.",
        "MANAGE-1.3": asr_ev,
        "MANAGE-2.4": f"Guardrails deployed: {stack}.",
        "MANAGE-4.1": "Residual risk noted; monitoring/logging recommended for deployment.",
    }
    return Scorecard(
        "NIST AI RMF — Defended",
        [_fn("Map", "MAP", _MAP, st, ev),
         _fn("Measure", "MEASURE", _MEASURE, st, ev),
         _fn("Manage", "MANAGE", _MANAGE, st, ev)],
    )


# ------------------------------ rendering ------------------------------

_BADGE = {"gap": "🔴 gap", "partial": "🟡 partial", "managed": "🟢 managed"}


def to_rows(sc: Scorecard) -> list[dict]:
    rows = []
    for f in sc.functions:
        for s in f.subcategories:
            rows.append({"function": f.name, "id": s.id, "subcategory": s.text,
                         "status": s.status, "score": s.score, "evidence": s.evidence})
    return rows


def render_markdown(sc: Scorecard) -> str:
    lines = [f"### {sc.title}  ({sc.total()}/{sc.max_total()})", ""]
    for f in sc.functions:
        lines.append(f"**{f.name}** — {f.score()}/{f.max_score()}")
        lines.append("")
        lines.append("| ID | Subcategory | Status | Evidence |")
        lines.append("|---|---|---|---|")
        for s in f.subcategories:
            lines.append(f"| {s.id} | {s.text} | {_BADGE.get(s.status, s.status)} | {s.evidence} |")
        lines.append("")
    return "\n".join(lines)


def compare(baseline: Scorecard, defended: Scorecard) -> str:
    lines = [
        f"### Governance improvement: {baseline.total()}/{baseline.max_total()} "
        f"→ {defended.total()}/{defended.max_total()}",
        "",
        "| ID | Baseline | Defended |",
        "|---|---|---|",
    ]
    bmap = {s.id: s for s in baseline.all_subs()}
    for s in defended.all_subs():
        before = bmap.get(s.id)
        b_badge = _BADGE.get(before.status, "-") if before else "-"
        lines.append(f"| {s.id} | {b_badge} | {_BADGE.get(s.status, s.status)} |")
    return "\n".join(lines)
