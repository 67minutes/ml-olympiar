# Ramba Joring geochem + ML (OlympiAR 2026 Round 2)

Team repository for the ML and data-analysis backbone of our OlympiAR 2026 Round 2 submission
(PT Agincourt Resources / IAGI / MGEI): an exploration + environmental report on the **Ramba
Joring (RJ) high-sulfidation epithermal Au-Cu prospect, Martabe district, North Sumatra**.

> **PRIVATE repo, team only.** It contains the committee's confidential data package and the brief
> (which includes our ioGAS licence key). Never make it public, never fork it to a public account,
> never upload the data to cloud ML services or chatbots, and never paste the licence key or
> committee contacts anywhere. See [AGENTS.md](AGENTS.md) §2.

**Bahasa Indonesia:** report writers and presenters should start with [PANDUAN_TIM.md](PANDUAN_TIM.md)
(terms first, then every file per report chapter) and the ML findings report
[outputs/laporan_ml/laporan_ml_v2.html](outputs/laporan_ml/laporan_ml_v2.html) (one local file, open in a
browser). The submission files for the 7 Nov email are in [outputs/kirim/](outputs/kirim/).

## Terms and file naming

Internal shorthand used in file names, code and `LOG.md`. In the report and slides use the long names.

| Shorthand | Meaning |
|---|---|
| ML-1 … ML-6 | The six ML tasks: 1 element thresholds (GMM), 2 lithology/alteration/oxidation from chemistry (Random Forest), 3 surface High/Medium/Low zonation (PCA + GMM), 4 downhole geochem-stratigraphy (Gaussian HMM), 5 PAF/NAF classification (conformal prediction), 6 drill targeting (Gaussian process = kriging, bonus) |
| §N | A section of [AGENTS.md](AGENTS.md); "§9" = the literature comparators (Jansson; Fontana) |
| ioGAS Stage 0–5, file prefix `s1_`…`s4_` | Order of the ioGAS work: 1 QAQC & thresholds, 2 surface, 3 drillholes, 4 environmental, 5 final projects. Always written "Stage 1" / "Tahap ioGAS 1" |
| HMM units S1–S5 | The five downhole geochemical units from ML-4 (e.g. "S4 Au sedang, Cu tinggi (Sulfida)"). Not the same as the stage prefix `s1_` |
| NAF / PAF-LC / PAF-HC | Non-acid forming / potentially acid forming, low capacity / high capacity. "NAG class" = lab test (RJDH012 only); "conformal class" (`ML_paf_kelas`) = one class or `ambigu`; "management class" (`ML_paf_kelola`) = worst plausible class, used for handling |
| SCIS, S2, S total | Two sulfide-S lab methods (never mixed) and total S (RJDH012 only); `S_pct` = S total for ioGAS's Halley diagrams |
| NS-SEL, DL, `_cens` | Not sampled; detection limit; below-DL flag (value = DL/2) |
| `ML_*` columns | Model outputs, prefixed by task (`ML_thr_`, `ML_alt_`/`ML_oks_`/`ML_lit_`, `ML_zona`, `ML_hmm_`, `ML_paf_`, `ML_gp_`, `ML_s9_`) |
| `_v1`, `_v2` | Frozen versions: a file used in the report is never overwritten |
| Figure prefixes `07_`…`14_` | Python figures, numbered after the script that made them |
| `penampang A/B/C`, `D–D'`, `Lain` | ML-4 sections A–C (holes ordered SE→NW), the bonus design section, holes off the sections (RJDH004, 010, 011) |
| `tanah`, `batuan`, `bor`/`DH`, `komposit_1m` | Soil, rock, drillhole, 1 m length-weighted composites |
| Gate | A human review that ends each step before the next starts |

The full Bahasa glossary is section 1 of [PANDUAN_TIM.md](PANDUAN_TIM.md).

## Where things are

