# IndexLite benchmark run

Measured at 2026-10-13T09:40:44.498511+00:00.

Seed 1729; 20 repetitions after 3 warm-ups; top-k 10.

Indexed scoring includes query tokenization, posting reads, BM25 and heap selection. Formatting includes fetching the selected text and generating snippets. The exhaustive reference scans preloaded term-frequency dictionaries and fully sorts matches; its loading and snippet work are excluded from the speedup comparison.

First-query measurements use new connections after the build. OS and SQLite cache conditions are uncontrolled; none of these measurements claim a cold cache.

Agreement validates execution consistency, not relevance. Synthetic queries are designed experiments, not user traffic. No memory measurements are reported.

## synthetic-1000 (1,000 documents)

Build: 12.872 s; 78 documents/s. Source: 794,653 bytes; index: 3,010,560 bytes.

| Query | Candidates | Indexed median/p95 ms | Reference median/p95 ms | Format median ms | Scoring speedup | Agreement |
|---|---:|---:|---:|---:|---:|---|
| `quasar` | 1 | 0.0193/0.0323 | 0.1672/0.2143 | 0.0955 | 8.69× | yes |
| `system` | 1,000 | 1.4635/1.6785 | 1.0093/1.4082 | 0.7311 | 0.69× | yes |
| `memory` | 200 | 0.3471/0.4553 | 0.3408/0.4426 | 0.6500 | 0.98× | yes |
| `quasar memory` | 200 | 0.3513/0.4550 | 0.4199/0.4569 | 0.6726 | 1.20× | yes |
| `term000 term001` | 498 | 0.9708/1.2929 | 0.7695/1.0007 | 1.5181 | 0.79× | yes |
| `doc000000` | 1 | 0.0184/0.0260 | 0.1463/0.2579 | 0.0913 | 7.95× | yes |
| `missingtoken` | 0 | 0.0067/0.0138 | 0.1370/0.2296 | 0.0003 | 20.61× | yes |
| `system quasar` | 1,000 | 1.4756/1.6963 | 1.1263/1.5097 | 0.7543 | 0.76× | yes |

Build boundaries (seconds): extraction=12.0299, tokenization=0.0633, construction=0.3466, validation=0.1044, publication=0.0004, total=12.8716

Open: 0.7252 ms; reference preload: 40.72 ms.

## synthetic-10000 (10,000 documents)

Build: 129.570 s; 77 documents/s. Source: 7,982,930 bytes; index: 30,289,920 bytes.

| Query | Candidates | Indexed median/p95 ms | Reference median/p95 ms | Format median ms | Scoring speedup | Agreement |
|---|---:|---:|---:|---:|---:|---|
| `quasar` | 10 | 0.1112/0.1894 | 2.5799/3.1321 | 1.6253 | 23.20× | yes |
| `system` | 10,000 | 22.8926/25.8339 | 13.2110/14.6552 | 0.7573 | 0.58× | yes |
| `memory` | 2,000 | 10.1107/10.9432 | 5.3622/6.5173 | 0.7459 | 0.53× | yes |
| `quasar memory` | 2,000 | 10.2769/11.4933 | 6.2591/7.9041 | 1.6287 | 0.61× | yes |
| `term000 term001` | 5,026 | 23.1851/32.0625 | 10.7149/12.3851 | 1.5004 | 0.46× | yes |
| `doc000000` | 1 | 0.0667/0.1305 | 3.7104/4.8022 | 0.0912 | 55.63× | yes |
| `missingtoken` | 0 | 0.0237/0.0995 | 3.1497/3.7949 | 0.0003 | 132.62× | yes |
| `system quasar` | 10,000 | 23.2643/32.1034 | 13.3487/16.1896 | 1.7450 | 0.57× | yes |

Build boundaries (seconds): extraction=115.4781, tokenization=0.6594, construction=4.6297, validation=5.0861, publication=0.0245, total=129.5698

Open: 0.8973 ms; reference preload: 505.86 ms.

## synthetic-50000 (50,000 documents)

Build: 689.640 s; 73 documents/s. Source: 40,023,266 bytes; index: 153,997,312 bytes.

| Query | Candidates | Indexed median/p95 ms | Reference median/p95 ms | Format median ms | Scoring speedup | Agreement |
|---|---:|---:|---:|---:|---:|---|
| `quasar` | 50 | 0.6291/0.8063 | 14.4441/15.9666 | 0.9133 | 22.96× | yes |
| `system` | 50,000 | 132.3952/141.8097 | 80.4172/88.0560 | 0.8739 | 0.61× | yes |
| `memory` | 10,000 | 56.8940/61.3293 | 31.1227/32.4987 | 0.8063 | 0.55× | yes |
| `quasar memory` | 10,000 | 57.6118/62.2060 | 35.7403/37.3833 | 0.9096 | 0.62× | yes |
| `term000 term001` | 25,277 | 133.6974/143.8425 | 64.1088/68.7629 | 1.4408 | 0.48× | yes |
| `doc000000` | 1 | 0.1084/0.3224 | 20.2725/22.1427 | 0.1204 | 187.02× | yes |
| `missingtoken` | 0 | 0.0424/0.1694 | 18.5917/19.3702 | 0.0005 | 438.48× | yes |
| `system quasar` | 50,000 | 132.9337/145.3181 | 82.0088/95.4176 | 0.9993 | 0.62× | yes |

Build boundaries (seconds): extraction=607.8408, tokenization=3.4460, construction=26.6439, validation=30.4346, publication=0.0006, total=689.6399

Open: 0.8350 ms; reference preload: 2354.02 ms.

## demo (8 documents)

Build: 0.143 s; 56 documents/s. Source: 2,759 bytes; index: 36,864 bytes.

| Query | Candidates | Indexed median/p95 ms | Reference median/p95 ms | Format median ms | Scoring speedup | Agreement |
|---|---:|---:|---:|---:|---:|---|
| `recursive function stack` | 2 | 0.0309/0.0363 | 0.0105/0.0125 | 0.2019 | 0.34× | yes |
| `memory` | 2 | 0.0139/0.1354 | 0.0061/0.0156 | 0.1696 | 0.43× | yes |
| `queue` | 1 | 0.0113/0.0287 | 0.0054/0.0062 | 0.0858 | 0.48× | yes |
| `unicode` | 1 | 0.0107/0.0138 | 0.0045/0.0060 | 0.0939 | 0.42× | yes |
| `the` | 7 | 0.0222/0.0488 | 0.0104/0.0196 | 0.6234 | 0.47× | yes |
| `missingtoken` | 0 | 0.0065/0.0126 | 0.0037/0.0046 | 0.0003 | 0.57× | yes |

Build boundaries (seconds): extraction=0.0921, tokenization=0.0017, construction=0.0084, validation=0.0037, publication=0.0008, total=0.1426

Open: 0.7852 ms; reference preload: 0.25 ms.

## Environment

```json
{
  "python": "3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]",
  "sqlite": "3.53.1",
  "os": "Windows-11-10.0.26300-SP0",
  "cpu": "Intel64 Family 6 Model 183 Stepping 1, GenuineIntel",
  "logical_cpus": 32,
  "indexlite": "0.1.0",
  "packages": {
    "pytest": "8.4.2",
    "ruff": "0.17.0",
    "pypdf": "6.20.1",
    "matplotlib": "3.11.2"
  },
  "unicode_database": "15.0.0"
}
```

See summary.json for first-query measurements and raw.csv for every warm sample.

Run note: The 1,000-document case was measured in a separate run after the main run. The 10,000/50,000/demo cases use the main run; all cases use identical settings.
