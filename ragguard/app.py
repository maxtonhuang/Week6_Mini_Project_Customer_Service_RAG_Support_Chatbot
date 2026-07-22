"""Gradio UI for RAGGuard — the presentation layer (Criterion 4).

Design: all logic lives in ``DemoController`` (pure Python, unit-tested offline with
the doubles). The Gradio wiring in ``build_app`` is a thin view over it and imports
gradio lazily, so this module imports fine without gradio installed.

Launch on Colab:
    from ragguard.app import launch
    launch(share=True)            # real models if available, else offline doubles
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Sequence

from . import config, detect
from .interfaces import Attack, Defense, Judge, Pipeline
from .schemas import Doc

# Attack metadata for the UI (label -> id). "None" = benign, use the free-text query.
ATTACK_CHOICES = [
    ("None (benign query)", "None"),
    ("A1 · Direct prompt injection", "A1"),
    ("A2 · Jailbreak / persona override", "A2"),
    ("A3 · Indirect injection (RAG poisoning)", "A3"),
    ("A4 · System-prompt extraction", "A4"),
    ("A5 · Canary / knowledge-base extraction", "A5"),
    ("A6 · Obfuscated injection (evasion)", "A6"),
]
DEFENSE_LABELS = {
    "D1": "D1 · Spotlighting + hardened prompt",
    "D2": "D2 · Input guardrail (injection classifier)",
    "D3": "D3 · Retrieval sanitisation",
    "D4": "D4 · Output filter (canary / PII / prompt-leak)",
    "D5": "D5 · Groundedness check",
    "D6": "D6 · De-obfuscation / normalisation",
}

# id -> human name / lab type, so IDs are never shown bare
ATTACK_NAME = {aid: lbl.split(" · ", 1)[1] for lbl, aid in ATTACK_CHOICES if aid != "None"}
ATTACK_LAB = {"A1": "LLM", "A2": "LLM", "A3": "Poisoning",
              "A4": "Extraction", "A5": "Extraction", "A6": "Evasion"}


@dataclass
class QueryResult:
    shown_input: str
    answer: str
    blocked: bool
    retrieved: list[Doc]
    fired_defenses: list[str]
    goal: str | None
    attack_success: bool | None
    refused: bool | None
    canary_leak: bool
    reason: str


class DemoController:
    """All non-UI logic. Testable offline; reused verbatim by the Gradio app."""

    def __init__(self, pipeline: Pipeline, attacks: Sequence[Attack], judge: Judge,
                 all_defenses: Sequence[Defense], canaries: Sequence[Doc] = (),
                 benign: Sequence[tuple[str, str]] = (), results: dict | None = None):
        self.pipeline = pipeline
        self.attacks = list(attacks)
        self.attacks_by_id = {a.id: a for a in attacks}
        self.judge = judge
        self.all_defenses = list(all_defenses)
        self.defenses_by_id = {d.id: d for d in all_defenses}
        self.canaries = list(canaries)
        self.benign = list(benign)
        self.results = results or {}

    # ---- construction ----
    @classmethod
    def offline(cls, seed: int = config.SEED) -> "DemoController":
        """Build a fully-offline controller (ScriptedLLM + KeywordRetriever)."""
        from . import corpus, prompts, rag
        from . import canary as canary_mod
        from .attacks import build_all_attacks
        from .defenses import build_all_defenses
        from .judge import RuleJudge
        from .testing import KeywordRetriever, ScriptedLLM

        docs, benign = corpus.build_knowledge_base(seed=seed)
        canaries = [d for d in docs if d.is_canary()]
        pipe = rag.RagPipeline(KeywordRetriever(docs), ScriptedLLM())
        judge = RuleJudge(canary_tokens=canary_mod.canary_tokens(canaries),
                          system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
        attacks = build_all_attacks(canary_docs=canaries)
        defenses = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
        return cls(pipe, attacks, judge, defenses, canaries, benign)

    # ---- helpers ----
    def defense_subset(self, defense_ids: Sequence[str]) -> list[Defense]:
        ids = set(defense_ids or [])
        return [d for d in self.all_defenses if d.id in ids]   # canonical order preserved

    def sample_case(self, attack_id: str):
        return self.attacks_by_id[attack_id].generate(1)[0]

    # ---- Tab 1: live demo ----
    def run_query(self, query: str, attack_id: str, defense_ids: Sequence[str]) -> QueryResult:
        defenses = self.defense_subset(defense_ids)
        if attack_id and attack_id != "None":
            case = self.sample_case(attack_id)
            resp = self.pipeline.answer(case.user_input, injected_docs=case.injected_docs,
                                        defenses=defenses)
            v = self.judge.verdict(case, resp)
            return QueryResult(case.user_input, resp.answer, resp.blocked, resp.retrieved,
                               resp.fired_defenses, str(case.goal.value),
                               v.success, v.refused,
                               bool(detect.CANARY_RE.search(resp.answer)), v.reason)
        resp = self.pipeline.answer(query, defenses=defenses)
        return QueryResult(query, resp.answer, resp.blocked, resp.retrieved,
                           resp.fired_defenses, None, None, None,
                           bool(detect.CANARY_RE.search(resp.answer)), "")

    @staticmethod
    def verdict_html(r: QueryResult) -> str:
        if r.goal is None:
            tone, msg = ("#0369a1", "Benign query")
        elif r.attack_success:
            tone, msg = ("#b91c1c", f"🔴 ATTACK SUCCEEDED — {r.reason or r.goal}")
        elif r.refused or r.blocked:
            fired = ", ".join(r.fired_defenses) or "refused"
            tone, msg = ("#15803d", f"🟢 BLOCKED by {fired}")
        else:
            tone, msg = ("#15803d", "🟢 attack failed")
        extra = " · ⚠️ CANARY LEAKED" if r.canary_leak else ""
        return (f'<div style="padding:10px 14px;border-radius:8px;color:#fff;'
                f'background:{tone};font-weight:600">{html.escape(msg)}{extra}</div>')

    @staticmethod
    def retrieved_markdown(docs: Sequence[Doc]) -> str:
        if not docs:
            return "_(no documents retrieved — blocked before retrieval)_"
        lines = []
        for d in docs:
            if d.is_canary():
                tag = "🔒 **INTERNAL/CANARY**"
            elif d.source == "web":
                tag = "☠️ **INJECTED (poisoned)**"
            else:
                tag = "📄 public"
            snippet = (d.text[:200] + "…") if len(d.text) > 200 else d.text
            lines.append(f"- {tag} · `{d.doc_id}`  \n  {html.escape(snippet)}")
        return "\n".join(lines)

    # ---- Tab 2: attack lab ----
    def attack_table(self, n: int, defense_ids: Sequence[str] | None = None) -> tuple[list[list], float]:
        from . import metrics, orchestrator
        defenses = self.defense_subset(defense_ids) if defense_ids else None
        recs = orchestrator.run_suite(self.pipeline, self.attacks, self.judge,
                                      defenses=defenses, n=n)
        by = metrics.group_asr(recs, "attack_id")
        rows = [[a.id, a.name, a.lab_type, f"{by.get(a.id, 0.0):.0%}"] for a in self.attacks]
        return rows, metrics.asr(recs)

    # ---- Tab 3: defense lab ----
    def defense_search(self, screen_n: int = None, benign_k: int = 10) -> dict:
        from . import orchestrator
        return orchestrator.two_stage_search(
            self.pipeline, self.attacks, self.judge, self.all_defenses,
            self.benign[:benign_k], screen_n=screen_n)

    # ---- Tab 4: governance ----
    def governance_markdown(self, results: dict | None = None) -> str:
        from . import governance
        base = governance.baseline_scorecard()
        deff = governance.defended_scorecard(results or self.results)
        return (governance.render_markdown(base) + "\n\n---\n\n"
                + governance.render_markdown(deff))

    # ---- cached artefacts (from the last full run) ----
    def artifact(self, name: str):
        """Absolute path to a saved artefact if it exists, else None."""
        p = config.artifact_dir() / name
        return str(p) if p.exists() else None

    def cached_attack_rows(self) -> list[list]:
        u = self.results.get("asr_by_attack_undefended", {})
        f = self.results.get("asr_by_attack_fullstack", {})
        ids = sorted(set(u) | set(f) | set(ATTACK_NAME))
        pct = lambda d, a: f"{d[a]:.0%}" if a in d else "–"
        return [[a, ATTACK_NAME.get(a, ""), ATTACK_LAB.get(a, ""), pct(u, a), pct(f, a)]
                for a in ids]

    def header_stats_html(self) -> str:
        r = self.results
        pct = lambda x: f"{x*100:.0f}%" if isinstance(x, (int, float)) else "—"
        chips = [
            f'<span class="chip"><b>Model</b> {html.escape(str(r.get("model", config.GEN_MODEL)))}</span>',
            f'<span class="chip red"><b>Undefended ASR</b> {pct(r.get("asr_undefended_overall"))}</span>',
            f'<span class="chip green"><b>Defended ASR</b> {pct(r.get("asr_fullstack_overall"))}</span>',
            f'<span class="chip teal"><b>Best stack</b> {html.escape(str(r.get("best_stack") or "—"))}</span>',
        ]
        return '<div id="rg-stats">' + "".join(chips) + "</div>"

    def best_summary_md(self) -> str:
        b = self.results.get("best") or {}
        if not b:
            return "_No saved results yet — run `run_full.py` (or `00_MAIN.ipynb`) first._"
        return (
            f"### Best defence stack: `{b.get('stack', '-')}`\n"
            f"- robustness **{b.get('robustness', 0):.0%}** · "
            f"utility **{b.get('utility', 0):.2f}** · FRR **{b.get('frr', 0):.0%}**\n"
            f"- overall ASR **{self.results.get('asr_undefended_overall', 0):.0%} → "
            f"{self.results.get('asr_fullstack_overall', 0):.0%}** · "
            f"{self.results.get('n_stacks_screened', 0)} stacks screened"
        )

    def evaluate_stack_quick(self, defense_ids, n: int = 4, benign_k: int = 8) -> str:
        """Fast live evaluation of one chosen defence stack (small samples)."""
        from . import orchestrator
        defs = self.defense_subset(defense_ids)
        m = orchestrator.evaluate_stack(self.pipeline, self.attacks, self.judge,
                                        defs or None, self.benign[:benign_k], n=n)
        return (f"### Stack `{m['stack']}`  _(quick: n={n}/attack, {benign_k} benign)_\n"
                f"- **ASR {m['asr']:.0%}** · robustness **{m['robustness']:.0%}**\n"
                f"- utility **{m['utility']:.2f}** · false-refusal **{m['frr']:.0%}** · "
                f"~{m['overhead']*1000:.0f} ms/query")

    # ---- demo script (4 beats) ----
    def demo_script(self, benign_query: str = "How do I reset my password?",
                    attack_id: str = "A5") -> str:
        beats = []
        r1 = self.run_query(benign_query, "None", [])
        beats.append(f"**1. It works** — _{benign_query}_\n\n> {r1.answer}")
        r2 = self.run_query("", attack_id, [])
        beats.append(f"**2. It breaks** — attack {attack_id}, no defenses\n\n> {r2.answer}\n\n"
                     f"{'⚠️ canary leaked' if r2.canary_leak else ''} (success={r2.attack_success})")
        best = ["D2", "D3", "D4"]
        r3 = self.run_query("", attack_id, best)
        beats.append(f"**3. We fix it** — enable {'+'.join(best)}\n\n> {r3.answer}\n\n"
                     f"(blocked by {', '.join(r3.fired_defenses) or 'defense'})")
        r4 = self.run_query(benign_query, "None", best)
        beats.append(f"**4. It still works** — same benign question, defenses on\n\n> {r4.answer}")
        return "\n\n".join(beats)


# ============================ Gradio wiring (lazy) ============================

def build_app(controller: DemoController):
    """Construct the gr.Blocks app. Imports gradio lazily."""
    import gradio as gr

    def _plot_asr(rows):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ids = [r[0] for r in rows]
        vals = [float(r[3].strip("%")) for r in rows]
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.bar(ids, vals, color="#b91c1c")
        ax.set_ylabel("ASR %"); ax.set_ylim(0, 100); ax.set_title("Attack success rate")
        fig.tight_layout()
        return fig

    _css = (
        ".gradio-container{max-width:1160px !important;margin:0 auto !important;}"
        "#rg-stats{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 12px;}"
        "#rg-stats .chip{padding:5px 12px;border-radius:999px;font-size:13px;"
        "background:var(--neutral-100);color:var(--body-text-color);"
        "border:1px solid var(--border-color-primary);}"
        "#rg-stats .chip.red{background:#fee2e2;color:#7f1d1d;border-color:#fecaca;}"
        "#rg-stats .chip.green{background:#dcfce7;color:#14532d;border-color:#bbf7d0;}"
        "#rg-stats .chip.teal{background:#ccfbf1;color:#134e4a;border-color:#99f6e4;}"
        ".step-card{border-radius:12px !important;padding:8px 14px 12px !important;"
        "margin-bottom:10px !important;border:1px solid var(--border-color-primary) !important;}"
        ".attack-card{border-left:4px solid #dc2626 !important;}"
        ".defense-card{border-left:4px solid #16a34a !important;}"
        ".section-hint{font-size:12px;color:#64748b;font-weight:400;}"
    )
    # Plain font names (no GoogleFont fetch) so the UI loads instantly offline —
    # uses Fira if installed locally, otherwise a clean system stack.
    theme = gr.themes.Soft(
        primary_hue="teal", secondary_hue="slate",
        font=["Fira Sans", "Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        font_mono=["Fira Code", "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
    )
    with gr.Blocks(title="RAGGuard — Trustworthy AI Demo", theme=theme, css=_css) as demo:
        gr.Markdown("# 🛡️ RAGGuard\n"
                    "*Trustworthy-AI red-team / blue-team demo — customer-service RAG chatbot*")
        gr.HTML(controller.header_stats_html())
        _prec = "4-bit" if config.LOAD_IN_4BIT else "bf16"
        gr.Markdown(f"<span style='font-size:12px;color:#64748b'>Runtime (auto-detected): "
                    f"{config.GEN_MODEL} · {_prec} · {config.device()} · batch {config.BATCH_SIZE}</span>")

        with gr.Tab("1 · Live Demo"):
            gr.Markdown("Ask a question, optionally launch an **attack**, and toggle **defenses**.")
            with gr.Accordion("ℹ️ How to use this demo (click to expand)", open=False):
                gr.Markdown(
                    "**The 60-second story — repeat with the four steps below (or just hit ▶ Run demo script):**\n\n"
                    "1. **It works** — Attack = *None*, no defenses ticked → **Ask**. A normal, helpful answer.\n"
                    "2. **It breaks** — Attack = *A1* or *A5*, still no defenses → **Ask**. Badge turns "
                    "🔴 *ATTACK SUCCEEDED* (the bot obeys the attacker or leaks a secret).\n"
                    "3. **We fix it** — tick **D2 + D3** (and **D6**) → **Ask** again. Badge turns 🟢 *BLOCKED*.\n"
                    "4. **It still works** — Attack = *None*, defenses still on → **Ask**. Still a good answer.\n\n"
                    "**Reading the output:** 🔵 benign · 🔴 attack succeeded · 🟢 blocked · ⚠️ canary leaked. "
                    "Retrieved docs are tagged 📄 public · 🔒 internal/canary · ☠️ injected. "
                    "*First answer is slow (model warm-up); the rest are fast. See UI_GUIDE.md for the full guide.*"
                )
            with gr.Row():
                with gr.Column(scale=5):
                    with gr.Group(elem_classes="step-card"):
                        gr.Markdown("**① Ask a question**")
                        query = gr.Textbox(value="How do I reset my password?", lines=2,
                                           show_label=False, container=False)
                    with gr.Group(elem_classes=["step-card", "attack-card"]):
                        gr.Markdown("**② Launch an attack** &nbsp;"
                                    "<span class='section-hint'>🔴 red-team · optional</span>")
                        attack = gr.Dropdown(choices=ATTACK_CHOICES, value="None",
                                             show_label=False, container=False)
                    with gr.Group(elem_classes=["step-card", "defense-card"]):
                        gr.Markdown("**③ Enable defences** &nbsp;"
                                    "<span class='section-hint'>🟢 blue-team</span>")
                        defenses = gr.CheckboxGroup(
                            choices=[(v, k) for k, v in DEFENSE_LABELS.items()],
                            show_label=False, container=False)
                    with gr.Row():
                        ask = gr.Button("Ask", variant="primary", scale=2)
                        script = gr.Button("▶ Run demo script", scale=1)
                with gr.Column(scale=6):
                    gr.Markdown("**Result**")
                    verdict = gr.HTML()
                    answer = gr.Textbox(label="Bot answer", lines=4)
                    retrieved = gr.Markdown()

            def _on_ask(q, a, ds):
                r = controller.run_query(q, a, ds or [])
                return (controller.verdict_html(r), r.answer,
                        "**Retrieved context**\n\n" + controller.retrieved_markdown(r.retrieved))
            ask.click(_on_ask, [query, attack, defenses], [verdict, answer, retrieved])
            script.click(lambda: ("", "", controller.demo_script()),
                         None, [verdict, answer, retrieved])

        with gr.Tab("2 · Attack Lab"):
            gr.Markdown("**Top:** the last full run. **Bottom:** run your own quick sweep live.")
            gr.Dataframe(value=controller.cached_attack_rows(),
                         headers=["ID", "Attack", "Type", "Undefended ASR", "Full-stack ASR"],
                         label="Per-attack ASR (undefended → full defence stack)")
            gr.Image(value=controller.artifact("asr_undefended.png"),
                     label="ASR per attack (undefended)", height=300)
            gr.Markdown("#### ↻ Run a quick attack sweep (live)")
            n_slider = gr.Slider(2, 20, value=5, step=1, label="Cases per attack")
            run_atk = gr.Button("Run attack sweep", variant="primary")
            atk_plot = gr.Plot(label="Live ASR")
            atk_table = gr.Dataframe(headers=["ID", "Attack", "Lab type", "ASR"],
                                     label="Live results")

            def _on_atk(n):
                rows, _ = controller.attack_table(int(n))
                return _plot_asr(rows), rows
            run_atk.click(_on_atk, n_slider, [atk_plot, atk_table])

        with gr.Tab("3 · Defense Lab"):
            gr.Markdown(controller.best_summary_md())
            with gr.Row():
                gr.Image(value=controller.artifact("heatmap.png"),
                         label="Full run — attack × defence ASR", height=320)
                gr.Image(value=controller.artifact("pareto.png"),
                         label="Full run — utility vs robustness (Pareto)", height=320)
            gr.Image(value=controller.artifact("adaptive_curve.png"),
                     label="Full run — adaptive attacker ASR by round", height=280)
            gr.Markdown("#### ↻ Evaluate any defence stack (live)")
            gr.Markdown("Tick defences and press **Evaluate** — a quick attack + benign "
                        "check on that exact stack.")
            def_boxes = gr.CheckboxGroup(
                choices=[(v, k) for k, v in DEFENSE_LABELS.items()],
                label="Defences to evaluate")
            eval_btn = gr.Button("Evaluate stack", variant="primary")
            eval_out = gr.Markdown()
            eval_btn.click(lambda ids: controller.evaluate_stack_quick(ids or []),
                           def_boxes, eval_out)

        with gr.Tab("4 · Governance"):
            gr.Markdown("**NIST AI RMF scorecard** — before vs after defences "
                        "(🔴 gap · 🟡 partial · 🟢 managed).")
            gov = gr.Markdown(controller.governance_markdown())

    return demo


def _has_heavy_deps() -> bool:
    import importlib.util
    return all(importlib.util.find_spec(m) for m in ("torch", "transformers",
                                                     "sentence_transformers", "faiss"))


def launch(share: bool = True, offline: bool | None = None, seed: int = config.SEED, **kw):
    """Build and launch the app. offline=None auto-detects (real models if available)."""
    if offline is None:
        offline = not _has_heavy_deps()
    if offline:
        controller = DemoController.offline(seed=seed)
    else:
        from . import corpus, prompts, rag
        from . import canary as canary_mod
        from .attacks import build_all_attacks
        from .defenses import build_all_defenses
        from .judge import RuleJudge
        docs, benign = corpus.build_knowledge_base(seed=seed)
        canaries = [d for d in docs if d.is_canary()]
        pipe = rag.build_pipeline(offline=False)
        judge = RuleJudge(canary_tokens=canary_mod.canary_tokens(canaries),
                          system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
        attacks = build_all_attacks(canary_docs=canaries)
        defenses = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
        controller = DemoController(pipe, attacks, judge, defenses, canaries, benign)
    return build_app(controller).launch(share=share, **kw)
