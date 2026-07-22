# Sophisticated D1–D6 / stack defences (L0 · L1 · L2)

Full ladder schema (attack × defence levels, metrics, report table):
[`SCHEMA_ATTACK_DEFENSE_LEVELS.md`](SCHEMA_ATTACK_DEFENSE_LEVELS.md).

**Yes, levelling defences makes sense** — especially as a *measurement story*:

| Defence level | Role |
|---|---|
| **L0** | Today's production `impl.py` (what Max's FULL ASR used) |
| **L1** | Stronger single controls (hierarchy prompt, provenance, decode-scan, …) |
| **L2** | Defence-in-depth / extra judges / consistency checks |

Cross with attack levels A0/A1/A2 → ASR matrix + utility/FRR. That is exactly the
accuracy–robustness narrative Criterion 3 wants.

You do **not** need to implement every L2 idea. Implement 1–2, keep the rest as
design in `sophisticated_defenses.py`.

```bash
python prototypes/print_sophisticated_defenses.py
python prototypes/print_sophisticated_defenses.py D3 1
python prototypes/print_sophisticated_defenses.py STACK 2
```
