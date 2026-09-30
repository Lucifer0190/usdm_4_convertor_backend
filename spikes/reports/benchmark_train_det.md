# Benchmark - deterministic only (no LLM)

Studies: 5 | reference items 976 | matched 567 | spurious 403

**Accuracy (matched / (reference + spurious)): 41.1%**  |  recall 58.1%

| Study | Accuracy | Recall | Matched | Reference | Spurious | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| C5091017 | 71.6% | 89.7% | 235 | 262 | 66 | 19 |
| C4601003 | 48.5% | 64.2% | 95 | 148 | 48 | 20 |
| C4891001 | 31.0% | 58.0% | 101 | 174 | 152 | 21 |
| C4891002 | 20.2% | 28.1% | 61 | 217 | 85 | 21 |
| C4891006 | 33.0% | 42.9% | 75 | 175 | 52 | 21 |

## By category (all studies pooled)

| Category | Matched | Reference | Delivered | Recall |
|---|---:|---:|---:|---:|
| scalars | 17 | 34 | 28 | 50% |
| identifiers | 18 | 23 | 22 | 78% |
| arms | 5 | 9 | 9 | 56% |
| interventions | 5 | 12 | 9 | 42% |
| criteria | 92 | 114 | 107 | 81% |
| objectives | 35 | 42 | 62 | 83% |
| endpoints | 38 | 73 | 111 | 52% |
| estimands | 6 | 20 | 7 | 30% |
| epochs | 6 | 20 | 13 | 30% |
| encounters | 38 | 60 | 50 | 63% |
| activities | 165 | 245 | 180 | 67% |
| marks | 142 | 290 | 365 | 49% |
| vendors | 0 | 34 | 7 | 0% |
