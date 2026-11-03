# Ramba Joring geochem + ML (OlympiAR 2026 Round 2)

Team repository for the ML and data-analysis backbone of our OlympiAR 2026 Round 2 submission
(PT Agincourt Resources / IAGI / MGEI): an exploration + environmental report on the **Ramba
Joring (RJ) high-sulfidation epithermal Au-Cu prospect, Martabe district, North Sumatra**.

> **PRIVATE repo, team only.** It contains the committee's confidential data package and the brief
> (which includes our ioGAS licence key). Never make it public, never fork it to a public account,
> never upload the data to cloud ML services or chatbots, and never paste the licence key or
> committee contacts anywhere. See [AGENTS.md](AGENTS.md) §2.

**Bahasa Indonesia:** report writers and presenters should start with the ML findings report
[outputs/laporan_ml/laporan_ml_v1.html](outputs/laporan_ml/laporan_ml_v1.html) (one local file, open in
a browser), then [PANDUAN_TIM.md](PANDUAN_TIM.md), which maps every file to its report chapter.

## Where things are

| File | What it is |
|---|---|
| [outputs/laporan_ml/laporan_ml_v1.html](outputs/laporan_ml/laporan_ml_v1.html) | ML findings report for teammates (Bahasa, English terms in brackets): per ML task the question, answer, figures with reading notes, confidence, limits, spoken script and likely judge questions. Built by `scripts/21_laporan_ml.py` from `reports/laporan_ml_src.html` |
| [PANDUAN_TIM.md](PANDUAN_TIM.md) | Team guide (Bahasa): files per report chapter, open items, references to verify, repo usage |
| [AGENTS.md](AGENTS.md) | Rules, data facts, verified findings and the ML plan. Single source of truth for coding agents (Claude Code, Codex) |
| [LOG.md](LOG.md) | Append-only log of every plan, decision, deviation, number and spoken explanation, in order |
| [CLAUDE.md](CLAUDE.md) | Claude Code specifics (it loads AGENTS.md) |
| `Technical Meeting 2nd Round OlympiAR 2026.pdf` | The committee brief: rules, report structure, rubric, deliverables |
| `data/raw/` | The committee data package, untouched. `RAW_MANIFEST.sha256` holds its hashes |
| `data/interim/` | Stage outputs of the cleaning pipeline (`01_…` to `06_…`) |
| `data/processed/` | Final tables: validation, geochemistry analysis, ML summaries |
| `data/processed/iogas/` | ioGAS-ready CSVs, the hand-off to the ioGAS teammate (see `README_iogas.txt` there) |
| `data/processed/ml/` | One file per ML task and table (`<table>__<task>.csv`: key + `ML_*` columns) |
| `gis/` | Derived layers (EPSG:32647): lidar DEM, hillshade, drainage, ML grids and sections |
| `outputs/figures/` | Report charts, 300 dpi, Bahasa labels, versioned `_v1`, `_v2` |
| `outputs/maps/` | QGIS projects (`.qgz`) and exported maps/sections; `qc/` holds check projects |
| `src/` | Importable functions (small, tested) |
| `scripts/` | Numbered runnable steps |
| `tests/` | pytest suite (131 tests), including `test_raw.py`, which fails if any raw file changes |

## Status (4 Nov 2026)

Everything on the ML and data side is done. Each row has a plan entry and a results entry in
`LOG.md`.

| Step | Script(s) | Main outputs | Report § |
|---|---|---|---|
| 0 Raw check | `00_inventory.py` | inventory, manifest check | — |
| 1 Semantics | `01_semantics.py` | surface 0 → blank, NS-SEL, detection limits harmonised, `<el>_cens` flags | 3 |
| 2 Lidar DEM | `02_dem.py` | `gis/lidar_dem.tif`, `hillshade.tif`, `dem_support_dist.tif` | 2, maps |
| 3 Coordinates | `03_coords.py` | surface Z re-draped on lidar, survey extrapolation, minimum-curvature desurvey | 3, 5 |
| 4 Codes | `04_codes.py` | harmonised lithology/alteration/mineral codes, `code_dictionary.csv` | 3, 5 |
| 5 Joins | `05_joins.py` | logs attached to assays by midpoint | 5 |
| 6 Composites | `06_composite.py` | 1 m length-weighted composites | 5 |
| 7 Deliverables | `07_export.py` | `validation_flags.csv`, `validation_summary.csv`, `qaqc_precision.csv`, ioGAS CSVs | 3 |
| ML-1 Thresholds | `08_ml1_thresholds.py` | GMM thresholds per element (`element_thresholds.csv`) | 3 |
| ML-2 Logging from chemistry | `09_ml2_classify.py` | RF classes, leave-one-pad-out CV, SHAP, review list | 3 |
| ML-3 Surface zonation | `10_ml3_zonation.py` | soil/rock H/M/L zones with probabilities, GP index map | 4 |
| ML-4 Geochem-stratigraphy | `11_ml4_hmm.py`, `12_ml4_sections.py`, `13_ml4_qgis_layouts.py` | Gaussian HMM states, sections A–C | 5 |
| ML-5 PAF/NAF | `14_ml5_paf.py` | NAF / PAF-LC / PAF-HC, conformal sets, NAG-test list, flowchart | 6 |
| Drainage | `15_drainage_qgis.py`, `15b_drainage_post.py` | derived streams (lidar), catchments, 50 m buffer | 6, 7 |
| ML-6 Targeting (bonus) | `16_ml6_targeting.py`, `17_ml6_qgis_layouts.py` | GP (= kriging) Au + uncertainty, 5 proposed holes, design map and section | 7 |
| Deliverable 3 | `18_geochem_analysis.py` | `geochem_analysis.csv` + statistics, group medians, column dictionary | 3–6 |
| §9.1 comparator | `19_s9_jansson.py` | Jansson-style k-means baseline vs our GMMs | discussion |
| §9.2 comparator | `20_s9_rf_smoother.py` | RF + downhole smoother vs our HMM | discussion |
| ML findings report | `21_laporan_ml.py` | `outputs/laporan_ml/laporan_ml_v1.html` (numbers read from `data/processed/`) | team |

