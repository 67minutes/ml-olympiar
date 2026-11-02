# Ramba Joring geochem + ML (OlympiAR 2026 Round 2)

Project rules, data facts and the ML plan live in [AGENTS.md](AGENTS.md). Decisions and
results live in [LOG.md](LOG.md). This file covers only how to run things and how we work.

## Setup (once per machine)

```bash
uv sync
uv run python scripts/00_inventory.py   # checks raw data is intact and complete
uv run pytest -q
```

### QGIS and the QGIS MCP server

QGIS 3.44 LTR and 4.2 are installed through OSGeo4W
(`C:\Users\mauli\AppData\Local\Programs\OSGeo4W`). The QGIS MCP plugin is in both QGIS
profiles; enable it once (Plugins → Manage and Install Plugins → Installed → "QGIS MCP"),
then click its toolbar button to start the server inside QGIS (localhost:9876).
The MCP client side is the `qgis` server in [.mcp.json](.mcp.json). It runs a local clone
of `nkarasiak/qgis-mcp` pinned at v0.15.2 in `C:\Users\mauli\tools\qgis-mcp`. On a new
machine: clone it there, `git checkout v0.15.2`, `uv sync --no-dev`.

`data/raw/` is a read-only copy of the committee package. `RAW_MANIFEST.sha256` holds its
hashes, and `tests/test_raw.py` fails if any raw file changes. Nothing under `data/` or
`gis/` is committed to git, and the repo has no remote. Keep it that way: the data is
confidential.

## How we work: one stage at a time

Every stage follows the same loop:

1. **Plan.** The agent appends a plan to `LOG.md` (inputs, method, outputs, checks).
2. **Approve.** A human reads it and says go, or changes it.
3. **Build.** One numbered script in `scripts/` that calls small functions in `src/`, with
   assertion checks after each step (row counts kept, flags filled, no silent NaN).
4. **Run and log.** The agent records the numbers and a 3–5 line plain-language
   explanation in `LOG.md`, written so a teammate can say it aloud in the presentation.
5. **Review.** A human checks the outputs (ioGAS, QGIS, or the CSV) before the next
   stage starts.

Outputs are never overwritten once they go into the report. Write `_v2` instead.

## Stages

| Stage | Script | Output | Feeds |
|---|---|---|---|
| 0 Setup | `00_inventory.py` | raw check | — |
| 1 Semantics | `01_semantics.py` | 0→NaN, NS-SEL, DL harmonisation, `<el>_cens` flags | everything |
| 2 Lidar DEM | `02_dem.py` | `gis/lidar_dem.tif`, hillshade | 3, maps, drainage |
| 3 Coordinates | `03_coords.py` | surface re-drape, survey extrapolation, desurvey XYZ | 4, maps, sections |
| 4 Codes | `04_codes.py` | harmonised lith/alt/min codes (originals kept) | 5 |
| 5 Joins | `05_joins.py` | logs attached to assays by midpoint | 6, ML |
| 6 Composites | `06_composite.py` | 1 m length-weighted composites | HMM, classifiers |
| 7 Deliverables | `07_export.py` | `validation_flags.csv`, ioGAS-ready CSVs | **ioGAS (human)** |
| ML-1 | `10_thresholds.py` | GMM thresholds per element | report §3 |
| ML-2 | `11_logging_clf.py` | alteration/oxidation from chemistry, GroupKFold by hole | report §3 |
| ML-3 | `12_surface_zones.py` | soil/rock H/M/L zones + membership probability | report §4, targeting |
| ML-4 | `13_hmm_strat.py` | downhole geochem states | report §5 sections |
| ML-5 | `14_paf_naf.py` | NAF / PAF-LC / PAF-HC with conformal sets | report §6 |
| GIS | `15_drainage.py` | derived drainage network | report §6, bonus |
| ML-6 | `16_targeting.py` | GP (kriging) Au + uncertainty, ranked collars | report §7, bonus |

Stages 1–7 run strictly in order. After stage 7, ML-1, ML-2, ML-3, ML-5 and drainage are
independent and can run in parallel. ML-4 needs stage 6. ML-6 needs ML-3, ML-5 and
drainage.

## Who does what

- **Agents:** cleaning, ML, Python charts, GIS layers (GeoTIFF/GeoPackage), ioGAS-ready
  CSVs, `LOG.md`.
- **Humans:** ioGAS project (probability plots, downhole plots, classification diagrams),
  final maps and sections in QGIS, report text in Bahasa Indonesia, checking every
  reference, approving each stage plan.
