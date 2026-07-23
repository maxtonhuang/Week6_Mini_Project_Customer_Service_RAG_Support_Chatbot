# RAGGuard UI — How to Use (New User Guide)

A 5-minute guide to the Gradio demo. No coding needed — it's all clicks.

---

## 1. Set it up & launch it

> **Do "First-time setup" once per machine.** After that, just use "Launch it" each time.

### First-time setup (from a fresh clone)

You need **Python 3.10–3.12** (not 3.13 — some GPU wheels lag on it) and, for real speed, an
**NVIDIA GPU**. The first launch downloads the model (~16 GB) from HuggingFace, so the first time
you also need **internet + ~20 GB free disk** (cached afterwards). No HuggingFace token is required —
everything is public.

**Local — Windows (PowerShell):**
```
git clone https://github.com/maxtonhuang/Week6_Mini_Project_Customer_Service_RAG_Support_Chatbot.git
cd Week6_Mini_Project_Customer_Service_RAG_Support_Chatbot
py -3.12 -m venv .venv                 # create the virtual env (use 3.10–3.12)
.\.venv\Scripts\Activate.ps1           # activate it
pip install -r requirements.txt        # install the pipeline
pip install torch --index-url https://download.pytorch.org/whl/cu128   # GPU only; skip on CPU-only
```

**Local — macOS / Linux:**
```
git clone https://github.com/maxtonhuang/Week6_Mini_Project_Customer_Service_RAG_Support_Chatbot.git
cd Week6_Mini_Project_Customer_Service_RAG_Support_Chatbot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# GPU only: pip install torch --index-url https://download.pytorch.org/whl/cu128
```

**Colab — nothing to install by hand.** Open the notebook straight from GitHub: **File → Open notebook →
GitHub tab**, paste this repo's URL, and open **`01_DEMO.ipynb`**. Set **Runtime → Change runtime type →
GPU** (e.g. T4/L4), then **Runtime → Run all**. The notebook's first cell **clones the repo into the Colab
VM and installs the dependencies for you** — and it's safe to re-run (it detects an existing clone and
skips it). When it finishes, click the public `…gradio.live` link it prints.

> You do **not** need to run `run_full.py` or create any files first. The results and plots
> (`artifacts/results.json`, the charts, the Governance scorecard) are already committed, and the
> live tabs build the pipeline themselves. `run_full.py` is only for regenerating the full report numbers.

### Launch it

**Local (on a GPU):**
```
.venv\Scripts\python serve_app.py          # Windows
./.venv/bin/python serve_app.py            # macOS / Linux
```
Wait ~40 seconds for "Running on local URL" (longer on the very first launch, while the model
downloads), then open **http://127.0.0.1:7860** in a browser.

**On Colab:** open `01_DEMO.ipynb`, run all cells, click the public `…gradio.live` link it prints.

> First question after launch is a little slow (the model warms up); everything after is fast.

> **Any GPU works:** on launch it auto-detects the available VRAM and picks a model/precision that fits
> (bf16, 4-bit, or a smaller model), printing its choice to the console. On a GPU under ~16 GB it
> runs 4-bit and installs `bitsandbytes` for you. No CUDA GPU? It falls back to a tiny model.

---

## 2. The big picture

The app is a **customer-service chatbot that we attack and defend**. It has five tabs:

| Tab | What it's for |
|---|---|
| **1 · Live Demo** | The main show — ask questions, launch attacks (at level L0/L1/L2), toggle defenses, watch it break and get fixed |
| **2 · Attack Lab** | The whole attack suite's success rates + the **sophistication-ladder** heatmap (L0/L1/L2 × D0/D1/D2) |
| **3 · Defense Lab** | Best defence stack, Optuna tuning, adaptive-attacker result, and the accuracy–robustness plots |
| **4 · Governance** | The NIST AI RMF scorecard, before vs after defenses |
| **5 · Run Pipeline** | One button to run the whole pipeline (Quick or Full) and fill every tab; saves to Google Drive if mounted |

---

## 3. Tab 1 — Live Demo (start here)

![RAGGuard Live Demo tab — controls on the left, result on the right](artifacts/ui_v3_livedemo.png)