Still for humans (details in [PANDUAN_TIM.md](PANDUAN_TIM.md)): the ioGAS project, the report and
deck, the regional location map (DEMNAS), a satellite check of the derived drainage, and verifying
every `[VERIFY]` reference.

## Deliverables

1. **Data validation (CSV):** `data/processed/validation_flags.csv` (one row per issue per record),
   `validation_summary.csv` (one row per check), `qaqc_precision.csv`.
2. **ioGAS project:** built by the ioGAS teammate from `data/processed/iogas/*.csv`
   (`README_iogas.txt` and `kolom_iogas.csv` explain every column).
3. **Geochemistry analysis (CSV):** `data/processed/geochem_analysis.csv`, `geochem_statistik.csv`,
   `geochem_statistik_kelompok.csv`, `geochem_analysis_kolom.csv`.
4. **Report (PDF)** and 5. **Presentation (PDF):** written by the team from the figures, maps and
   numbers here.

## Reproduce

Requirements: Windows/macOS/Linux, [uv](https://docs.astral.sh/uv/), Python 3.11–3.12 (uv installs
it). QGIS 3.44+ only for steps that build maps.

```bash
uv sync
uv run python scripts/00_inventory.py   # raw data intact?
uv run pytest -q                        # 127 tests
```

All outputs are already in the repo, so you do not need to rerun anything to write the report.
To rerun a step: `uv run python scripts/<step>.py`, then `uv run python scripts/07_export.py`,
which merges every `data/processed/ml/*.csv` into the ioGAS files. On Windows, prefix
`PYTHONIOENCODING=utf-8` if the console chokes on Bahasa characters. Seeds are fixed, so reruns
give identical files.

Order: steps 1–7 strictly in sequence. Then ML-1, ML-2, ML-3, ML-5 and drainage are independent.
ML-4 needs step 6. ML-6 needs ML-3, ML-5 and drainage.

Not in the repo: `data/interim/ml6_gp.joblib` (19 MB, a fitted scikit-learn model that only loads
with the same library versions). Rebuild it with
`uv run python scripts/16_ml6_targeting.py --stage gp` before running the later ML-6 stages.

Steps that drive QGIS (`13_…`, `15_…`, `17_…`) run through the QGIS MCP server
([.mcp.json](.mcp.json)), a local clone of `nkarasiak/qgis-mcp` v0.15.2. The path in `.mcp.json` is
the repo owner's machine; change it on yours. The `.qgz` projects in `outputs/maps/` use relative
paths and open directly from a clone. If QGIS reports an unavailable layer, point it to the file of
the same name in `gis/`.

## How we work

1. **Plan:** the agent appends a plan to `LOG.md` (inputs, method, outputs, checks).
2. **Approve:** a human says go, or changes it.
3. **Build:** one numbered script calling small functions in `src/`, with assertion checks.
4. **Run and log:** numbers, deviations and a 3–5 line plain-language explanation go to `LOG.md`.
5. **Review:** the repo owner checks the outputs before the next step.

Rules that matter for everyone:
- **Flag, don't delete.** Every issue is a flag column; exclusions happen inside an analysis and are
  logged.
- **Never edit `data/raw/`.** `tests/test_raw.py` will fail.
- **Never overwrite a figure that is in the report.** Write `_v2`.
- **`LOG.md` is append-only.** Add a new entry; never rewrite old ones.
- **No invented references.** Anything not checked against the source stays `[VERIFY]`.
- Line endings: `.gitattributes` keeps `data/` byte-exact (the raw CSVs are CRLF). Do not change it.

## Who does what

- **Repo owner (ML lead):** cleaning, validation, ML, CSV and GIS outputs. Approves each plan.
- **ioGAS teammate:** the ioGAS project on the team's one licensed machine, from
  `data/processed/iogas/`.
- **Rest of the team:** report text in Bahasa Indonesia (EYD, Times New Roman), final maps in QGIS,
  the deck, and checking every reference.
- **Agents (Claude Code, Codex):** follow `AGENTS.md`; read the tail of `LOG.md` first; pull before
  working; log everything.