| File | What it is |
|---|---|
| [outputs/laporan_ml/laporan_ml_v2.html](outputs/laporan_ml/laporan_ml_v2.html) | ML findings report for teammates (Bahasa, English terms in brackets): per ML task the question, answer, figures with reading notes, confidence, limits, spoken script and likely judge questions. Built by `scripts/21_laporan_ml.py` from `reports/laporan_ml_src.html`. v2 adds the ioGAS threshold comparison; v1 is frozen |
| [outputs/kirim/](outputs/kirim/) | Submission folder for the 7 Nov email: deliverables 1–3 with Bahasa READMEs and `MANIFEST.csv`; the team adds the report and deck PDFs |
| [outputs/iogas_project/](outputs/iogas_project/) | ioGAS projects: 4 final (`*_final_v1.gas`) + 47 supporting; `BACA_SAYA.txt`, `indeks_proyek_iogas.csv` |
| [outputs/figures/iogas/](outputs/figures/iogas/) | 129 figures drawn by ioGAS; `indeks_gambar_iogas.csv` gives chapter, content and caption notes per figure |
| [PANDUAN_TIM.md](PANDUAN_TIM.md) | Team guide (Bahasa): files per report chapter, open items, references to verify, repo usage |
| [AGENTS.md](AGENTS.md) | Rules, data facts, verified findings and the ML plan. Single source of truth for coding agents (Claude Code, Codex) |
| [LOG.md](LOG.md) | Append-only log of every plan, decision, deviation, number and spoken explanation, in order |
| [CLAUDE.md](CLAUDE.md) | Claude Code specifics (it loads AGENTS.md) |
| `Technical Meeting 2nd Round OlympiAR 2026.pdf` | The committee brief: rules, report structure, rubric, deliverables |
| `data/raw/` | The committee data package, untouched. `RAW_MANIFEST.sha256` holds its hashes |
| `data/interim/` | Stage outputs of the cleaning pipeline (`01_…` to `06_…`) |
| `data/processed/` | Final tables: validation, geochemistry analysis, ML summaries |
| `data/processed/iogas/` | ioGAS-ready CSVs (see `README_iogas.txt` there) and matching `.gas` projects from `22_iogas_link.py` |
| `data/processed/ml/` | One file per ML task and table (`<table>__<task>.csv`: key + `ML_*` columns) |
| `gis/` | Derived layers (EPSG:32647): lidar DEM, hillshade, drainage, ML grids and sections |
| `outputs/figures/` | Report charts, 300 dpi, Bahasa labels, versioned `_v1`, `_v2` |
| `outputs/maps/` | QGIS projects (`.qgz`) and exported maps/sections; `qc/` holds check projects |
| `src/` | Importable functions (small, tested) |
| `scripts/` | Numbered runnable steps |
| `tests/` | pytest suite (`uv run pytest -q`; the live ioGAS round trip runs only with `IOGAS_LIVE=1`), including `test_raw.py`, which fails if any raw file changes |

## Status (6 Nov 2026)

Everything on the ML, data and ioGAS side is done; the report and deck are with the team. Each row has a plan entry and a results entry in
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
| ioGAS projects + link | `22_iogas_link.py` | `data/processed/iogas/*.gas` (EPSG:32647, rows coloured by ML class); `--check DIR` drives a local ioGAS over gRPC (`src/iogas_link.py`) | 3–6 |
| ioGAS Stage 1 (QAQC, thresholds) | `23_iogas_s1_qaqc.py --phase blind\|qaqc\|ambang` | `outputs/figures/iogas/s1_*_v1.png`, `outputs/iogas_project/RJ_*_s1_*_v1.gas`, `element_thresholds_v2.csv`, `s1_ambang_perbandingan_v1.csv`, `s1_aat_ringkasan_v1.csv` | 3 |
| ioGAS Stage 2 (surface) | `24_iogas_s2_surface.py` | `outputs/figures/iogas/s2_*_v1.png`, `outputs/iogas_project/RJ_tanah_s2_v1.gas`, `RJ_batuan_s2_v1.gas`, `s2/*.gas`, `s2_zona_vs_kelas_v1.csv`, `s2_zona_ringkasan_v1.csv` | 4 |
| ioGAS Stage 3 (drillhole) | `25_iogas_s3_drillhole.py` | `outputs/figures/iogas/s3_*_v1.png`, `outputs/iogas_project/RJ_bor_s3_v1.gas`, `s3/*.gas`, `s3_status_ringkasan_v1.csv`, `s3_status_per_lubang_v1.csv` | 5 |
| ioGAS Stage 4 (environmental) | `26_iogas_s4_environmental.py` | `outputs/figures/iogas/s4_*_v1.png`, `outputs/iogas_project/RJ_RJDH012_s4_v1.gas`, `RJ_DH_s4_kelola_v1.gas`, `s4/*.gas`, `s4_kelas_nag_ringkasan_v1.csv`, `s4_kelola_per_lubang_v1.csv` | 6 |
| ioGAS Stage 5 (final projects) | `27_iogas_s5_final.py` (`--index`: indexes only) | `outputs/iogas_project/RJ_{tanah,batuan,bor_komposit,lingkungan}_final_v1.gas`, `indeks_proyek_iogas.csv`, `BACA_SAYA.txt`, `outputs/figures/iogas/indeks_gambar_iogas.csv` | deliverable 2 |
| Submission folder | `28_kirim.py` | `outputs/kirim/` (copies of deliverables 1–3, ioGAS zip, manifest, < 25 MB) | email |