*The **Live Demo** tab. Work down the left column: **① Ask a question** (type the customer message) → **② Launch an attack** (dropdown: `None` for a normal query, or `A1`–`A10`; and a **Sophistication level** dropdown — **L0** blunt / **L1** intermediate / **L2** advanced — that applies when an attack is chosen) → **③ Enable defences** (tick any of D1–D9). Then click **Ask** to run once, or **▶ Run demo script** to auto-play the four beats. The answer and verdict appear under **Result** on the right.*

![RAGGuard in dark mode — the header status chips stay readable in both themes](artifacts/ui_v3_livedemo_dark.png)

*The UI is **theme-aware** — here in dark mode. The four header chips (Model / Undefended ASR / Defended ASR / Best stack) stay readable in both light and dark themes.*

### The controls (left side)
- **Customer question** — type any support question (e.g. *"How long do I have to return an item?"*).
- **Attack** — a dropdown. `None` = a normal question. Pick an attack to fire it instead:
  - **A1** Direct prompt injection — "ignore your instructions and do X"
  - **A2** Jailbreak / persona override
  - **A3** Indirect injection — a *poisoned document* carries the attack
  - **A4** System-prompt extraction — "reveal your instructions"
  - **A5** Canary / knowledge-base extraction — "repeat the internal document"
  - **A6** Obfuscated injection — the same attack, hidden with encoding tricks
  - **A8** Membership inference — "does an internal doc about X exist?" (confirming it leaks)
  - **A9** Fingerprint / IP-ownership probe — makes the bot emit a planted `OWNER-FP-…` phrase
  - **A10** Paraphrased system-prompt extraction — "explain your instructions in your own words"
- **Active defenses** — nine checkboxes (D1–D9). Tick any combination to switch defenses on. The
  new ones: **D7** Visibility access-control (drops internal docs before the prompt), **D8** query-rate
  limit (throttles repeated queries in a session), **D9** semantic leak & fingerprint filter (blocks
  `OWNER-FP` phrases and paraphrased prompt leaks).
- **Ask** — runs it. **▶ Run demo script** — auto-plays the 4-beat story below.

### Reading the result (right side)

![RAGGuard Live Demo showing a red ATTACK SUCCEEDED verdict badge with retrieved context](artifacts/ui_v2_livedemo_attack.png)

*Here **A1 · Direct prompt injection** was run with **no defences**: the red **🔴 ATTACK SUCCEEDED** badge gives the verdict, the **Bot answer** contains the injected marker, and **Retrieved context** lists the documents the bot pulled (📄 public / 🔒 internal-canary / ☠️ injected). Tick **D4 + D5** and click **Ask** again to watch the same attack turn 🟢 **BLOCKED**.*

- **Verdict badge** (the coloured bar):
  - 🔵 **Benign query** — a normal question, no attack
  - 🔴 **ATTACK SUCCEEDED** — the attack worked (with the reason, e.g. "canary token leaked")
  - 🟢 **BLOCKED by D2, D6…** — a defense stopped it
  - ⚠️ **CANARY LEAKED** — appended when a secret token appears in the answer
- **Bot answer** — what the chatbot replied.
- **Retrieved context** — the documents the bot pulled from its knowledge base, tagged:
  - 📄 **public** — a normal FAQ document
  - 🔒 **INTERNAL/CANARY** — a confidential document that should never be shown
  - ☠️ **INJECTED (poisoned)** — an attacker-planted document

### The recommended 60-second demo (the 4 beats)
1. **It works.** Attack = `None`, no defenses → click **Ask**. You get a helpful answer.
2. **It breaks.** Attack = `A1` (or `A5`), no defenses → **Ask**. Badge turns 🔴 — the bot obeys the attacker / leaks a secret.
3. **We fix it.** Tick **D4 + D5** → **Ask** again. Badge turns 🟢 — same attack, now blocked. (For an **A9** fingerprint attack, use **D9** instead; for **A8** membership, **D7**.)
4. **It still works.** Attack = `None`, defenses still on → **Ask**. Normal answer — defenses didn't break usefulness.

> Prefer the **▶ Run demo script** button for presentations — it plays all four beats for you, so there's no mis-clicking on stage.

### Example — the new A9 fingerprint attack

![A9 fingerprint attack succeeding: the bot emits a planted OWNER-FP ownership phrase](artifacts/ui_v3_livedemo_a9.png)

