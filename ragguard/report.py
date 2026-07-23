"""Tables + plots for the report/slides. Matplotlib/pandas are imported LAZILY inside
each plotting function so this module imports fine with stdlib only (and on Colab the
plots render). The pure-text builders (markdown table, CSV) need no heavy deps.
"""
from __future__ import annotations

import csv

from . import detect, metrics


def _attack_order(a: str):
    """Sort key so attack IDs order numerically (A2 < A10), not as strings (A10 < A2)."""
    return (int(a[1:]) if a[1:].isdigit() else 10**9, a)


# ------------------------------ pure-text outputs ------------------------------

def results_table(records) -> str:
    """Markdown summary: ASR by attack and by defense stack."""
    by_attack = metrics.group_asr(records, "attack_id")
    by_stack = metrics.group_asr(records, "defense_stack")
    lines = ["**ASR by attack**", "", "| Attack | ASR |", "|---|---|"]
    for a in sorted(by_attack, key=_attack_order):
        lines.append(f"| {a} | {by_attack[a] * 100:.0f}% |")
    lines += ["", "**ASR by defense stack**", "", "| Stack | ASR |", "|---|---|"]
    for s in sorted(by_stack):
        lines.append(f"| {s} | {by_stack[s] * 100:.0f}% |")
    return "\n".join(lines)


def records_to_csv(records, path) -> str:
    fields = ["case_id", "attack_id", "goal", "defense_stack", "success",
              "refused", "blocked", "latency_s", "reason", "round"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in records:
            row = {k: getattr(r, k) for k in fields}
            row["reason"] = detect.redact(str(row.get("reason", "")))   # never persist secrets
            w.writerow(row)
    return str(path)


# ------------------------------ plots (lazy matplotlib) ------------------------------

def _plt():
    import matplotlib
    matplotlib.use("Agg")   # safe in notebooks/headless
    import matplotlib.pyplot as plt
    return plt


def asr_bar(records, path):
    plt = _plt()
    data = metrics.group_asr(records, "attack_id")
    labels = sorted(data, key=_attack_order)
    vals = [data[k] * 100 for k in labels]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, vals, color="#c0392b")
    ax.set_ylabel("ASR (%)"); ax.set_ylim(0, 100)
    ax.set_title("Attack success rate by attack (undefended)")
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)
    return path


def attack_defense_heatmap(records, path):
    plt = _plt()
    attacks = sorted({r.attack_id for r in records}, key=_attack_order)
    stacks = sorted({r.defense_stack for r in records}, key=lambda s: (s != "none", s))
    grid = []
    for a in attacks:
        row = []
        for s in stacks:
            sub = [r for r in records if r.attack_id == a and r.defense_stack == s]
            row.append(metrics.asr(sub) * 100 if sub else float("nan"))
        grid.append(row)
    fig, ax = plt.subplots(figsize=(1.4 * len(stacks) + 2, 0.6 * len(attacks) + 2))
    im = ax.imshow(grid, cmap="RdYlGn_r", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(stacks))); ax.set_xticklabels(stacks, rotation=45, ha="right")
    ax.set_yticks(range(len(attacks))); ax.set_yticklabels(attacks)
    for i in range(len(attacks)):
        for j in range(len(stacks)):
            v = grid[i][j]
            if v == v:  # not NaN
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8)
    ax.set_title("ASR (%) — attack × defense")
    fig.colorbar(im, ax=ax, label="ASR (%)")
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)
    return path


def pareto_plot(front, path, knee=None, all_points=None):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6, 5))
    if all_points:
        ax.scatter([p[0] for p in all_points], [p[1] for p in all_points],
                   color="#bbb", s=20, label="all stacks")
    fx = [p[0] for p in front]; fy = [p[1] for p in front]
    ax.plot(fx, fy, "-o", color="#2980b9", label="Pareto front")
    if knee:
        ax.scatter([knee[0]], [knee[1]], color="#27ae60", s=120, marker="*",
                   zorder=5, label=f"knee: {knee[2]}")
    ax.set_xlabel("Utility"); ax.set_ylabel("Robustness (1 − ASR)")
    ax.set_title("Accuracy–robustness trade-off"); ax.legend()
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)
    return path


def adaptive_curve_plot(curve, path):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6, 4))
    rounds = list(range(1, len(curve) + 1))
    ax.plot(rounds, [c * 100 for c in curve], "-o", color="#8e44ad")
    ax.set_xlabel("Round"); ax.set_ylabel("Cumulative ASR (%)")
    ax.set_ylim(0, 100); ax.set_title("Adaptive attacker: ASR vs round")
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)
    return path


# ------------------------------ orchestrated save ------------------------------

def save_all(context: dict, outdir=None):
    """Render whatever artefacts are present in ``context``. Skips plots gracefully
    if matplotlib is unavailable. ``context`` keys (all optional):
    records, matrix_records, pareto, knee, pareto_all, adaptive_curve.
    """
    from . import config
    import pathlib
    outdir = pathlib.Path(outdir) if outdir else (config.artifact_dir() / "figures")
    outdir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    if context.get("records") is not None:
        written.append(records_to_csv(context["records"], outdir / "results.csv"))
        (outdir / "results_table.md").write_text(results_table(context["records"]), encoding="utf-8")
        written.append(str(outdir / "results_table.md"))

    try:
        if context.get("records") is not None:
            written.append(asr_bar(context["records"], outdir / "asr_bar.png"))
        if context.get("matrix_records") is not None:
            written.append(attack_defense_heatmap(context["matrix_records"], outdir / "heatmap.png"))
        if context.get("pareto") is not None:
            written.append(pareto_plot(context["pareto"], outdir / "pareto.png",
                                       knee=context.get("knee"), all_points=context.get("pareto_all")))
        if context.get("adaptive_curve") is not None:
            written.append(adaptive_curve_plot(context["adaptive_curve"], outdir / "adaptive.png"))
    except ImportError:
        written.append("(plots skipped: matplotlib not installed)")

    return written
