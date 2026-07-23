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
- **SHOW:** the 9 static attacks (6 core + 3 extended) + A7 adaptive; the ASR definition; "rule-based judge".
- **SAY:** 9 static attacks across LLM / extraction / poisoning / evasion + **membership-inference &
  IP-fingerprinting**, plus an **adaptive agent**. **ASR** = fraction where a **deterministic judge**
  confirms the goal (canary match, prompt-leak n-grams, injected-marker echo, ownership phrase).
  Deterministic = reproducible & defensible under Q&A.

### Slide 6 — Attack results ⭐  ·  ~60s  ·  [C2]
- **SHOW:** `artifacts/asr_undefended.png` (per-attack ASR bar chart). Big.
- **SAY (real numbers, 9 attacks):** Overall undefended **ASR 31%**. **A1 direct injection 88%**,
  **A9 fingerprint 100%** (a planted ownership phrase sitting in the retrieved doc), A8 membership 30%,
  A2 26%, A5 24% — but **A4 and A10 = 0%** (the aligned 8B resists revealing *or paraphrasing* its own
  system prompt).
- **SAY:** The spread (not a saturated ~100%) is *because* we used a genuinely aligned
  model — attacks are non-trivial, so the defence story is meaningful.

### Slide 7 — Adaptive attacker  ·  ~30s  ·  [C2/C3]
- **SHOW:** `artifacts/adaptive_curve.png`.
- **SAY:** A PAIR-style loop with the **real Qwen3-8B as the mutator**, run **against our
  best stack (D2+D5)**. Across **6 rounds it never breaks through — 0% ASR**. The defence
  holds even under an adaptive LLM attacker (D2 guardrail + D5 groundedness).

### Slide 8 — Defences  ·  ~45s  ·  [C3]
- **SHOW:** D1–D6 at 3 hook points (pre-retrieval / post-retrieval / post-generation).
- **SAY:** Six core defences across three hook points. Ordering matters — **D6 de-obfuscation
  runs before D2 the classifier**, or the classifier never sees the decoded payload.
- **SAY (one line):** A hardening pass adds **D7–D9** (access-control, rate-limit, semantic/fingerprint
  filter) for the extended attacks — see the "extended coverage" slide.

### Slide 9 — What robustness costs ⭐⭐  ·  ~70s  ·  [C3]  *(your strongest slide)*
- **SHOW:** `artifacts/heatmap.png` (attack×defence) **and** `artifacts/pareto.png`.
- **SAY (real numbers):** We searched **all 64 D1–D6 stacks**, then **Optuna-tuned** the winner
  (D2→0.74, D5→0.26). The *minimal* **D2+D5** hits **96% robustness / 5% FRR** — but it **can't block the
  IP-fingerprint attack A9** (no D1–D6 filter catches an output-side ownership leak). The **targeted
  D7–D9** (outside the 64-stack search) close A8/A9/A10, so the **full stack → 0% ASR** (undefended
  **31% → 0%**), utility 0.44 on a **held-out benign set disjoint from the KB**.
- **SAY:** That's the accuracy–robustness tradeoff, measured — and it shows *why* the extended defences
  were needed: the classic filters alone don't cover the new attack families.

### Slide 10 — Governance re-score + deployment  ·  ~30s  ·  [C3]
- **SHOW:** baseline → defended scorecard (🔴→🟢) + risk→control mapping.
- **SAY:** Post-defence, RMF Measure/Manage move to green. For real deployment we'd add
  index segregation for internal docs, canary-hit alerting, and periodic re-testing.

