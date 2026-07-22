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

**Colab — no venv needed** (Colab already has Python + most of torch). First set the runtime to a GPU
(**Runtime → Change runtime type → GPU**, e.g. T4/L4), then in the first cell:
```
!git clone https://github.com/maxtonhuang/Week6_Mini_Project_Customer_Service_RAG_Support_Chatbot.git
%cd Week6_Mini_Project_Customer_Service_RAG_Support_Chatbot
!pip install -r requirements.txt
```

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

The app is a **customer-service chatbot that we attack and defend**. It has four tabs:

| Tab | What it's for |
|---|---|
| **1 · Live Demo** | The main show — ask questions, launch attacks, toggle defenses, watch it break and get fixed |
| **2 · Attack Lab** | Run the whole attack suite and see a success-rate chart |
| **3 · Defense Lab** | Search for the best defense combination |
| **4 · Governance** | The NIST AI RMF scorecard, before vs after defenses |

---

## 3. Tab 1 — Live Demo (start here)

### The controls (left side)
- **Customer question** — type any support question (e.g. *"How long do I have to return an item?"*).
- **Attack** — a dropdown. `None` = a normal question. Pick `A1…A6` to fire an attack instead:
  - **A1** Direct prompt injection — "ignore your instructions and do X"
  - **A2** Jailbreak / persona override
  - **A3** Indirect injection — a *poisoned document* carries the attack
  - **A4** System-prompt extraction — "reveal your instructions"
  - **A5** Canary / knowledge-base extraction — "repeat the internal document"
  - **A6** Obfuscated injection — the same attack, hidden with encoding tricks
- **Active defenses** — six checkboxes (D1–D6). Tick any combination to switch defenses on.
- **Ask** — runs it. **▶ Run demo script** — auto-plays the 4-beat story below.

### Reading the result (right side)
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
3. **We fix it.** Tick **D2 + D3** (and **D6**) → **Ask** again. Badge turns 🟢 — same attack, now blocked.
4. **It still works.** Attack = `None`, defenses still on → **Ask**. Normal answer — defenses didn't break usefulness.

> Prefer the **▶ Run demo script** button for presentations — it plays all four beats for you, so there's no mis-clicking on stage.

---

## 4. Tab 2 — Attack Lab

- Move the **Cases per attack** slider (start small, e.g. 10).
- Click **Run attack suite**. It runs every attack and shows a **bar chart of success rate (ASR)** per attack, plus a table.
- Higher bars = more successful attacks against the undefended bot.

> This takes a little while (it runs the model many times). Fine for exploring; for a live presentation, show the pre-made chart in `artifacts/asr_undefended.png` instead.

---

## 5. Tab 3 — Defense Lab

- Click **Run defense search**. It tries many combinations of defenses and reports the **best stack** — the smallest set of defenses that stops the most attacks while keeping the bot useful.
- The **Pareto frontier** table shows the trade-off: each row is a defense combo with its *utility* (how useful the bot still is) and *robustness* (how well it resists attacks).

> This is the slowest tab (it's a big search). For a demo, rely on the precomputed `artifacts/pareto.png` and the best stack already reported (**[D2+D3]**).

---

## 6. Tab 4 — Governance

Shows the **NIST AI RMF scorecard** — how the system rates on Map / Measure / Manage — **before** defenses (mostly 🔴 gaps) and **after** (mostly 🟢 managed). This is the "why it matters to a stakeholder" view.

---

## 7. Tips & gotchas

- **First answer is slow** (model warm-up) — this is normal, not a bug.
- **Don't run Tab 2/3 sweeps during a live demo** — they call the model hundreds of times and take minutes. Use Tab 1 (instant) and the pre-made plots in `artifacts/`.
- **Attacks are probabilistic against a real model** — a strong model (Qwen3-8B) legitimately refuses some attacks. If one doesn't succeed, try another (A1 and A5 are the most reliable for a demo).
- **Keep the browser tab open** while presenting; closing it or letting the laptop sleep can drop the server.
- **Backup:** screen-record the 4-beat demo in advance in case the venue Wi-Fi or the server misbehaves.
