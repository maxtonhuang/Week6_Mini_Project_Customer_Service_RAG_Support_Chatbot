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
    ("A8 · Membership inference", "A8"),
    ("A9 · Fingerprint / IP-ownership probe", "A9"),
    ("A10 · Paraphrased system-prompt extraction", "A10"),
]
DEFENSE_LABELS = {
    "D1": "D1 · Spotlighting + hardened prompt",
    "D2": "D2 · Input guardrail (injection classifier)",
    "D3": "D3 · Retrieval sanitisation",
    "D4": "D4 · Output filter (canary / PII / prompt-leak)",
    "D5": "D5 · Groundedness check",
    "D6": "D6 · De-obfuscation / normalisation",
    "D7": "D7 · Visibility access-control (internal docs)",
    "D8": "D8 · Query-rate limit / budget",
    "D9": "D9 · Semantic leak & fingerprint filter",
}

# id -> human name / lab type, so IDs are never shown bare
ATTACK_NAME = {aid: lbl.split(" · ", 1)[1] for lbl, aid in ATTACK_CHOICES if aid != "None"}
ATTACK_LAB = {"A1": "LLM", "A2": "LLM", "A3": "Poisoning",
              "A4": "Extraction", "A5": "Extraction", "A6": "Evasion",
              "A8": "Extraction", "A9": "Extraction", "A10": "Extraction"}


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
        self._run_log = ""            # latest Run-tab progress; survives tab switches / reloads

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

    def sample_case_at_level(self, attack_id: str, level: int = 0):
        """One attack case at sophistication level 0/1/2 for the Live Demo. Level 0 (or a
        family not on the ladder, e.g. adaptive A7) falls back to the production L0 case."""
        if not level:
            return self.sample_case(attack_id)
        from .attacks.levels import LADDER_FAMILIES, level_cases
        if attack_id not in LADDER_FAMILIES:
            return self.sample_case(attack_id)
        return level_cases(attack_id, int(level), 1,
                           production=self.attacks_by_id, canary_docs=self.canaries)[0]

    def ladder_markdown(self) -> str:
        """Markdown table of the sophistication ladder (from the last saved run), or a hint."""
        lad = self.results.get("ladder")
        if not lad:
            return ("_No ladder data yet — run the pipeline on the **Run Pipeline** tab "
                    "(it computes the L0/L1/L2 × D0/D1/D2 matrix)._")
        from . import report
        return report.ladder_table_md(lad)

    # ---- Tab 1: live demo ----
    def run_query(self, query: str, attack_id: str, defense_ids: Sequence[str],
                  level: int = 0) -> QueryResult:
        defenses = self.defense_subset(defense_ids)
        # reset_session=False: the Live Demo is one persistent session, so D8's rate limit
        # accumulates across repeated Asks (that's how you see it throttle).
        if attack_id and attack_id != "None":
            case = self.sample_case_at_level(attack_id, level)
            resp = self.pipeline.answer(case.user_input, injected_docs=case.injected_docs,
                                        defenses=defenses, reset_session=False)
            v = self.judge.verdict(case, resp)
            return QueryResult(case.user_input, resp.answer, resp.blocked, resp.retrieved,
                               resp.fired_defenses, str(case.goal.value),
                               v.success, v.refused,
                               bool(detect.CANARY_RE.search(resp.answer)), v.reason)
        resp = self.pipeline.answer(query, defenses=defenses, reset_session=False)
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
        # numeric sort so A10 follows A9 (not string-sorted between A1 and A2)
        ids = sorted(set(u) | set(f) | set(ATTACK_NAME),
                     key=lambda a: (int(a[1:]) if a[1:].isdigit() else 10**9, a))
        pct = lambda d, a: f"{d[a]:.0%}" if a in d else "–"
        return [[a, ATTACK_NAME.get(a, ""), ATTACK_LAB.get(a, ""), pct(u, a), pct(f, a)]
                for a in ids]

    def header_stats_html(self) -> str:
        r = self.results
        pct = lambda x: f"{x*100:.0f}%" if isinstance(x, (int, float)) else "—"

        def stat(label: str, value, tone: str = "") -> str:
            cls = ("stat " + tone).strip()
            return (f'<span class="{cls}"><span class="lbl">{html.escape(label)}</span>'
                    f'<span class="val">{html.escape(str(value))}</span></span>')
        # Flat label+value read-out (not clickable pills): a summary strip, not buttons.
        stats = [
            stat("Model", r.get("model", config.GEN_MODEL)),
            stat("Undefended ASR", pct(r.get("asr_undefended_overall")), "red"),
            stat("Defended ASR", pct(r.get("asr_fullstack_overall")), "green"),
            stat("Best stack", r.get("best_stack") or "—", "teal"),
        ]
        return ('<div id="rg-stats" role="group" aria-label="Run summary (read-only)">'
                + "".join(stats) + "</div>")

    def best_summary_md(self) -> str:
        r = self.results
        b = r.get("best") or {}
        if not b:
            return "_No saved results yet — run `run_full.py` (or `00_MAIN.ipynb`) first._"
        lines = [
            f"### Best defence stack: `{b.get('stack', '-')}`",
            f"- robustness **{b.get('robustness', 0):.0%}** · "
            f"utility **{b.get('utility', 0):.2f}** · FRR **{b.get('frr', 0):.0%}**",
            f"- overall ASR **{r.get('asr_undefended_overall', 0):.0%} → "
            f"{r.get('asr_fullstack_overall', 0):.0%}** (undefended → full D1–D9 stack) · "
            f"{r.get('n_stacks_screened', 0)} of 64 stacks screened",
        ]
        # Optuna threshold tuning (a whole phase — surface its result)
        tt = r.get("tuned_thresholds") or {}
        tm = r.get("tuned_metrics") or {}
        if tt:
            thr = " · ".join(f"`{k}`={v:.2f}" for k, v in tt.items())
            tail = (f" → robustness {tm.get('robustness', 0):.0%} / FRR {tm.get('frr', 0):.0%}"
                    if tm else "")
            lines.append(f"- **Optuna-tuned thresholds:** {thr}{tail}")
        else:
            lines.append("- **Optuna:** best stack has no continuous thresholds to tune")
        # Adaptive attacker (A7) vs the best stack — LLM-driven + heuristic baseline
        curve = r.get("adaptive_curve") or []
        hcurve = r.get("adaptive_curve_heuristic") or []
        if curve:
            hb = f" · heuristic **{hcurve[-1]:.0%}**" if hcurve else ""
            lines.append(
                f"- **Adaptive attacker** (A7) vs `{r.get('adaptive_vs_stack', '-')}`, "
                f"{len(curve)} rounds: cumulative ASR LLM **{curve[-1]:.0%}**{hb} "
                f"— curve `{' → '.join(f'{x:.0%}' for x in curve)}`")
        el = r.get("elapsed_s")
        meta = f"{r.get('mode', '?')} run · model `{r.get('model', '')}`"
        if isinstance(el, (int, float)):
            meta += f" · full-run compute {el / 60:.1f} min"
        lines.append(f"\n<sub>{meta}</sub>")
        return "\n".join(lines)

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
        best = ["D4", "D5"]
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
        # Header = a flat read-only STAT STRIP (label + value, divided), deliberately NOT
        # pill/filled buttons — so it reads as a summary read-out, not clickable controls.
        # Colours are explicit per-theme (not theme tokens) so contrast holds ≥4.5:1 in both.
        "#rg-stats{display:flex;flex-wrap:wrap;align-items:center;margin:2px 0 14px;"
        "font-size:13px;cursor:default;}"
        "#rg-stats .stat{display:inline-flex;align-items:baseline;gap:7px;padding:0 18px;"
        "border-right:1px solid #e2e8f0;}"
        "#rg-stats .stat:first-child{padding-left:0;}"
        "#rg-stats .stat:last-child{border-right:none;padding-right:0;}"
        "#rg-stats .stat .lbl{color:#64748b;font-size:11px;font-weight:600;"
        "text-transform:uppercase;letter-spacing:.04em;}"
        "#rg-stats .stat .val{font-weight:700;color:#0f172a;}"
        "#rg-stats .stat.red .val{color:#b91c1c;}"
        "#rg-stats .stat.green .val{color:#15803d;}"
        "#rg-stats .stat.teal .val{color:#0f766e;}"
        ".dark #rg-stats .stat{border-right-color:#334155;}"
        ".dark #rg-stats .stat .lbl{color:#94a3b8;}"
        ".dark #rg-stats .stat .val{color:#e2e8f0;}"
        ".dark #rg-stats .stat.red .val{color:#f87171;}"
        ".dark #rg-stats .stat.green .val{color:#4ade80;}"
        ".dark #rg-stats .stat.teal .val{color:#2dd4bf;}"
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
        hdr = gr.HTML(controller.header_stats_html())
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
                    "3. **We fix it** — tick **D4 + D5** → **Ask** again. Badge turns 🟢 *BLOCKED*.\n"
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
                                    "<span class='section-hint'>🔴 attack · optional</span>")
                        attack = gr.Dropdown(choices=ATTACK_CHOICES, value="None",
                                             show_label=False, container=False)
                        level = gr.Dropdown(
                            choices=[("L0 · production (blunt)", 0), ("L1 · intermediate", 1),
                                     ("L2 · advanced", 2)],
                            value=0, label="Sophistication level (applies when an attack is chosen)")
                    with gr.Group(elem_classes=["step-card", "defense-card"]):
                        gr.Markdown("**③ Enable defences** &nbsp;"
                                    "<span class='section-hint'>🟢 defences</span>")
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

            def _on_ask(q, a, ds, lv):
                r = controller.run_query(q, a, ds or [], level=int(lv or 0))
                return (controller.verdict_html(r), r.answer,
                        "**Retrieved context**\n\n" + controller.retrieved_markdown(r.retrieved))
            ask.click(_on_ask, [query, attack, defenses, level], [verdict, answer, retrieved])
            script.click(lambda: ("", "", controller.demo_script()),
                         None, [verdict, answer, retrieved])

        with gr.Tab("2 · Attack Lab"):
            gr.Markdown("**Top:** the last full run. **Bottom:** run your own quick sweep live.")
            cached_tbl = gr.Dataframe(value=controller.cached_attack_rows(),
                         headers=["ID", "Attack", "Type", "Undefended ASR", "Full-stack ASR"],
                         label="Per-attack ASR (undefended → full defence stack)")
            asr_img = gr.Image(value=controller.artifact("asr_undefended.png"),
                     label="ASR per attack (undefended)", height=300)

            gr.Markdown("#### 🪜 Sophistication ladder — attacks **L0/L1/L2** × defences **D0/D1/D2**")
            gr.Markdown("<span class='section-hint'>Smarter attacks (L0 blunt → L2 composed) vs. "
                        "stronger defences (D0 none → D1 content filters → D2 defence-in-depth). "
                        "Each cell is ASR; lower-right = hardest attack meets strongest defence.</span>")
            ladder_img = gr.Image(value=controller.artifact("ladder_heatmap.png"),
                     label="Overall ASR — attack level × defence level", height=300)
            ladder_tbl = gr.Markdown(controller.ladder_markdown())

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
            best_md = gr.Markdown(controller.best_summary_md())
            with gr.Row():
                heat_img = gr.Image(value=controller.artifact("heatmap.png"),
                         label="Full run — attack × defence ASR", height=320)
                pareto_img = gr.Image(value=controller.artifact("pareto.png"),
                         label="Full run — utility vs robustness (Pareto)", height=320)
            adap_img = gr.Image(value=controller.artifact("adaptive_curve.png"),
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

        with gr.Tab("5 · Run Pipeline") as run_tab:
            gr.Markdown(
                "Run **all attacks + defenses** across the whole pipeline and populate every tab. "
                "Results + resumable checkpoints save to `artifacts/` — or to **Google Drive** "
                "if it's mounted, so they survive a reload. A re-run **resumes** from saved "
                "checkpoints — so if a run already finished it completes in seconds instead of "
                "recomputing. Tick **Start fresh** to force every phase to recompute.")
            with gr.Row():
                profile = gr.Radio(["Quick (~minutes)", "Full (~hours, resumable)"],
                                   value="Quick (~minutes)", label="Profile", scale=3)
                run_btn = gr.Button("▶ Run Quick pipeline", variant="primary", scale=1)
                stop_btn = gr.Button("⏹ Stop run", variant="stop", scale=1)
            from .fullrun import PROFILES as _PROF
            _q, _f = _PROF["quick"], _PROF["full"]
            gr.Markdown(
                "<span class='section-hint'>Both profiles run the <b>same phases</b> on all 9 attacks and "
                "every defence (undefended suite · full-stack defence · 64-stack search · Optuna tuning · "
                "adaptive attacker · <b>sophistication ladder</b> L0/L1/L2 × D0/D1/D2) — only the "
                "<b>sample sizes</b> differ, so Full is more statistically reliable but slower.<br>"
                f"&nbsp;•&nbsp;<b>Quick</b> — {_q['n']} prompts/attack · {_q['rounds']} adaptive rounds · defence "
                f"search screens each stack on {_q['screen_n']} attacks + {_q['screen_benign']} benign · "
                f"ladder {min(_q['n'], 12)}/cell: a fast pass that still fills every tab, for demos &amp; "
                "sanity checks (minutes, not hours).<br>"
                f"&nbsp;•&nbsp;<b>Full</b> — {_f['n']} prompts/attack · {_f['rounds']} rounds · {_f['screen_n']} "
                f"attacks + {_f['screen_benign']} benign per screen · ladder {min(_f['n'], 12)}/cell: the "
                "report-grade numbers you cite in the write-up (hours, and resumable if the runtime "
                "disconnects).</span>")
            fresh = gr.Checkbox(
                value=False,
                label="Start fresh — ignore saved checkpoints and recompute every phase")
            reload_btn = gr.Button("🔄 Reload saved results into the other tabs", size="sm")
            gr.Markdown("<span class='section-hint'>Re-reads the last saved `results.json` and refreshes the "
                        "header stats + the **Attack Lab / Defense Lab / Governance** tabs — use it after a "
                        "run here, or after running `run_full.py` in a terminal. (It doesn't change "
                        "anything on this tab; the confirmation appears in the log below.)</span>")
            run_log = gr.Markdown("_Idle — pick a profile, tick Start fresh if you want a clean run, then press Run._")

        # ---- Run tab refreshes every results-backed panel on completion ----
        from . import fullrun
        results_out = [hdr, cached_tbl, asr_img, ladder_img, ladder_tbl,
                       best_md, heat_img, pareto_img, adap_img, gov]

        def _refresh_all():
            controller.results = fullrun.load_saved_results() or controller.results
            return (controller.header_stats_html(), controller.cached_attack_rows(),
                    controller.artifact("asr_undefended.png"),
                    controller.artifact("ladder_heatmap.png"), controller.ladder_markdown(),
                    controller.best_summary_md(),
                    controller.artifact("heatmap.png"), controller.artifact("pareto.png"),
                    controller.artifact("adaptive_curve.png"), controller.governance_markdown())

        def _run_gen(profile_label, fresh_flag):
            # Run the pipeline in a background thread and stream its progress. A heartbeat
            # with an elapsed timer is emitted every few seconds so a long phase (e.g. the
            # 64-stack search) never looks frozen; the run continues across tab switches.
            import threading, queue, time
            from . import orchestrator
            prof = "quick" if str(profile_label).startswith("Quick") else "full"
            q: "queue.Queue" = queue.Queue()
            _DONE = object()
            stop_event = threading.Event()
            controller._stop_event = stop_event   # the ⏹ Stop button sets this

            def _worker():
                try:
                    for msg in fullrun.run(prof, controller=controller, fresh=bool(fresh_flag),
                                           should_stop=stop_event.is_set):
                        q.put(msg)
                except orchestrator.RunCancelled:
                    q.put("⏹ stopped by user — previous saved results kept (nothing overwritten). "
                          "Completed phases are checkpointed, so pressing Run resumes from here.")
                except Exception as e:                       # surface errors in the log
                    q.put(f"ERROR: {e}")
                finally:
                    controller._stop_event = None
                    q.put(_DONE)

            threading.Thread(target=_worker, daemon=True).start()
            lines: list[str] = []
            start = time.time()

            def _render(extra=""):
                body = "\n".join(lines[-60:] + ([extra] if extra else []))
                controller._run_log = "```\n" + body + "\n```"   # also kept server-side
                return controller._run_log

            while True:
                try:
                    item = q.get(timeout=3)
                except queue.Empty:
                    item = None
                if item is _DONE:
                    yield _render()
                    return
                if item is not None:
                    lines.append(item)
                el = int(time.time() - start)
                yield _render(f"[ still running -- elapsed {el // 60}m{el % 60:02d}s ]")

        _idle = "_Idle — pick a profile, tick Start fresh if you want a clean run, then press Run._"

        def _ck_count(profile_label):
            # How many of the 6 phase checkpoints already exist for this profile — drives the
            # button's Run/Resume wording so a seconds-long resume is never a surprise.
            prof_dir = "full_fast" if str(profile_label).startswith("Quick") else "full"
            ck = config.artifact_dir() / prof_dir
            return len(list(ck.glob("*.json"))) if ck.exists() else 0

        def _btn_label(profile_label, fresh_flag):
            word = "Quick" if str(profile_label).startswith("Quick") else "Full"
            n = _ck_count(profile_label)
            if n and not fresh_flag:
                return gr.update(value=f"↻ Resume {word} run ({n}/7 saved)")
            return gr.update(value=f"▶ Run {word} pipeline")

        def _stop_run():
            # Signal the in-flight run to abort at the next phase/loop boundary. The run raises
            # RunCancelled BEFORE results.json is written, so saved results are never touched.
            ev = getattr(controller, "_stop_event", None)
            if ev is not None:
                ev.set()
                note = "\n_(stop requested — finishing the current step, then halting; saved results are kept.)_"
            else:
                note = "\n_(nothing is running.)_"
            controller._run_log = (controller._run_log or _idle) + note
            return controller._run_log

        def _reload():
            # Re-read results.json from disk (e.g. after an external run_full.py) into every
            # panel, and confirm in the log so it's clearly not a no-op.
            vals = _refresh_all()
            r = controller.results
            if r:
                msg = ("```\n[reload] saved results loaded from artifacts/  |  undefended "
                       f"{r.get('asr_undefended_overall', 0):.0%} -> {r.get('asr_fullstack_overall', 0):.0%}"
                       f"  |  best stack {r.get('best_stack', '-')}\n```")
            else:
                msg = "_No saved results in artifacts/ yet — run the pipeline first._"
            controller._run_log = msg
            return (*vals, msg)

        run_btn.click(_run_gen, [profile, fresh], run_log) \
               .then(_refresh_all, None, results_out) \
               .then(_btn_label, [profile, fresh], run_btn)      # a fresh run creates checkpoints -> becomes "Resume"
        reload_btn.click(_reload, None, results_out + [run_log])
        # Stop runs OUTSIDE the queue (queue=False) so it fires even while the run generator
        # is streaming and holding the queue worker — it just sets a threading.Event.
        stop_btn.click(_stop_run, None, run_log, queue=False)
        # Keep the button's Run/Resume wording in sync with the current selection so it
        # always reflects what pressing it will actually do.
        profile.change(_btn_label, [profile, fresh], run_btn)
        fresh.change(_btn_label, [profile, fresh], run_btn)
        # Re-show the in-progress (or last) run whenever the Run tab is re-opened —
        # the run itself keeps going server-side regardless of which tab is visible.
        run_tab.select(lambda: controller._run_log or _idle, None, run_log)
        # On first page load, reflect any existing checkpoints in the button (▶ Run vs ↻ Resume)
        # instead of always showing the static default until the user touches a control.
        demo.load(_btn_label, [profile, fresh], run_btn)

    return demo


def _has_heavy_deps() -> bool:
    import importlib.util
    return all(importlib.util.find_spec(m) for m in ("torch", "transformers",
                                                     "sentence_transformers", "faiss"))


def launch(share: bool | None = None, offline: bool | None = None,
           seed: int = config.SEED, **kw):
    """Build and launch the app. offline=None auto-detects (real models if available).

    On a GPU this **auto-configures the model for the available VRAM** (bf16 / 4-bit /
    smaller model) via ``autotune`` — the same path ``serve_app.py`` uses — so an 8B model
    fits a 16 GB Colab GPU instead of spilling to CPU/disk. Progress is printed at each step.

    ``share`` defaults to env ``RAGGUARD_SHARE`` (on). The public ``gradio.live`` link can be
    slow/flaky on Colab; pass ``share=False`` for a reliable inline view in the cell instead.
    """
    import os

    def _log(m):
        print(f"[RAGGuard] {m}", flush=True)

    if offline is None:
        offline = not _has_heavy_deps()
    if offline:
        _log("offline mode — building the lightweight demo (no GPU model).")
        controller = DemoController.offline(seed=seed)
    else:
        from . import autotune, corpus, prompts, rag
        from . import canary as canary_mod
        from .attacks import build_all_attacks
        from .defenses import build_all_defenses
        from .judge import RuleJudge
        _log("auto-detecting GPU / VRAM…")
        autotune.apply()   # bf16 / 4-bit / smaller model to fit the GPU (+ installs bitsandbytes if needed)
        _log(f"config: model={config.GEN_MODEL} · {'4-bit' if config.LOAD_IN_4BIT else 'bf16'} · "
             f"{config.device()} · batch {config.BATCH_SIZE}")
        _log("loading corpus + knowledge base…")
        docs, benign = corpus.build_knowledge_base(seed=seed)
        canaries = [d for d in docs if d.is_canary()]
        _log("loading the model + embedder — the slow step (~16 GB; the first run downloads it "
             "unless the Drive cache is on)…")
        pipe = rag.build_pipeline(offline=False)
        # Wrap the model in the disk generation cache so a Run/Resume reuses generations across
        # runs (and shares the CLI's gen_cache.json) instead of recomputing every prompt.
        from .cache import CachedLLM
        if getattr(pipe, "llm", None) is not None and not isinstance(pipe.llm, CachedLLM):
            pipe.llm = CachedLLM(pipe.llm, path=config.artifact_dir() / "gen_cache.json")
        judge = RuleJudge(canary_tokens=canary_mod.canary_tokens(canaries),
                          system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
        attacks = build_all_attacks(canary_docs=canaries)
        defenses = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
        controller = DemoController(pipe, attacks, judge, defenses, canaries, benign)
        _log("model ready.")
    # On Colab with Drive mounted-but-empty the active artifact dir has no results yet; seed it
    # from the cloned repo's committed ./artifacts so the graphs/tables aren't blank. No-op locally.
    if config.seed_artifacts_from_repo():
        _log("seeded results/plots from the repo's committed artifacts/ (empty Drive/artifact dir)")
    # Load the last full run's results (from artifacts/ or a mounted Drive) so the
    # Attack / Defense / Governance tabs show real numbers right away.
    from . import fullrun
    controller.results = fullrun.load_saved_results() or controller.results
    import gradio as gr
    gr.close_all()   # release any server left by a previous run so re-running this cell is safe
    app = build_app(controller)
    app.queue()      # enable streaming for the Run tab's progress log
    if share is None:
        share = os.environ.get("RAGGUARD_SHARE", "1").lower() not in ("0", "false", "no")
    _log("starting the UI… " + ("creating the public gradio.live link — this can take ~30–60 s "
                                 "on Colab. If it stalls, re-run with share=False for an inline view."
                                 if share else "rendering inline in this cell (no public link)."))
    # allowed_paths lets Gradio serve the plot PNGs from the artifact dir wherever it lives
    # (repo/artifacts, a mounted Drive, or a custom RAGGUARD_ARTIFACTS) — the Run tab's refresh
    # returns those image paths, and Gradio blocks paths outside cwd/temp unless allow-listed.
    kw.setdefault("allowed_paths", [str(config.artifact_dir())])
    return app.launch(share=share, show_error=True, **kw)
