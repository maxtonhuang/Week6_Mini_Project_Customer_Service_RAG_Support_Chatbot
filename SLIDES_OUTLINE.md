<!--
============================================================================
 RAGGuard — SLIDE-DECK OUTLINE  (10-min talk incl. 2–3 min demo + 5-min Q&A)
============================================================================
Criterion 4 (20%): presentation + attack/defence demo + Q&A + report.

HOW TO USE
  • One slide per block below. Timings sum to ~10 min (demo = 2.5 min of it).
  • "SHOW" = the visual (drop in the named figure from artifacts/).
  • "SAY" = pre-filled talking points (facts/numbers are real — verify).
  • "✍️" = personalise / decide as a team.
  • Design: ONE idea per slide, big visuals, ≤6 lines of text, no paragraphs.
    Let the plots do the talking; you narrate the story.
  • VERIFY every number against artifacts/results.json before the talk.
============================================================================
-->

# RAGGuard — Presentation Outline
**Format:** 10-min live talk (incl. **2–3 min demo**) + **5-min Q&A**
**Narrative arc:** *It works → it breaks → we measure → we fix → what it costs.*

**Speaker split (✍️ decide — the brief requires every member to contribute):**
Member A = §Setup+Threat (slides 1–4) · Member B = §Attacks (5–7) · Member C = §Defences (8–10) · Member D = §Demo + Close. Rotate for Q&A.

---

### Slide 1 — Title  ·  ~15s
- **SHOW:** project title, team names, one-line tagline, the 🛡️ logo / a UI screenshot.
- **SAY:** "We red-teamed and then defended a customer-service RAG chatbot."
- ✍️ team names + module.

### Slide 2 — The system & why it's risky  ·  ~45s  ·  [C1]
- **SHOW:** the architecture diagram (Fig 1 from the report) — user → embed → FAISS (public **+ internal** docs) → Qwen3-8B → answer.
- **SAY:** RAG support bot: `Qwen3-8B` + `MiniLM` + `FAISS` over a Bitext FAQ corpus.
  The catch: **internal/confidential docs live in the same index as public FAQs**, and
  the LLM treats user text *and* retrieved text as trusted.
- **SAY:** We planted **40 "canary" documents** with unique tokens → leakage becomes a
  deterministic string match (reproducible ASR).

### Slide 3 — Threat model  ·  ~45s  ·  [C1]
- **SHOW:** the attacker box (goals · capabilities · surface) + the 6-attack table.
- **SAY:** Black-box attacker (a normal user). Two channels of untrusted input: the
  **user query** and the **retrieved context**. Goals: leak secrets, break policy, obey
  injected instructions.
- **SAY:** Risks (map to OWASP-LLM): **LLM01 prompt injection**, **LLM06 sensitive-info
  disclosure**.

### Slide 4 — Governance baseline (NIST AI RMF)  ·  ~40s  ·  [C1]
- **SHOW:** baseline scorecard — mostly 🔴 (Map/Measure/Manage). (`artifacts/governance.md`)
- **SAY:** Before any controls we scored the system against NIST AI RMF. Undefended = red
  across the board: no threat map, no adversarial measurement, no controls. That's our
  starting point.

### Slide 5 — How we attack & measure  ·  ~40s  ·  [C2]
- **SHOW:** the 6 attacks + A7 adaptive; the ASR definition; "rule-based judge".
- **SAY:** 6 attack families (LLM / extraction / poisoning / evasion) + an **adaptive
  agent**. **ASR** = fraction where a **deterministic judge** confirms the goal (canary
  match, prompt-leak n-grams, injected-marker echo). Deterministic = reproducible &
  defensible under Q&A.

### Slide 6 — Attack results ⭐  ·  ~60s  ·  [C2]
- **SHOW:** `artifacts/asr_undefended.png` (per-attack ASR bar chart). Big.
- **SAY (real numbers):** Overall undefended **ASR 25%**. **A1 direct injection 88%**,
  A5 canary-extraction 24%, A2 jailbreak 26% — but **A4 system-prompt extraction 0%**
  (the aligned 8B model resists it).
- **SAY:** The spread (not a saturated ~100%) is *because* we used a genuinely aligned
  model — attacks are non-trivial, so the defence story is meaningful.

### Slide 7 — Adaptive attacker  ·  ~30s  ·  [C2/C3]
- **SHOW:** `artifacts/adaptive_curve.png`.
- **SAY:** A PAIR-style loop with the **real Qwen3-8B as the mutator**, run **against our
  best stack (D4+D5)**. Across **6 rounds it never breaks through — 0% ASR**. The defence
  holds even under an adaptive LLM attacker (D4/D5 filter *after* generation).

