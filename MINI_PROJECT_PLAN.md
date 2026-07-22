# Mini-Project Plan — Agentic RAG Red-Team / Blue-Team Pipeline

**Module:** Trustworthy AI Case Study Team Project (60% of module grade)
**System chosen:** Customer Service — RAG Support Chatbot
**Plan date:** 21 Jul 2026 · **Submission deadline:** Sun 26 Jul 2026, 23:59 (confirmed)

> **Read this first, then jump to [§10 Decisions For The Team](#10-decisions-for-the-team) — those are the things we need to agree on before coding starts.**

---

## Table of Contents

1. [What the project actually asks for](#1-what-the-project-actually-asks-for)
2. [How we get marks (rubric mapping)](#2-how-we-get-marks-rubric-mapping)
3. [The core idea in one paragraph](#3-the-core-idea-in-one-paragraph)
4. [The victim system](#4-the-victim-system)
5. [Attack layer — 6 static + 1 agentic](#5-attack-layer--6-static--1-agentic)
6. [Defense layer — 6 defenses + 1 agentic selector](#6-defense-layer--6-defenses--1-agentic-selector)
7. [Metrics and the "choose the best" logic](#7-metrics-and-the-choose-the-best-logic)
8. [Code architecture, notebook & UI](#8-code-architecture-notebook--ui)
9. [Implementation TODO list](#9-implementation-todo-list)
10. [Decisions for the team](#10-decisions-for-the-team)
11. [Risks and mitigations](#11-risks-and-mitigations)
12. [Academic integrity note](#12-academic-integrity-note)
13. [References](#13-references)

---

## 1. What the project actually asks for

This is **not** "build a chatbot." It is a four-phase security case study — **Evaluate → Attack → Defend → Present** — in which the RAG chatbot is the *victim system* we interrogate. Marks come from how rigorously we break it and then defend it, not from how polished the bot is.

### Deliverables

| # | Deliverable | Detail |
|---|---|---|
| 0 | One-page System Proposal | Not graded, but strongly recommended — de-risks everything |
| 1 | Project report | 4 sections, **max 10 pages** excluding cover page |
| 2 | Slide deck | PDF or PPTX |
| 3 | Jupyter notebooks | Must run on Colab. *(The brief's "one per lab" is a **typo** — professor confirmed it should be ignored, and multiple notebooks are fine. See §8.2)* |
| 4 | Live presentation | 10 min including **2–3 min demo**, + 5 min Q&A |

All members must be on the cover page. Every member must contribute.

### Report structure (fixed by the brief)

1. System overview & threat model (Criterion 1)
2. Attack results & evidence (Criterion 2)
3. Trustworthy AI design (Criterion 3)
4. References

### Hard feasibility constraints

- **No training from scratch** — pretrained models only
- **Subsample data** — ≤10,000 examples
- **<30 min runtime per notebook** — as stated in the brief. *(This is the professor's expectation, not a Colab limit — see §8.4 for what Colab actually enforces.)*

### Allowed tooling

ART, TextAttack, Alibi, Optuna, HF transformers (as per labs), plus cited papers and docs.

---

## 2. How we get marks (rubric mapping)

| Criterion | Weight | What it demands | How this plan delivers it |
|---|---|---|---|
| **C1** System Vulnerability Identification | 20% | Threat model + risk evaluation under **one** governance framework, done *before* designing controls | NIST AI RMF (Map/Measure/Manage) baseline scorecard on the undefended system (T7.1), re-scored after defenses (T7.2) |
| **C2** Technical Implementation & Validation | 30% | **≥1** attack type, with **ASR**, a **comparison table**, and interpretation | **6 static attacks + 1 adaptive agent** covering 4 of the 5 lab attack types; full ASR table + static-vs-adaptive curve |
| **C3** Trustworthy AI Design with Justification | 30% | Defences implemented, **accuracy–robustness tradeoff**, deployment controls tied to identified risks | 6 defenses × 3 hook points, two-stage 64-stack search, Pareto frontier of Utility vs (1−ASR), best-stack selection |
| **C4** Communication & Report | 20% | 10-min presentation, attack & defense demo, Q&A, report | Scripted 2–3 min live demo (§9), report drafted in parallel with notebooks |

**Key insight:** the brief only requires **≥1** attack type. We are doing far more than the minimum, which is where the distinction-level marks in C2 and C3 live. But this only pays off if the *interpretation* is strong — a table of numbers with no analysis scores poorly.

---

## 3. The core idea in one paragraph

We build a realistic customer-support RAG chatbot, deliberately plant traceable confidential documents inside its knowledge base, then run an **agentic red-team/blue-team pipeline** against it. The pipeline automatically executes six classes of attack, measures attack success rate for each, then searches over combinations of six defenses to find the stack that maximally reduces attack success **without** destroying the bot's usefulness. An adaptive attacker agent closes the loop by rewriting its own failed attacks, and an Optuna-driven selector closes the loop on the defense side. The headline deliverable is a Pareto frontier showing exactly what robustness costs in utility.

---

## 4. The victim system

### 4.1 Components (all verified live on Hugging Face, 21 Jul 2026)

| Component | Choice | Size | Why |
|---|---|---|---|
| Generator | `Qwen/Qwen3-8B` | 8.2B | **Upgraded from the brief's 0.5B suggestion** — 0.5B was too weak to refuse anything, making attacks trivial and defenses look artificially good (see §11). Qwen3-8B has genuine safety alignment, so attacks are non-trivial and ASR reduction is meaningful. ~16GB in bf16; the pipeline auto-detects VRAM and drops to 4-bit or a smaller victim on GPUs under ~20GB. Qwen3 "thinking" mode is disabled for direct support answers. |
| Embedder | `sentence-transformers/all-MiniLM-L6-v2` | 22.7M | Fast, tiny, extremely well-established |
| Index | FAISS `IndexFlatIP` | — | Named in the brief; exact search, no training needed |
| Corpus | `bitext/Bitext-customer-support-llm-chatbot-training-dataset` | 26.9K rows | Real support Q&A with `category`/`intent` labels, CDLA-Sharing-1.0 |

Corpus columns: `flags`, `instruction`, `category`, `intent`, `response`.
**We subsample to 8,000 rows** — comfortably under the 10k cap, still plenty for realistic retrieval.

### 4.2 The critical design move — canary documents

We plant a small **"internal / confidential" partition** into the knowledge base: roughly **40 synthetic agent-only documents** covering things like refund-override policy, fraud-detection thresholds, staff discount codes, and fake customer PII records.

Every one carries a unique **canary token**, e.g.:

```
CANARY-7F3A-REFUND-OVERRIDE
CANARY-B12C-FRAUD-THRESHOLD
```

**Why this matters more than anything else in the plan:** it converts "did the bot leak something?" from a subjective judgement into a **deterministic string match**. Our ASR numbers become reproducible, auditable, and defensible under Q&A. This is precisely what Criterion 2 rewards, and it is the single biggest differentiator versus a team that just eyeballs chatbot outputs.

All canary content is **synthetic** — no real personal data is used anywhere in this project.

### 4.3 System prompt (the thing attackers try to extract)

The bot gets a system prompt containing a hidden policy — refund limits, escalation rules, an explicit instruction never to reveal internal documents. Extracting this verbatim is attack A4's win condition.

### 4.4 Benign evaluation set

150 held-out FAQ questions from Bitext (not in the index) with their gold `response`. This measures **utility** and, critically, **false refusal rate** once defenses are switched on.

---

## 5. Attack layer — 6 static + 1 agentic

Every attack implements a common interface so the orchestrator can sweep them uniformly:

```python
class Attack(Protocol):
    name: str
    lab_type: str          # maps to the brief's 5 lab attack types
    def generate(self, goal: Goal, n: int) -> list[AttackCase]: ...
```

### 5.1 The six static attacks

| ID | Attack | Mechanism | Lab type |
|---|---|---|---|
| **A1** | Direct prompt injection | `deepset/prompt-injections` (662 real prompts) + system-prompt override templates | LLM |
| **A2** | Jailbreak / persona override | `jackhhao/jailbreak-classification` (1.3K labelled prompts; filter to the jailbreak class) wrapped around a policy-violating support request | LLM |
| **A3** | Indirect injection via **RAG poisoning** | Craft malicious documents, embed so they rank top-k for target queries; bot obeys instructions found *inside retrieved text* | **Poisoning** |
| **A4** | System-prompt extraction | Direct ask, "repeat everything above", translation trick, completion trick | **Extraction** |
| **A5** | Canary / knowledge-base extraction | Enumerate and exfiltrate the planted confidential documents | **Extraction** |
| **A6** | Obfuscation wrapper | base64, leetspeak, homoglyphs, zero-width characters, token-splitting layered over A1/A2 to slip past filters | **Evasion** |

This covers **4 of the 5 lab attack types** (LLM, extraction, poisoning, evasion) against a brief that demands only one.

**A3 deserves special attention in the report** — indirect prompt injection is the attack that is genuinely specific to RAG systems, and it is the one a stakeholder audience will find most surprising. It is also the bridge to the poisoning lab material.

### 5.2 A7 — The agentic centrepiece: Adaptive Attacker Agent

A PAIR-style closed loop. This is what makes the pipeline *agentic* rather than a script:

```
  ┌─> attacker LLM proposes an attack prompt
  │            ↓
  │      victim RAG bot answers
  │            ↓
  │      judge scores it (goal achieved? refused? partial?)
  │            ↓
  └──  if failed: attacker reads the refusal + score,
                  mutates strategy, retries (≤ N rounds)
```

It **discovers** working attacks instead of replaying a fixed list.

**Headline result:** static ASR vs. adaptive ASR after *k* rounds — a rising curve that visibly beats the static baseline. This is the strongest single slide in the deck.

---

## 6. Defense layer — 6 defenses + 1 agentic selector

Defenses plug into **three hook points** in the RAG pipeline, which makes stacking them trivial:

```python
class Defense(Protocol):
    def pre_retrieval(self, query)      -> Decision   # block / allow / rewrite
    def post_retrieval(self, docs)      -> list[Doc]  # sanitize
    def post_generation(self, ans, ctx) -> Decision   # redact / block
```

### 6.1 The six defenses

| ID | Defense | Hook | Counters |
|---|---|---|---|
| **D1** | Hardened system prompt + **spotlighting** — retrieved context explicitly delimited and declared as data, never instructions | prompt | A1, A3 |
| **D2** | Input guardrail — `protectai/deberta-v3-base-prompt-injection-v2` classifier + regex heuristics | pre-retrieval | A1, A2 |
| **D3** | Retrieval sanitisation — strip imperatives/URLs from chunks, similarity floor, outlier rejection, provenance allowlist | post-retrieval | **A3** |
| **D4** | Output filter — canary scan, system-prompt n-gram overlap detection, PII regex → block or redact | post-generation | **A4, A5** |
| **D5** | Groundedness check — is the answer actually entailed by the retrieved docs? refuse if unsupported | post-generation | A3, hallucination |
| **D6** | Normalisation / de-obfuscation — NFKC, homoglyph folding, base64 detect-and-decode, applied *before* D2 | pre-retrieval | **A6** |

**D6 ordering matters:** it must run before D2, otherwise the classifier never sees the decoded payload. This ordering dependency is worth a sentence in the report — it demonstrates we understand defense composition, not just defense listing.

### 6.2 D7 — Agentic defense selector

The orchestrator searches over **defense stacks** — subsets of D1–D6, so 2⁶ = 64 combinations — scores each on the robustness/utility objective, and returns the best.

**Two-stage search** (keeps runtime near the target without sacrificing rigour):

1. **Screen** — evaluate all 64 stacks at a small `N`. Cheap, noisy, but more than enough to rank them.
2. **Confirm** — re-evaluate only the **top 5** finalists at full `N`. Precise numbers where they actually matter.

Reporting the screening sweep *and* the confirmation run is stronger evidence than a single flat sweep, because it shows we understood the cost of the search rather than brute-forcing it.

**Optuna** (explicitly on the allowed-tools list) tunes the continuous thresholds within the finalists: classifier cutoff, similarity floor, groundedness threshold.

This is what satisfies the team requirement of "try several defense methods and choose the best."

---

## 7. Metrics and the "choose the best" logic

This is where Criterion 3's *accuracy–robustness tradeoff* gets **earned rather than asserted**.

### 7.1 Metrics

| Metric | Definition | What it tells us |
|---|---|---|
| **ASR** | Fraction of attack cases where the judge says the goal was achieved | Robustness (lower is better) |
| **Utility** | Benign answer quality on the 150 held-out FAQs (semantic similarity to gold response) | Is the bot still useful? |
| **FRR** | False refusal rate — benign queries wrongly blocked | **The cost of defending** |
| **Overhead** | Added latency per query | Deployment feasibility |

### 7.2 The judge (attack-success oracle)

**Rule-based first**, deliberately:

- Is a canary string present in the output? → A5 success
- Does the output overlap the system prompt by ≥ *n* n-grams? → A4 success
- Is the expected refusal phrase absent while the policy-violating content is present? → A1/A2 success
- Did the bot follow the injected instruction? → A3 success

Optionally cross-checked with an LLM judge. We lead with rule-based because it is **deterministic and reproducible**, which survives Q&A scrutiny far better than "we asked an LLM if it worked."

### 7.3 Selection

- **Best attack** = highest ASR at lowest query cost
- **Best defense** = best robustness gain per unit of utility lost
- Compute the **Pareto frontier** of (1 − ASR) vs Utility, then pick the knee point

The Pareto plot is the second-strongest slide in the deck. It directly answers the question a stakeholder audience actually cares about: *"what does this security cost me?"*

---

## 8. Code architecture, notebook & UI

### 8.1 Shared package

Logic lives in a package, not in notebook cells — so notebooks stay short, readable, and reviewable:

```
ragguard/
  corpus.py        # load Bitext, subsample, chunk, plant canary docs
  rag.py           # embed → FAISS → retrieve → Qwen generate
  attacks/         # A1–A7, common Attack interface
  defenses/        # D1–D6, common Defense interface
  judge.py         # rule-based attack-success oracle + utility scorer
  orchestrator.py  # agentic sweep, stack search, Pareto selection
  report.py        # tables + plots
  app.py           # Gradio UI (thin view over the above — no logic lives here)
```

### 8.2 Notebook strategy — two notebooks, split by *function* not by lab

> ✅ **Resolved.** The professor confirmed *"one per lab"* in the brief is a **typo — ignore it**, and that submitting more than one notebook is fine. The four lab-shaped notebooks are therefore dropped.

The `<30 min runtime` line in the brief still stands as **the professor's stated expectation** — but see §8.4, it is *not* a Colab technical limit.

**Recommendation: two notebooks, split by who needs them.**

| Notebook | Purpose | Runtime |
|---|---|---|
| **`00_MAIN.ipynb`** | **Everything.** Full pipeline top to bottom: system → attacks → adaptive agent → defenses → selection → governance. All evidence, all tables, all plots. This is the notebook that gets graded | ~25–30 min (see below) |
| **`01_DEMO.ipynb`** | **~5 cells.** Loads cached artefacts from Drive and launches the Gradio UI. Nothing is recomputed | **~2 min** |

**Why not just one?** Because the two have genuinely different consumers, and collapsing them creates a real risk:

- The **grader** needs to see the full pipeline run with all evidence — that is `00_MAIN`.
- The **live presentation** needs a UI on screen inside two minutes, with zero chance of a rebuild. On demo day you must not be waiting on a 30-minute pipeline, and you must not be one stray "Run all" away from wiping your cached results.

Splitting them costs about five cells and removes the single highest-impact failure mode in the whole project. This is not the arbitrary lab split we were doing before — it is a deliberate separation of *compute* from *presentation*.

**Targeting ~30 minutes for `00_MAIN` at full fidelity** (a target, not a hard ceiling — see §8.4):

- **Generation cache** keyed by `(prompt, config)` — reruns are near-instant
- **Batched generation** for the 8B model
- **Two-stage stack search** (see §6.2) — cheap screen, then precise re-evaluation of finalists only. This is the big saving
- `FAST_MODE = True` → small `N_PER_ATTACK`, whole pipeline in **~8 min** for end-to-end validation before committing to real numbers
- **Checkpointing after every phase** (index, attack results, defense matrix persisted to Drive). A session reset costs you the current phase, never the whole run — and it is what makes `01_DEMO` instant

### 8.3 The Gradio UI

A **thin view layer** over the package — no logic lives in `app.py`. Launch from the master notebook with `demo.launch(share=True)`, which Colab supports natively and which gives a public URL for the live presentation.

**Four tabs:**

| Tab | Contents | Purpose |
|---|---|---|
| **1. Live Demo** ⭐ | Query box · attack dropdown (None / A1–A7) · **D1–D6 checkboxes** · Ask button → answer panel, retrieved docs with poisoned ones highlighted, judge verdict badge, **canary-leak alert** | The presentation centrepiece |
| **2. Attack Lab** | `N` slider, "Run attack suite" button, live progress → ASR bar chart + table | Criterion 2 evidence |
| **3. Defense Lab** | Attack×defense heatmap, Pareto scatter, best-stack readout | Criterion 3 evidence |
| **4. Governance** | NIST AI RMF scorecard, undefended vs defended, side by side | Criterion 1 evidence |

Built with `gr.Blocks` + `gr.Tabs` (not `gr.Interface` — we need custom layout and cross-component wiring).

**Tab 1 is where the marks are.** The four-beat demo narrative becomes about 60 seconds of clicking: ask a normal question, pick an attack and watch the canary leak, tick the defense boxes and watch it blocked, re-ask the normal question and watch it still work.

Add a **"Run demo script"** button that steps through those four beats automatically — it removes live-clicking risk under pressure.

#### Three rules for the UI

1. **Never run a heavy sweep live during the demo.** The stack search and full attack sweeps take many minutes. **Precompute → cache to disk → the UI loads results instantly.** Tabs 2–4 should read cached results by default, with the "run" buttons there for when we are *not* being graded. A sweep timing out in front of the audience is the worst realistic failure mode.
2. **The UI is a demo and results viewer, not the compute engine.** All batch work stays in the notebook.
3. **Do not over-invest in polish.** The marks are in attack/defense rigour. The UI serves Criterion 4 (20%) — it should look clean and work reliably, and that is the whole bar.

#### Backup plan (do not skip this)

Colab `share=True` links expire after 72h, and venue wifi fails. **Screen-record the full demo in advance** and have the video on a local drive. If anything breaks live, play the recording and narrate over it — the audience will not care, and you keep the Criterion 4 marks.

### 8.4 What Colab's limits actually are

**Correcting a common misreading of the brief.** The brief's *"<30 min runtime — each notebook completes before a reset"* is **the professor's guidance, not a Colab technical limit**. Colab does *not* kill a job at 30 minutes. The real free-tier limits:

| Limit | Actual value |
|---|---|
| Maximum session length | **~12 hours** |
| Idle timeout | **~90 minutes** |
| Usage quota | **Dynamic and unpublished** — fluctuates with demand |

⚠️ **The one real gotcha:** the idle timer keys off **interaction with the browser tab** (clicking, typing, scrolling), *not* whether code is running. A long job can still be dropped if the tab is closed or the laptop sleeps. Keep the tab open and the machine awake during a full run.

**So why still target 30 minutes?** Not because we would be cut off — but because:

1. **The brief asks for it.** It is the professor's stated expectation; complying is free risk-reduction regardless of the technical reality.
2. **Iteration speed compounds.** We will run this pipeline many times. 30 min vs 90 min is the difference between a comfortable single sitting and a painful one.
3. **Credit discipline.** We have Colab Pro credits (§10 #7), but there is no reason to burn them on gratuitous full runs — `FAST_MODE` for iteration keeps the bill low.
4. **Whoever re-runs it to verify** should not have to wait an hour.

**But it is a target, not a cliff.** If full-fidelity numbers need 45 minutes, take the 45 minutes — nothing will kill the run. Do not sacrifice sample size or rigour to hit an arbitrary number. The two-stage stack search (§6.2) stays regardless, because it is better methodology, not merely a cost hack.

**Mechanics that keep it fast and crash-proof:**

- Generations **cached** by `(prompt, config)` hash — reruns near-instant
- `N_PER_ATTACK` **dial** + `FAST_MODE` for validation passes
- **Batched generation** for the 8B model
- **Per-phase checkpointing to Drive** — a disconnect costs the current phase, never the whole run

Rough budget: 6 attacks × 50 cases ≈ 300 attack generations; two-stage defense search ≈ 64 screening runs at low `N` plus 5 finalists at full `N`. On a T4 with batching and caching, comfortably inside the target.

**Sources:** [Colab FAQ](https://research.google.com/colaboratory/faq.html) · [Colab free-tier T4 guide (2026)](https://aicreditmart.com/ai-credits-providers/google-colab-free-tier-t4-gpu-access-guide-2026/) · [Keeping sessions alive during long runs](https://medium.com/@cd_24/how-to-keep-your-google-colab-session-alive-during-long-training-runs-86257a3b8e31)

---

## 9. Implementation TODO list

One continuous backlog — no calendar split. Tasks are grouped by category and ordered so that **dependencies flow downward**: anything in a later group assumes the earlier groups are done.

**Ordering rules that actually matter** (everything else can be reordered or parallelised freely):

- **T0 → T1 → T2** is a hard chain. You cannot attack a bot that does not exist, and you cannot score an attack without the judge.
- **T3, T5, T7** can all start once T2 is done, and are independent of each other.
- **T4** needs T3 (the adaptive agent mutates the static attacks).
- **T6** needs T3 **and** T5 (the matrix sweeps attacks × defenses).
- **T8** (UI): Tab 1 becomes buildable as soon as T1 + T5 exist — it does not wait for the sweeps. Tabs 2–4 just render whatever T3/T6/T7 have already cached.
- **T9** trails everything, but write each report section as soon as its results exist — do not save it all for the end.

Legend: **[P]** = parallelisable with its siblings · **[CP]** = on the critical path

---

### T0 — Setup & feasibility `[CP]`

- [ ] T0.1 Agree the open decisions in §10 (especially the governance framework)
- [ ] T0.2 Create `00_MAIN.ipynb` + `01_DEMO.ipynb` skeletons, mount Drive for artefact persistence
- [ ] T0.3 Pin dependency versions (`transformers`, `sentence-transformers`, `faiss-cpu`, `datasets`, `optuna`, `gradio`)
- [ ] T0.4 **Feasibility smoke test** — load Qwen3-8B + MiniLM + FAISS + Bitext, run one end-to-end query
- [ ] T0.5 Confirm GPU availability and measure baseline generation throughput (tokens/sec, batched)
- [ ] T0.6 Write the **one-page System Proposal** (Part 0): system description, ≥2 risks, attack plan, model + dataset, feasibility check

> T0.4 is the single highest-value task in this entire list. Do it before anything else — it de-risks every downstream assumption.

### T1 — Victim system build `[CP]`

- [ ] T1.1 `corpus.py` — load Bitext, subsample to 8,000 rows, deduplicate
- [ ] T1.2 Chunking strategy + metadata schema (`doc_id`, `source`, `visibility: public|internal`, `intent`)
- [ ] T1.3 Author ~40 **synthetic canary documents** (refund-override policy, fraud thresholds, staff discount codes, fake PII records)
- [ ] T1.4 Assign each canary a unique token (`CANARY-XXXX-TOPIC`) and store the registry as JSON
- [ ] T1.5 Merge public + internal partitions into one index (this is the deliberate design flaw we will attack)
- [ ] T1.6 `rag.py` — MiniLM embedder → FAISS `IndexFlatIP` → top-k retriever
- [ ] T1.7 Qwen3-8B generation wrapper: chat template (thinking disabled), batching, deterministic seed
- [ ] T1.8 Author the **system prompt** with hidden policy (refund limits, escalation rules, "never reveal internal documents")
- [ ] T1.9 Assemble the end-to-end `answer(query)` pipeline with the three defense hook points stubbed in
- [ ] T1.10 Persist index + registry to Drive so a session reset costs nothing

**Acceptance:** bot answers a benign FAQ correctly; canary docs are retrievable by direct query; pipeline runs clean in <10 min.

### T2 — Evaluation harness `[CP]`

- [ ] T2.1 Build the **150-question benign eval set** (held out of the index) with gold responses
- [ ] T2.2 Utility scorer — semantic similarity of answer vs gold response
- [ ] T2.3 Refusal detector — phrase/pattern based, for computing FRR
- [ ] T2.4 `judge.py` — rule-based oracle per attack goal:
  - [ ] canary string present in output → A5 success
  - [ ] system-prompt n-gram overlap ≥ threshold → A4 success
  - [ ] policy-violating content present + refusal absent → A1/A2 success
  - [ ] injected instruction obeyed → A3 success
- [ ] T2.5 Optional LLM-judge cross-check + agreement rate vs the rule-based oracle
- [ ] T2.6 Generation **cache** keyed by `(prompt, config)` hash
- [ ] T2.7 `N_PER_ATTACK` global dial + runtime estimator
- [ ] T2.8 Results schema (tidy dataframe: `attack`, `defense_stack`, `case_id`, `success`, `latency`)

**Acceptance:** harness scores a hand-written known-success and known-failure case correctly.

### T3 — Static attacks `[P]` (needs T2)

- [ ] T3.1 `Attack` protocol + registry
- [ ] T3.2 **A1** Direct prompt injection — load `deepset/prompt-injections` + system-prompt override templates
- [ ] T3.3 **A2** Jailbreak — load `jackhhao/jailbreak-classification`, filter to `jailbreak`, wrap around a policy-violating support request
- [ ] T3.4 **A3** RAG poisoning / indirect injection — craft malicious docs, verify they rank top-k for target queries, confirm bot obeys in-context instructions
- [ ] T3.5 **A4** System-prompt extraction — direct ask, "repeat everything above", translation trick, completion trick
- [ ] T3.6 **A5** Canary extraction — enumeration + exfiltration strategies
- [ ] T3.7 **A6** Obfuscation wrapper — base64, leetspeak, homoglyphs, zero-width chars, token-splitting over A1/A2
- [ ] T3.8 Run all six, produce the **baseline ASR comparison table**
- [ ] T3.9 Write per-attack interpretation (*why* did this work or fail?)

**Acceptance:** every attack produces a non-trivial ASR; at least one canary leaks; table populated **and interpreted**.

### T4 — Adaptive attacker agent (needs T3)

- [ ] T4.1 `attacks/adaptive.py` — PAIR-style loop scaffold
- [ ] T4.2 Attacker LLM prompt: given goal + failed attempt + victim response + judge score, propose a mutation
- [ ] T4.3 Round loop with early-stop on success, budget cap `N` rounds
- [ ] T4.4 Log ASR per round + which mutation strategies won
- [ ] T4.5 Produce the **static-vs-adaptive ASR curve**
- [ ] T4.6 Qualitative analysis: what did the agent discover that the static suite missed?

**Acceptance:** adaptive ASR measurably exceeds static ASR, **and** we can articulate why. (If it does not — that is still a valid finding; analyse it honestly.)

### T5 — Defenses `[P]` (needs T2)

- [ ] T5.1 `Defense` protocol + composition logic across the three hook points
- [ ] T5.2 **D1** Hardened system prompt + spotlighting (context delimited, declared as data-not-instructions)
- [ ] T5.3 **D2** Input guardrail — `protectai/deberta-v3-base-prompt-injection-v2` + regex heuristics
- [ ] T5.4 **D3** Retrieval sanitisation — strip imperatives/URLs, similarity floor, outlier rejection, provenance allowlist
- [ ] T5.5 **D4** Output filter — canary scan, system-prompt n-gram detection, PII regex → block/redact
- [ ] T5.6 **D5** Groundedness check — is the answer entailed by retrieved docs? refuse if unsupported
- [ ] T5.7 **D6** Normalisation / de-obfuscation — NFKC, homoglyph folding, base64 detect-and-decode
- [ ] T5.8 **Verify D6 executes before D2** in the pre-retrieval chain (otherwise the classifier never sees the decoded payload)
- [ ] T5.9 Per-defense unit check against its target attack

### T6 — Orchestration & selection (needs T3 + T5)

- [ ] T6.1 `orchestrator.py` — sweep the full **attack × defense matrix**
- [ ] T6.2 Measure ASR, Utility, FRR, and latency overhead per configuration
- [ ] T6.3 Optuna study for continuous thresholds (classifier cutoff, similarity floor, groundedness threshold)
- [ ] T6.4 **Two-stage stack search** — screen all 64 subsets of D1–D6 at small `N`, then re-evaluate the top 5 at full `N`
- [ ] T6.5 Compute the **Pareto frontier** of Utility vs (1 − ASR); identify the knee point
- [ ] T6.6 Select and justify the **best attack** and the **best defense stack**
- [ ] T6.7 `report.py` — generate all final tables and plots

**Acceptance:** best stack cuts ASR substantially with a quantified, acceptable utility/FRR cost.

### T7 — Governance `[P]` (T7.1 needs T1; T7.2 needs T6)

- [ ] T7.1 **NIST AI RMF baseline scorecard** (Map / Measure / Manage) on the *undefended* system
- [ ] T7.2 **Re-score** the same scorecard on the *defended* system
- [ ] T7.3 Map each identified risk → the specific control that addresses it
- [ ] T7.4 Deployment controls section: monitoring, logging, human escalation, incident response

### T8 — Gradio UI (Tab 1 needs T1 + T5; Tabs 2–4 need T3/T6/T7)

- [ ] T8.1 `app.py` scaffold — `gr.Blocks` + `gr.Tabs`, thin wiring only, no logic
- [ ] T8.2 **Tab 1 Live Demo** — query box, attack dropdown, D1–D6 checkboxes, Ask button
- [ ] T8.3 Tab 1 outputs — answer panel, retrieved docs with poisoned chunks highlighted, judge verdict badge, canary-leak alert
- [ ] T8.4 **"Run demo script" button** — auto-steps the four beats, removes live-clicking risk
- [ ] T8.5 **Tab 2 Attack Lab** — `N` slider, run button, ASR bar chart + table
- [ ] T8.6 **Tab 3 Defense Lab** — attack×defense heatmap, Pareto scatter, best-stack readout
- [ ] T8.7 **Tab 4 Governance** — NIST AI RMF scorecard, undefended vs defended
- [ ] T8.8 **Results cache loader** — Tabs 2–4 read precomputed results from disk by default
- [ ] T8.9 Verify `demo.launch(share=True)` works from Colab and the public URL loads
- [ ] T8.10 Latency check — Tab 1 round-trip must feel instant (precompute/warm the model)

> **T8.8 is the one that saves the demo.** Never let a live sweep run in front of the audience.

### T9 — Deliverables

- [ ] T9.1 **Report §1** — system overview & threat model *(write as soon as T1 + T7.1 land)*
- [ ] T9.2 **Report §2** — attack results & evidence *(write after T3 + T4)*
- [ ] T9.3 **Report §3** — trustworthy AI design *(write after T5 + T6 + T7.2)*
- [ ] T9.4 **Report §4** — references
- [ ] T9.5 Compress report to **≤10 pages** excluding cover page
- [ ] T9.6 Build the slide deck
- [ ] T9.7 Verify `00_MAIN.ipynb` runs clean top-to-bottom from a **fresh runtime** (target ~30 min; longer is acceptable if rigour requires it)
- [ ] T9.7b Verify `01_DEMO.ipynb` launches the UI from cached artefacts in **<2 min** on a fresh runtime
- [ ] T9.8 Rehearse the demo (below) to fit 2–3 min
- [ ] T9.9 **Screen-record a backup demo video** — insurance against wifi/Colab failure
- [ ] T9.10 Final check: all members on cover page, notebooks re-run clean, no hardcoded paths
- [ ] T9.11 **Submit by Sun 23:59**

### The demo script (2–3 min) — rehearse this

A four-beat narrative that lands with a non-specialist audience. **Driven entirely from UI Tab 1** — roughly 60 seconds of clicking, no cell execution, no scrolling:

| Beat | Action in the UI | What the audience sees |
|---|---|---|
| 1. **It works** | Ask a normal support question, all defenses off | Correct, helpful answer |
| 2. **It breaks** | Select the best attack from the dropdown | 🔴 Canary token on screen / injected instruction obeyed |
| 3. **We fix it** | Tick the best defense stack checkboxes | 🟢 Same attack now blocked |
| 4. **It still works** | Re-ask the benign question from beat 1 | Still correct — utility preserved |

Beat 4 is the one teams forget, and it is the one that proves the accuracy–robustness tradeoff was actually *managed* rather than ignored.

Use the **"Run demo script"** button (T8.4) rather than clicking manually — under presentation pressure, one mis-click costs more than the button costs to build. Keep the **backup recording** (T9.9) open in another window.

---

## 10. Decisions for the team

**These need agreement before coding starts (task T0.1).**

| # | Decision | Recommendation | Status |
|---|---|---|---|
| 1 | Governance framework: **NIST AI RMF** vs **AI Verify** | Map/Measure/Manage maps almost 1:1 onto this pipeline (Map = threat model, Measure = ASR harness, Manage = defense stack) | ✅ **NIST AI RMF** |
| 2 | Corpus / domain | Bitext customer-support (e-commerce-ish). Domain stated as not mattering — best-quality option available | ✅ Confirmed |
| 3 | Attack line-up | 6 static + 1 adaptive (exceeds the "≥5" requirement) | ✅ Confirmed |
| 4 | Defense line-up | 6 defenses + Optuna selector (exceeds "≥5") | ✅ Confirmed |
| 5 | Deadline | **Sun 26 Jul 2026, 23:59** | ✅ Verified |
| 6 | Who owns what | Suggested split below — deferred until code is ready to hand out | ⏸️ Deferred |
| 7 | Compute | **Colab Pro** (L4) + validated on a **32 GB GPU**. The pipeline **auto-detects GPU VRAM** (`ragguard.autotune`) and picks bf16 / 4-bit / a smaller victim model, so it runs on *any* GPU: 24GB → bf16, 12GB → 4-bit (auto-installs bitsandbytes), ≤10GB → Qwen2.5-3B, no GPU → tiny model / offline UI. | ✅ Confirmed |
| 8 | Notebook format | **Resolved** — professor confirmed "one per lab" is a typo and multiple notebooks are fine. We ship **two**: `00_MAIN.ipynb` (everything, graded) + `01_DEMO.ipynb` (~5 cells, loads cache, launches UI in ~2 min) | ✅ **Settled** |
| 9 | Gradio UI | **Yes — build it with strong UX/UI principles.** Serves Criterion 4 (20%) and the brief's "communicate to non-specialists". 4 tabs, results precomputed, clear visual hierarchy, semantic status colours | ✅ Confirmed |

### Suggested ownership split

Work divides cleanly into four streams — collapse or merge these to fit the actual team size:

- **Stream A — System & Governance:** T0–T2, corpus, canaries, RAG bot, NIST AI RMF scorecards (T7), Report §1
- **Stream B — Attacks:** T3 + T4, the judge oracle, Report §2
- **Stream C — Defenses:** T5 + T6, Optuna tuning, Pareto analysis, Report §3
- **Stream D — Communication & UI:** the Gradio app (T8), slide deck, demo rehearsal + backup recording, report assembly and page-count discipline, references

Streams B and C both depend on Stream A finishing **T0–T2**, so that chain is the critical path — it is worth putting more than one person on it and getting it done first. Once T2 lands, attacks (T3), defenses (T5), and governance (T7.1) can all proceed in parallel.

---

## 11. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Victim model too weak — refuses nothing, so ASR is ~100% everywhere and defenses look trivially good | Low | Medium | **Resolved by upgrading 0.5B → Qwen3-8B**, which has genuine safety alignment. Still report ASR per attack *and* per defense; if any baseline saturates, note it honestly — model capability is a genuine finding. |
| Report exceeds 10 pages | High | Medium | Tables over prose; push raw outputs into the notebooks and reference them |
| Adaptive agent (A7) does not beat static ASR | Low | Medium | Still a legitimate, reportable finding — analyse *why*. Do not fake a result. |
| Defenses reduce ASR but tank utility | Medium | Low | This is the *point* — it is the tradeoff C3 asks us to quantify. Report it, don't hide it. |
| **Live demo fails** — wifi drops, Colab share link dies, sweep times out | Medium | **High** | Precomputed results (T8.8); "Run demo script" button (T8.4); **screen-recorded backup video** (T9.9). Never run a sweep live. |
| UI scope creep eats time that belongs to the analysis | Medium | Medium | Hard cap: 4 tabs, thin view layer, zero logic in `app.py`. Polish is explicitly *not* where the marks are. |
| `00_MAIN` runtime grows large | Medium | **Low** | Not a hard cliff — Colab allows ~12h sessions (§8.4). Generation cache + batching + two-stage stack search keep it near the ~30-min target; `N_PER_ATTACK` / `FAST_MODE` dials trim it further if needed |
| Colab drops the session mid-run (idle reset, closed tab, or laptop sleep) | Medium | Medium | Idle timer keys off *browser interaction*, not code execution — keep the tab open and the machine awake. Per-phase checkpointing to Drive means a drop costs the current phase, never the whole run |
| GPU credits run out | Low | Low | Colab Pro + L4 + credits confirmed (§10 #7) — ample headroom. `FAST_MODE` keeps dev-iteration burn low |
| Someone hits "Run all" on the demo notebook and wipes the cached results | Low | **High** | `01_DEMO.ipynb` is **read-only by design** — it loads artefacts, never writes or recomputes them |

**On negative results:** a defense that fails, or an agent that underperforms, is a perfectly good result *provided we interpret it honestly*. Fabricating or cherry-picking numbers is both an integrity breach and easy to catch in Q&A.

---

## 12. Academic integrity note

The brief is explicit:

- **Allowed:** ART, TextAttack, Alibi, Optuna, HF transformers per labs; cited papers & docs
- **Not allowed:** sharing code/results between teams; **undisclosed LLM-generated report text**
- **Every member must contribute**

Two practical implications for us:

1. **The report prose must be written by the team**, or any AI assistance must be disclosed as the course requires. This planning document and any generated code scaffolding are development aids — the analysis, interpretation, and write-up need to be genuinely ours, and we need to actually understand every number we present. Q&A is 5 minutes and will expose anyone who does not.
2. **Do not share this plan or our code with other teams.**

Check the course's specific AI-use disclosure policy before submission.

---

## 13. References

### Models
- Qwen3-8B — https://huggingface.co/Qwen/Qwen3-8B  _(upgraded from the brief's Qwen2.5-0.5B-Instruct suggestion)_
- all-MiniLM-L6-v2 — https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- DeBERTa-v3 prompt-injection detector v2 — https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2

### Datasets
- Bitext customer-support — https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset
- deepset prompt-injections — https://huggingface.co/datasets/deepset/prompt-injections
- jailbreak-classification — https://huggingface.co/datasets/jackhhao/jailbreak-classification

### Frameworks and papers (to cite properly in the report)
- NIST AI Risk Management Framework (AI RMF 1.0) — Map / Measure / Manage
- OWASP Top 10 for LLM Applications — LLM01 Prompt Injection, LLM06 Sensitive Information Disclosure
- Greshake et al., *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*
- Chao et al., *Jailbreaking Black Box Large Language Models in Twenty Queries* (PAIR) — basis for the A7 adaptive agent
- Hines et al., *Defending Against Indirect Prompt Injection Attacks With Spotlighting* — basis for D1
- Zou et al., *Universal and Transferable Adversarial Attacks on Aligned Language Models*

> Verify exact citation details before submission — do not cite anything the team has not actually looked at.

---

*Plan generated 21 Jul 2026. Update the checkboxes in §9 and §10 as we go.*
