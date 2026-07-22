# Attack × Defence Level Schema

Learning / report schema for the RAGGuard prototypes. **Not** the scored production
suite (`build_all_attacks` / `build_all_defenses`). Those stay L0.

The goal is a **ladder experiment**, not a one-to-one duel:

> Show that smarter attacks raise ASR under the usual (L0) defences, then that
> L1 and L2 defences reduce ASR further — at a measurable utility / FRR cost.

That matches Criterion 3 (accuracy–robustness tradeoff).

---

## 1. Axes

| Axis | Symbol | Values | Meaning |
|------|--------|--------|---------|
| **Attack sophistication** | \(A_\ell\) | \(\ell \in \{0,1,2\}\) | How hard the prompt / poison is |
| **Defence strength** | \(D_k\) | \(k \in \{0,1,2\}\) | How strong the control stack is |
| **Family** | A1–A7 / D1–D6 / STACK | ids | Which threat or control |

Cells in the experiment are pairs \((A_\ell, D_k)\). Primary metric: **ASR**.
Side metrics: **utility** (benign answer quality) and **FRR** (false refusal / block rate).

```text
                 D0 (production)     D1 (upgraded)      D2 (in-depth)
               ┌──────────────────┬──────────────────┬──────────────────┐
  A0 blunt     │  baseline ASR    │  (optional)      │  (optional)      │
  A1 mid       │  ASR ↑ vs A0     │  ASR ↓ vs D0     │  ASR ↓ further   │
  A2 advanced  │  hardest on L0   │  still reduced   │  strongest guard │
               └──────────────────┴──────────────────┴──────────────────┘
```

You do **not** need every cell filled. Minimum useful story:

1. \(A_1\) or \(A_2\) vs \(D_0\) — usual stack breaks (or ASR rises).
2. Same attacks vs \(D_1\) — ASR drops.
3. Same attacks vs \(D_2\) (or one deep upgrade) — ASR drops more; FRR noted.

---

## 2. Attack levels (\(A_\ell\))

| Level | Name | Source | Intent |
|-------|------|--------|--------|
| **A0 / L0** | Blunt / production | `ragguard/attacks/static.py` | Direct imperatives (`Ignore your instructions…`, obvious markers). What FULL ASR already used. |
| **A1 / L1** | Intermediate | `prototypes/sophisticated_attacks.py` | **One** clear technique per example (authority spoof, fiction frame, soft delimiter breakout, …). |
| **A2 / L2** | Advanced | same file | **Composed** techniques (encoding + persona, gradual escalation, format smuggling, adaptive recipes). |

Per-family catalogue keys: `A1` … `A7`, each with `level ∈ {1, 2}`.

Judge-compatible win tokens where possible: `INJECTED-OK-A1`, `PWNED-A2`, …

```bash
python prototypes/print_sophisticated_attacks.py
python prototypes/print_sophisticated_attacks.py A1 2
```

---

## 3. Defence levels (\(D_k\))

| Level | Name | Source | Intent |
|-------|------|--------|--------|
| **D0 / L0** | Production baseline | `ragguard/defenses/impl.py` | Current D1–D6 and reported best stack (e.g. D4+D5 in FULL artefacts). |
| **D1 / L1** | Single-control upgrades | `prototypes/sophisticated_defenses.py` | Stronger *one* control: hierarchy prompt, provenance allowlist, ensemble detector, decode-then-scan, … |
| **D2 / L2** | Defence-in-depth | same file | Composition: signed tools, secondary judge, query–answer consistency, recursive decode + stack order. |

Catalogue also documents **STACK** L1/L2 (ordered pipelines), not only atomic Di.

```bash
python prototypes/print_sophisticated_defenses.py
python prototypes/print_sophisticated_defenses.py STACK 2
```

---

## 4. Family map (what counters what)

Rough pairing for report prose — not a hard requirement that every upgrade ships.