### Slide 8 — Defences  ·  ~45s  ·  [C3]
- **SHOW:** D1–D6 at 3 hook points (pre-retrieval / post-retrieval / post-generation).
- **SAY:** Six defences across three hook points. Ordering matters — **D6 de-obfuscation
  runs before D2 the classifier**, or the classifier never sees the decoded payload.

### Slide 9 — What robustness costs ⭐⭐  ·  ~70s  ·  [C3]  *(your strongest slide)*
- **SHOW:** `artifacts/heatmap.png` (attack×defence) **and** `artifacts/pareto.png`.
- **SAY (real numbers):** We searched **all 64 defence stacks**, then **Optuna-tuned** the
  winner's threshold (D5→0.18). Best = **D4 + D5** (output filter + groundedness):
  **ASR 25% → 0%**, **false-refusal 0%**, utility preserved (0.45) on a **held-out benign
  set disjoint from the KB**. A *minimal* two-defence stack neutralises every attack at
  **no** cost to legitimate users.
- **SAY:** That's the accuracy–robustness tradeoff, measured — not asserted.

### Slide 10 — Governance re-score + deployment  ·  ~30s  ·  [C3]
- **SHOW:** baseline → defended scorecard (🔴→🟢) + risk→control mapping.
- **SAY:** Post-defence, RMF Measure/Manage move to green. For real deployment we'd add
  index segregation for internal docs, canary-hit alerting, and periodic re-testing.

### 🎬 DEMO — live, on the Gradio UI  ·  **~2.5 min**  ·  [C2+C3+C4]
> Launch `serve_app.py` (or `01_DEMO.ipynb`) BEFORE the talk so the model is warm.
> **Have the backup screen-recording ready** in case wifi/UI fails.

Four beats on **Tab 1 · Live Demo** (use the **▶ Run demo script** button to avoid mis-clicks):
1. **It works** — benign question, no defences → helpful answer.
2. **It breaks** — pick **A1** (or A5), no defences → 🔴 *ATTACK SUCCEEDED* (bot obeys / canary leaks).
3. **We fix it** — tick **D4 + D5** → 🟢 *BLOCKED*.
4. **It still works** — re-ask the benign question, defences on → still correct.
- Optionally flash **Tab 2 (named ASR table)** and **Tab 3 (Pareto)** for 5 seconds each.
- ✍️ Rehearse to hit 2.5 min. One person drives, one narrates.

### Slide 11 — Takeaways  ·  ~25s
- **SAY:** (1) RAG bots leak because untrusted text is trusted; (2) a stronger victim
  gives realistic numbers (25%, not 100%); (3) a **minimal** stack (D4+D5) → **0% ASR at
  0% false-refusals**; (4) governance moved red→green.
- ✍️ one forward-looking line (LLM-driven attacker, larger model, real PII controls).

### Slide 12 — Q&A / backup  ·  (holds during 5-min Q&A)
- **SHOW:** "Thank you — questions?" + repo link + a small results recap.
- Keep **backup slides** after this (full ASR table, transcripts, method details).

---

## Anticipated Q&A — prep answers (✍️ refine)
- **"Why is A4 0% but A1 88%?"** → A4 asks the model to reveal its own instructions — Qwen3-8B is aligned against that; A1 injects a concrete instruction the model follows. Model-capability finding.
- **"Isn't 8B too small / why not GPT-4?"** → We need a *self-hostable, reproducible, attackable* victim with real alignment; the 8B runs on a single GPU (auto-scaling to available VRAM) and gives non-saturated ASR. Bigger = future work.
- **"How do you know defences don't just refuse everything?"** → We measure **false-refusal rate on 150 benign queries** — the best stack is **0%**.
- **"Is the judge reliable?"** → Deterministic rules (canary string, n-gram overlap) — reproducible; canaries make extraction exact. (LLM-judge cross-check available.)
- **"Adaptive attacker flat — is that a failure?"** → It's an honest negative result; heuristic mutations didn't beat the refusals. We report it, we don't hide it.
- **"Real-world fix?"** → Segregate internal docs behind access-controlled retrieval; don't co-mingle with public FAQs; monitor canary hits.

## Logistics checklist (✍️)
- [ ] Deck ≤ ~12 slides, one idea each, big figures, minimal text.
- [ ] Every member speaks (contribution requirement).
- [ ] Demo rehearsed to time; UI pre-warmed; **backup recording on a local drive**.
- [ ] Total run-through ≤ 10 min (leave buffer); Q&A answers rehearsed.
- [ ] Export to PDF/PPTX for submission.

<!-- Figures to drop in (all in artifacts/): asr_undefended.png, adaptive_curve.png,
heatmap.png, pareto.png, ui_v2_livedemo_attack.png, ui_v2_attacklab.png, ui_v2_governance.png,
governance.md (for the scorecard tables). Delete these comments before exporting. -->