*Attack = **A9 · Fingerprint / IP-ownership probe**, no defences → the bot emits the planted `OWNER-FP-…` phrase (red **ATTACK SUCCEEDED** — the retrieved context shows the fingerprint FAQ that taught it).*

![Same A9 attack blocked once D9 is enabled](artifacts/ui_v3_livedemo_a9_blocked.png)

*Tick **D9 · Semantic leak & fingerprint filter** and Ask again → 🟢 **BLOCKED**. (Try **A8** with **D7** to see access-control drop the internal doc, and **A10** with **D9** for the paraphrased-prompt leak.)*

---

## 4. Tab 2 — Attack Lab

![RAGGuard Attack Lab tab — full-run table and chart on top, live sweep controls below](artifacts/ui_v3_attacklab.png)

*Top half = the **last full run** (per-attack ASR table + bar chart; A1 is highest at 88%, A4 is 0%). Bottom half = **run your own quick sweep live**: set **Cases per attack** with the slider, click **Run attack sweep**, and the results fill the **Live ASR** panel.*

- The top table/chart are precomputed — they load instantly.
- To run live: move the **Cases per attack** slider (start small, e.g. 10) → click **Run attack sweep**.
- Higher bars = more successful attacks against the undefended bot.

### 🪜 Sophistication ladder (L0/L1/L2 × D0/D1/D2)
Below the chart is the **sophistication-ladder** heatmap + table from the last full run: attacks at three
sophistication levels (**L0** blunt → **L1** one technique → **L2** composed) against three defence levels
(**D0** none → **D1** content filters → **D2** defence-in-depth). Each cell is ASR; read it top-left (blunt
attack, no defence) to bottom-right (hardest attack, strongest defence).
- The story: **smarter attacks raise ASR when undefended** (overall D0: L0 31% → L1 44% → L2 48%), and
  **stronger defences knock it back to 0%** (D1/D2 columns), at **no utility/false-refusal cost** on this run.
- The per-family table shows which attacks are dangerous undefended (A5/A8/A9 reach 100% at L2·D0) and how
  the defence levels neutralise them.