**ioGAS work (done, 5–6 Nov).** The repo owner built the ioGAS project on this PC
(IMDEX 14-day trial, expires 19 Nov 2026), with agents driving ioGAS through its local gRPC server
via the skill `.claude/skills/iogas/SKILL.md`. Staged plan, gates and rules: [AGENTS.md](AGENTS.md) §10.

| Stage | Report § | ioGAS content |
|---|---|---|
| 0 Foundation | all | action catalogue verified live (`src/iogas_project.py`, skill `reference/actions.md`), drillhole support, Bahasa aliases (non-element columns and legends only), skill, docs |
| 1 QAQC & thresholds | 3 | probability-plot grids, blind threshold picks → `thr_probplot_iogas`, Tukey outliers, Anomaly Assessment, precision scatters, era box plots |
| 2 Surface | 4 | attribute maps by ML zone and threshold class, scatters and box plots per zone, alteration, Al-K-Mg ternary |
| 3 Drillhole | 5 | stacked strip logs (`*_log10` columns) by HMM state / alteration / oxidation, twin pads, XYZ views of sections A–C (rotation set by hand) |
| 4 Environmental | 6 | RJDH012 NAG pH vs S, Fe vs S pyrite line, Ca-Fe-S ternary, AMD elements by PAF class |
| 5 Project & polish | deliverable 2 | four final projects `outputs/iogas_project/RJ_*_final_v1.gas` (all columns, key windows), indexes, ML report v2; no GUI screenshots (team decision) |

Each stage exports PNGs to `outputs/figures/iogas/` and saves a `.gas` in `outputs/iogas_project/`,
and ends at a human gate.

Still for humans (details in [PANDUAN_TIM.md](PANDUAN_TIM.md) section 6): the report and deck, the
regional location map (DEMNAS), a satellite check of the derived drainage, verifying every `[VERIFY]`
reference, and sending `outputs/kirim/` by email.

## Deliverables

1. **Data validation (CSV):** `data/processed/validation_flags.csv` (one row per issue per record),
   `validation_summary.csv` (one row per check), `qaqc_precision.csv`.
2. **ioGAS project:** four final projects `outputs/iogas_project/RJ_*_final_v1.gas` plus 47 supporting
   ones (index and Bahasa README in the same folder), built from `data/processed/iogas/*.csv`
   (`README_iogas.txt` and `kolom_iogas.csv` explain every column); zipped for the email in
   `outputs/kirim/2_proyek_iogas/`. ioGAS exports are in `outputs/figures/iogas/`.
3. **Geochemistry analysis (CSV):** `data/processed/geochem_analysis.csv`, `geochem_statistik.csv`,
   `geochem_statistik_kelompok.csv`, `geochem_analysis_kolom.csv`, plus the thresholds
   (`element_thresholds_v2.csv`, with the ioGAS probability-plot picks) and the ioGAS summary tables
   (`s1_`–`s4_*.csv`). Copies with plain Bahasa names are in `outputs/kirim/3_analisis_geokimia/`.
4. **Report (PDF)** and 5. **Presentation (PDF):** written by the team from the figures, maps and
   numbers here.

## Reproduce

Requirements: Windows/macOS/Linux, [uv](https://docs.astral.sh/uv/), Python 3.11–3.12 (uv installs
it). QGIS 3.44+ only for steps that build maps.

```bash
uv sync
uv run python scripts/00_inventory.py   # raw data intact?
uv run pytest -q                        # whole suite (live ioGAS test skipped)
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

- **Repo owner (ML lead):** cleaning, validation, ML, CSV and GIS outputs, and the ioGAS project
  (on this PC, the team's one ioGAS machine, with an IMDEX trial licence). Approves each plan.
  The old "ioGAS teammate" role is retired.
- **Rest of the team:** report text in Bahasa Indonesia (EYD, Times New Roman), final maps in QGIS,
  the deck, and checking every reference.
- **Agents (Claude Code, Codex):** follow `AGENTS.md`; read the tail of `LOG.md` first; pull before
  working; log everything. They drive ioGAS only through `.claude/skills/iogas/SKILL.md`, on
  localhost, and never touch the human's own ioGAS window.