### Slide 10b — Extended coverage (hardening pass)  ·  ~30s  ·  [C1/C3]  *(optional / backup)*
- **SHOW:** the extended attack→defence map: A8/A9/A10 → D7/D8/D9.
- **SAY:** Beyond the core suite we (1) **fixed a real access-control hole** — internal docs were
  never filtered by visibility; **D7** now drops them at retrieval (prevention, not post-hoc scanning);
  (2) added **membership inference (A8)** and **IP fingerprinting (A9**, from a teammate's prototype)
  and **paraphrased prompt extraction (A10)**; (3) added **rate-limiting (D8)** and a **semantic/
  fingerprint output filter (D9)**.
- **SAY (real numbers):** undefended **A8 30% · A9 100% · A10 0%** — all **→ 0%** under the full stack.
  Crucially the D1–D6 Pareto search (D2+D5) **cannot** block A9; **D7–D9 are what close it** — so the
  extended defences aren't optional, they cover a gap the classic filters miss.
- ✍️ Optional: live-demo **A9 fingerprint** in Tab 1 (bot emits `OWNER-FP-…`, then D9 blocks it).

### 🎬 DEMO — live, on the Gradio UI  ·  **~2.5 min**  ·  [C2+C3+C4]
> Launch `serve_app.py` (or `01_DEMO.ipynb`) BEFORE the talk so the model is warm.
> **Have the backup screen-recording ready** in case wifi/UI fails.

Four beats on **Tab 1 · Live Demo** (use the **▶ Run demo script** button to avoid mis-clicks):
1. **It works** — benign question, no defences → helpful answer.
2. **It breaks** — pick **A1** (or A5), no defences → 🔴 *ATTACK SUCCEEDED* (bot obeys / canary leaks).
3. **We fix it** — tick the defence that counters it (**D2+D5** for A1; **D4** for A5 canary; **D9** for A9 fingerprint) → 🟢 *BLOCKED*.
4. **It still works** — re-ask the benign question, defences on → still correct.
- Optionally flash **Tab 2 (named ASR table)** and **Tab 3 (Pareto)** for 5 seconds each.
- *(The UI also has a **Tab 5 · Run pipeline** one-click button — pre-run it to populate results; don't run it live, as even Quick takes minutes.)*
- ✍️ Rehearse to hit 2.5 min. One person drives, one narrates.

### Slide 11 — Takeaways  ·  ~25s
- **SAY:** (1) RAG bots leak because untrusted text is trusted; (2) a stronger victim gives realistic
  numbers (**31%**, not 100%); (3) the minimal D1–D6 stack (**D2+D5**, 96%) misses the new IP/MIA
  attacks — the **full D1–D9 stack → 0% ASR**; (4) governance moved red→green.
- ✍️ one forward-looking line (LLM-driven attacker, larger model, real PII controls).

### Slide 12 — Q&A / backup  ·  (holds during 5-min Q&A)
- **SHOW:** "Thank you — questions?" + repo link + a small results recap.
- Keep **backup slides** after this (full ASR table, transcripts, method details).

---

## Anticipated Q&A — prep answers (✍️ refine)
- **"Why is A4 0% but A1 88%?"** → A4 asks the model to reveal its own instructions — Qwen3-8B is aligned against that; A1 injects a concrete instruction the model follows. Model-capability finding.
- **"Isn't 8B too small / why not GPT-4?"** → We need a *self-hostable, reproducible, attackable* victim with real alignment; the 8B runs on a single GPU (auto-scaling to available VRAM) and gives non-saturated ASR. Bigger = future work.
- **"How do you know defences don't just refuse everything?"** → We measure **false-refusal rate on 150 held-out benign queries** — the minimal D2+D5 stack costs only **~5% FRR**, reported explicitly as the accuracy price.
- **"Why add D7–D9 if D2+D5 is the 'best' stack?"** → The 64-stack search only ranges over D1–D6, and **no D1–D6 filter blocks the IP-fingerprint attack A9** (an output-side leak). D7–D9 target the new families (access-control, rate-limit, semantic/fingerprint) — the **full stack** is what reaches 0%.
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
heatmap.png, pareto.png, ui_v3_livedemo.png, ui_v2_livedemo_attack.png (attack-succeeded state),
ui_v3_attacklab.png, ui_v3_defenselab.png, ui_v3_governance.png, ui_v3_run.png
(+ ui_v3_livedemo_dark.png for a dark-mode view; ui_v3_livedemo_a9.png / ui_v3_livedemo_a9_blocked.png
for the A9 fingerprint demo), governance.md (for the scorecard tables).
Delete these comments before exporting. -->