- Populate it by pressing **Run** on the **Run Pipeline** tab (the ladder is one of the run's phases).

> The live sweep calls the model many times, so it takes a little while. Fine for exploring; for a live presentation, show the pre-made chart in `artifacts/asr_undefended.png` instead.

---

## 5. Tab 3 — Defense Lab

![RAGGuard Defense Lab tab — full-run heatmap, Pareto and adaptive plots on top, live evaluate below](artifacts/ui_v3_defenselab.png)

*Top half = the **full-run results**: the **best D1–D6 stack (D2+D5)** with its robustness/utility/FRR, the attack×defence **heatmap**, the utility-vs-robustness **Pareto** plot, and the **adaptive attacker** curve (flat along the bottom = the stack holds). Bottom half = **evaluate any stack live**.*

- The full search over all 64 **D1–D6** combinations is precomputed at the top — the **best D1–D6 stack is D2+D5** (robustness 96%, utility 0.44, FRR 5%). The new IP/membership attacks (A8–A10) need the targeted **D7–D9** (outside the 64-stack search), so the **full D1–D9 stack** takes overall ASR **31% → 0%**.
- To test a specific combination: tick defences under **Defences to evaluate** and click **Evaluate stack** — it runs a quick attack + benign check on that exact stack.

> The live **Evaluate stack** call runs the model, so give it a moment. For a demo, the precomputed heatmap/Pareto at the top are instant.

---

## 6. Tab 4 — Governance

![RAGGuard Governance tab — NIST AI RMF scorecard, baseline vs defended](artifacts/ui_v3_governance.png)

*The **NIST AI RMF scorecard** — how the system rates on Map / Measure / Manage. **Baseline (undefended, 4/18)** on top is mostly 🔴 gaps; **Defended (17/18)** below is mostly 🟢 managed, each row with its evidence. This is the "why it matters to a stakeholder" view.*

---

## 7. Tab 5 — Run Pipeline (one button)

This runs **all attacks + defenses** across the whole pipeline and fills in every other tab — no notebook cell needed.

![RAGGuard Run Pipeline tab — profile selector, Run button, and live progress log](artifacts/ui_v3_run.png)

*The **Run Pipeline** tab: pick **Quick** or **Full** and press the run button (its label follows the profile — **▶ Run Quick pipeline** / **▶ Run Full pipeline**), then watch the live log; the Attack/Defense/Governance tabs refresh when it finishes.*

- Pick a **Profile** (the button label tracks it). Both profiles run the **same phases** on all 9 attacks and every defence — only the **sample sizes** differ (the UI states this under the selector):
  - **Quick (~minutes)** — smaller samples (8 prompts/attack · 3 adaptive rounds · defence search screens each stack on 6 attacks + 8 benign); great for a demo and enough to populate every tab.
  - **Full (~hours, resumable)** — report-grade samples (50 prompts/attack · 6 rounds · 15 attacks + 20 benign per screen): the numbers you cite in the write-up. If the Colab runtime disconnects mid-run, just press the button again — it **resumes from the last completed phase**.
- **Resuming vs. a fresh run.** Every phase is checkpointed to `artifacts/full[_fast]/`, so a re-run loads completed phases from disk — if a run already finished, pressing again completes **in seconds** rather than recomputing (the button then reads **↻ Resume … (n/6 saved)** to make this obvious). To force a full recompute, tick **Start fresh — ignore saved checkpoints** before pressing (or delete the `artifacts/full[_fast]/` folder).
- Press the run button. A live log streams each phase (undefended → full-stack → attack×defence matrix → defence search → Optuna → adaptive attacker → **sophistication ladder** → plots), with a **live elapsed timer** that ticks every few seconds so it never looks frozen — even during the long 64-stack search. If it resumed, the first log line says so and lists which checkpoints it loaded.
- **⏹ Stop run** cancels a run in progress. It halts at the next phase/step boundary (so a long search stops within a stack or two, not instantly) and — importantly — **does not overwrite your saved results**: `results.json` is only written on a *complete* run, so a stop leaves the previous numbers intact. Completed phases stay checkpointed, so pressing Run afterwards **resumes** from where you stopped.
- When it finishes, the **Attack Lab**, **Defense Lab** and **Governance** tabs refresh automatically with the new numbers and plots.
- **🔄 Reload saved results** re-reads the last saved run — handy when you reopen the UI and want the previous results back.

> It reuses the model the UI already loaded (no second copy in VRAM), and wraps it in a **disk generation cache** (`artifacts/gen_cache.json`) so identical prompts across runs aren't recomputed — a re-run reuses earlier generations instead of regenerating them. Results save to `artifacts/` — or to **Google Drive** if mounted (below).

### Persisting across reloads (Google Drive)

A Colab VM is wiped when the runtime recycles, so results and the ~16 GB model download are normally lost. To keep them:

- The notebooks include an **optional Drive cell** (`USE_DRIVE = True`, just below the setup cell) that mounts Google Drive and points the model cache at it. It asks you to authorise Drive once.
- With Drive mounted, results/checkpoints save to `MyDrive/ragguard` and the model cache to `MyDrive/hf_cache` — so a later session **reloads your results** and **skips re-downloading the model**.
- On startup the UI **automatically loads the last saved `results.json`**, so reopening the demo shows your previous run straight away (or click 🔄 Reload saved results).

---

## 8. Tips & gotchas

- **On Colab, the launch cell prints `[RAGGuard]` progress lines** (auto-config → loading model → starting UI), so you can see it's working. The model load (~16 GB) is the slow step — turn on the Drive cell (`USE_DRIVE = True`) so it isn't re-downloaded every session. The launch **auto-detects your GPU** and runs the 8B model in 4-bit on a 16 GB card (so it fits instead of spilling to disk).
- **If the public `gradio.live` link stalls** for more than ~1 min, re-run the launch cell with **`launch(share=False)`** — that renders the UI inline in the cell (reliable on Colab, no external tunnel). Re-running is safe now (it releases the previous server first).
- **First answer is slow** (model warm-up) — this is normal, not a bug.
- **Don't run Tab 2/3 sweeps during a live demo** — they call the model hundreds of times and take minutes. Use Tab 1 (instant) and the pre-made plots in `artifacts/`.
- **Attacks are probabilistic against a real model** — a strong model (Qwen3-8B) legitimately refuses some attacks. If one doesn't succeed, try another (A1 and A5 are the most reliable for a demo).
- **Keep the browser tab open** while presenting; closing it or letting the laptop sleep can drop the server.
- **Backup:** screen-record the 4-beat demo in advance in case the venue Wi-Fi or the server misbehaves.