| Attack family | Threat sketch | L0 defence | L1 / L2 defence ideas |
|---------------|---------------|------------|------------------------|
| **A1** | Prompt injection / override | D1 spotlight, D2 | D1 hierarchy / dual-channel; D2 ensemble + judge |
| **A2** | Jailbreak / persona | D2, D1 | Intent gate; secondary judge |
| **A3** | Retrieval poison | D3, D5 | Provenance allowlist; chunk instruction classifier |
| **A4** | System / canary exfil | D4 | Expanded secret lexicon; decode-then-scan |
| **A5** | Indirect / auditor framing | D4, D1 | Structured output allowlist; secret n-grams |
| **A6** | Obfuscation | D6 → D2 | Recursive decode; fragment reassembly |
| **A7** | Adaptive / multi-turn style | Stack + search | Evaluate adaptive *against* L1/L2 stack |

---

## 5. Metrics & reporting

| Symbol | Definition | Notes |
|--------|------------|-------|
| **ASR** | Fraction of attack cases that succeed (judge / marker / policy) | Report **raw** and **post-block** if D4 hides markers from the user. |
| **Utility** | Benign QA quality (e.g. support accuracy / judge score) | Same benign set across \(D_k\). |
| **FRR** | Benign queries blocked or wrongly refused | Expect FRR ↑ as \(D_k\) ↑. |

Suggested table for the report / appendix:

| Attack level | Defence level | N | ASR | Utility | FRR |
|--------------|---------------|---|-----|---------|-----|
| A0 | D0 | … | … | … | … |
| A1 | D0 | … | … | … | … |
| A1 | D1 | … | … | … | … |
| A2 | D0 | … | … | … | … |
| A2 | D2 | … | … | … | … |

Narrative one-liner:

> Under production defences (\(D_0\)), moving from blunt (\(A_0\)) to sophisticated
> (\(A_1\)/\(A_2\)) attacks raises ASR; upgrading to \(D_1\)/\(D_2\) recovers
> robustness at cost \(\Delta\) FRR / latency.

---

## 6. Implementation scope

| Layer | Wired into scored suite? | Role |
|-------|--------------------------|------|
| Production A0 / D0 | **Yes** | Official FULL / LOCAL_SMOKE numbers |
| Sophisticated A1–A2 scripts | **No** (prototypes) | Learning catalogue + optional smoke eval |
| Sophisticated D1–D2 designs | **No** (prototypes) | Spec first; implement 1–2 deeply if measuring |

**Practical advice:** implement one or two L1/L2 controls (e.g. D1 instruction hierarchy + D4 decode-then-scan), keep the rest as design notes in `sophisticated_defenses.py`, and measure against a fixed sophisticated attack subset.

Local 4-bit / smoke ≠ Max FULL bf16 — label runs clearly.

---

## 7. File index

| Path | Role |
|------|------|
| `ragguard/attacks/static.py` | Attack **L0** |
| `ragguard/defenses/impl.py` | Defence **L0** |
| `prototypes/sophisticated_attacks.py` | Attack **L1 / L2** catalogue |
| `prototypes/sophisticated_defenses.py` | Defence **L0 notes + L1 / L2** catalogue |
| `prototypes/print_sophisticated_attacks.py` | Pretty-print attacks |
| `prototypes/print_sophisticated_defenses.py` | Pretty-print defences |
| `prototypes/README_SOPHISTICATED_ATTACKS.md` | Short attack cheat-sheet |
| `prototypes/README_SOPHISTICATED_DEFENSES.md` | Short defence cheat-sheet |
| **This file** | Full schema for the ladder experiment |

---

## 8. What this schema is *not*

- Not a claim that L2 defences are invulnerable.
- Not a requirement that attack L2 must be paired only with defence L2.
- Not a replacement for Max’s official A1–A7 / D1–D6 ids in the scored pipeline.
- Not automatically included in `artifacts/results.json` until you choose to melt and re-run.
