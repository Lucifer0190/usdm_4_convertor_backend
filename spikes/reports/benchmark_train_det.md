# Benchmark - deterministic only (no LLM)

Studies: 5 | reference items 976 | matched 564 | spurious 402

**Accuracy (matched / (reference + spurious)): 40.9%**  |  recall 57.8%

| Study | Accuracy | Recall | Matched | Reference | Spurious | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| C5091017 | 71.6% | 89.7% | 235 | 262 | 66 | 15 |
| C4601003 | 48.5% | 64.2% | 95 | 148 | 48 | 14 |
| C4891001 | 30.4% | 56.9% | 99 | 174 | 152 | 17 |
| C4891002 | 19.9% | 27.6% | 60 | 217 | 84 | 17 |
| C4891006 | 33.0% | 42.9% | 75 | 175 | 52 | 13 |

## By category (all studies pooled)

| Category | Matched | Reference | Delivered | Recall |
|---|---:|---:|---:|---:|
| scalars | 17 | 34 | 28 | 50% |
| identifiers | 18 | 23 | 22 | 78% |
| arms | 3 | 9 | 7 | 33% |
| interventions | 4 | 12 | 7 | 33% |
| criteria | 92 | 114 | 107 | 81% |
| objectives | 35 | 42 | 62 | 83% |
| endpoints | 38 | 73 | 111 | 52% |
| estimands | 6 | 20 | 7 | 30% |
| epochs | 6 | 20 | 13 | 30% |
| encounters | 38 | 60 | 50 | 63% |
| activities | 165 | 245 | 180 | 67% |
| marks | 142 | 290 | 365 | 49% |
| vendors | 0 | 34 | 7 | 0% |
