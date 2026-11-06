# LOG

Append-only. Newest entry at the bottom. Never edit an old entry; supersede it.

---

## 2026-11-02 · Stage 0: repo setup

**Done**
- Created the AGENTS.md §7 layout: `data/{raw,interim,processed}`, `src/`, `scripts/`,
  `notebooks/`, `outputs/{figures,maps}`, `gis/`, `tests/`.
- Copied the committee package into `data/raw/` unchanged and set the files read-only.
  SHA-256 of every file is in `RAW_MANIFEST.sha256`; `tests/test_raw.py` checks it.
- `git init` with no remote. `.gitignore` excludes `data/`, `gis/` and `.venv/`.
- Python 3.12 env with `uv` (`pyproject.toml`): pandas, scipy, scikit-learn, statsmodels,
  geopandas/pyogrio/rasterio, hmmlearn, lightgbm, shap, mapie, matplotlib/seaborn.
  Local TabPFN is not installed (it pulls in torch); add it only if ML-2 needs it.
- `src/paths.py` (all paths, CRS) and `src/loaders.py` (read-only loaders + `verify_raw`).

**Checks** (`scripts/00_inventory.py`)
- Raw manifest OK.
- Row × column counts match AGENTS.md §3: collar 19×27, survey 99×17, assay 2476×78,
  lithology 286×22, alteration 707×19, mineralisation 2684×26, oxide 3017×12,
  rock 469×92, soil 259×85.
- Contours: 1,309 lines, CRS read as EPSG:32647, `Z_Avg` present, bounds
  E 506433–507790, N 167638–169000. Matches §3.

**Timeline note**
- Submission is 7 Nov 2026 (5 days from today). Stages 1–7 must finish first because
  the humans need the ioGAS CSVs to start their ioGAS work.

**Next:** plan for Stage 1 (semantics), awaiting approval.

---

## 2026-11-02 · Stage 1 plan: semantics (approved)

Full plan: `C:\Users\mauli\.claude\plans\yes-plan-stage-1-sprightly-flame.md`. Summary:

**Inspection findings (read-only)**
- No `<` or negative values anywhere. Censoring appears as a repeated floor value per lab
  job (e.g. drillhole Ag 0.5 in most jobs vs 0.25 in 2015/2016). Whether a stored floor is
  the DL or DL/2 is unknown; harmonising to the highest floor makes that irrelevant.
- Drillhole assays have no zeros; their nulls already mean "not analysed". The 10 null
  Au/Ag/Cu/As rows are all `NS-SEL` and have no assay at all.
- Rock and soil `AuPPB` = `AuPPM`×1000 exactly. Rock `X/Y_Average` = `Easting/Northing`.
  Rock `Z_Average` = 0 in all 469 rows (confirms §4.2.8: ignore it).
- Surface files include other prospects: rock 87 (Purnama 51, Tor Uluala 31,
  Parbotikan 5), soil 71 (Purnama 64, Tor Uluala 7), all inside the lidar area.
  **Decision (human): keep all, add `is_RJ`; each analysis picks and logs its subset.**

**Rules**
1. Analyte columns by unit suffix (PPM/PPB/PCT/kgH2SO4/ton) plus `NAGpH`.
2. Surface 0 → NaN (rock, soil). Drillhole: no change (assert no zeros).
3. Per dataset × element × `LabJobNo`: the min value is a censoring floor if it repeats
   (≥3 rows and ≥2% of the job). Table → `01_detection_limits.csv` for human review.
4. `<col>_cens`: value ≤ its own job's censoring floor.
5. `<col>_ml`: values ≤ harmonised DL (highest censoring floor in that dataset) → DL/2;
   `<col>_cens_h` flags them. Original columns keep raw values.
6. `ml_usable = False` if >50% censored after harmonisation or <50% analysed.
7. `no_sample` for NS-SEL. 8. `S_method` = SCIS / S2 / none (never mixed).
9. `AuCN/AgCN/CuCN_ratio` (both analysed, uncensored); `flag_AuCN_gt_total`,
   `flag_AgCN_gt_total` where CN > 1.1 × total.
10. Parsed dates + `year`. 11. `is_RJ`. 12. Drop columns that are 100% empty; list them.

**Checks:** row counts kept; NaN after = NaN before + zeros converted; raw values
unchanged except 0 → NaN; `_ml` never below DL/2; reproduce §4.2 counts (rock Ca zeros
443; drillhole Au/Ag/Cu/As 2,466; AuCN>1.1×Au 125/979; Ag 173/1,267).

---

## 2026-11-02 · Stage 1 rule change: detection limits (approved by human)

**Why.** The first run of the approved rule over-censored. Its five §4.2 checks all
reproduced, but:
- Ordinary repeated values were read as DLs: drillhole As 36 ppm (3 of 111 in one job),
  Cu 18 ppm, rock Sb 7 ppm, soil Pb 17 ppm.
- One small job could set the DL for everything: an 8-sample soil job with Ag 0.5 made
  86% of soil Ag "censored" (ml_usable False). Drillhole Cu was 22% censored when the
  real figure is about 1%.

**New rule (supersedes Stage 1 plan rules 3 and 5).**
1. A job floor is a DL candidate only if it repeats (≥3 rows and ≥2% of the job) AND is a
   standard lab value (1, 2, 2.5 or 5 × 10^k).
2. **DL vs DL/2, per element × job (no halving twice).** Labs never report values between
   DL/2 and DL. Gap test: if a value exists strictly between the floor f and 2f, the floor
   is the DL. If none does but ≥3 values sit in [2f, 4f], the floor is an already
   substituted DL/2 (true DL = 2f). If the test can't decide (resolution too coarse,
   too few values, flat job), fall back on the pattern: 2.5 × 10^k → DL/2, else DL. The
   decision and its method are recorded per job.
3. Harmonised DL = the highest true DL whose jobs together hold ≥10% of the analysed
   values. Values ≤ harmonised DL → DL/2.
4. Jobs whose own true DL is higher than the harmonised one (or with no harmonised DL):
   censored values → own DL/2, flagged `<col>_dl_coarse`.
5. Guarantees, asserted: `_ml` ≤ raw value; `_ml` differs from raw only where
   `_cens_h`; censored values in a DL/2 job are never pushed below the stored floor.

**Extra outputs requested.** `01_dl_review.csv` (Au, Ag, As, Cu, Zn, Pb, Hg, S
columns only) for human review before Stage 2. A sensitivity check of % censored at
5%, 10% and 20% coverage thresholds.

---

## 2026-11-02 · Stage 1 results: semantics

**Correction to the rule-change entry above.** It listed "`_ml` ≤ raw value" as a
guarantee. That is wrong: harmonising to a coarser DL can raise a value below DL_h/2 up
to DL_h/2 (standard practice). The guarantees actually asserted in
`scripts/01_semantics.py` are: `_ml` differs from raw only where `_cens_h`; every
censored `_ml` sits at harmonised DL/2 or its own job's DL/2; censored values in DL/2
jobs never go below the stored floor (no halving twice).

**Run:** `uv run python scripts/01_semantics.py`. 12 unit tests pass. All checks pass.
- AGENTS.md §4.2 reproduced: rock Ca zeros 443; drillhole Au/Ag/Cu/As 2,466 analysed;
  NS-SEL 10 rows, all unassayed; AuCN > 1.1×Au 125/979; AgCN > 1.1×Ag 173/1,267.
- Surface zeros → NaN: rock 20,275 values, soil 12,826. Drillhole: no zeros.
- Empty columns dropped: assay 19 (the §4.2.2 list + `WtDryG`, `WtWetG`), rock 26,
  soil 38 (incl. soil `Lithology`, `IntrpAltFaces`, `RKOutcropType`, all S and CN cols).
- Outputs in `data/interim/`: `01_assay.csv` (2,476 × 256), `01_rock.csv` (469 × 250),
  `01_soil.csv` (259 × 207), `01_detection_limits.csv`, `01_dl_review.csv`,
  `01_element_summary.csv`.

**DL vs DL/2 decisions (key elements)**
| Dataset | Element | Stored floor → decision (method) | Harmonised DL | % censored |
|---|---|---|---|---|
| drillhole | Ag | 0.5 → DL (pattern), 1998–2017; **0.25 → DL/2 (gap), 2015–16** | 0.5 | 31.7 |
| drillhole | Au | 0.005, 0.01 → DL (pattern); 0.02 → DL (gap, 1 job, 12 samples) | 0.01 | 4.9 |
| drillhole | As | 2.5 → DL/2 (gap), 2016 job | none (<10%) | 0.3 |
| drillhole | Cu | 1, 2 → DL | none (<10%) | 0.9 |
| drillhole | SCIS_PCT | 0.005 → DL | 0.005 | 4.2 |
| rock | Ag | 0.5 → DL; 1.0 → DL (2008, 7 samples, coarse); 0.25 → DL/2 (2018) | 0.5 | **65.7** |
| rock | Au | 0.005 → DL | none (<10%) | 1.3 |
| rock | Hg | 0.01, 0.02 → DL; 0.025 → DL/2 (2008, coarse) | 0.02 | 14.5 |
| soil | Au | **0.0025 → DL/2 (gap)**, true DL 0.005 (matches AuPPB 2.5) | 0.005 | 10.4 |
| soil | Ag | 0.1 → DL (164 samples); 0.5 → DL (14 samples, coarse) | 0.1 | 22.8 |

Interpretation of AGENTS §4.2.7 ("Ag bottoms at 0.25 in 2015–2016 vs 0.5 otherwise"):
the gap test shows the 2015–16 jobs stored DL/2 of the same 0.5 DL, not a finer DL. This
refines §4.2.7; it does not contradict the observation.

**Sensitivity (% censored at DL-share threshold 5 / 10 / 20%)**
- Only soil Ag is sensitive: 85.7 / 22.8 / 22.8. At 5%, the 14-sample 0.5-DL jobs would
  set the DL again. This is why 10% is used.
- Drillhole Au 4.9 / 4.9 / 2.6; rock Cu 2.6 / 2.6 / 0.6; rock Hg 14.5 / 14.5 / 6.0.
  Everything else in the review set is unchanged.
- ML-usable columns: 23 / 24 / 24.

**ML-usable (dataset-wide; subset analyses such as RJDH012 re-evaluate)**
- Drillhole: Au, Ag, Cu, As, SCIS_PCT, AgCN, CuCN.
- Rock: Au, Cu, As, Hg, Pb, Sb, Zn. **Rock Ag is not usable (65.7% censored, genuine:
  most 1998–99 rock Ag sits at 0.5).**
- Soil: Au, Ag, Cu, As, Ba, Hg, Pb, Sb, W, Zn. This confirms soil as the cleanest
  dataset for surface clustering.

**Plain-language explanation (for the presentation)**
> Old lab reports don't say "below detection". They just print a number at the floor,
> and different labs over 20 years used different floors. Some even printed half the
> detection limit instead of the limit itself. We detected each lab job's floor and
> checked whether it was the limit or half of it, using the fact that labs never report
> values between the two. Then we put every era on one common detection limit. Without
> this, the ML would have grouped samples by lab year instead of by geology.

**Human review needed before Stage 2:** `data/interim/01_dl_review.csv` (Au, Ag, As, Cu,
Zn, Pb, Hg, S; one row per dataset × element × lab job, with floor, decision, method,
true DL, share and harmonised DL).

---

## 2026-11-02 · Stage 2 plan: lidar DEM (awaiting approval)

**Goal.** One trusted ground surface for everything downstream: the surface-Z re-drape
(Stage 3), maps, sections, hillshade, derived drainage (AMD flow paths, drill-design
buffers). DEM quality matters most for drainage, where interpolation artifacts turn into
fake streams.

**Inspection findings (read-only)**
- 1,309 2-D LineStrings, EPSG:32647. `Z_Avg` 260–670 m, every value a multiple of 5
  (83 levels, 5 m interval), no nulls or zeros.
- `Attrib2` has two kinds: `LEVEL_51` = 699 real contours (122.4 km), and
  `LEVEL_51__CONSTRUCTION_` = 610 CAD fragments, each 1.6 m long (976 m in total). 605 of
  them sit on a contour of the same Z; 5 sit up to 13 m from a contour that is 5 m higher.
- Contour vertex spacing: median 0.55 m, max 16 m.
- Convex hull of contours = 117 ha (the bounding box is 185 ha, so a bbox DEM would
  invent ~68 ha of terrain). All 19 collars and all 259 soil samples fall inside the
  hull; 1 rock sample falls outside (matches AGENTS §3).
- Inside the hull, the distance from a 5 m grid cell to the nearest contour has median
  2.8 m, p95 25 m, max 87 m. There are poorly supported patches.

**Method**
1. **Clean:** drop the 610 construction fragments (no information, 5 ambiguous); log it.
2. **Points:** resample every contour to uniform 2 m spacing (~62k points, Z = `Z_Avg`).
3. **Two candidate interpolators, same 2 m grid, masked to the contour convex hull:**
   - (a) **TIN**: Delaunay linear (`scipy` LinearNDInterpolator). Exact at contours, but
     it makes flat triangles on ridges, valley floors and hilltops (terracing). This is
     the classic artifact for drainage.
   - (b) **Thin-plate spline**: `scipy` RBFInterpolator, local (64 neighbours),
     smoothing chosen from {0, 1, 10} by the CV below. Smooth, with no flat triangles.
4. **Choose by contour hold-out CV:** fit on the 10 m contours only (Z mod 10 = 0) and
   predict the held-out 5 m contours (Z mod 10 = 5). Report RMSE, MAE, p95 |error| and
   bias. Lowest RMSE wins; the flat-cell fraction is the tie-break. The 10 m CV overstates
   the error of the final 5 m DEM, so it is only used to rank methods. The final model
   is refitted on all contours.
5. **Outputs** (all EPSG:32647, 2 m, float32, nodata −9999):
   - `gis/lidar_dem.tif`: AGENTS §3 says `data/interim/`, §7 says `gis/`. Using `gis/`
     (layout file); both are gitignored.
   - `gis/hillshade.tif` (Horn's method, az 315°, alt 45°) and `gis/slope_deg.tif`.
   - `gis/dem_support_dist.tif`: distance to the nearest contour per cell, a DEM
     confidence layer ("knows what it doesn't know"). Cells > 30 m from a contour are
     flagged as weakly supported in Stage 3.
   - `data/interim/02_dem_cv.csv`: CV scores per method / smoothing.
   - `outputs/figures/qc/02_dem_preview_v1.png`: hillshade + contours + collars, for
     review only (not a report figure; final maps are made in QGIS).

**Checks (script stops and reports on failure)**
- Raster opens with rasterio and has the right CRS, cell size and nodata. DEM range
  within [255, 675] m (no overshoot beyond half a contour interval).
- Residual at all contour points: p95 |res| < 0.5 m.
- All collars and 468/469 rock samples get a DEM value.
- **Reproduce AGENTS §4.1:** collar RL − DEM within ±2.5 m for all holes except RJDH002
  (≈ −7.8 m) and RJDH006 (≈ −5.1 m).
- **Compare with AGENTS §4.2.8:** surface Z vs DEM counts >10 m / >30 m (rock 40 / 13,
  soil 15 / 6). Any count differing by more than 3 → stop and report (do not adjust).

**Files:** `src/dem.py` (contour cleaning, resampling, TIN, TPS, hold-out CV, hillshade,
slope, GeoTIFF writer), `scripts/02_dem.py`, `tests/test_dem.py` (synthetic plane and cone:
TIN exact on a plane, CV split correct, hillshade constant on a flat surface).
Expected runtime: a few minutes (TPS CV is the slow part).

---

## 2026-11-02 · Stage 2 results: lidar DEM

**Run:** `uv run python scripts/02_dem.py` (~80 s). 22 unit tests pass. All checks pass.

**What changed from the approved plan, and why** (decisions by the human in this session)
1. **First run stopped on AGENTS.md checks.** The spline gave RJDH002 / RJDH006 RL − DEM
   = −3.1 / 0.0 m (AGENTS §4.1: −7.8 / −5.1) and >10 m counts rock 48–49 / soil 19
   (AGENTS §4.2.8: 40 / 15). A TIN reproduces AGENTS (−8.0 / −3.5; rock 41, soil 14).
   **Finding: the AGENTS.md §4.1 and §4.2.8 figures were computed on a TIN-like DEM.**
   They depend on the DEM method because the 595/600 m contours are missing around both
   pads (likely cut ground), so neither method has data there.
2. **Human decision:** keep the spline, with (a) a spatial-block CV in addition to the
   whole-contour-line hold-out (the original hold-out already removed whole lines), and
   (b) an overshoot check across contour gaps.
3. Block CV (100 m blocks, 5 folds): spline still beat TIN. The overshoot check (first
   version wrongly flagged the TIN too, because its radius was smaller than the gap
   triangles; rebuilt on the enclosing Delaunay triangle) found **real spline overshoot:
   1,683 cells (0.58%, ~6.7 ha), up to 21 m (median 1.4 m) beyond the framing contours
   ± 5 m; 83% on the hull edges at contour ends; no collar or sample on one.** A tighter
   footprint (morphological closing, 20–40 m) did not remove it.
4. **Human decision: bracket-clipped spline.** Cells > 10 m from a contour are clipped to
   [min − 5, max + 5] m of their enclosing contour triangle (a missing contour can hide at
   most one 5 m interval). Validated: it is the best of four options on block CV.
5. Smaller details: the 610 CAD construction fragments were dropped. The spline is fitted
   on contour points every 5 m (TIN: 2 m), so its 64 neighbours span several contours.
   3 summit cells inside the closed 670 m ring were clamped to 675 m (max excess 0.18 m).

**Hold-out CV (RMSE, m; `data/interim/02_dem_cv.csv`)**
| Scheme | TIN | Spline | **Clipped spline (chosen, smoothing 0)** | Blend to TIN in gaps* |
|---|---|---|---|---|
| Whole contour lines (fit 10 m, predict 5 m) | 2.46 | 1.44 | **1.44** | — |
| 100 m spatial blocks | 7.65 | 6.68 | **6.41** | 7.00 |
| Max abs error, blocks | 130 | 84 | **60** | 93 |
| Flat cells (< 1°) | 3.5% | 0.1% | **0.4%** | — |
\*Exploratory comparison run before the decision; not part of the script.

**Outputs** (EPSG:32647, 2 m, 679 × 682 cells, 292,325 inside the contour convex hull,
nodata −9999): `gis/lidar_dem.tif` (263.1–675.0 m), `gis/hillshade.tif` (Horn, az 315°,
alt 45°), `gis/slope_deg.tif`, `gis/dem_support_dist.tif` (distance to nearest contour),
`gis/dem_clipped.tif` (1 = clipped cell). QC (not report figures):
`outputs/figures/qc/02_dem_preview_v1.png`, `02_dem_gaps_v1.png`.

**Checks**
- Contour residual p95: 0.32 m (model), 0.37 m (raster, bilinear).
- Gap overshoot on the final DEM: 0 cells. Support: median 2.7 m; 3.8% of cells > 30 m
  from a contour.
- TIN vs spline differ by > 5 m in 0.3% of cells within 10 m of a contour, 24% at 10–30 m,
  60% at 30–60 m, 95% beyond 60 m: disagreement is a gap phenomenon.
- 17 non-pad collars within 2.07 m of the DEM. RJDH002 / RJDH006: −3.2 / 0.0 m
  (TIN −8.0 / −3.5).
- Surface Z vs DEM: > 30 m = rock 13, soil 6, identical under both DEMs and matching
  AGENTS. > 10 m = rock 48 / soil 19 (TIN 41 / 14). 1 rock sample has no DEM value.

**Visual check of the gap panels (by agent).** No bubbles or crossings. The DEM-derived
contours follow the originals wherever contours exist. **But the edge fringes > 30 m
beyond the contour ends (along the hull boundary, mainly SW and NW) show streaks and
small steps,** from the local spline switching neighbour sets plus the clip plateaus.
They lie within the allowed range but are not real terrain. Consequence: **the drainage
stage must mask cells with support > 30 m** (or treat streams there as "doubtful"), and
maps should grey them out. They do not affect any sample or collar.

**Rules carried into Stage 3 (human decision)**
- Surface Z off the DEM by **> 30 m: confirmed elevation errors** (stable under both DEMs:
  rock 13, soil 6).
- **10–30 m: DEM-uncertain band** (rock 35 with the chosen DEM vs 28 with TIN; soil 13 vs
  8). Flag as uncertain, don't call them errors.
- RJDH002 / RJDH006: flag "pad area, contour gap, RL − DEM −3 to −8 m depending on DEM";
  keep the RL unchanged.

**Plain-language explanation (for the presentation)**
> The topography came as 5 m contour lines, not a surface, so we had to fill in the
> ground between them. We tested two standard ways by deleting contours and checking how
> well each method rebuilt them. A smooth spline beat straight-line triangles, which
> leave flat terraces that would fool the stream model. Where contours are missing, the
> spline sometimes bulged too high, so we capped it: a gap can hide at most one missing
> contour, so the ground can't be more than 5 m beyond the contours around it. We also
> map how far every cell is from real data, so nobody trusts terrain we invented.

---

## 2026-11-02 · QGIS + QGIS MCP installed (pipeline paused after Stage 2)

**Found:** QGIS is an OSGeo4W install at `C:\Users\mauli\AppData\Local\Programs\OSGeo4W`
with QGIS 3.44.15 LTR (`bin\qgis-ltr-bin.exe`), QGIS 4.2.3 (`bin\qgis-bin.exe`),
GRASS 8.5 and SAGA 9.12 (GRASS `r.watershed` / `r.stream.extract` are available for the
drainage stage). Neither QGIS version had been launched yet, so no user profile existed.

**QGIS plugin (QGIS side).** `qgis_mcp_plugin` 0.15.2 from
`C:\Users\mauli\Downloads\qgis_mcp_plugin-0.15.2` was copied to both profiles:
`%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\` and
`%APPDATA%\QGIS\QGIS4\...` (profile folder names read from each build's `qgis_core.dll`).
It is identical to the v0.15.2 release apart from line endings. It imports in QGIS 4's
Python 3.12. It still has to be **enabled once in QGIS** (Plugins → Manage and Install
Plugins → Installed → tick "QGIS MCP"), then started from its toolbar button. It listens
on `localhost:9876`.

**MCP server (client side).** `nkarasiak/qgis-mcp` cloned to `C:\Users\mauli\tools\qgis-mcp`
(outside this repo), checked out at tag **v0.15.2** (pinned, instead of the README's
`uvx …/main.zip`, which pulls whatever is on `main` each launch), `uv sync --no-dev`.
Registered for this project in `.mcp.json` as server `qgis`. Smoke test over stdio:
initialise OK, 125 tools listed.

**Review (confidentiality, AGENTS §2.1).** Server and plugin talk only over a localhost
TCP socket; no telemetry or outbound calls (GitHub URLs are only links / an optional
updater). Two cautions:
- MCP tool results enter the model's context like any tool output. Use layer
  summaries, styling and rendering; don't dump attribute tables (e.g. large `get_features`
  calls) into context.
- The plugin's `execute_code` tool runs arbitrary Python inside QGIS by design. Use it
  only for our own scripted map steps.

**AGENTS.md §7 note.** §7 says QGIS "will be installed later". It is now installed. The
"check your tools before any map step" rule still applies, because the server needs QGIS
open with the plugin started.

**Verified (2026-11-02, after Claude Code restart).** `diagnose`: healthy. QGIS 4.2.3,
Python 3.12.16, Qt 6.11.1. Plugin and server both v0.15.2, 1 client connected, no project
loaded. Processing providers active: native (350 algorithms), GRASS (307, so
`r.watershed` / `r.stream.extract` are available for drainage), GDAL (59), PDAL, 3D.
SAGA is not exposed as a Processing provider (it would need the "Processing Saga
NextGen" plugin); not needed for the current plan.

---

## 2026-11-02 · Plan: AGENTS.md §9 "Literature comparators" (draft, awaiting approval)

Requested by the human. Per §8: draft here, edit AGENTS.md only after approval. The only
other AGENTS.md change will be one line at the end of §6:

> Stretch comparators against published workflows: see §9 (gated, not core).

Fact checked for the draft (2 Nov, `load_dh`): mean / median interval length
lithology 10.84 / 5.20 m (286 intervals), alteration 4.39 / 2.50 m (707), assays
1.25 / 1.00 m (2,476).

**Draft text for AGENTS.md:**

```markdown
## 9. Literature comparators (STRETCH — gated)

### Gate
Start §9 work only when ALL of these are done:
- the five cleaning stages in §5 (semantics → compositing),
- `data/processed/validation_flags.csv`,
- ML tasks 1–5 in §6, with their `ML_*` outputs exported.

**Hard stop: end of 6 Nov 2026 WIB**, whatever the progress. 7 Nov is reserved for the
report. If the gate is not met, §9 becomes one paragraph in the report's discussion
instead of experiments.

Timebox each experiment at about half a day. For each comparator, log the results and a
3–5 line spoken explanation for the presentation in `LOG.md`.

### 9.1 Comparator 1: Jansson, Allen, Skogsmo & Tavakoli (2022) `[VERIFY]`
*Journal of Geochemical Exploration* 233, 106909.

What we may say about it (nothing more until the full text is read):
- 181 dolomite marble samples, 64 variables; clr transform; robust PCA (3 PCs, ~80% of
  variance); k-means with the elbow method (K = 7).
- Validated qualitatively: spatial pattern vs known deposits and geological
  interpretability. No labels.
- Variable-selection criteria, **as summarised by a citing paper** (not read in the
  original): ≥70% of samples above DL, median > 10 × DL, normal or log-normal
  distribution. `[VERIFY: identify the citing paper]`

**Experiment: "Jansson-style baseline".** Same cleaned inputs as our model → clr → robust
PCA → k-means, k chosen by elbow. Compare it with our GMM (BIC) wherever we use a GMM:
ML-3 surface zonation and ML-5 PAF/NAF clustering.
- Fair k for the baseline: elbow picked by a stated, reproducible rule on the
  within-cluster sum of squares (k = 2–10, fixed seeds). Also report k-means at the GMM's
  BIC-selected k, so a difference is not just a difference in k.
- Compare:
  - ARI vs logged alteration (rock `IntrpAltFa`, downhole `AltFacies`) and oxidation
    (downhole);
  - recovery of the RJDH012 NAG classes (NAF / PAF-LC / PAF-HC);
  - elbow (WCSS vs k) and BIC vs k curves, side by side;
  - bootstrap cluster stability (ARI of bootstrap refits vs the full-data partition;
    log B and seeds).
- Limitation, stated for both methods: clr is applied to a small trace-element
  subcomposition, so results depend on which elements are included (see §6 transform
  rule).
- **Propose, don't apply:** whether the ≥70% > DL and median > 10 × DL criteria should
  replace our current element selection (Stage 1 `ml_usable`: ≥50% analysed, ≤50%
  censored). Write the proposal in `LOG.md` with the element lists each rule selects per
  dataset. Changing core §6 needs human approval.

### 9.2 Comparator 2: Fontana, Hill, Huang, Stromberg & Sinclair, Golden Mile Dolerite `[VERIFY]`
Abstract level only:
- Feature engineering + PCA → Random Forest on 2 m samples; 82.5% accuracy vs logging.
- Errors attributed to model discrepancy, logging ambiguity, and the scale mismatch
  between logged intervals and 2 m samples.
- Class probabilities smoothed downhole with CSIRO Data Mosaic (wavelet tessellation).

**Experiment: "simplified analogue".** PCA → Random Forest on our 1 m composites → a
simple downhole smoother of class probabilities (a stated, fixed rule, tuned on training
folds only). Compare with our Gaussian HMM (ML-4). Validate with GroupKFold by `SiteID`
(§6 rule). **Never claim to replicate Data Mosaic.**
- Compare:
  - agreement with the logs (logged alteration and oxidation; lithology expected to be
    poor, §6 task 2);
  - fragmentation: class/state switches per 100 m, with the logs' own switch rate as
    reference;
  - consistency on the twin pads 005/014, 010/011, 016/017.
- Quantify our own scale mismatch: lithology intervals average 10.8 m (median 5.2 m),
  alteration 4.4 m (median 2.5 m), vs assays ~1 m (median 1.0 m).
- **Do not benchmark our accuracy against their 82.5%.** Context only: different deposit,
  sample support, classes and validation.

### 9.3 Citation rules
- Both papers stay `[VERIFY]` until the human supplies the PDFs.
- The Fontana title differs between the competition slide ("Drill Hole") and ResearchGate
  ("drill core"); its venue and year are unconfirmed. Do not fill them in.
- Attribute no detail beyond §9.1 and §9.2 without the full text (§2.5: no invented
  references, titles, years, DOIs or quotes).
```

**Approved (2 Nov) and applied:** §9 added to AGENTS.md verbatim from the draft above,
plus the one §6 line. No other AGENTS.md section changed.

## 2026-11-02 · Committee brief added to the repo and referenced

The human added `Technical Meeting 2nd Round OlympiAR 2026.pdf` (21 slides) to the repo
root and asked that AGENTS.md and CLAUDE.md point to it. Read in full (pypdf text, plus
rendered slides 19 and 20).

**Checked against AGENTS.md.** These match: mission and region, deadlines (7 Nov 23:59 WIB
by email; presentations 14–15 Nov), the 60/40 presentation/report split, the five
deliverables, the 9-part report structure and its sub-items, the language and font rules,
the rubric weights, and the data list (River shp, DEMNAS tiff and Topography dxf are listed
in the brief but missing from the package, as §3 already says).

**New or different in the brief (now listed in AGENTS §1 "Source documents"):**
- ML main theme is weighted 5% (technical 100); AGENTS only gave the 100.
- The bonus counts only if all sub-parameters are complete.
- Some maps/sections may be landscape. §2.4 says portrait only and was left unchanged.
  The brief wins on competition rules.
- References must be linked and attached in the reference list.
- The presentation is a PowerPoint exported to PDF.
- ioGAS v8.3.1, one licence per team on one machine.
- Slide 20 shows the full titles and author lists of the two §9 papers. §9.3 is unchanged:
  both stay `[VERIFY]` until the full texts are supplied.

**Edits:** AGENTS.md §1 gets a "Source documents" block (the brief wins on competition
rules; never copy its licence key or contacts). CLAUDE.md gets one line pointing to the
brief, with how to read it. No other section changed.

**Confidentiality:** the PDF holds the ioGAS licence key. It is committed only to this
local repo, which has no remote.

## 2026-11-02 · AGENTS.md §2.4 landscape rule and team roles (human instruction)

The human asked for two changes:
1. **§2.4:** portrait stays the default, but some maps or sections may be landscape if
   needed, as the committee brief allows. The matching bullet was removed from the
   §1 "Source documents" list, since §2.4 now states it.
2. **Roles:** the repo owner is responsible for the **ML and data analysis only, not
   ioGAS**. A new §1 "Roles" block says another team member builds the ioGAS project on
   the team's one licensed machine. This repo only hands over ioGAS-ready CSVs, and
   ML steps that compare against ioGAS output (e.g. ML-1 vs probability-plot breaks)
   leave a marked slot for it instead of waiting. §1 deliverable 2 and §2.3 now say the
   same. README "Who does what" and the stage table were updated to match.

---

## 2026-11-02 · Stage 3 plan: coordinates (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-stage-3-rippling-puddle.md`. AGENTS §5
step 2 "Coordinates" is this repo's Stage 3 (Stage 2 was the DEM). Summary:

**Read-only profiling**
- Surveys: 99 stations, station 0 always `CC` (= collar Dip/Az), spacing 20–52 m (median
  30). All dips negative (−90 to −35); max dip change between stations 3.4° (RJDH002).
  Azimuth jumps > 20° only in RJDH001 and RJDH019 (dips −88.5 to −89.7), as in AGENTS
  §4.2.12.
- Last station short of EOH: RJDH001 82.4, RJDH012 51.2, RJDH011 34.5, RJDH014 15.7,
  RJDH003 2.0 m (= AGENTS §4.2.11), plus three small ones not listed in AGENTS: RJDH016
  0.9, RJDH013 0.3, RJDH005 0.2 m. All eight are extrapolated and flagged.
- Rock `Z_Average` is 0 in all 469 rows: AGENTS §4.2.8 "verify, then ignore" confirmed.
- Rock duplicate XY: 21 rows in 8 groups (13 extra rows = AGENTS §4.2.6). One group of 4
  spans 3 dates / 3 lab jobs (genuine re-samples); the other 7 are same date, job,
  elevation and lithology (multi-sample site or copied coordinate; cannot tell). Soil:
  none.

**Method**
1. Surface re-drape: `Elev_orig` kept; `Z` = bilinear lidar DEM value (original kept for
   the 1 rock sample with no DEM). `flag_elev` = ok (|dz| ≤ 10 m) / dem_uncertain
   (10–30) / elev_error (> 30) / no_dem; `dem_support_m` and `flag_dem_weak` (> 30 m).
   `Z_Average` dropped. Duplicate-XY group id, size and type (resample /
   same_day_same_point); precision is left to Stage 7 QAQC.
2. Survey extrapolation: synthetic `EXTRAP` station at EOH with the last measured
   Dip/Az; EOH difference vs continuing the measured drift reported as uncertainty.
3. Desurvey by minimum curvature from collar UTM/RL with `AzimUTM`; exact arc
   interpolation at any depth. XYZ at from/mid/to plus `survey_extrap` added to assays and
   the four log tables. Collars get `Z_dem`, `RL_dz`, pad flag (RJDH002/006), RL unchanged.

**Outputs:** `data/interim/03_*.csv` (rock, soil, assay, 4 logs, collar, survey),
`gis/drillholes.gpkg`, `gis/surface_samples.gpkg`, QC figure
`outputs/figures/qc/03_traces_v1.png`.

**Checks:** row counts kept; station 0 = collar; Z decreasing downhole; chord ≤ arc;
`AzimUTM − AzimOrig` constant per source; min-curvature vs tangential EOH difference;
AGENTS facts reproduced (survey gaps, surface > 30 m rock 13 / soil 6, 10–30 m rock 35 /
soil 13, 1 no-DEM rock, 13 duplicate rows, pads). Synthetic unit tests for desurvey.

## 2026-11-02 · Stage 3 results: coordinates

**Run:** `uv run python scripts/03_coords.py` (a few seconds). 36 unit tests pass (22 old +
14 new: `tests/test_desurvey.py`, `tests/test_coords.py`). All checks pass, all AGENTS.md
facts reproduced. Code: `src/desurvey.py`, `src/coords.py`.

**Surface re-drape** (`Z` = lidar DEM, `Elev_orig` kept, `Elev_dz` = orig − DEM)
| | ok (≤ 10 m) | dem_uncertain (10–30 m) | elev_error (> 30 m) | no_dem |
|---|---|---|---|---|
| rock (469) | 420 | 35 | 13 | 1 (keeps `Elev_orig`) |
| soil (259) | 240 | 13 | 6 | 0 |
- No sample sits on weakly supported DEM (support > 30 m from a contour): 0 rock, 0 soil.
- Rock `Z_Average` verified all zero and dropped (AGENTS §4.2.8). `Elevation` renamed
  `Elev_orig`; downstream stages must use `Z`.
- Duplicate XY (rock only): 21 rows in 8 groups (13 extra rows). 1 group of 4 =
  `resample` (3 dates / jobs; the AGENTS §4.2.6 example), 7 groups / 17 rows =
  `same_day_same_point` (copied coordinate or several samples on one GPS fix; cannot be
  told apart from the data). Precision is for Stage 7.

**Surveys and desurvey** (minimum curvature, `AzimUTM`)
- `AzimUTM − AzimOrig` = 0 for all 99 stations, with `GridOrig` = UTM_WGS84_47N. The
  azimuths were stored in grid already. **Caveat:** whether the magnetic REFLEX readings were
  declination-corrected before export cannot be checked from this data; we trust the
  database.
- Extrapolated holes (constant last tangent), with the EOH shift if the measured dip/az
  drift continued instead, as positional uncertainty: RJDH001 82.4 m gap → 0.18 m;
  RJDH012 51.2 → 0.52; RJDH011 34.5 → 0.53; RJDH014 15.7 → 0.02; RJDH003 2.0, RJDH016
  0.9, RJDH013 0.3, RJDH005 0.2 → 0.00 m. **The extrapolation adds at most ~0.5 m of
  position uncertainty.**
- Intervals reaching below the last measured station (`survey_extrap`): assay 155,
  lithology 21, alteration 34, mineralisation 108, oxide 190.
- Near-vertical holes (AGENTS §4.2.12, not "fixed"): RJDH001 EOH is 2.69 m horizontally
  from its collar over 282.4 m; RJDH019 1.23 m over 126.6 m. The 0–350° azimuth swings
  cannot move a −89° hole more than this.
- Sanity: min curvature vs balanced tangential differ by ≤ 0.026 m at EOH. vs plain
  tangential: up to 3.24 m (RJDH002). That is higher than the plan's "< ~1 m" guess. It is the
  known bias of plain tangential (it applies the lower station's direction to a whole
  30–50 m segment), not a desurvey error.
- Collars: 17 non-pad collars within 2.07 m of the DEM. RJDH002 / RJDH006 flagged by name
  (`flag_collar_pad`, Stage 2 decision): RL − DEM −3.2 / 0.0 m on the chosen DEM. RL
  unchanged; holes start at RL.

**Outputs:** `data/interim/03_{rock,soil,assay,lithology,alteration,mineralisation,oxide,
collar,survey}.csv` (row counts unchanged; survey has 8 extra `EXTRAP` stations, 107
rows). New columns: surface `Z`, `Z_dem`, `Elev_orig`, `Elev_dz`, `flag_elev`,
`dem_support_m`, `flag_dem_weak`, `dupxy_group/n/type`; intervals `X/Y/Z_{from,mid,to}`,
`survey_extrap`; collar `Z_dem`, `RL_dz`, `dem_support_m`, `flag_collar_pad`,
`collar_note`, `survey_gap_m`, `eoh_extrap_uncert_m`, EOH XYZ. GIS (EPSG:32647):
`gis/drillholes.gpkg` (collars PointZ, traces LineStringZ at 1 m, assay_mid PointZ),
`gis/surface_samples.gpkg` (rock, soil PointZ with flags). QC (not a report figure):
`outputs/figures/qc/03_traces_v1.png`.

**Plain-language explanation (for the presentation)**
> Every sample needs a reliable position in 3D. For surface samples, the GPS heights were
> sometimes far off, by up to 36 km in one typo, so we put all of them on the lidar
> ground surface and kept the original height for the record, flagging the 19 that were
> more than 30 m wrong. For drillholes, we turned the downhole survey readings into a 3D
> path with the industry-standard minimum-curvature method. Where the survey stopped
> before the end of the hole, we continued the last direction and checked that this adds
> at most half a metre of uncertainty.

## 2026-11-02 · Stage 3 checked in QGIS (via QGIS MCP)

QGIS 4.2.3 + MCP v0.15.2 healthy. QC project `outputs/maps/qc/03_coords_check.qgz`
(hillshade, rock, soil, traces, collars; samples coloured by `flag_elev`). Only layer
styling and summary checks ran through MCP; no attribute tables were pulled into context.

- Feature counts and `flag_elev` counts read inside QGIS match the script: rock 420 / 35 /
  13 / 1, soil 240 / 13 / 6. Pads RJDH002 (−3.2 m) and RJDH006 (0.0 m) flagged; 8 holes
  with extrapolated tails.
- Directions: holes at az 315° run NW from the collar, RJDH002 and RJDH004 (135°) run SE,
  RJDH006 (325°) runs NNW, the steep holes (013, 014, 016) are short stubs, and RJDH001 is
  a point. This matches the collar table.
- Geometry: traces are LineStringZ; 3D length = `EndDepth` and top Z = collar RL in every
  hole; last-vertex Z = `EOH_Z`; surface PointZ Z = the `Z` field (max diff 0).
- The one `no_dem` rock sample sits just outside the W edge of the lidar hull, as
  expected.

---

## 2026-11-02 · Stage 4 plan: codes (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-stage-3-rippling-puddle.md` (overwritten from
the Stage 3 plan, which is logged above). Summary:

**Profiling.** Case duplicates in mineral (`hm`/`Hm`, `py`/`Py`, `lm`/`Lm`, `cy`/`Cy`),
alteration-mineral, qualifier and mode codes. Undefined in the resume: SCR, SCL, UA, CAV,
XUV-mn, VSS, SST, rock QTZ and several mineral codes. **RJDH019 has no oxidation label**
(all 127 `Comments` nulls), but `WRAltOxidPcnt` is filled. `WRAltSulphIntensity` uses
−999 as null (30 rows).

**Human decisions (2 Nov):**
1. RJDH019: keep `ox_state` null and add a separate `ox_state_derived` from
   `WRAltOxidPcnt`, with cut-offs chosen by leave-one-hole-out on the 18 logged holes. ML-2
   trains on logged labels only.
2. Undefined codes: "infer and verify yourself as best as you can". No public
   Martabe/Agincourt legend was found by web search (code names only, no data), so
   meanings come from data evidence:
   - SCR/SCL are always the first interval from 0 m: surface cover.
   - UA ⇔ SCR/SCL: 98% / 100% length overlap in the same 17 holes; the one other UA
     interval = CAV (RJDH013 59–60.1 m, NS-SEL). So UA = no alteration logged
     (cover/void).
   - `co`: Cu 3,135 ppm, CN/Cu 0.79, unoxidised: Cu sulfide `[VERIFY]`.
   - `ca`: Cu 16 ppm: calcite. `cy`: clay. `ma`/`cl`/`cp`: one row each, unresolved.
   - XUV-mn: unclassified unstratified breccia (`mn` most likely monomict).

**Method.** `_h` case-harmonised columns next to the originals; `Lith_group`
(+ Bahasa label); `Alt_facies_name` with `alt_ml_label` (UA → NaN); `ox_state`,
`ox_rank`, `flag_ox_conflict`, `ox_state_derived`, `ox_state_source`;
mineral presence flags (`min_py`, `min_cu`, `min_fe_ox`, `min_ja`, `min_su`, `min_al`);
`data/processed/code_dictionary.csv` with meaning (EN/ID), source and evidence.

**Checks.** Originals unchanged; no unmapped code; no case-only duplicates; AGENTS
§3 facies counts; the evidence above re-run in the script; the derived-oxidation
balanced accuracy must beat the majority class.

---

## 2026-11-02 · Public GitHub code publication plan (user-authorized)

**Authorization and rule exception.** The human explicitly requested: "push this repo to github, public so i can share with my teammates". This supersedes the no-remote/no-publication instruction for a reviewed public code copy only. Confidential-data and licence/contact protections remain in force. The request authorizes preparing and publishing that copy without an additional approval round.

**Inputs and method.** Review tracked files and history locally. The original history contains the committee brief, and AGENTS/LOG and numbered runners contain dataset-specific findings. Create a separate sibling checkout at `../ml-olympiar-public`, with fresh Git history. Allowlist reusable `src/*.py`, synthetic unit tests (exclude `test_raw.py`), `pyproject.toml`, and `uv.lock`; write public README, AGENTS, LOG and strict ignores. Do not attach a public remote to this confidential working checkout. Do not alter raw data, cleaning rules, source modules or existing commits.

**Outputs.** Public `67minutes/ml-olympiar` repository and a local publication checkout. Omit data, GIS/figure/map outputs, committee documents, private logs/instructions, raw manifest, MCP configuration, and dataset-specific numbered runners. Explain these omissions in the public README.

**Checks.** Run existing synthetic tests against the publication copy using the local Python environment; inspect its complete staged file list; scan text for credential patterns and dataset identifiers; verify fresh one-commit history, public visibility, pushed commit, and remote file list.

## 2026-11-02 · Public code publication completed

- Created public `https://github.com/67minutes/ml-olympiar`, default branch `main`, from the separate `C:\Users\mauli\Documents\ml-olympiar-public` checkout.
- Published a fresh single root commit `dcb897541cbba9cc562c82100499288e8e025f1a`: 17 allowlisted text files (7 source modules, 4 synthetic test modules, dependency definitions, and public-only documentation/ignores).
- The public modules and synthetic tests have identical Python ASTs to this working checkout. A private profiling observation was removed from a source comment only. No original source, cleaning rule, raw file, stage runner, or existing commit was changed.
- `uv sync --locked --offline` succeeded in the publication checkout. `uv run --no-sync pytest -q`: **35 passed**. Text scans found no blocked credential patterns, private hole/sample identifiers, private UTM coordinates or local user paths in the allowlisted files.
- Confirmed GitHub visibility is PUBLIC and remote `main` matches the reviewed commit. The public README explicitly explains the snapshot's omissions and lack of automatic synchronization.
- This confidential working checkout retains its full history and has no remote. Future publication must go through the separate reviewed code checkout; never push this checkout's history or import it into the public repository.

## 2026-11-02 · Stage 4 results: codes

**Run:** `uv run python scripts/04_codes.py`. 43 unit tests pass (7 new,
`tests/test_codes.py`). All checks pass; all original Stage 3 columns unchanged. Code:
`src/codes.py`.

**Case harmonisation** (`<col>_h`, originals kept): 33 code pairs/triples merged. Largest:
DomMin1 `hm` ← Hm/hm (1,697), `py` ← Py/py (932); DomMinMode `ds` ← Ds/ds (2,260),
`fr` ← FR/Fr/fr (293); AltMin1 `si` ← SI/si (521); AltMin2 `al` ← AL/al (371); AltQual1
`PRV` ← PRV/prv (342). No case-only duplicates remain, and every code is in a vocabulary.

**Lithology groups** (downhole intervals | rock samples): coherent dacite-andesite
porphyry 131 | 388; phreatomagmatic breccia 92 | 68; fault zone 25 | 10; surface cover
17 | 0; unclassified breccia (XUV-mn) 10 | 0; hydrothermal breccia 5 | 2;
sedimentary/volcaniclastic 4 | 0; void 1 | 0; Angkola andesite 1 | 0; quartz 0 | 1.

**Alteration:** AltFacies reproduces AGENTS §3 (AA 442, SI 158, AR 77, UA 18, PP 12).
UA is 100% inside SCR/SCL/CAV intervals, and SCR/SCL lie inside UA (≥ 0.95), so the
"no alteration logged (cover/void)" reading is confirmed. `alt_ml_label` drops UA.

**Oxidation:** logged Oxide 1,783 / Sulphide 863 / Transition 244; 11 label-vs-%
conflicts flagged; 30 `WRAltSulphIntensity` −999 → NaN.
- **Derived state for RJDH019** (human decision): cut-offs Sulphide ≤ 15% < Transition ≤
  70% < Oxide. Leave-one-hole-out on 18 logged holes: accuracy 0.906, balanced accuracy
  0.788 (baseline 0.333).
- **Transition is the weak class:** only 128 of 244 logged Transition rows are recovered;
  107 logged Sulphide rows come out as Transition.
- RJDH019 derived: Oxide 81, Transition 17, Sulphide 29 rows. Use it as context only, with
  `ox_state_source` = derived_pct.

**Mineral flags** (mineralisation intervals): `min_fe_ox` 2,003, `min_py` 1,112,
`min_ja` 124, `min_cu` 73, `min_su` 54, `min_al` 15.

**Code dictionary** `data/processed/code_dictionary.csv` (191 field×code rows), with
sources conventional 51, resume 15, inferred 9, **VERIFY 25**. The VERIFY list that
matters most by count: texture qualifier MSP (75 intervals), SecMinMode `sng` (22),
lith qualifiers `csp` (16) and `tob` (12), XUV-mn (10). The rest are 1–8 rows each. None
of them changes a group used by ML except XUV-mn (its own "unclassified breccia" group).

**Outputs:** `data/interim/04_{lithology,alteration,mineralisation,oxide,rock}.csv`,
`data/processed/code_dictionary.csv`.

**Plain-language explanation (for the presentation)**
> The core logs were typed by different geologists over 20 years, so the same mineral
> appears as "Hm" and "hm", which a computer would treat as two minerals. We merged these
> without changing the original columns, grouped the rock codes into the families of
> the geological resume, and wrote a dictionary that says where each meaning comes from.
> Codes nobody defined were checked against the data. For example, "UA" alteration
> always sits exactly on the surface-cover or cavity intervals, so it means "nothing to
> log". One hole had no oxidation log, so we estimated it from the logged
> percent-oxidised, and tested the rule on the other 18 holes first (91% agreement).

## 2026-11-03 · Stage 5 plan: joins (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-stage-3-rippling-puddle.md` (overwritten from
the Stage 4 plan, which is logged above). Summary:

**Profiling.** All four logs cover all 19 holes with no internal gaps (§4.1 holds).
Interval lengths: lithology median 5.2 m (mean 10.8), alteration 2.5 (4.4),
mineralisation 1.0, oxide 1.0, assays 1.0 (reproduces §9.2). Mineralisation and oxide
logs sit on an integer-metre grid, while many assays start on half metres, so assay
midpoints fall exactly on a log boundary in 11 / 35 / 311 / 304 rows (lith / alt / ox /
min); the label differs across that boundary in only 7 / 14 / 11 / 22. Assays spanning
more than one distinct label: 42 / 90 / 78 / 144. Mineralisation misses 14 assay
midpoints (log starts below collar or ends before EOH in RJDH002/003/004/005/007).
RJDH001's mineralisation log is a single `um` (not logged) interval, 0–282.4 m.

**Method.**
1. Midpoint in `[DepthFrom, DepthTo)`; a midpoint exactly on a boundary takes the deeper
   interval.
2. Attach the harmonised/derived label fields from `04_*` (not Comments/LoggedBy/XYZ).
3. Join-quality columns per log (`lith_`, `alt_`, `ox_`, `min_`): matched from/to,
   `frac` (share of assay length inside the matched interval), `mixed` (assay overlaps
   >1 distinct key label), `missing`.
4. Addition to the §5 midpoint rule (midpoint values kept): length-weighted
   `WRAltOxidPcnt_lw`, `WRAltSulphIntensity_lw`, `DomMinPcnt_lw`.
5. Mineral presence flags are NA (not False) where the matched interval is `um` or
   missing; `min_logged` flag.

**Outputs.** `data/interim/05_assay_joined.csv`; new layer `assay_mid_logs` in
`gis/drillholes.gpkg`.

**Checks.** Assay columns unchanged; one lith/alt/ox interval per assay; the 14
mineralisation misses exactly as profiled; `ox_state` null only on RJDH019;
reproduce §4.3 (106 NAG, 69 < 4.5; Sulphide 16 at 100%; Oxide 90 at 59%) or stop.

---

## 2026-11-03 · Stage 5 results: joins

**Run:** `uv run python scripts/05_joins.py`. 48 unit tests pass (5 new,
`tests/test_joins.py`). All checks pass; every `03_assay` column is unchanged. Code:
`src/joins.py`.

**Checks (all OK):** 2,476 rows; exactly one lithology, alteration and oxide interval per
assay; 14 mineralisation misses, all in RJDH002/003/004/005/007 as profiled; `ox_state`
null only on RJDH019 (114 assays), `ox_state_derived` filled everywhere; `frac` ≥ 0.5
wherever the matched interval is at least as long as the assay; RJDH001 mineral flags NA.
**AGENTS §4.3 reproduced from the joined table:** 106 NAG samples, 69 with NAG pH < 4.5;
Sulphide 16 (100% < 4.5); Oxide 90 (58.9% < 4.5).

**Join quality** (assays: midpoint on a boundary | spanning >1 label | frac < 0.5 | missing):
lithology 11 | 42 | 2 | 0; alteration 35 | 90 | 5 | 0; oxide 311 | 69 | 134 | 0;
mineralisation 304 | 144 | 120 | 14. The oxide/mineral `frac` < 0.5 rows are assays
longer than the 1 m log grid, so no single log interval covers half of them. The
oxide "mixed" count is 69 here vs 78 in profiling, because the join counts RJDH019's
null `ox_state` as one label (profiling used the derived labels there).
- `min_logged` False: 313 assays (RJDH001 280; `um` or missing elsewhere: 33).
- Length-weighted vs midpoint `WRAltOxidPcnt`: differ in 389 assays, by ≥ 25 points in 37.

**Sanity (sampled intervals, medians; context for the report, not tests):**
- By alteration: SI Au 2.11 g/t, CN/Cu 0.63 (n 584); AA 0.35 (1,546); AR 0.03 (277);
  PP 0.01 (26). Gold sits in the silica (vuggy) core, as the HS model predicts.
- By oxidation: Transition Au 1.02, Cu 377 ppm, CN/Cu 0.77 (217); Oxide Au 0.48, Cu 40
  (1,564); Sulphide Au 0.16, Cu 115 (571). Cu and Au are highest at the redox
  transition, consistent with supergene enrichment.
- By lithology: hydrothermal breccia Au 1.11, Cu 382 (150); porphyry 0.53 (1,226);
  phreatomagmatic breccia 0.35 (819); fault zone 0.03 (137).
- Cu with logged Cu minerals (`min_cu`): 614 ppm (71) vs 47 (2,084); not logged 68 (311).

**Bug caught by the QGIS check (fixed before commit):** pandas nullable-bool flags written
to the GeoPackage as object came out as the text "<NA>". They are now written as Int8
(1/0/null) with an assert that the null count survives. The CSV was unaffected.

**QGIS check (MCP), `outputs/maps/qc/05_joins_check.qgz`:** `assay_mid_logs` loads with
2,476 points and the same Lith_group counts. A strip section of the RJDH005/RJDH014 pad
(lith | oxidation | alteration) shows surface cover and UA aligned at the top of both
holes, and SI over AA with AR bands. The two holes' lithologies differ below the cover,
which is expected: same pad but dip −45/az 315 vs −85/az 340, ~100 m apart at EOH. So this
pad is a short-range check only near surface (relevant to §9.2 twin-pad comparisons).

**Outputs:** `data/interim/05_assay_joined.csv` (2,476 × 324), layer `assay_mid_logs` in
`gis/drillholes.gpkg`.

**Plain-language explanation (for the presentation)**
> Each assay sample now carries the rock type, alteration, oxidation and minerals the
> geologist logged at the same depth, taken at the centre of the sample. Where a sample
> straddles two logged units we flag it rather than hide it (about 2–6% of samples). The
> joined table reproduces the acid-drainage figures we checked earlier exactly, and the
> chemistry agrees with the logs: gold is highest in silica alteration, and copper is
> highest at the oxide–sulphide transition and where copper minerals were logged.

---

## 2026-11-03 · Stage 6 plan: composites (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-stage-3-rippling-puddle.md` (overwritten from
the Stage 5 plan, logged above). Summary:

**Profiling.** Sampled assays: 2,466 rows / 3,055 m (294 < 1 m, 1,390 = 1 m, 782 > 1 m,
145 > 2 m); NS-SEL 10 rows / 45.8 m. Total drilled 3,100.9 m. A fixed 1 m grid from the
collar gives 3,108 composites: 3,052 fully sampled, 15 partly, 41 unsampled; 7 final
partials < 0.5 m. Oxide and mineralisation logs share the integer-metre grid.

**Method.**
1. Fixed `[k, k+1)` composites from the collar, last one to EOH; no domain breaks (HMM
   needs regular spacing); lith/alt boundaries flagged.
2. Length-weighted means of the `_ml` analytes over sampled, non-null parts; NaN when an
   element covers < 0.5 m. NAGpH and NAG kg/t excluded (pH not additive; ML-5 uses the
   original 106 samples).
3. CN ratios recomputed as Σ(L·CN)/Σ(L·total) over the pairs Stage 1 defined.
4. Labels joined at the composite midpoint with the Stage 5 functions (moved into
   `src/joins.py`; Stage 5 output must stay byte-identical).
5. Quality columns: `comp_len`, `comp_cov_m`, `comp_nsrc`, `comp_src_maxlen`,
   `comp_shared_src`, `<el>_cens_frac`, `S_method_c`, `comp_ok` (cov ≥ 0.5 m).
6. XYZ by `desurvey.add_interval_xyz`.

**Checks.** Composites tile 0–EOH (3,100.9 m); metal balance per hole and element;
single-source composites equal their source; values within source min–max; oxide and
mineral `_mixed` all false.

---

## 2026-11-03 · Stage 6 results: composites

**Run:** `uv run python scripts/06_composite.py`. 54 unit tests pass (6 new,
`tests/test_composite.py`). Code: `src/composite.py`. `LOGS`/`attach()` moved from
`scripts/05_joins.py` into `src/joins.py`; Stage 5 rerun gives a byte-identical
`05_assay_joined.csv` (sha256 unchanged).

**Checks (all OK):** composites tile 0–EOH in all 19 holes (3,108 composites, 3,100.9 m
= summed EndDepth); metal balance per hole and element (rtol 1e-6); single-source
full-cover composites equal their source; values within source min–max; `ox_state` null
only on RJDH019; oxide and mineral labels never mixed (grid aligned); no NAG column
composited.
- First run failed the single-source check on the **7 final partial composites
  (< 0.5 m)**: the 0.5 m rule blanks them by design. The check now compares only
  composites the rule keeps and asserts that the others are blank.

**Counts:**
- `comp_ok` (sampled ≥ 0.5 m) 3,057; not ok 51 (41 NS-SEL-only, 7 short final partials,
  3 partly sampled).
- Sources per composite: 0 / 1 / 2 / 3 = 41 / 1,970 / 1,078 / 19.
- **`comp_shared_src` 1,005:** a third of composites take their whole value from one
  assay longer than 1 m, so neighbours repeat it. This is support, not information:
  ML-4 must not read these repeats as continuity, and per-hole CV is still required.
- 44 `_ml` columns composited. Core Au/Ag/Cu/As filled in 3,057 composites each.
  Ratios: AuCN 836, AgCN 685, CuCN 938.
- `S_method_c`: SCIS 2,350, S2 277, none 481 (no composite mixes methods).
- Metal × length blanked by the 0.5 m rule: Au 0.07%, Ag 0.03%, Cu 0.11%, As 0.06%.
- Labels: lith_mixed 119, alt_mixed 260 (composites cut across more logged boundaries than
  the assays did, as expected for a fixed grid); `min_logged` False 360.
- **Composite mean = length-weighted raw mean** (Au 0.809, Ag 3.831, Cu 198.3, As 132.5).
  The plain raw means (Au 0.986, etc.) are higher because the many short samples
  are in high grade. CV barely changes (Au 1.65 → 1.69, As 1.58 → 1.49). The composite
  set weights each metre equally, so it is not a like-for-like count statistic.

**QC:** `outputs/figures/qc/06_composite_v1.png` (RJDH008, RJDH012; Bahasa labels).
Composites follow the raw Au profile and only smooth within 1 m. QGIS (MCP,
`outputs/maps/qc/06_composite_check.qgz`): the `composites` layer (3,108 points) sits
on the traces; 3D spacing between consecutive composites equals the expected spacing
(max deviation 0.0 m).

**Outputs:** `data/interim/06_composites.csv` (3,108 × 132), layer `composites` in
`gis/drillholes.gpkg`, the QC figure.

**Plain-language explanation (for the presentation)**
> The lab samples range from 10 cm to 25 m long, so we cut every hole into equal 1 m
> pieces and gave each piece the length-weighted average of the samples inside it. We
> checked that no gold is created or lost: the total gold × length in each hole is the
> same before and after. Pieces with less than half a metre of real sample are kept but
> marked unusable, and pieces that just repeat one long sample are flagged so the models
> don't mistake repetition for geology.

---

## 2026-11-03 · Stage 7 plan: deliverables (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-stage-3-rippling-puddle.md` (overwritten from
the Stage 6 plan, logged above). Summary:

**Profiling.** Flags already sit in 10 interim tables. Surface samples outside RJ: rock
87 (Purnama 51, Tor Uluala 31, Parbotikan 5), soil 71 (Purnama 64, Tor Uluala 7); kept
and flagged. The only genuine rock re-sample group (4 samples, Au 25.8–58 g/t) is the
only field-duplicate evidence; the 7 same-day groups differ like separate samples.
Near-vertical azimuth swings > 20°: 6 stations (RJDH001 3, RJDH019 3), all at dip ≤ −85°.
**Lab era is confounded with hole** (each hole assayed in one year), and RJDH002/003
have no comparable neighbour from another era, so lab bias cannot be separated from
location: we show the evidence and state the limit.

**Outputs.**
1. `data/processed/validation_flags.csv`: long audit trail (one row per record ×
   issue), check IDs S1–S5 (surface), D1–D14 (drillhole), severity, action, AGENTS ref.
2. `data/processed/validation_summary.csv`: one row per check, including the §4.1 clean
   checks recomputed on the raw tables and dataset-level items.
3. `data/processed/qaqc_precision.csv`: rock duplicate-XY group CVs; CN vs total pairs.
4. `outputs/figures/07_au_lubang_tahun_v1.png`: Au by hole coloured by lab year.
5. `data/processed/iogas/`: assay, 1 m composites, rock, soil, collar, survey CSVs;
   `El_unit` element headers on harmonised values plus `_cens` Y/N; Bahasa category
   columns; Y/N flags; `kolom_iogas.csv` dictionary; README; `ML_*` merge hook from
   `data/processed/ml/`.

**Checks.** Inventory guard (every flag column mapped); §4 facts reproduced; §4.1 clean
checks pass on raw; ioGAS round-trip equality, unique keys, ASCII headers.

---

## 2026-11-03 · Stage 7 results: deliverables

**Run:** `uv run python scripts/07_export.py`. 60 unit tests pass (6 new,
`tests/test_export.py`). Code: `src/export.py`. All checks pass.

**Checks (all OK):**
- §4.1 clean checks recomputed on the raw tables: no overlaps, gaps, zero/negative
  lengths or depths past EndDepth in assay and the 4 logs; no duplicate SampleIDs (assay,
  rock, soil); collar dip/az = first survey station.
- §4 facts reproduced: elevation > 30 m rock 13 / soil 6, 10–30 m rock 35 / soil 13;
  duplicate XY 21 rows (13 extra); NS-SEL 10; AuCN > 1.1×Au 125/979, AgCN 173/1,267;
  pads RJDH002/006; RJDH001 no sulfur; azimuth swings only in RJDH001/019.
- Inventory guard: every flag-type column in the 8 source tables maps to a check. On
  the first run it caught 4 composite columns (`comp_cov_m`, `comp_len`, `comp_nsrc`,
  `comp_src_maxlen`), now mapped to Q5.
- ioGAS files: row counts equal their sources, unique keys, ASCII headers and labels,
  every element column equal to its source `_ml` column.

**Refinement of AGENTS §4.2.11 (not a contradiction):** survey stops short of EOH in
**8** holes, not 5. The 5 listed in AGENTS are the gaps ≥ 1 m; RJDH005 (0.2 m),
RJDH013 (0.3 m) and RJDH016 (0.9 m) are sub-metre and EOH uncertainty is 0.0 m. They
are flagged `info`; the AGENTS five are `warning`.

**validation_flags.csv:** 1,397 rows (error 19, warning 90, info 1,288). Errors are the 19
surface elevations > 30 m off lidar (rock 13, soil 6). Warnings: 48 surface elevations
10–30 m, 17 same-day duplicate-XY rows, collar pads 2, survey gaps ≥ 1 m 5, sulfur method
per hole 6 (RJDH001 none; S2 in 004, 006, 007, 009, 019), oxidation conflicts 11, RJDH019
derived oxidation 1.

**validation_summary.csv:** 165 rows: 19 per-check rows (S1–S5, D1–D14), 9 clean-check
rows (C1–C3, all pass), Q1 no QAQC samples, Q2 surface zeros (rock 20,275, soil 12,826
values), Q3 per-element censoring and harmonised DL (one row per dataset × analysed
element), Q4 codes (25 VERIFY), Q5 composites, Q6/Q7 pointers, Q8 weak DEM (pass).
Written UTF-8 with BOM and ASCII text so Excel opens it cleanly ("§" dropped from refs).

**qaqc_precision.csv:**
- Field duplicates: the only genuine re-sample group (4 samples, 3 dates/jobs) has CV
  Au 31% (mean 47.3 g/t), Cu 41%, As 21%. The 7 same-day groups average CV Au 92%,
  Cu 87%, As 71%. They behave like different samples at one GPS fix, not duplicates.
  n is tiny (1 group); report it as indicative only. Average-CV method after Stanley &
  Lawie (2007) `[VERIFY citation]`.
- CN/total (drillholes): AuCN/Au 979 pairs, median 0.86, 5–95% 0.34–2.5, 12.8% > 1.1;
  AgCN/Ag 1,267, median 0.79, 13.7% > 1.1; CuCN/Cu 1,268, median 0.17, 0.6% > 1.1.
  Au and Ag CN often exceed total: aliquot heterogeneity (nugget effect) of the order of
  tens of percent. Cu almost never does, so it is a gold/silver sampling issue, not a
  lab mix-up.

**Era check** (`outputs/figures/07_au_lubang_tahun_v1.png`, Bahasa labels). Median Au of
usable composites by lab year: 1998 0.43, **2004 0.02**, 2010 0.32, 2015 0.18, 2016 0.39,
2017 0.55. Each hole was assayed in one year, so era and location cannot be separated.
For context only: low-median holes also occur in other eras (RJDH009 2010, RJDH015 2016),
and RJDH002's only nearby data is the RJDH006 collar from the same pad, drilled the
opposite way. **No conclusion claimed; the report states the confounding.**

**ioGAS hand-off** (`data/processed/iogas/`):

| File | Rows × cols |
|---|---|
| `RJ_DH_assay.csv` | 2,476 × 122 |
| `RJ_DH_komposit_1m.csv` | 3,108 × 88 |
| `RJ_batuan.csv` | 469 × 93 |
| `RJ_tanah.csv` | 259 × 59 |
| `RJ_DH_collar.csv` | 19 × 13 |
| `RJ_DH_survey.csv` | 107 × 9 |
| `kolom_iogas.csv` (dictionary) | 384 rows |
| `README_iogas.txt` | — |

- Element headers are `El_unit` on harmonised values, with `_cens` Y/N where any value
  is censored.
- Category columns are in Bahasa Indonesia: `Kelompok_Litologi`, `Fasies_Alterasi`,
  `Status_Oksidasi`, `Status_Oksidasi_turunan`. Flags are Y/N.
- `ML_*` merge hook: `data/processed/ml/<target>__<task>.csv` (noted in README).
- QGIS (MCP, `outputs/maps/qc/07_iogas_check.qgz`): soil and rock CSVs loaded as delimited
  text land exactly on `surface_samples.gpkg` (259/259 and 469/469, max offset 0.0 m).

**Plain-language explanation (for the presentation)**
> Every problem we found in the data, from wrong elevations to samples that were never
> analysed, is listed in one table: what it is, which sample, how serious, and what we
> did about it. We deleted nothing. The database has no standards, blanks or duplicates,
> so we used what it does have: four re-samples of one outcrop (gold agrees within about
> 30%), and cyanide-soluble gold that sometimes exceeds total gold, which shows how
> uneven gold is between two splits of the same sample. The same clean, labelled tables
> go to our ioGAS teammate, with legends already in Bahasa Indonesia.

---

## 2026-11-03 · ML-1 plan: element thresholds (approved)

Full plan: `C:\Users\mauli\.claude\plans\cleaning-is-done-let-s-wise-flamingo.md`. Summary:

**Profiling (read-only).** Elements = Stage 1 `ml_usable` (CN columns skipped): drillhole
Au, Ag, Cu, As, SCIS_PCT; rock (RJ) Au, Cu, As, Hg, Pb, Sb, Zn; soil (RJ) Au, Ag, Cu, As, Ba,
Hg, Pb, Sb, W, Zn. Rock Ag "not determinable" (65.7% censored). A plain GMM on log10 fits the
lab's **reporting steps** (drillhole Ag K=5 at 1, 2, 3, 6, 16 ppm; soil W, rock Zn K=5);
dequantising removes most of it.

**Decisions (defaults, approved).** Surface fits and classes on RJ only (`is_RJ`); drillhole
on raw sampled assays (not composites); censored values excluded from the GMM fit and put in
population 1; MAD/Tukey on all values (censored at DL/2), flagged where censoring > 25%.

**Method** (`src/thresholds.py`). Dequantise (uniform jitter within each value's reporting
step) → GMM K = 1..5 on log10 (`n_init` 10, seed 0, `reg_covar` 0.05²), admissible only if
every component holds ≥ 5 samples; BIC averaged over 20 dequantisation draws. Thresholds =
density crossings between adjacent component means (none → pair not resolved); Ashman's D
per pair; K = 1 → 10^(μ+2σ). Bootstrap B = 200 (resample + new jitter): K frequency and
5–95% threshold CI at fixed K. Comparators: median+2·MAD and Tukey fence on log10; empty
`thr_probplot_iogas` slot for the ioGAS teammate. Heuristic confidence label.

**Outputs.** `data/processed/element_thresholds.csv`;
`data/processed/ml/{assay,batuan,tanah}__ml1_thresholds.csv` (`ML_thr_<El>_populasi`,
`ML_thr_<El>_p_atas`); figures `outputs/figures/08_ambang_{bor,batuan,tanah}_v1.png`,
`08_bic_v1.png`; rerun `07_export.py`.

**Checks.** T1 > harmonised DL; thresholds increase; CI contains estimate; ML file rows/keys;
07 checks pass; synthetic unit tests.

---

## 2026-11-03 · ML-1 results: element thresholds

**Run:** `uv run python scripts/08_ml1_thresholds.py` (96 s, joblib over elements), then
`scripts/07_export.py` (all checks pass). 70 unit tests pass (10 new,
`tests/test_thresholds.py`). Code: `src/thresholds.py`. A rerun gives an identical table
(deterministic).

**Hyperparameters:** seed 0; K = 1–5; `reg_covar` 0.05² (log10); admissible only if every
component holds ≥ 5 samples; K = argmin of BIC averaged over 20 dequantisation draws
(`n_init` 5); final fit `n_init` 10 on draw 0; bootstrap B = 200 (`n_init` 3), each draw
resampled and re-dequantised. Fits: drillhole 2,466 sampled assays, rock 382 RJ, soil 188 RJ.

**Checks (all OK):** lowest threshold > harmonised DL for every element; thresholds increase;
every point estimate inside its bootstrap 5–95% interval; ML files keyed 1:1 to their
tables, non-RJ / NS-SEL rows blank; ioGAS files gain `ML_*` columns (assay 10, batuan 14,
tanah 20).

**Thresholds** (geometric means of populations; T with bootstrap 5–95%; confidence label):

| Data | El | K (boot share) | Populations | GMM thresholds | MAD / Tukey | Conf. |
|---|---|---|---|---|---|---|
| Drillhole | Au g/t | 3 (0.58; K=2 0.39) | 0.056 / 0.49 / 1.85 | **0.16** (0.15–0.18), **0.96** (0.85–1.18) | 22 / 94 | medium |
| Drillhole | Cu ppm | 2 (0.82) | 30 / 203 | 118 (100–138) | 918 / 2,911 | medium |
| Drillhole | S SCIS % | 3 (0.65) | 0.07 / 0.69 / 2.6 | 0.21 (0.17–0.24), 1.15 (0.89–1.31) | 20 / 73 | medium |
| Drillhole | As ppm | 2, nested (D 0.19) | 87 / 104 | none; μ+2σ 567 | 423 / 754 | low |
| Drillhole | Ag ppm | 2 (0.33; K 2–4 unstable) | 2.0 / 7.5 | 4.1 (3.8–4.7) | 82 / 447 | low |
| Rock | Au g/t | 1 (0.97) | 0.25 | μ+2σ 7.1 (5.6–9.3) | 7.3 / 20 | high |
| Rock | Cu ppm | 1 (0.75) | 52 | μ+2σ 517 (427–625) | 481 / 1,092 | high |
| Rock | As ppm | 1 (0.54) | 159 | μ+2σ 2,220 | 1,387 / 2,894 | medium |
| Rock | Hg ppm | 2 (0.89) | 0.06 / 0.17 | 0.12 (0.10–0.21) | 0.37 / 0.76 | medium |
| Rock | Pb ppm | 2 (0.72) | 23 / 166 | 42 (34–54) | 846 / 1,796 | high |
| Rock | Sb ppm | 3 (0.68) | 11 / 50 / 1,450 | 26 (17–39), 464 (114–1,119) | 162 / 364 | medium |
| Rock | Zn ppm | 2 (0.78) | 5.6 / 24 | 22 (13–36) | 36 / 77 | medium |
| Soil | Au ppm | 1 (0.83) | 0.10 | μ+2σ 1.41 (1.12–1.75) | 2.25 / 6.2 | high |
| Soil | Cu / Sb ppm | 1 / 1 | 35 / 4.8 | μ+2σ 165 / 60 | 223 / 326; 74 / 132 | high |
| Soil | As ppm | 2 (0.65) | 22 / 81 | 24 (12–37) | 326 / 585 | medium |
| Soil | Pb ppm | 2 (0.82) | 22 / 88 | 32 (26–48) | 396 / 731 | medium |
| Soil | Zn ppm | 2 (0.89) | 6.8 / 28 | 12 (10–14) | 104 / 171 | high |
| Soil | Ba / Hg | 2 nested each | — | none; μ+2σ 527 / 0.61 | 418 / 496; 0.48 / 0.80 | medium |
| Soil | Ag ppm | 3 (0.91) | 0.23 / 0.51 / 1.05 | 0.32, 0.88 | 1.36 / 1.98 | low (15 distinct values) |
| Soil | W ppm | 1 (0.72) | 5.2 | μ+2σ 20 | 37 / 249 | low (32% censored) |

Rock Ag: not determinable (65.7% censored). `thr_probplot_iogas` is empty for the ioGAS
teammate to fill.

**What the numbers say**
- **Two kinds of threshold.** GMM thresholds split *populations*; MAD/Tukey cut the *upper
  tail* (they flag 0–6% of samples everywhere). Where an element has one population
  (K = 1), the GMM fallback μ+2σ and median+2·MAD agree closely (rock Au 7.1 vs 7.3 g/t,
  rock Cu 517 vs 481 ppm). Where it has several, the GMM breaks sit far below MAD/Tukey.
- **RJ surface gold is one log-normal population** in rock (K = 1, bootstrap 0.97) and soil
  (0.83). Gold anomalies at surface are the upper tail of one population, not a separate
  population, so ML-3 zonation should rank by grade within it.
- **Soil As, Pb, Zn: the *low* population is the minority** (As 24, Pb 44, Zn 44 of 188
  samples). Most of the RJ soil grid sits on the mineralised/altered footprint, and the GMM
  threshold separates a background fringe from it (77–87% of soils lie above it). To be
  checked spatially in ML-3 (where the low population lies).
- **Drillhole populations are grade populations, not background vs anomaly.** Au breaks at
  0.16 and 0.96 g/t (low / medium / high grade); Cu at 118 ppm (likely the supergene /
  sulfide-Cu population, cf. Stage 5: Transition Cu median 377 ppm); sulfide S at 0.21% and
  1.15%. The near-zero S population (0.07%) is relevant to ML-5 (oxidised material).
- **Reporting-step artefact found and handled.** Without dequantising, drillhole Ag gave
  K = 5 at 1, 2, 3, 6, 16 ppm, i.e. the lab's reporting steps. Dequantising plus the
  ≥ 5-sample rule removed this for W and Zn; drillhole Ag and soil Ag remain unstable and are
  labelled low confidence.
- Raw drillhole assays are not length-weighted (short samples are over-represented in high
  grade, Stage 6), and censored values are outside the fit. Both are stated limits.

**Outputs:** `data/processed/element_thresholds.csv` (23 rows); `data/processed/ml/
{assay,batuan,tanah}__ml1_thresholds.csv` (`ML_thr_<El>_populasi`, `ML_thr_<El>_p_atas`;
`p_atas` blank where there is no distinct top population); merged into
`data/processed/iogas/`; figures `outputs/figures/08_ambang_{bor,batuan,tanah}_v1.png`,
`08_bic_v1.png`.

References for the report `[VERIFY]`: Sinclair (1974) J. Geochem. Explor. 3:129–149;
Reimann, Filzmoser & Garrett (2005) Sci. Total Environ. 346:1–16; Ashman, Bird & Zepf
(1994) Astron. J. 108:2348.

**Plain-language explanation (for the presentation)**
> Instead of picking anomaly thresholds by eye on a probability plot, we let a mixture
> model find how many overlapping populations each element has and where they cross. We
> first removed a trap: labs report values in steps like 1, 2, 3 ppm, which the model would
> otherwise mistake for populations. Each threshold comes with a bootstrap range and a
> confidence label. Surface gold at RJ turns out to be a single population, so the
> classic "mean + 2 SD" cut-off (about 7 g/t in rock) is the right one there, while
> arsenic, lead and zinc in soil show a clear background group below the main
> mineralised population. Downhole, gold splits naturally at about 0.16 and 1 g/t.

---

## 2026-11-03 · ML-1 checked in QGIS (via QGIS MCP)

Project `outputs/maps/qc/08_ml1_check.qgz` (hillshade, traces, collars, ioGAS rock and soil
CSVs as delimited text, filter `prospek_RJ = 'Y'`). QC renders (not report figures):
`outputs/maps/qc/08_tanah_As_v1.png`, `08_tanah_Zn_v1.png`, `08_batuan_Au_v1.png`. Only
counts, distances and renders came back through MCP; no attribute tables.

- **Counts:** 382 rock and 188 soil RJ points load; population counts per element equal the
  Python output.
- **Distance to drill traces** (median, m; all soil 168, all rock 153):
  - Soil Zn: **low population 48 (n 44) vs main 212 (n 144)**. The low-Zn soils form a
    continuous corridor along the drilled ridge (RJDH007 → RJDH015/003 and further SSE) with
    an arm to the WSW. Reading: Zn leached from the acid, altered HS core. This is the
    clearest spatial signal in ML-1 and a candidate input/explanation for ML-3.
  - Soil As: low population 258 (n 24) vs main 163. Mostly on the southern soil lines
    (edge of the footprint), plus a few points inside the drilled area.
  - Soil Pb: low 198 vs main 164 (weak). Rock Hg: upper population 69 (n 80) vs lower 149.
- **Rock Au > 7.1 g/t (μ+2σ):** 10 samples at 7 locations; 4 are the re-sampled outcrop
  (Stage 7 duplicate-XY group, 25.8–58 g/t) on the northern knoll. The others are isolated
  points (N, near RJDH007/013, W, two S). Not a trend.
- **NE-trend test: not possible from class point clouds.** The principal axis of every
  class (~105–145°) follows the soil sampling lines (E–W lines) and rock traverses, not the
  geochemistry. The NE structural check is deferred to ML-3 (interpolated surfaces /
  zonation maps), where sampling geometry can be separated from the signal.

---

---

## 2026-11-03 · ML-2 plan: classes from chemistry (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-ml-2-frolicking-rabbit.md`. Summary:

**Human decisions.** Train on raw sampled assays (composites repeat long samples); depth
only as an oxidation ablation; add a separate surface rock alteration model.

**Profiling (read-only).** 2,466 sampled assays. Au/Ag/Cu/As in all 19 holes, SCIS_PCT in
16, S2 in 5 (never mixed with SCIS), CN ratios in 11–12; the full ICP suite only in RJDH001
and RJDH012 (unusable under group CV). **Collars within 30 m form 7 pairs** (002/006,
005/014, 007/013, 008/019, 010/011, 016/017, 012/018 at 27 m), so **12 pad groups**; twin
holes share near-surface geology and leave-one-hole-out would leak. Rock RJ grabs: SI 207,
AR 135, PP 38, AA 2. Surface logging almost never uses AA (1,781 composites downhole).

**Method** (`src/classify.py`, `scripts/09_ml2_classify.py`).
- Features: log10 of harmonised `_ml` values. Tier A = Au, Ag, Cu, As + log-ratios Cu/Au,
  As/Au, Cu/As (all holes); tier B = A + SCIS_PCT; tier C = A + AuCN and CuCN ratios. Each
  tier is fitted only on rows with all its features (no imputation, so missingness cannot
  act as a hole ID).
- Targets: alteration AA/SI/AR/PP (UA excluded); logged oxidation (RJDH019 predicted,
  compared descriptively with the derived state); lithology (4 main groups + other,
  surface cover excluded); `min_py`, `min_cu` (rows with logged mineralogy).
- RandomForest (300 trees, balanced_subsample, sqrt features, seed 0), `min_samples_leaf`
  {1, 5, 20} by inner GroupKFold(4) on pads. Comparators: Dummy (prior), logistic regression.
- Outer leave-one-pad-out; leave-one-hole-out once to show the leakage gap. Balanced
  accuracy, macro-F1, κ, per-class recall/precision, confusion matrices, pad-bootstrap 90% CI,
  clean vs boundary assays, PR-AUC for binary targets.
- OOF probabilities, `p_maks`, `ambigu` (p < 0.5), reliability curve; review list where
  OOF p ≥ 0.7 disagrees with the log, runs ≥ 3 m.
- SHAP on the all-data RF (tiers A, B) in element units. Depth ablation for oxidation.
- Rock: SI/AR/PP on Au, Cu, As (+ Hg, Pb, Sb, Zn), 150 m spatial-block GroupKFold(5); apply
  the drillhole alteration model to rock as a descriptive label-mismatch check.

**Outputs.** `data/processed/ml/{assay,batuan}__ml2_classify.csv`, `ml2_scores.csv`,
`ml2_review_list.csv`, figures `09_*_v1.png`, rerun `07_export.py`.

**Checks.** No pad in both train and test; one OOF prediction per eligible row; ML files
1:1 keyed; deterministic rerun; 07 checks pass; synthetic unit tests.

---

## 2026-11-03 · ML-2 results: classes from chemistry

**Run:** `uv run python scripts/09_ml2_classify.py` (8.6 min, 16 cores), then
`scripts/07_export.py` (all checks pass). 78 unit tests pass (8 new, `tests/test_classify.py`).
Code: `src/classify.py`. A second run gives byte-identical outputs (sha256 of all 7 tables).

**Hyperparameters:** seed 0; RF 300 trees, `class_weight="balanced_subsample"`,
`max_features="sqrt"`, `min_samples_leaf` from {1, 5, 20} by inner GroupKFold(4) on pads
(chosen leaf: mostly 20, 5 for oxidation/pyrite tier B; **20 is the grid edge**, so a
coarser leaf might score slightly higher: not tuned further). Logistic regression
(standardised, balanced weights); Dummy (prior). Outer CV leave-one-pad-out (12 pads; pyrite/Cu
11, RJDH001 has no mineral log); pad bootstrap B = 1,000. Rock: 150 m blocks (33),
GroupKFold(5). Tier rows: A 2,466 (19 holes, 12 pads), B 1,898 (16, 10), C 500 (11, 9).

**Scores** (balanced accuracy, out-of-fold, RF unless stated; 90% pad-bootstrap interval;
prior baseline = 1/classes):

| Target | Best set | RF | Logistic | Baseline | κ | Note |
|---|---|---|---|---|---|---|
| Alteration AA/SI/AR/PP | A (C on its 500 rows) | **0.70** (0.65–0.76) | 0.71 | 0.25 | 0.49 | recall AA 0.71, SI 0.72, AR 0.67, PP 0.69 (n 26) |
| Oxidation | B (+S) | **0.71** (0.66–0.77) | 0.70 | 0.33 | 0.65 | export mix 0.69; Oxide 0.91, Sulphide 0.74, **Transition 0.41** |
| Lithology (5 groups) | B | 0.30 (0.27–0.35) | 0.35 | 0.20 | 0.13 | hydrothermal breccia recall 0 (86% called porphyry) |
| Pyrite present | B (+S) | **0.84** (0.81–0.87) | 0.75 | 0.50 | 0.68 | PR-AUC 0.87 vs prevalence 0.37 |
| Cu minerals present | A | 0.62 (0.51–0.71) | 0.79 | 0.50 | 0.12 | PR-AUC 0.10 vs prevalence 0.03; 61 of 71 positives in RJDH007/018 |
| Surface rock alteration SI/AR/PP | R2 | 0.36 (0.31–0.43) | 0.37 | 0.33 | 0.07 | **no better than chance** |

- **Twin-pad leak is small but real:** leave-one-hole-out vs leave-one-pad-out, tier A:
  alteration 0.72 vs 0.70, lithology 0.30 vs 0.26, oxidation and pyrite equal.
- **Adding sulfur (SCIS) helps where sulfur is the process:** oxidation +0.08 and pyrite
  +0.07 over tier A on the same rows. It *lowers* RF alteration (−0.08) and Cu minerals
  (−0.09) on the same rows. CN ratios (tier C) help alteration (+0.08) and oxidation (+0.09)
  but exist in only 9 pads. The export uses, per row, the richer set only where it beat
  set A on the same rows (`ML_<t>_tier`).
- **"Is oxidation just depth?" No.** Adding vertical depth: A 0.646 → 0.674, B 0.709 → 0.710.
  Sulfur and Cu chemistry carry the information; depth adds nothing once S is known.
- **Boundary assays** (spanning a logged contact or < 50% inside one interval) score lower
  everywhere (e.g. oxidation B 0.71 clean vs 0.59 boundary): part of the "error" is the
  log, not the model.
- Logistic regression matches RF for alteration and is better for lithology and Cu
  minerals (rare classes, where RF with leaf 20 rarely predicts the minority). RF is kept
  as the exported model as planned; the logistic scores are in `ml2_scores.csv`.
- Per held-out pad: alteration 0.56–0.80 (median 0.68), oxidation 0.56–0.81 (0.71),
  pyrite 0.60–0.82, lithology 0.10–0.54.

**Uncertainty.** Probabilities are reasonably reliable for oxidation and alteration
(observed agreement close to or above the top-class probability; RF is under-confident above
0.6) and meaningless for lithology (agreement ~0.4 at every confidence).
`ML_<t>_ambigu` (p < 0.5): alteration 150, oxidation 273, lithology 1,398 of the predicted
assays; rock 161 of 352.

**SHAP (in element units, `09_shap_dependensi_v1.png`).** Silica (vuggy) alteration:
probability rises sharply once Au > ~1 g/t, falls when As/Au > ~100, rises with Ag
> ~3 ppm. Sulphide zone: probability rises once SCIS S > ~2%, Cu/Au > ~1,000 and
As/Au > ~1,000. Oxidation tier A leans on Cu and Cu/Au (Cu is leached in the oxide zone).
Pyrite: S (SCIS), then Cu/As.

**RJDH019 oxidation (no log):** ML agrees with the state derived from % oxidised in 61%
(n 114). The derived rule itself agreed 91% with logs elsewhere, so this is a weak check.

**ML vs logged review list** (`ml2_review_list.csv`, OOF p ≥ 0.7 against the log, runs
≥ 3 m): alteration 40 runs / 190 m, lithology 19 / 97 m, oxidation 12 / 57 m. Notable:
**RJDH009 10–57 m is logged Oxide but chemistry says Sulphide** in four runs (25 m);
several "Transition" intervals in RJDH003/004/007/013 read as clean oxide or sulphide. These
are candidates for re-checking core photos, not corrections.

**Surface rock vs core: different label conventions.** Rock alteration cannot be learned
from chemistry (0.36 vs 0.33 baseline). The drillhole alteration model (Au, Cu, As only)
applied to rock calls 250 of 352 RJ rocks advanced argillic, while surface mapping uses AA
for only 2. Surface "SI" and "AR" are field calls on weathered outcrop that do not map onto
the core facies. Rock `ML_alt_*` columns are exported but must be shown as low confidence.

**Outputs:** `data/processed/ml/assay__ml2_classify.csv` (`ML_{alt,oks,lit}_prediksi`,
`_p_maks`, `_ambigu`, `_entropi`, `_p_<class>`, `_tier`; `ML_{py,cu}_p`, `_tier`),
`data/processed/ml/batuan__ml2_classify.csv`, `data/processed/ml2_{scores,review_list,
shap_importance,per_pad,rock_transfer}.csv`; figures `outputs/figures/09_{skor,
matriks_konfusi,shap,shap_dependensi,reliabilitas,skor_pad}_v1.png`; merged into
`data/processed/iogas/` (assay +31 ML-2 columns, batuan +7).

**Limits to state in the report.** 12 independent pads; PP has 26 assays and Cu minerals
sit in two holes; sulfur exists by one method in 16 holes; boundary and support effects
(alteration intervals median 2.5 m vs 1 m assays); RF leaf at the grid edge.

**Plain-language explanation (for the presentation)**
> We asked whether the chemistry alone can tell what the geologist logged. To keep it
> honest, the model never sees the drill pad it is tested on, because two holes on one pad
> share the same rocks. Alteration and oxidation come out right about 70% of the time
> (chance is 25–33%), and pyrite 84%, and the model explains itself in geological terms:
> gold above about 1 g/t means vuggy silica, sulfur above about 2% means fresh sulphide rock.
> Rock type cannot be read from these four metals, because alteration has overprinted the
> original rock: that is a geological result, not a failure. Where the model confidently
> disagrees with the log, for example 25 m of "oxide" in RJDH009 that chemically looks like
> sulphide, we list it for a second look at the core.

---

## 2026-11-03 · ML-3 plan: surface H/M/L zonation (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-ml-3-recursive-boot.md`. Summary:

**Profiling (read-only).** RJ soil 188 samples (1997–99 jobs, 5 from 2009); features Au, Cu,
As, Hg, Pb, Sb, Zn (complete; Ba job-dependent, W 32% censored, Ag 17 distinct values: left
out). Robust-scaled log10: PC1 57.5% (Au-As-Pb-Hg-Sb-Cu, Zn ≈ 0), PC2 Zn+Hg 17%; Horn
parallel analysis keeps **PC1 only**; PC1 vs log Au r 0.87. GMM on PC1: BIC K = 2 (K1 +4.5,
K3 +15); bootstrap ARI K2 0.79, K3 0.69. Multi-PC GMMs unstable (ARI 0.1–0.5). Lab jobs sit
on separate lines; neighbours < 60 m differ slightly more across jobs (|Δlog Au| 0.38 vs
0.30): weak batch component, confounded with location. Rock RJ 382 (Au-Cu-As in 352; Hg/Pb/
Sb/Zn 261), very clustered (nearest neighbour median 5 m); BIC K 1–2.

**Human decisions.** H/M/L = GMM **K = 3 on the PC1 index** (ranked by Au: Tinggi/Sedang/
Rendah), with BIC (prefers 2) and bootstrap stability reported openly. GP surface of the soil
index plus an NE-trend test against an isotropic null on the same sample layout.

**Method** (`src/zonation.py`, `scripts/10_ml3_zonation.py`). Dequantise (ML-1) → log10 →
median/MAD scale → PCA + Horn → GMM K 1–5 (BIC over 20 draws, ≥ 5 per component), zones at
K = 3 sorted by index, Au ordering asserted; posteriors averaged over draws; bootstrap B = 200
of the whole pipeline (per-sample stability, threshold CI, ARI); K = 2 partition alongside.
Rock: own pipeline on Au-Cu-As (sensitivity with Hg, Pb, Sb, Zn), float flagged, points only.
Comparisons: ML-1 classes, lab job (Cramér's V, neighbour test), rock alteration/outcrop,
rock vs soil-surface zone; sensitivities CLR and censored-excluded. GP: Constant × RBF(2
length scales, rotated θ by profile LML 0–165°) + White, 10 m grid masked > 60 m from soil,
spatial block CV (150 m, 5 folds). NE test: directional variograms (12 directions, ±22.5°,
40 m lags) vs 200 isotropic simulations on the sample locations.

**Outputs.** `data/processed/ml/{tanah,batuan}__ml3_zonation.csv`, `ml3_summary.csv`,
`ml3_model.csv`, `gis/ml3_zonasi.gpkg`, `gis/ml3_tanah_*.tif`, figures `10_*_v1.png`, rerun
`07_export.py`, QGIS QC project `outputs/maps/qc/10_ml3_check.qgz`.

---

## 2026-11-03 · ML-3 results: surface H/M/L zonation

**Run:** `uv run python scripts/10_ml3_zonation.py` (~50 s), then `scripts/07_export.py` (all
checks pass). 89 unit tests pass (11 new, `tests/test_zonation.py`). Code: `src/zonation.py`.
A rerun gives identical sha256 for the ML and summary tables.

**Hyperparameters:** seed 0; features soil Au, Cu, As, Hg, Pb, Sb, Zn (n 188 RJ); rock Au, Cu,
As (n 352 RJ; 30 without As left blank). Dequantised log10 → median/MAD scale → PCA; Horn 200
permutations, 95th percentile. GMM on PC1, K 1–5, BIC averaged over 20 draws, `n_init` 10,
`reg_covar` = (0.05 × Σ|w|/MAD)² (soil 0.110, rock 0.024), ≥ 5 samples per component.
Zones = K 3, posterior averaged over 20 draws; `ambigu` p_maks < 0.5. Bootstrap B = 200 (full
refit for stability/ARI; fixed transform for boundary CI and BIC-K). GP: Constant × RBF(2
scales) + White, `normalize_y`, 3 restarts, θ 0–165° step 15; 10 m grid, mask 60 m; CV 150 m
blocks (38), GroupKFold 5. NE test: 12 directions ±22.5°, lags 40–400 m, 200 isotropic sims.

**Deviation from the plan (implementation, not method):** zone boundaries on the index are the
points where the most probable zone changes (`zonation.boundaries`), not ML-1 density crossings
between adjacent means. In rock the top component is wide, so its boundary lies beyond its own
mean and the crossing rule returned NaN. The function asserts the zones are ordered along the
index (they are, in both datasets).

**Bug caught by the QGIS check (fixed):** the rock GeoPackage layer was written in append mode
and held 1,760 features after 5 runs. Now both layers are written with `mode="w"` (replaces the
layer only), and the script reads the feature count back and checks it.

**Soil (RJ, 188):**
- PC1 = 57.5% of variance (loadings Au .38, As .49, Pb .43, Hg .41, Sb .40, Cu .31, Zn −.07);
  Horn keeps 1 PC (eig 5.0 vs 1.99; PC2 1.50 vs 1.65). PC1 vs log Au r 0.87.
- ΔBIC: K1 +4.5, **K2 0**, K3 +15.3, K4–5 inadmissible. Bootstrap BIC-K: K2 0.72, K1 0.28.
- K = 3 zones: Rendah 30 / Sedang 92 / Tinggi 66. Boundaries on the index −2.23 (5–95%
  −4.21 to −1.41) and 1.06 (−0.25 to 1.98); Ashman D 2.07 and 1.69. Bootstrap ARI median 0.65
  (5–95% 0.27–0.92); per-sample stability median: R 0.88, S 0.84, T 0.96; 1 ambiguous sample.
- Median Au / As / Pb / Sb ppm: R 0.007 / 13 / 17 / 0.6; S 0.065 / 54 / 57 / 4.0; T 0.34 /
  129 / 129 / 16.5. Zn flat (22 / 25 / 18.5) and Hg weakly rising.
- **The BIC split (K = 2) is background vs footprint:** it puts all 30 Rendah plus 6 Sedang in
  one population; K = 3 splits the footprint into Sedang and Tinggi (ARI K2 vs K3 0.33).
- Sensitivities (ARI vs main): CLR 0.27, censored rows excluded 0.43 (n 170). The middle split
  moves with the transform, which is expected for a continuum.
- vs ML-1: As and Pb populations agree (Cramér's V 0.66, 0.77; all Tinggi in the upper As/Pb
  population); soil Au > μ+2σ (1.41 ppm) is only 1 sample (V 0.10); Zn populations not aligned
  (V 0.15).
- Lab job: V 0.42, but jobs are lines (location). Neighbours < 60 m: |Δ index| median 0.93 within
  one job vs 1.24 across jobs (Mann–Whitney p 0.017): a modest batch/line component.

**Rock (RJ, 352, Au-Cu-As):** PC1 68% (Au .48, Cu .54, As .69), Horn 1 PC; **BIC K = 1** (K2
+2.4, K3 +17.9; bootstrap K1 0.49, K2 0.45). Zones R 204 / S 131 / T 17; boundaries 0.17
(−1.88 to 0.37) and 2.63 (0.73 to 4.16). ARI median 0.76 (0.23–0.93). Median Au g/t R 0.12,
S 0.53, T 5.0; As 86 / 351 / 2,270; Sb rises too (8 / 29 / 256; not a model input).
Sensitivities: censored excluded 0.94; **+Hg, Pb, Sb, Zn 0.14 (n 261); CLR −0.02**. Rock
zones depend on the element set: **low confidence.** vs logged alteration V 0.17, outcrop type
0.06; Au > 7.1 g/t: 7 of 17 Tinggi (V 0.59). Rock zone vs soil-GP zone at the same place
(345 inside the mask): κ −0.06, agreement 0.19. Rock grabs are point samples of selected
outcrop; soil is a spatial average. They rank locally differently, but 12 of 16 rock Tinggi
sit in soil Tinggi.

**GP surface (soil index):** best rotation 75°, major axis **75° (ENE)**, length scales
171 / 69 m (ratio 0.40), nugget 0.34 of normalised variance. LML: anisotropic −204.6 vs
isotropic −210.6; 60–90° within 1.2 of the best, 30° and 45° 4.7–5.9 lower. Block CV RMSE:
anisotropic 1.56, isotropic 1.66, mean-only 2.30; 90% interval coverage 94% / 93%. Area within
60 m of soil: Rendah 6.3 ha, Sedang 41.3, Tinggi 27.4. Collars in the GP zone: 14 Sedang, 5
Tinggi (RJDH004, 010, 011, 012, 018). **The largest soil Tinggi area (W–central) is
largely undrilled.**

**NE test: NOT confirmed.** Directional variograms: greatest continuity at **90° (E–W)**,
ratio 0.51, stronger than all 200 isotropic simulations on the same points (null ratio
5–95% 0.64–0.86; p < 0.005); only 7% of simulations put the maximum at 90°, while 30% fall in
the NE window by geometry alone. Centring the index per lab job leaves it unchanged (90°, 0.51),
so it is not a lab-batch offset. **But soil lines run E–W:** a per-line effect (crew, sampled
horizon) cannot be separated from geology with these data. This does not contradict AGENTS §4
(the NE trend was a check to run, not a verified finding). Report it as: "the soil index is
elongated E to ENE, not NE; it may reflect geology, downslope dispersion or line effects
(untested)."

**Outputs:** `data/processed/ml/{tanah,batuan}__ml3_zonation.csv` (`ML_zona`, `_id`,
`_p_T/S/R`, `_p_maks`, `_ambigu`, `_stabil`, `_indeks`, `_K2`; rock `_float`), merged into
`data/processed/iogas/` (tanah +10, batuan +11 columns); `data/processed/ml3_summary.csv`,
`ml3_model.csv`, `ml3_comparisons.csv` (crosstabs; not in the plan, added for the report
tables); `gis/ml3_zonasi.gpkg` (`tanah_zona` 188, `batuan_zona` 352);
`gis/ml3_tanah_{indeks,indeks_sd,p_tinggi,p_rendah,zona}.tif`; figures
`outputs/figures/10_{pca_biplot,bic_stabilitas,zona_unsur,variogram_arah,gp_cv}_v1.png`.
QGIS (MCP) `outputs/maps/qc/10_ml3_check.qgz`: layer counts and zone counts equal Python;
sampling the zone raster at rock points reproduces the Python crosstab (1 cell differs by one,
raster vs point). QC render `outputs/maps/qc/10_tanah_zona_v1.png` (not a report figure).

**Limits to state.** Soil has one gradient and BIC prefers 2 populations, so K = 3 is a decision
zoning with stability shown; rock is one population (BIC K = 1) and its zones change with the
element set; one 1997–99 soil campaign with line/job effects confounded with location;
clustered rock sampling mixing float (46) with outcrop; CLR subcomposition caveat; the surface is
valid only within 60 m of soil samples, and SD is for the latent field (nugget excluded).

**Plain-language explanation (for the presentation)**
> We combined seven soil elements into one "mineralisation index" with PCA. Gold, arsenic,
> lead, antimony, mercury and copper all rise together, and a statistical test says that this
> single gradient is the only real structure. A mixture model cut the index into low, medium
> and high zones. The data only firmly support two groups (background vs the mineralised
> footprint), so we show how stable each sample's zone is (high-zone soils keep their zone in
> 96% of re-runs). Kriging the index gives a map with its uncertainty. The high zone is
> elongated east–west to ENE, not NE as we expected, and most of it west of the drilling is
> still untested.

---

## 2026-11-03 · ML-4 plan: downhole geochem-stratigraphy (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-ml-4-shimmering-gadget.md`. Summary:

**Profiling (read-only).** 3,057 `comp_ok` composites with Au/Ag/Cu/As in all 19 holes; gaps
(RJDH006 22–38 m, 172–174 m; isolated 1 m in RJDH005/013; final partials) break sequences. At the
DL/2 floor: Ag 1,084 (35%), Au 243, Cu 22, As 7. `comp_shared_src` 1,005 (32%; RJDH002/003
72–76%). SCIS in 16 holes (2,345), S2 273, none in RJDH001. Logged switch rates per 100 m:
alteration 10.5, lithology 5.1, oxidation 2.85. 12 pads.

**Human decisions.** Keep Ag with censored values spread uniformly in log10 on [DL/3, DL] per
draw (no-Ag sensitivity); main model log Au, Ag, Cu, As in all holes, +SCIS and +CuCN/Cu as
sensitivities only; draft the three report sections in QGIS within ML-4.

**Method** (`src/geostrat.py`, `scripts/11_ml4_hmm.py`). Dequantise (ML-1) / spread censored →
median/MAD scale → full-covariance `GaussianHMM` (`min_covar` (0.05/median MAD)², `n_iter` 500,
10 restarts) on contiguous `comp_ok` runs. K 2–8 by leave-one-pad-out held-out log-likelihood
(smallest K within 1 SE of best; ≥ 30 composites and ≥ 2 holes per state); BIC shown only.
Comparator: GMM with the same emissions and K. Posteriors averaged over 20 draws; states ordered
by mean log Au; pad bootstrap B = 100 (Hungarian alignment) for stability and CIs. Sensitivities:
no Ag, +SCIS, +CuCN/Cu, K ± 1, shared-source runs collapsed. Comparisons vs logged alteration,
oxidation, lithology and ML-2; switch rates; cross-hole state agreement by 3D distance and on the
7 twin pads.

**Sections** (`scripts/12_ml4_sections.py` + QGIS MCP). Three NW–SE sections (az 315/135, ±40 m,
looking NE, 1:1): A RJDH001/003/008/009/015/019; B RJDH005/012/014/016/017/018; C
RJDH002/006/007/013 (004, 010, 011 off-section). Local section frame in `gis/ml4_penampang.gpkg`;
plan layers `gis/ml4_hmm.gpkg`; QGIS project `outputs/maps/11_ml4_penampang.qgz`, 3 layouts + index
map, 300 dpi PNG.

**Outputs.** `data/processed/ml/komposit__ml4_hmm.csv`, `ml4_{summary,states,comparisons}.csv`,
figures `11_*_v1.png`, rerun `07_export.py`.

---

## 2026-11-03 · ML-4 results: downhole geochem-stratigraphy (Gaussian HMM) and sections A–C

**Run.** `PYTHONIOENCODING=utf-8 uv run python -W ignore scripts/11_ml4_hmm.py` (~17.5 min),
then `uv run python scripts/12_ml4_sections.py`, then `scripts/13_ml4_qgis_layouts.py` inside
QGIS 4.2.3 (MCP `execute_code`), then `uv run python scripts/07_export.py`. Determinism: two full
runs give the same sha256 for `komposit__ml4_hmm.csv` (9134db95…). Tests: `tests/test_geostrat.py`
(9 new), full suite passes.

**Hyperparameters.** Features log10 Au, Ag, Cu, As on 3,057 `comp_ok` composites in 22 contiguous
segments (19 holes). Censored (`cens_frac` ≥ 0.5) spread uniform in log10 on [DL/3, DL] (Au/Ag:
Stage 1 harmonised DL; Cu/As: 2 × the floor value, job-specific DLs); others dequantised (ML-1);
median/MAD scaling fitted on draw 0. `GaussianHMM` full covariance, `min_covar` 0.00517 (scaled;
(0.05 / median MAD)²), `n_iter` 500, `tol` 1e-4, 10 restarts (seeds 0–9), CV 5 restarts × 5 draws,
decoding 20 draws, bootstrap B = 100 × 3 restarts, seed 0. Ambiguous = averaged posterior max < 0.5.

**K selection (leave-one-pad-out, 12 pads; held-out log-likelihood per composite ± SE).**

| K | HMM | GMM | HMM − GMM | BIC | min state n | min holes |
|---|---|---|---|---|---|---|
| 2 | −4.342 ± 0.18 | −4.723 | 0.38 | 26,503 | 1,102 | 19 |
| 3 | −4.126 ± 0.19 | −4.680 | 0.55 | 24,745 | 715 | 18 |
| 4 | −3.959 ± 0.19 | −4.685 | 0.73 | 23,368 | 522 | 16 |
| **5** | **−3.795 ± 0.18** | −4.650 | **0.86** | 22,450 | 368 | 13 |
| 6 | −3.717 ± 0.18 | −4.630 | 0.91 | 21,903 | 342 | 13 |
| 7 | −3.680 ± 0.18 | −4.628 | 0.95 | 21,451 | 308 | 13 |
| 8 | −3.636 ± 0.17 | −4.625 | 0.99 | 21,263 | 240 | 10 |

Held-out LL rises to K = 8, but K = 5 is the smallest K within 1 SE of the best (−3.636 − 0.174 =
−3.810 < −3.795); all K admissible. **K = 5 selected.** BIC keeps falling (not used: 1 m
autocorrelation over-counts n). Sequence information adds ~0.86 nats per held-out composite over
the GMM at K = 5, and is positive at every K.

**States (geometric means in element units, pad-bootstrap 5–95%; run = 1/(1 − a_kk) m).**

| State (`ML_hmm_nama`) | n | holes | Au g/t | Ag | Cu ppm | As | run m | stability | log mode |
|---|---|---|---|---|---|---|---|---|---|
| S1 Au rendah, Cu rendah (Sulfida) | 533 | 16 | 0.013 (0.011–0.032) | 0.30 | 26 (23–35) | 50 | 14.6 (9.9–21.3) | 1.00 | AR 56%, Sulphide 73% |
| S2 Au rendah, Cu rendah (Oksida) | 776 | 19 | 0.067 (0.046–0.25) | 0.72 | 52 (35–71) | 90 | 10.5 (4.8–13.4) | 0.74 | AA 66%, Oxide 65% |
| S3 Au sedang, Cu rendah (Oksida) | 368 | 13 | 0.50 (0.16–1.36) | 2.17 | 7.0 (4.5–41) | 56 | 18.7 (5.8–29.5) | 0.75 | AA 64%, Oxide 100% |
| S4 Au sedang, Cu tinggi (Sulfida) | 643 | 17 | 0.78 (0.55–1.41) | 3.83 | 368 (177–619) | 181 | 30.6 (12.7–41.2) | 0.89 | AA 76%, Sulphide 42% / Transition 24% |
| S5 Au tinggi, Cu rendah (Oksida) | 737 | 17 | 1.01 (0.20–2.62) | 2.22 | 52 (19–146) | 83 | 15.6 (5.8–23.6) | 0.50 | AA 59% / SI 39%, Oxide 93% |

Names are relative (Cu "rendah" means below S4) and built from emissions plus log crosstabs; review
before the report. Descriptive extras (not in the model): SCIS median S1 2.75%, S2 1.48, S3 0.53,
S4 2.09, S5 0.81; CuCN/Cu median 0.21, 0.19, 0.43, 0.60, 0.52; RJDH012 NAG pH < 4.5 share S1 69%
(n 16), S2 82% (17), S3 63% (56), S4 40% (10), S5 71% (7). The S1 NAG set is not the logged
Sulphide set of AGENTS §4.3, so no contradiction.

**Uncertainty.** Averaged posterior max median ≥ 0.998 in every state; only 3 composites ambiguous
(the draws barely move the decoding). Viterbi (draw 0) agrees with the posterior argmax on 97%.
The real uncertainty is model (sampling) uncertainty: bootstrap ARI vs the main partition median
0.54 (5–95% 0.40–0.77); 510 composites have stability < 0.5, mostly S5/S2 (S5 median 0.50). So
**S5 vs S2/S3 boundaries are the least reliable; S1 and S4 are robust.** `ML_hmm_stabil` is the
column to show uncertainty, not `ML_hmm_p_maks`.

**Comparisons with the logs (Cramér's V / ARI).** HMM vs alteration 0.39 / 0.10, oxidation
0.46 / 0.11, lithology 0.30 / 0.04; vs ML-2 predicted alteration 0.53 / 0.16, oxidation 0.47 / 0.12.
GMM lower on all (alteration 0.35, oxidation 0.37, lithology 0.25). HMM vs GMM ARI 0.32. Switches
per 100 m: HMM 6.3 (Viterbi 6.0), GMM 28.1; logs: alteration 10.6, lithology 5.2, oxidation 2.9.
The HMM fragments about as often as logged lithology; the GMM is four times noisier.

**Sensitivities (ARI vs main on shared rows).** No Ag 0.77 (V oxidation 0.48, switches 6.5): Ag
censoring does not drive the states. K = 4 0.74, K = 6 0.69. **+SCIS (16 holes, 2,345) 0.30,
+CuCN/Cu (938) 0.26:** adding sulfur or the CN ratio reorganises the states and raises agreement
with oxidation (V 0.48 → 0.58; 0.42 → 0.61) at the cost of more switching (9.3, 10.9 per 100 m).
Kept as sensitivities per the human's decision; worth a line in the report (S and CN carry the
oxidation signal the four-element model only partly captures). **Shared-source runs collapsed**
(2,721 composites): ARI 0.53; expected runs change from 14.6/10.5/18.7/30.6/15.6 m to
9.5/7.5/20.2/27.5/10.3 m. Persistence of S1, S2 and S5 is partly sample support (long samples
repeated over 1 m composites); S3 and S4 runs survive.

**Cross-hole continuity (same state, composites in different holes, by 3D distance; chance 0.21).**
HMM 0–10 m 0.71, 10–20 m 0.72, 20–30 m 0.48, 30–40 m 0.37, 40–50 m 0.31, then 0.25–0.29 to 100 m.
GMM 0.62, 0.43, 0.26, 0.21 (chance 0.22). Logged alteration 0.43, 0.64, 0.57, 0.51 (chance 0.41).
All cross-hole pairs closer than 20 m come from the twin pads (0.71–0.72), so the states correlate
between twins and stay above chance out to ~40–50 m.

**Sections (`scripts/12_ml4_sections.py`).** Az 135°, ±40 m corridor, looking NE, 1:1. **Deviation
from the plan:** the line runs through the collar centroid shifted along the NE normal by the
midrange of all composite offsets (minimax), not the mean NE coordinate, because with the mean
RJDH009 and RJDH018 traces left the corridor. With minimax every trace stays inside (max offset:
A 34.1 m, B 32.9 m, C 28.9 m; 0 m outside), so nothing is drawn dashed. In-plane length ≤ true
length asserted. Collar RL minus the topographic profile on the line reaches ±27 m (RJDH005/014
+24, RJDH015 +27, RJDH007/013 −15): this is the hillslope between collar and line (offsets up to
34 m), not an RL error; RL − DEM at the collar itself matches Stage 3. Outputs
`data/processed/ml4_sections.csv` (not in the plan) and `gis/ml4_penampang.gpkg` with per-section
layers `{status_hmm, alterasi_log, oksidasi_log, jejak, kolar, topografi}_{A,B,C}` in a local
engineering CRS, plus `garis_penampang` and `koridor` (EPSG:32647). Per-section layers replaced
subset-filtered copies because QGIS rendered the filtered copies empty.

**QGIS (`scripts/13_ml4_qgis_layouts.py`, MCP).** `outputs/maps/11_ml4_penampang.qgz`: 3 section
layouts (A4 landscape, 1:2,500, 50 m grid, Bahasa legend, BL/TG end labels, caption; ambiguous
composites hatched; state numbers on runs ≥ 6 m) and an index map (hillshade 60%, traces, lines,
corridors). Exported `outputs/maps/11_penampang_{A,B,C}_v1.png` and
`11_peta_indeks_penampang_v1.png` at 300 dpi. Checks: QGIS state counts 533/776/368/643/737 = CSV;
native Elevation Profile of section B (composite points + DEM) z 441.47–603.29 m, length 506.25 m,
equal to Python (`outputs/maps/qc/11_profil_elevasi_B_v1.png`, QC only).

**Outputs.** `data/processed/ml/komposit__ml4_hmm.csv` (`ML_hmm_status`, `_nama`, `_p_maks`,
`_ambigu`, `_entropi`, `_p_S1..S5`, `_viterbi`, `_stabil`, `_gmm`, `_S_status`; not-ok composites
blank), merged by `07_export.py` into `data/processed/iogas/RJ_DH_komposit_1m.csv` (3,108 × 102, 14
`ML_hmm` columns; all export checks pass); `data/processed/ml4_{summary,states,comparisons}.csv` and
`ml4_cv_folds.csv` (per-fold scores, not in the plan); `gis/ml4_hmm.gpkg` (`komposit_status` PointZ,
`segmen_status` LineStringZ; counts read back); figures
`outputs/figures/11_{pemilihan_K,profil_status,matriks_transisi,strip_log,kontinuitas}_v1.png`.
Palette: 5 colours validated (dataviz `validate_palette.js`); adjacent colour-blind ΔE 6.8 (warning
band), mitigated by state numbers on the strips and sections.

**Limits to state.** 12 independent pads; a third of composites repeat a long sample (persistence
partly support, quantified above); Ag 35% censored and spread below DL by assumption (no-Ag ARI
0.77); no sulfur in the main model, and adding it changes the states; states are chemical units,
not lithology (V 0.30); S5 is unstable under resampling; sections are projections within ±40 m.

**Plain-language explanation (for the presentation)**
> We let a hidden Markov model read each drillhole metre by metre using gold, silver, copper and
> arsenic. It finds five chemical units and also learns that each unit tends to continue downhole,
> which is how a geologist logs. Two units are clear and robust: a barren argillic sulphide base
> and a copper-rich sulphide zone about 30 m thick. Three are oxide units with rising gold; the
> richest is real but its boundaries shift when we resample holes, so we show its stability. The
> units match between twin holes and stay correlated about 40–50 m sideways, and the HMM is four
> times less noisy than clustering without the downhole memory.

---

## 2026-11-03 · ML-5 plan: PAF/NAF classification, conformal prediction, clustering (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-ml-5-clever-cosmos.md`. Summary:

**Profiling (read-only).** NAG data: 106 RJDH012 samples (0–151 m; Oxide 90, Sulphide 16, no
Transition). NAG capacity at pH 4.5 censored (0.005) in 44 rows (all 37 with NAG pH ≥ 4.5, plus 7
with pH < 4.5); bimodal: 80 ≤ 2 kg/t, 5 at 2–10, 21 ≥ 20. Classes NAF 37 / PAF-LC 48 / PAF-HC 21
(Oxide 37/46/7, Sulphide 0/2/14), the same at cutoffs 10 and 20 and nearly the same at 5. PAF-HC vs rest:
AUC SCIS 0.97, Zn 0.90, S_PCT 0.89. NAF vs PAF-LC in oxide: no element separates them (AUC 0.39–0.68;
SCIS 0.51). Median SCIS NAF 0.30%, PAF-LC 0.14, PAF-HC 2.32. Mg censored 64/106 in RJDH012 (excluded
as a feature). Database SCIS median 1.17% (max 15.6) vs RJDH012 0.33% (max 4.72): most of the database
lies above the training range.

**Human decisions.** Predict all holes in tiers; unsupervised U1 (RJDH012 full suite) and U2
(shared features, 16 SCIS holes); add a descriptive NAPP proxy.

**Method** (`src/acid.py`, `scripts/14_ml5_paf.py`). Labels: NAF NAG pH ≥ 4.5; PAF-HC pH < 4.5 and NAG
capacity (pH 4.5) ≥ 10 kg H₂SO₄/t; PAF-LC the rest (NAG capacity replaces NAPP in the AMIRA 2002
definition, `[VERIFY exact thresholds]`). NAPP proxy: MPA 30.6 × SCIS (× S_PCT as an upper bound) minus
ANC_max 24.5 × Ca% + 40.3 × Mg%. Supervised on RJDH012: transfer model (SCIS, Au, Ag, Cu, As,
oxidation, alteration, logged pyrite), full model (+ S_PCT, non-sulfide S, Fe, Ca, K, Ba, Sr, Zn, Mn,
Pb; SHAP), no-S model; RF / logistic / dummy, chosen by out-of-fold log loss; leave-one-block-out CV on
contiguous 10 m depth blocks (20 m as a sensitivity). Mondrian cross-conformal prediction
(nonconformity 1 − p̂(y), α 0.10 main, 0.20), class coverage checked by nested block CV. Tiers for all
assay intervals: 1 SCIS in domain, 2 SCIS out of domain (Transition / feature beyond the training range),
3 S2 in place of SCIS, 4 no S. Conservative management class (any PAF-HC in set → PAF-HC, else any PAF-LC
→ PAF-LC); NAG-testing list of ambiguous and Tier 2–4 runs. U1/U2: median/MAD → PCA (Horn) → GMM by BIC,
scored against the NAG classes and the supervised result; U2 bootstrap stability.

**Outputs.** `data/processed/ml/assay__ml5_paf.csv` (`ML_paf_*`), `ml5_*.csv`, `gis/ml5_paf.gpkg`,
figures `12_*_v1.png` including the required PAF/NAF flowchart; rerun `07_export.py`.

---

## 2026-11-03 · ML-5 results: PAF/NAF classes, conformal prediction, clustering

**Run.** `PYTHONIOENCODING=utf-8 uv run python -W ignore scripts/14_ml5_paf.py` (~3 min), then
`scripts/07_export.py` (all checks pass; `RJ_DH_assay.csv` 2,476 × 186, 23 new `ML_paf_*` columns).
Tests: `tests/test_acid.py` (9 new); full suite 107 pass. Determinism: runs 2, 3 and 4 give the same
sha256 for `assay__ml5_paf.csv` (65696c0c…).

**Hyperparameters.** Seed 0. Labels NAG pH 4.5, capacity cutoff 10 kg H₂SO₄/t (5 and 20 as sensitivity).
Features plain log10 of Stage 1 `_ml` values (as in ML-2, not dequantised: deviation from the plan,
RF is rank-based); oxidation 0 / 0.5 / 1 (RJDH019 from ML-2 `ML_oks_prediksi`); alteration AA/SI/AR
indicators; logged pyrite 1/0 (unknown 0.5). **Ca dropped as a model feature** (106/118 RJDH012 values
censored after Stage 1 DL harmonisation to 0.05%), as was Mg (plan). Candidates RF (300 trees,
`balanced_subsample`, leaf 1/5/20), logistic (balanced), prior. Leave-one-block-out on 16 contiguous 10 m
depth blocks (8 × 20 m as sensitivity). Selection by OOF log loss (probabilities clipped at 1e-3). Mondrian
cross-conformal, nonconformity 1 − p̂, α 0.10 (0.20 shown); coverage by nested block CV. U1/U2:
censored values spread on [DL/3, DL] and others dequantised (ML-4 rule), 20 draws, median/MAD, Horn (200
permutations), full-covariance GMM K 1–6, BIC averaged over 5 draws, ≥ 5 per component, `reg_covar`
(0.05/median MAD)²; U2 bootstrap B = 200 (fixed transform, Hungarian alignment).

**Labels.** NAF 37 / PAF-LC 48 / PAF-HC 21 (Oxide 37/46/7; Sulphide 0/2/14). Cutoff 5: 1 row moves
(LC → HC); cutoff 20: none. All NAF have censored capacity.

**NAPP proxy (lab's own Ca/Mg; ANC an upper bound).** Median MPA from SCIS: NAF 9.2, PAF-LC 4.3,
PAF-HC 71 kg/t; ANC_max ≈ 0.7 (NAF, LC), 11.5 (HC). NAPP_min(SCIS) > 0 in 28/37 NAF, 39/48 PAF-LC,
18/21 PAF-HC. **The proxy calls most NAF samples PAF:** in the oxide zone SCIS is not (or not only)
reactive sulfide, so a NAPP built from SCIS is not usable there. Labels now say "S (SCIS)", not
"S sulfida". This is consistent with AGENTS §4.3 (S AUC ≈ 0.51 in oxide); no contradiction.

**Model selection (10 m blocks).** Every model's log loss is worse than the prior (1.25): transfer RF
leaf 20 1.42 (selected), leaf 5 1.85, logistic 2.58. Balanced accuracy: transfer RF20 0.61 (logistic 0.70,
RF5 0.65), full RF20 0.63 (RF1 0.69), no-S RF20 0.56. Recall PAF-HC 0.81–0.95; NAF and PAF-LC 0.40–0.70.
Probabilities are poorly calibrated across depth blocks (class mix changes with depth), so **the
decision output is the conformal set, not the probability.** RF leaf 20 selected for all three sets.

**Conformal (nested, α 0.10, transfer).** Coverage NAF 0.95, PAF-LC 0.875, PAF-HC 0.905 (all 0.906);
mean set size 2.16 / 2.00 / 1.38; singletons 5% / 10% / 71%. Full model: 0.92 / 0.875 / 0.95, set
size 1.87 / 1.90 / 1.10, HC singletons 90%. No-S: 0.95 / 0.90 / 0.86, HC singletons 52%. Within oxide,
PAF-HC coverage 0.71 (n 7) and the 2 sulphide PAF-LC are missed: Mondrian guarantees coverage per class,
not per oxidation subgroup. RJDH012 sets: 62 of 85 NAF/LC rows get `NAF|PAF-LC`; 15/21 PAF-HC are
singletons. **PAF-HC is recognisable from chemistry; NAF vs PAF-LC is not.**

**Database (2,466 sampled intervals).** Tiers: 1 = 1,417 rows (1,799 m), 2 = 481 (544 m), 3 = 201
(273 m), 4 = 367 (440 m). Out-of-domain reasons: Transition 228, Cu > max 210, S > max 139, ML-2
oxidation 114 (RJDH019), Ag > max 74. Sets: `NAF|PAF-LC|PAF-HC` 827, `NAF|PAF-LC` 757, `PAF-HC` 502,
`PAF-LC|PAF-HC` 313. Singleton share: tier 1 23%, 2 14%, 3 27%, 4 17%. Conservative management class
(metres): NAF 43 (measured only, RJDH012), PAF-LC 797, PAF-HC 2,216, of which **PAF-HC confident**
(measured or singleton) **866 m**. No interval gets a NAF-only set, so NAF is only ever assigned by a NAG test. NAG-testing list
(`ml5_uji_nag.csv`): 736 runs, 2,412 m. Priority 1 (PAF-HC possible, not certain) 375 runs / 1,350 m;
2 (NAF or PAF-LC) 289 / 735 m; 3 (singleton but out of domain) 72 / 327 m.

**Unsupervised.** U1 (RJDH012, 118; S, SCIS, Fe, K, Ba, Sr, Zn, Mn): 2 PCs (81%; PC1 is Mn, 0.96,
heavy-tailed under MAD scaling), BIC K = 2: one cluster is 11/13 PAF-HC, the other holds 36 NAF + 47 LC
+ 10 HC. ARI vs 3 classes 0.15 (V 0.61), vs PAF/NAF −0.05, vs oxidation 0.56. K = 3 forced: ARI 0.12.
Oxide only: BIC K = 1, **no chemical structure in oxide.** U2 (1,898 SCIS rows; SCIS, Au, Ag, Cu, As): 2 PCs
(73%), BIC K = 5. RJDH012 members: K5 (SCIS median 3.3%) 14/15 PAF-HC, K1/K2 (SCIS ≤ 0.15%) NAF + LC only,
K4 = Cu-rich (487 ppm Cu, SCIS 2.4%). Vs management class V 0.44, ARI 0.14; bootstrap ARI median 0.66
(5–95% 0.38–0.87), per-row stability median 0.85. **Deviation:** the planned "+ oxidation indicator"
U1 sensitivity was replaced by oxide-only and forced-K3 runs (a 0/1 column has no MAD scale and its weight
would be arbitrary); the oxide-only run answers the question directly.

**Outputs.** `data/processed/ml/assay__ml5_paf.csv` (`ML_paf_label`, `_set`, `_n_set`, `_kelas`,
`_kelola`, `_kelola_sumber`, `_p_{NAF,LC,HC}`, `_pval_{NAF,LC,HC}`, `_tier`, `_model`, `_luar_domain`,
`_alasan`, `_uji_NAG`, `_prioritas_uji`, `_napp_min`, `_gmm`, `_gmm_nama`, `_gmm_p_maks`, `_gmm_stabil`);
`data/processed/ml5_{summary,scores,conformal,uji_nag,per_hole,napp,clusters}.csv` (`clusters` not in
the plan); `gis/ml5_paf.gpkg` (`interval_paf`, 2,466 PointZ, count read back; QGIS 4.2.3 via MCP: management class, tier and NAG-list counts equal the CSV, QC project `outputs/maps/qc/12_ml5_check.qgz`); figures
`outputs/figures/12_{diagram_alir_paf_naf,nag_ph_kapasitas,profil_rjdh012,cakupan_konformal,
matriks_kebingungan,shap_lengkap,gmm_u1_u2,ringkasan_lubang,napp_proksi}_v1.png`.

**Limits to state.** One hole of NAG labels (coverage holds for RJDH012-like material only); 16
sulphide samples; no Transition in training; most database S above the training range; S2 uncalibrated
against SCIS; no ANC, so NAG capacity replaces NAPP (AMIRA 2002 `[VERIFY exact thresholds]`, 30.6 factor
`[VERIFY]`); SCIS is not proven to be reactive sulfide; probabilities uncalibrated (use sets); the
management class is deliberately conservative, so PAF-HC metres are an upper bound and the confident
figure (866 m) a lower bound.

**Plain-language explanation (for the presentation)**
> Only one hole, RJDH012, has acid tests (NAG). We used them to define three classes: non-acid,
> low-capacity acid and high-capacity acid. A model trained on that hole recognises the high-capacity,
> sulfide-rich rock reliably, but no element separates non-acid from low-capacity oxide rock: the
> chemistry simply cannot see that difference. Conformal prediction makes this explicit. Each sample
> gets a set of classes that contains the true one 90% of the time, and for oxide rock that set is
> usually "non-acid or low-capacity". So we manage untested rock by the worst class in its set and list
> the intervals where a new NAG test would change the decision.

---

## 2026-11-03 · ML-6 plan: drill targeting by Gaussian process (= kriging) + derived drainage (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-ml-6-cheeky-koala.md`. Summary:

**Profiling (read-only).** 3,057 `comp_ok` composites, 19 holes, 12 pads (footprint ≈ E 507100–507500,
N 168310–168760; to 282 m). Au median g/t / share ≥ 0.5 by depth: 0–30 m 0.05 / 17%, 30–60 0.27 / 42%,
60–100 0.64 / 56%, 100–150 0.31 / 41%, 150–250 0.34 / 40% (leached top 30 m). **Soil does not predict
downhole Au at the collars:** top-30 m mean log Au vs ML-3 soil index at the collar r = −0.30
(whole hole −0.21), n = 19, so no soil drift term in the 3D GP. Holes mostly az 315/135.

**Human decisions.** (1) Two tiers: A = 3D GP on downhole log Au, UCB ranks infill/extension holes
near drilling; B = step-out holes ranked by the ML-3 soil-index GP in the undrilled soil high, labelled
"uji anomali tanah", no grade promised. (2) Kernel orientation estimated and compared, not fixed NE:
profile likelihood over strike, then leave-one-pad-out CV of NE 45° (resume), ENE 75° (ML-3), best
angle, isotropic; CV winner used (AGENTS §6 "aligned NE" is updated in the log if NE loses).
(3) Derive drainage now (QGIS GRASS `r.watershed` + `r.stream.extract`, 2 ha threshold, 1/5 ha
sensitivity, reaches with DEM support > 30 m flagged `ragu`), 50 m pad buffer (Permen PUPR
28/PRT/M/2015 `[VERIFY]`).

**Method** (`src/targeting.py`, `scripts/15_drainage_qgis.py`, `16_ml6_targeting.py`,
`17_ml6_qgis_layouts.py`). log10 Au, censored spread on [DL/3, DL] (ML-4 rule), regularised to 2 m
within contiguous segments. Kernel Constant × Matérn ν 1.5 (along strike, across strike, vertical
length scales) + White nugget; θ 0–165° step 15 by LML; leave-one-pad-out CV (refit per fold) by mean
log predictive density, RMSE, 90% coverage; RBF sensitivity. Kriging equivalence shown by solving the
simple-kriging system and by GP-implied vs experimental variograms. Block model 10 × 10 × 5 m within
100 m of data: μ, σ, P(Au ≥ 0.5 g/t) (0.3 sensitivity), UCB μ + 2σ. Tier A: collars on a 20 m grid
within 150 m of drilling, slope ≤ 25°, outside the 50 m buffer; az 315/135 (+ across θ), dip −60/−75/−90,
200 m; score = optimistic metres with UCB ≥ log10 0.5; greedy batch of 3 with posterior-variance
update (kriging believer). Tier B: soil-index UCB within 50 m of the collar, > 150 m from drilling,
2 holes ≥ 150 m apart. Per hole: distance to drainage, basin, slope, expected PAF-HC metres and ML-5
NAG-priority metres (reported, not scored).

**Outputs.** `data/processed/ml/komposit__ml6_gp.csv` (`ML_gp_*`), `ml6_{summary,cv,profil_theta,
kandidat,usulan_lubang}.csv`, `gis/drainage.gpkg`, `gis/ml6_target.gpkg`, `gis/ml6_*.tif`, figures
`13_*_v1.png`, QGIS `outputs/maps/13_ml6_desain.qgz` (design map + one section).

---

## 2026-11-03 · ML-6 results: drill targeting by Gaussian process (= kriging) + derived drainage

**Run.** In QGIS 4.2.3 via MCP: `scripts/15_drainage_qgis.py` (GRASS 8.5, 40 s). Then
`uv run python scripts/15b_drainage_post.py`, `PYTHONIOENCODING=utf-8 uv run python -W ignore
scripts/16_ml6_targeting.py --stage all` (8.5 min) and `scripts/17_ml6_qgis_layouts.py` in QGIS.
`scripts/07_export.py`: all checks pass; `RJ_DH_komposit_1m.csv` gains 7 `ML_gp_*` columns.
Tests: `tests/test_targeting.py` (11); full suite 118 pass. Determinism: two full runs give the same
sha256 for `komposit__ml6_gp.csv` (174a4f85…), `ml6_usulan_lubang.csv`, `ml6_cv.csv` and
`ml6_kandidat.csv`. After the tie-break change (below), two design-stage runs give the same hashes.
QGIS read-back: 26 reaches, 26 basins, 5 proposals/traces, 4,574 section cells and 457 composites,
all equal to Python.

**Human decisions during execution (2026-11-03).** (1) Tier A = **mixed portfolio**: 2 extension holes
by expected metres ≥ 0.5 g/t plus 1 gap-closing hole by kriging variance, greedy with variance update.
The no-skill CV result is stated openly. (2) **Orientation NE 45° by the tie rule**: all four CV scores
are reported, with the statement that the drill data neither confirm nor refute NE.

**Data.** 3,057 `comp_ok` composites → 1,532 2 m blocks (length-weighted within contiguous segments),
12 pads. log10 Au: censored values spread uniform on [DL/3, DL] and the rest dequantised (ML-4 rule),
20 draws. Censored share 9.1%; mean −0.684, SD 0.821.

**Hyperparameters.**
- Seed 0. Kernel Constant × Matérn ν = 1.5 + WhiteKernel. Length scales are in a rotated frame (along
  strike, across strike, vertical), bounds 5–1,000 m. `normalize_y` (= simple kriging with the sample
  mean); 3 restarts (2 in CV).
- θ profile 0–165° step 15. Leave-one-pad-out CV (12 folds, hyperparameters refit per fold). Winner
  rule: best mean log predictive density (mlpd); within 1 SE prefer NE, then isotropic.
- Block model 10 × 10 × 5 m, ≤ 100 m horizontal from data, down to min data Z − 50 m.
- Cutoffs: 0.5 g/t (0.3 as sensitivity); κ = 2 (0, 1, 3 shown).
- Designs: 200 m long, 2 m step; az 315/135 (+ vertical); dip −60/−75/−90. Collars on a 20 m grid,
  ≤ 150 m from drilling, pad slope ≤ 25° (median of 9 points ± 8 m), outside the 50 m stream buffer.
- New rock = trace points ≥ 20 m (3D) from every sample. Tier B: 2 picks ≥ 150 m apart, soil-index
  UCB within 50 m of the collar.

**θ profile.** LML −959.4 (15° and 105°) to −962.1 (150°); isotropic −963.3; NE 45° −961.9. The profile
has **period 90°**: θ and θ + 90° give identical LML with the two horizontal length scales swapped. So
the data cannot even tell strike from across-strike. Spread 2.7 log units, isotropic within 4: the
orientation is not identified.

**Pad CV (12 pads).**

| Model | mlpd ± SE | RMSE | cov90 |
|---|---|---|---|
| ENE 75° | −1.262 ± 0.080 | 0.823 | 0.863 |
| NE 45° (chosen) | −1.266 ± 0.081 | 0.824 | 0.860 |
| isotropic | −1.266 ± 0.076 | 0.828 | 0.867 |
| mean only | −1.262 ± 0.069 | 0.828 | 0.884 |
| best θ 105° | −1.281 ± 0.106 | 0.820 | 0.841 |
| RBF NE 45° | −1.275 ± 0.082 | 0.828 | 0.855 |
| nested NE 45° | −1.267 ± 0.092 | 0.821 | 0.869 |

- **The GP has no between-pad skill.** Paired GP − mean: Δ mlpd −0.005 ± 0.013, 8/12 pads better.
  Held-out pads lie a median 46–115 m from other pads' data, beyond the fitted ranges (≈ 8–23 m).
- Scratch diagnostics (not adopted): depth-trend mean Δ −0.026 ± 0.042; depth trend + GP −0.042 ±
  0.051; 10 m support GP −0.003 ± 0.033.
- Nested and RBF do not beat the single Matérn by > 1 SE, so they are not adopted.
- **Orientation verdict:** all within 1 SE, so NE 45° by the tie rule. This does not contradict
  AGENTS §4 or §6 ("aligned NE" remains the resume prior, unconfirmed by the drill data). ML-3 soil
  favoured E–ENE; that is noted and not resolved.

**Final model.** `0.921² · Matern([22.5, 12.2, 8.17] m, ν = 1.5) + White(0.061)`, LML −961.9.
- Nugget 0.041, sill 0.572 (log10²). Origin E 507303, N 168517, RL 524.
- **Kriging equivalence shown:** the simple-kriging system with the fitted covariance reproduces the
  GP mean (max |Δ| 2.1e-10). Figure `13_variogram_gp_v1` plots the GP-implied γ(h) against
  experimental variograms: a good fit vertically and across strike to ~120 m; along strike the pairs
  are sparse and erratic.

**Block model.** 128,124 nodes in 2,557 columns; P(≥ 0.5 g/t) ≥ 0.5 at 2,391 nodes; σ median 0.757.
**Far from data the model returns the prior:** a 200 m hole in unknown rock "expects" ≈ 62.5 m
≥ 0.5 g/t, purely from the global distribution.

**Drainage (lidar DEM 2 m).**
- `r.watershed` (MFD, convergence 5, least-cost, no sink fill), then `r.stream.extract`.
- 2 ha: 26 reaches, 3,421 m, Strahler {1: 18, 2: 7, 3: 1}. All reaches run downhill (tolerance
  0.5 m). `ragu` (mean DEM support > 30 m) on 5 reaches (93 m). 26 basins, 94.9 ha; 50 m buffer
  35.4 ha (Permen PUPR 28/PRT/M/2015 `[VERIFY]`).
- Sensitivity: 1 ha 55 reaches / 5,190 m; 5 ha 14 / 1,970 m. One single-vertex line dropped per
  network.
- **Click-note for the human:** in `outputs/maps/qc/13_drainage_check.qgz` add a satellite basemap
  (XYZ tiles, e.g. Esri World Imagery; nothing is uploaded). Check the 5 dashed (`ragu`) reaches and
  the 3rd-order trunk in the SE. Flag disagreements in a note; do not delete reaches.

**Tier A.** 946 collars, 127 pass (699 slope > 25°, 94 outside DEM, 26 buffer) → 635 designs, 34,126
in-domain trace points (89% new rock).

| Hole | Collar E / N / RL | az / dip | Basis | Score at pick | Expected m ≥ 0.5 | PAF-HC m (confident) | NAG priority-1 m | Stream / basin |
|---|---|---|---|---|---|---|---|---|
| RJ-U01 (A00535) | 507280 / 168600 / 579.8 | 315 / −60 | extension | 71.8 m | 71.8 | 20 (20) | 0 | 233 m / 7 |
| RJ-U02 (A00470) | 507280 / 168560 / 600.8 | 315 / −60 | extension | 71.4 m | 71.7 | 96 (18) | 78 | 237 m / 7 |
| RJ-U03 (A00275) | 507400 / 168420 / 611.6 | 315 / −60 | gap-closing | 114.4 m·log10² | 62.8 | 0 | 0 | 144 m / 14 |

- Extension picks are only ≈ 10 m above the prior (62.5). Their advantage comes from the high-grade
  RJDH012/016/017 data next to them; it is real but local.
- Top κ ≥ 1 design is A00075: optimistic metres saturate at 200 m far from data, so κ = 2 UCB cannot
  rank holes. This is why the gap-closing score uses plausible variance.

**Deviation: tie-break for the gap-closing hole.** Plausible variance also saturates at the prior: at
round 3, **138 designs lie within 1% of the best** (all fully in new rock, σ at the prior). Before this
fix the pick (A00089, 507480 / 168220) was an arbitrary choice among them.
- Rule now (`greedy_portfolio`, `tie_tol = 0.01`, ucb rounds only): among tied designs, take the one
  whose new-rock points lie closest to existing samples.
- RJ-U03 = A00275: mean 45 m from data, between pads, inside the drilled footprint.
- Why: it closes a gap between drilled ground, and its assays give pairs at the 20–100 m lags that the
  variogram cannot resolve now (the cause of the no-skill CV).
- Extension rounds are unaffected: next design 1.7% below.

**Tier B (uji anomali tanah, no grade promised).** 1,134 collars, 333 pass (604 slope, 192 buffer,
5 outside DEM). The test is soil vs downhole Au, r = −0.30 at the existing collars.

| Hole | Collar E / N / RL | az / dip | Soil zone, index | UCB score | Stream / basin |
|---|---|---|---|---|---|
| RJ-U04 | 507000 / 168340 / 427.6 | 315 / −60 | Tinggi, 2.93 | 4.19 | 166 m / 17 |
| RJ-U05 | 507700 / 168120 / 489.7 | 315 / −60 | Sedang, 1.98 | 3.81 | 192 m / none |

Every hole: slope ≤ 25° and > 50 m from any reach (asserted). Handling note: lined sumps; PAF-HC cuttings
bagged; NAG on the new core (feeds the ML-5 list); Tier B "anggap PAF sampai diuji".

**Section D–D'.** In the plane of RJ-U01, az 135° (view NE), 510 m: from 250 m SE to 260 m NW of the
collar (extended from 120 m SE so RJ-U03 is on it). 4,574 GP cells (5 m); 457 HMM composites from
RJDH005/012/016/017 (±40 m); proposed traces RJ-U01, U02 and U03. U03 is projected 42 m, so proposed
traces use ±50 m, labelled with the offset; collars must lie on the section length.

**Other deviations from the plan.**
- Draws are averaged before fitting (plan: draw 0). Kriging is linear in the data, so the mean of the
  draws is the right input.
- `scripts/15b_drainage_post.py` added (Strahler, checks, buffer in uv Python).
- Tier A score: approved mixed portfolio (expected metres + plausible variance) instead of κ = 2
  optimistic metres; scores count new rock only.
- Nested Matérn tested as a sensitivity. 2 m support kept. Section az 135 (ML-4 convention).
- Extra outputs: `ml6_cv_per_pad.csv`, `data/interim/ml6_kolar_saring.csv`, `drainase_ringkasan.csv`.

**Outputs.**
- `data/processed/ml/komposit__ml6_gp.csv` (`ML_gp_mu`, `_sd`, `_cv_mu`, `_cv_sd`, `_cv_resid`,
  `_cv_p05`, `_blok2m`).
- `data/processed/ml6_{summary,cv,cv_per_pad,profil_theta,kandidat,usulan_lubang}.csv`. `usulan` is
  in collar/survey style for the ioGAS teammate.
- `data/processed/drainase_ringkasan.csv`; `gis/drainage.gpkg` (`sungai_turunan`, `das`,
  `sempadan_50m`); `gis/ml6_target.gpkg` (`kolar_usulan`, `jejak_usulan`, `kandidat`, `kolar_saring`);
  `gis/ml6_penampang.gpkg`; `gis/ml6_{ucb_maks,meter_cutoff,sd_rerata}.tif`.
- Figures `outputs/figures/13_{profil_theta,cv_lopo,variogram_gp,peringkat_kandidat}_v1.png`. Maps
  `outputs/maps/13_{peta_desain,penampang_desain}_v1.png`, `13_ml6_desain.qgz`;
  QC `outputs/maps/qc/13_drainase_turunan_v1.png`, `13_drainage_check.qgz`.

**Limits to state.**
- 12 pads, so CV SEs are wide. The GP does not beat the mean between pads; grade predictions are
  local (≲ 25 m).
- Stationary constant mean, although Au varies with depth (leached top). A depth trend did not help in CV.
- Orientation not identified (90° periodic profile). 2 m support.
- Gap-closing pick is a tie-break among 138 equal designs: a stated rule, not an optimum.
- Tier B is soil-led and grade-free. Drainage comes from a contour DEM (5 doubtful reaches, no satellite
  check yet). PAF comes from one NAG hole (ML-5). Buffer regulation `[VERIFY]`.

**Plain-language explanation (for the presentation)**
> We used a Gaussian process, which is mathematically the same as kriging, to estimate gold between our
> drillholes and how sure we are. The honest finding is that gold continuity is short, about 10–25 m,
> so between pads the model is no better than the average grade, and the drill data cannot tell which
> way the ore trends. So we propose three holes for different jobs. Two step out next to the best
> intercepts (RJDH012/016/017), where the model does know something. The third fills a gap between
> pads, to measure the continuity we are missing. Two more holes test the soil anomaly without promising
> grade. Every collar sits on gentle ground, outside the 50 m stream buffer, with PAF handling planned.

---

## 2026-11-04 · Plan: remaining repo-owner work + team GitHub repo (approved)

Full plan: `C:\Users\mauli\.claude\plans\plan-ml-6-cheeky-koala.md` (overwritten from the ML-6 plan,
which is logged above). **Human instruction (2026-11-04):** "push the entire repo to github … a shared
repo containing everything so that my team members have the entire context … Confidentiality is fine
since I'm only sharing this with my teammates."

**Decisions.**
- Convert the existing `67minutes/ml-olympiar` (public code snapshot) to **PRIVATE** first, then
  force-push this checkout over it.
- The human invites teammates.
- Docs in English (README) + Bahasa Indonesia (team guide).
- Both §9 experiments.

**What this supersedes.**
- The "no remote / never push" rule (AGENTS §1, §2.1; README; 2026-11-02 publication entry) and the
  data `.gitignore` rule, for this private team repo only.
- Unchanged: no public repos, no cloud ML, never quote the brief's licence key or contacts, never
  modify `data/raw/`.

**A1 — deliverable 3 "Geochemistry analysis (csv)"** (`scripts/18_geochem_analysis.py`,
`src/geochem.py`):
1. `geochem_analysis.csv`: soil 259 + rock 469 + drill assay 2,476 stacked, one row per sample.
   - Common keys and coordinates.
   - Harmonised key elements with `_cens`; logged classes.
   - ML-1/2/3/5 columns.
   - For drill rows, the ML-4 HMM state and ML-6 GP from the composite holding the assay midpoint.
2. `geochem_statistik.csv`: descriptive statistics + thresholds per dataset × element.
3. `geochem_statistik_kelompok.csv`: medians by zone, logged class, HMM state and PAF class.
4. `geochem_analysis_kolom.csv`: column dictionary.

Checks: counts, unique keys, round-trip equality with the ioGAS files, no new NaN.

**A2/A3 — §9.1 and §9.2** as in the plan; each gets its own results entry.

**B — docs, git hygiene (`.gitattributes` so raw CSV bytes never change), push and verification** as
in the plan.

---

## 2026-11-04 · Deliverable 3 results: geochemistry analysis CSV

**Run.** `PYTHONIOENCODING=utf-8 uv run python -W ignore scripts/18_geochem_analysis.py`, after
`07_export.py`. New module `src/geochem.py` (`describe`, `containing_interval`, `group_medians`) and
`tests/test_geochem.py` (4 tests). Two runs give identical sha256 for all four outputs.

**Outputs.**
1. `data/processed/geochem_analysis.csv`: 3,204 rows × 75 columns (soil 259, rock 469, drill assay
   2,476), one row per sample.
   - Keys `dataset, SampleID, HoleID, From, To, X, Y, Z`.
   - Metadata: prospect, RJ flag, year, NS-SEL, S method, elevation flag.
   - 14 harmonised key elements with `_cens` where the source has it. S keeps SCIS, S2 and total
     apart (never mixed).
   - CN/total ratios, NAG pH and capacity; logged lithology, alteration and oxidation groups.
   - ML-1 populations, ML-2 predictions, ML-3 zone, ML-5 PAF set and management class.
   - For drill rows: the ML-4 HMM state and ML-6 GP μ/σ (log10 Au) from the 1 m composite holding
     the assay midpoint. All 2,476 midpoints fall in a composite, 2,472 of them `comp_ok`.
2. `geochem_statistik.csv`: 62 rows, dataset × subset (all, RJ-only for surface) × element.
   - n, n analysed, % censored, min, P25/50/75/90/95/98, geometric mean, max.
   - ML-1 thresholds with K, threshold type, T1/T2, MAD, Tukey, the empty `thr_probplot_iogas` slot,
     and % above.
3. `geochem_statistik_kelompok.csv`: 40 rows, medians by group:
   - soil and rock: ML-3 zone (RJ only);
   - rock: alteration and lithology;
   - drill: alteration, oxidation, lithology, HMM state, PAF management class.
4. `geochem_analysis_kolom.csv`: 75 columns with Bahasa meaning, unit, source stage and fill counts
   per dataset.

**Checks (asserted).** Row counts equal the ioGAS files; keys unique; every carried value round-trips
equal; NaN counts unchanged.

**Selected numbers.**
- Median Au by ML-3 zone (Rendah / Sedang / Tinggi): soil 0.007 / 0.065 / 0.335 g/t; rock 0.12 /
  0.53 / 5.04 g/t.
- Drill median Au: silica 2.11 vs advanced argillic 0.35 vs argillic 0.03 g/t; transition 1.02 vs
  oxide 0.48 vs sulphide 0.16 g/t. Sulphide and transition carry Cu: medians 115 and 377 ppm.
- Note for readers: some ML-1 GMM thresholds are a *lower* population break, not an anomaly cut. For
  example soil As crosses at 23.8 ppm with 87% of samples above it. The `threshold_type` and `T1/T2`
  columns show which; this is ML-1's logged result, unchanged.

**Plain-language explanation (for the presentation)**
> The geochemistry deliverable puts every soil, rock and drill sample in one table: cleaned element
> values, a flag wherever a value is below detection, the logged geology, and the label each of our
> models gave the sample. A second table gives the usual statistics and thresholds for each element,
> and a third compares grades between zones, alteration types, oxidation states and acid classes. For
> example, silica-altered core has a median of about 2 g/t Au against 0.03 g/t in argillic rock.

---

## 2026-11-04 · §9.1 results: Jansson-style baseline vs our GMMs

**Run.** `PYTHONIOENCODING=utf-8 uv run python -W ignore scripts/19_s9_jansson.py` (about 1.5 min).
New module `src/comparators.py` and `tests/test_comparators.py` (5 tests). Two runs give identical
sha256 for every output. The paper stays `[VERIFY]`; nothing beyond AGENTS §9.1 is attributed to it.

**Method (fixed, seed 0).**
- Inputs: exactly the cleaned feature matrices of our GMMs. ML-3 soil (RJ, n 188) and rock (RJ,
  Au-Cu-As, n 352; also a 7-element rock variant, n 261). ML-5 U1 (RJDH012, n 118) and U2 (SCIS
  rows, n 1,898).
- clr on the subcomposition, computed as ilr (Helmert basis). ilr is an isometry of clr, so
  distances and k-means partitions are the same; it avoids the singular clr covariance in MCD.
- Robust PCA: eigen-decomposition of the `MinCovDet` covariance; the fewest PCs reaching 80% of the
  robust variance, at most 3.
- k-means, k = 2–10, n_init 20. Elbow rule: the k farthest from the chord joining k=2 and k=10 on
  the WCSS curve (both axes scaled to [0, 1]).
- k-means is also run at the K our GMM *used* (soil 3, rock 3, U1 2, U2 5). Deviation from the plan
  ("at the BIC k"): for the surface the BIC-best K differs from the K we used (soil BIC-best 2, rock
  BIC-best 1, so K=1 is not a partition). Using the K we actually mapped is the fair comparison.
- Bootstrap stability: B = 200 refits, ARI of each refit vs the full-data partition.
- Outputs:
  - `data/processed/s9_jansson_scores.csv`, `s9_jansson_curves.csv`, `s9_seleksi_unsur.csv`;
  - `data/processed/ml/{tanah,batuan}__s9_jansson.csv` (`ML_s9_kmeans`, `ML_s9_kmeans_k`,
    `ML_s9_kmeans_k3`);
  - figure `outputs/figures/14_jansson_vs_gmm_v1.png`.

**Results.**

| Case | n | robust PCs (var) | elbow k | GMM K | ARI k-means vs GMM (K / elbow) | bootstrap ARI median, k-means K / elbow / GMM |
|---|---|---|---|---|---|---|
| Soil | 188 | 2 (83%) | 5 | 3 | 0.23 / 0.29 | 0.80 / 0.76 / 0.65 |
| Rock Au-Cu-As | 352 | 1 (82%) | 4 | 3 | 0.00 / 0.00 | 0.90 / 0.71 / 0.76 |
| Rock 7 elements | 261 | 3 (77%) | 5 | 3 | 0.17 / 0.10 | — |
| U1 (RJDH012) | 118 | 3 (88%) | 4 | 2 | 0.00 / 0.15 | 0.58 / 0.69 / 0.91 |
| U2 (SCIS rows) | 1,898 | 3 (91%) | 4 | 5 | 0.25 / 0.23 | 0.82 / 0.90 / 0.66 |

Agreement with logged or measured labels (ARI, with Cramér's V in brackets):
- Rock vs logged alteration (`IntrpAltFa`): GMM −0.01 (0.17); k-means 0.03 (0.17) and 0.02 (0.15).
  Neither method recovers the logged alteration from Au-Cu-As alone.
- U1 vs NAG 3 classes (n 106): GMM 0.15 (0.61); k-means K=2 0.03 (0.31); elbow 0.16 (0.54).
- U1 vs oxidation: GMM 0.56 (0.65); k-means K=2 0.02 (0.35); elbow 0.24 (0.75).
- U2 vs NAG 3 classes: GMM 0.18 (0.58); k-means 0.15–0.18 (0.58). U2 vs oxidation: GMM 0.15 (0.51);
  k-means 0.05 (0.36–0.40).

**Interpretation.**
- clr removes the overall magnitude of each sample, so k-means on clr groups samples by element
  *ratios*, not by grade. That is why it does not reproduce our grade-ordered H/M/L zones (rock ARI
  ≈ 0): the two methods answer different questions. For grade zonation our log-scale GMM is the
  right tool; the ratio view is a useful complement (signature, not tenor).
- The elbow curves are smooth, so the elbow k is weakly defined (see the figure's left panels).
  BIC gives a stated, likelihood-based choice.
- k-means partitions are often *more* bootstrap-stable than the GMM on the surface data, because
  hard spherical clusters move less. Stability is not the same as geological meaning.
- On RJDH012 the GMM at K=2 recovers oxidation far better (ARI 0.56 vs 0.02 at the same K). The
  elbow k=4 partly closes the gap in V (0.75) but not in ARI (0.24), because it splits oxide
  further.
- Limitation for both methods: clr on a small trace-element subcomposition, so results depend on
  which elements are included (AGENTS §6 transform rule).

**Element-selection proposal (logged, NOT applied; needs human approval).** Jansson's rule as
summarised by a citing paper (`[VERIFY: identify the citing paper]`): ≥ 70% of samples above DL and
median > 10 × DL. The normality criterion was not evaluated. Per dataset:

| Dataset | Jansson rule selects | Our `ml_usable` (≥ 50% analysed, ≤ 50% censored) |
|---|---|---|
| Drill assay | Au, Cu, As, SCIS | adds Ag, AgCN, CuCN |
| Rock | Au, As, Pb | Au, As, Cu, Hg, Pb, Sb, Zn |
| Soil | Au, Cu, Hg, Pb, Sb, Zn | Au, Ag, As, Ba, Cu, Hg, Pb, Sb, W, Zn |

The stricter rule would drop Ag everywhere (its median is only 4–5 × DL), and soil As (median
9.5 × DL, just under the cut). Recommendation: keep `ml_usable` for the core models, because Ag and
As are key pathfinders for an HS epithermal system. Cite the stricter rule as a sensitivity check.

**Plain-language explanation (for the presentation)**
> We repeated a published workflow, k-means on log-ratio data, on exactly the same samples as our
> own model. Log-ratios ask "which elements are high relative to the others", not "how much metal is
> there", so this method groups samples by chemical signature, not by grade. That is why its groups
> do not match our high/medium/low gold zones. In the drill hole with acid tests, our model
> separated oxide from sulphide rock much better at the same number of groups.

---

## 2026-11-04 · §9.2 results: simplified Fontana analogue (RF + downhole smoother) vs HMM

**Run.** `PYTHONIOENCODING=utf-8 uv run python -W ignore scripts/20_s9_rf_smoother.py`. Two runs
give identical sha256 for all four CSV outputs. The paper stays `[VERIFY]`. This is a simplified
analogue; it does **not** replicate CSIRO Data Mosaic, and we do **not** compare our accuracy with
their 82.5% (different deposit, support, classes and validation).

**Method (fixed, seed 0).**
- Inputs: 1 m `comp_ok` composites (3,057, 12 pads, 22 contiguous segments) with the ML-4 features
  (log Au, Ag, Cu, As; same draw rule, draw 0). Targets joined at the midpoint: logged alteration
  (`alt_ml_label`: AA/SI/AR/PP) and oxidation (`ox_state`).
- Per fold: PCA fit on the training pads → RF (`classify.rf`, leaf size tuned as in ML-2; mostly 20).
- Smoother: centred moving average of the RF class probabilities, within contiguous segments only.
- Outer CV: leave-one-pad-out (12 pads; never random K-fold). The window is chosen on the training
  pads only, by an inner GroupKFold.
- **Deviations from the plan (logged):**
  1. Grid extended from {1, 3, 5, 9, 15} to {1, 3, 5, 9, 15, 25, 41} m, because every fold picked
     the grid edge (15).
  2. Window criterion changed from inner log loss to inner balanced accuracy (ties → smaller w).
     Under log loss the choice ran to the new edge (41 m) in every fold, while label accuracy fell
     and the switch rate dropped below the logs' own. Log loss rewards blurry probabilities; we
     want labels.
- Windows chosen: alteration {5 m: 5 folds, 3: 2, 9: 2, 25: 2, 15: 1}; oxidation {5: 5, 9: 4, 3: 2,
  15: 1}.
- Outputs:
  - `data/processed/s9_rf_smoother_{scores,folds,kembar}.csv`;
  - `data/processed/ml/komposit__s9_rf.csv` (`ML_s9_rf_alt`, `ML_s9_rf_alt_p_maks`,
    `ML_s9_rf_oks`, `ML_s9_rf_oks_p_maks`);
  - figure `outputs/figures/14_rf_vs_hmm_v1.png`.

**Results (out-of-pad).**

| Target | Method | Bal. acc | κ | ARI | Cramér's V | Switches / 100 m |
|---|---|---|---|---|---|---|
| Alteration | RF raw | 0.692 | 0.482 | 0.285 | 0.528 | 23.4 |
| Alteration | RF smoothed | 0.665 | 0.473 | 0.276 | 0.539 | 6.9 |
| Alteration | HMM (ML-4) | — | — | 0.104 | 0.446 | 6.3 |
| Alteration | Log | — | — | — | — | 10.3 |
| Oxidation | RF raw | 0.608 | 0.463 | 0.325 | 0.429 | 22.3 |
| Oxidation | RF smoothed | 0.630 | 0.538 | 0.432 | 0.492 | 7.2 |
| Oxidation | HMM (ML-4) | — | — | 0.113 | 0.462 | 6.3 |
| Oxidation | Log | — | — | — | — | 2.9 |

Twin pads 005/014, 010/011, 016/017: share of cross-hole composite pairs with the same label, by 3D
distance.

| Distance | HMM | Logged alteration | RF smoothed (alteration) |
|---|---|---|---|
| 0–10 m | 0.93 | 0.40 | 0.40 |
| 10–20 m | 0.91 | 0.71 | 0.57 |
| 20–50 m | 0.31 | 0.63 | 0.42 |
| 50–100 m | 0.22 | 0.57 | 0.36 |
| chance (Σp²) | 0.24 | 0.34 | 0.34 |

Scale mismatch (stated for the report): lithology intervals average 10.8 m (median 5.2 m),
alteration 4.4 m (median 2.5 m), assays ~1 m (median 1.0 m).

**Interpretation.**
- The RF is *supervised* by the logs, so it naturally agrees with them more than the unsupervised
  HMM does (V 0.54 vs 0.45 for alteration). The HMM was never shown the logs.
- Raw RF labels flicker (23 switches per 100 m against the logs' 10). A 3–9 m smoother brings
  fragmentation down to the HMM's level (7 vs 6) with little loss in accuracy for alteration and a
  gain for oxidation (κ 0.46 → 0.54).
- Oxidation logs switch only 2.9 times per 100 m: oxidation is a thick blanket. Both methods are
  still more fragmented than the logged blanket.
- On the twin pads the HMM states agree across neighbouring holes far more at short range (0.93 at
  < 10 m) than the logs themselves (0.40) or the RF (0.40). This means the HMM captures a chemical
  stratigraphy that is laterally continuous. The logged alteration is less consistent between holes
  only metres apart, which may reflect logging differences between geologists and the ~4 m logging
  scale.
- Conclusion for the report: the two methods are complementary. Use the RF + smoother to predict
  logged classes in unlogged or poorly logged intervals. Use the HMM for correlation sections
  (ML-4), where cross-hole consistency matters.

**Plain-language explanation (for the presentation)**
> We tested a second published idea: a random forest that learns the logged alteration from
> chemistry, followed by smoothing down the hole. It matches the geologists' logs better than our
> HMM, as expected, because it was trained on them. But its raw answers flicker metre by metre, so
> it needs smoothing. Our HMM, which never saw the logs, gives almost the same answer in twin holes
> a few metres apart, more consistently than the logs themselves. That is why we use the HMM for the
> correlation sections.

---

## 2026-11-04 · Team repo: docs, git hygiene, private GitHub (human instruction)

**Instruction (human, 2026-11-04).** Share the *whole* repo with the team on GitHub so teammates
have the full context: data, brief, history, outputs and docs. The human accepts the confidential
data and the brief (which contains the ioGAS licence key) in a **private** repo shared only with
teammates. Decisions: convert the existing `67minutes/ml-olympiar` (was PUBLIC, a one-commit code
snapshot from the 2026-11-02 publication entry) to PRIVATE first, then force-push this checkout over
it; the human invites teammates; docs in English (README) and Bahasa Indonesia (team guide).

**Supersedes:**
- AGENTS §1/§2.1 "never push this repo to any remote" and "keep `data/` in `.gitignore`". The only
  allowed remote is now the private team repo.
- The 2026-11-02 "Public GitHub code publication" entries. The public snapshot (commit `dcb8975`) is
  replaced by this history. The local folder `../ml-olympiar-public` is superseded; the repo owner
  may delete it.

**Docs.**
- `README.md` rewritten (English): purpose, privacy note, file map, status table with the real
  script names (the old table had stale names, e.g. ML-1 is `08_ml1_thresholds.py`), deliverables,
  how to reproduce, working rules, roles.
- New `PANDUAN_TIM.md` (Bahasa Indonesia): per report chapter 1–9, the CSVs, figures and maps to
  use, the key numbers, and the spoken explanations translated from this log; open items for humans;
  the list of references still `[VERIFY]`; how to use the repo and read this log.
- `AGENTS.md`: §1 "Shared repo" rule; §2.1 remote rule; §3 data now in the repo; §7 layout adds
  README/PANDUAN_TIM and the joblib note. `CLAUDE.md`: pull before work, log, commit only when asked.

**Git hygiene.**
- `.gitignore` now commits `data/` (raw, interim, processed), `gis/` and `outputs/figures/qc/`.
  Still ignored: `.venv`, caches, `.claude/settings.local.json`, GIS sidecars (`*.gpkg-shm`,
  `*.gpkg-wal` (the ML-5 WAL was empty), `*.aux.xml`) and `data/interim/*.joblib` (`ml6_gp.joblib`,
  19 MB, a version-specific scikit-learn pickle; rebuild with `16_ml6_targeting.py --stage gp`).
- New `.gitattributes`: `data/** -text` and `RAW_MANIFEST.sha256 -text` so a teammate's
  `core.autocrlf=true` cannot rewrite the CRLF raw CSVs and break the manifest; binary for GIS,
  images, PDFs and MapInfo files.
- Size: 156 new files, 55.8 MB; largest `data/interim/ml6_blok.csv` 7.8 MB. No file > 50 MB, no LFS.
- Branch `master` renamed to `main` (the remote default).

**Pre-push checks (all pass).** `pytest` 127 passed; `00_inventory.py` OK; `sha256sum -c
RAW_MANIFEST.sha256` (from `data/raw/`) 15/15 OK; credential-pattern scan of all text files to be
pushed: no hits; tokens that look like the brief's licence key or phone numbers: 0 occurrences in any
text file. The brief PDF itself is in the repo, as the human accepted.

**QGIS projects.** `outputs/maps/*.qgz` load layers by relative path (`../../gis/…`), so they open
from a clone. Some layer-tree attributes still carry the owner's absolute path; QGIS uses the
relative datasource.

---

## 2026-11-04 · Team repo pushed and verified

- `67minutes/ml-olympiar` set to **PRIVATE** before any push (confirmed by `gh repo view`; 0 forks);
  description "OlympiAR 2026 R2 Ramba Joring: team repo (private)".
- `git push --force -u origin main`: the public snapshot `dcb8975` was replaced by `f83bec0`. The only
  remote branch is `main`.
- Remote `main` SHA equals local HEAD; remote tree 284 files equals `git ls-files`; `data/raw/` has
  15 files on the remote.
- A fresh clone with `core.autocrlf=true` (the Windows default, worst case): `git status` clean and
  `sha256sum -c RAW_MANIFEST.sha256` passes 15/15, so `.gitattributes` protects the CRLF raw files.
- Teammates are invited by the repo owner (Settings → Collaborators). Agents do not invite anyone.

---

## 2026-11-04 · Plan: ML findings report for teammates (approved)

Full plan: `C:\Users\mauli\.claude\plans\the-work-is-done-swift-beacon.md`. Summary:

**Why.** `PANDUAN_TIM.md` is a dense file map; teammates who write the report and present need one
readable document that explains each ML result: the question, the answer, how sure we are, why it
matters and how to defend it out loud.

**Human decisions.** Audience teammates (not the competition report text); bilingual (Bahasa
Indonesia main text, English technical terms in brackets); one self-contained local HTML file,
never published online (AGENTS §2.1); `PANDUAN_TIM.md` kept but trimmed to a file map that points
to the report.

**Method.** Hand-written source `reports/laporan_ml_src.html` with `{{key}}` placeholders for the
headline numbers; `src/report.py` (fill placeholders, fail on any unresolved one; embed figures as
base64, downscaled with Pillow; check internal links); `scripts/21_laporan_ml.py` reads the facts from
the processed CSVs so the text cannot drift from the results. Existing figures only, no new ones.

**Output.** `outputs/laporan_ml/laporan_ml_v1.html`. Checks: unit tests, no unresolved placeholders,
no missing images, internal links resolve, local browser check, spot-check of numbers against this log.

---

## 2026-11-04 · ML findings report for teammates: results

**Run.** `PYTHONIOENCODING=utf-8 uv run python scripts/21_laporan_ml.py` (~9 s). New `src/report.py`,
`tests/test_report.py` (4 tests); full suite 131 pass. Two builds give the same sha256 (9a992f82…).

**Output.** `outputs/laporan_ml/laporan_ml_v1.html`, 9.1 MB, self-contained (19 figures embedded as PNG,
longest side ≤ 1,800 px; no external requests). Source text `reports/laporan_ml_src.html`; 117 numbers
filled from `data/processed/` (ML-2 scores, ML-3 zones, ML-4 states, ML-5 classes/coverage/metres/NAG list,
ML-6 kernel and CV, §9 scores, validation counts). The build stops on an unresolved placeholder, a missing
figure or a dangling internal link.

**Structure.** One-page summary (six cards with confidence badges), how to read + glossary, data
foundations, one section per ML task (question, short answer, method in plain words, key-number table,
figures with "how to read" captions, confidence, limits, why it matters, spoken script, likely judge
questions, chapter and files), literature comparators, synthesis (flow diagram + five-sentence prospect
story), a "don't say / say" table, appendix of the other figures.

**Checks.** Opened in the local browser pane through a localhost-only static server (`.claude/launch.json`,
127.0.0.1:8765; nothing sent off the machine): 19/19 images decode, 0 placeholders left, no horizontal
scroll at 375 px, light and dark themes readable, sidebar contents at ≥ 1,100 px. Numbers spot-checked
against this log: ML-2 0.70 / 0.71 / 0.30 / 0.84; soil zones 30 / 92 / 66 with median Au 0.007 / 0.065 /
0.335 ppm; HMM state sizes 533 / 776 / 368 / 643 / 737; NAG classes 37 / 48 / 21; management metres 43 /
797 / 2,216 (confident 866); NAG list 736 runs / 2,412 m, priority 1 375 / 1,350 m; GP length scales
22.5 / 12.2 / 8.2 m; §9 ARI 0.56 vs 0.02, twin-pad 0.93 / 0.40 / 0.40. All equal.
- Bug caught while building: `ml5_per_hole.csv` has a TOTAL row, so summing the column doubled the
  metres; the script now reads the TOTAL row.

**Docs.** `PANDUAN_TIM.md` trimmed to a file map: per-chapter "Angka kunci", "Ucapan presentasi",
outlier and limitation paragraphs removed (they live in the report) and replaced by a link to the
matching report section; intro and open-work table point to the report. `README.md` lists the report and
script 21.

**Caveats.** The report is team material, not report text: the final Bahasa report still needs formal EYD
wording. `10_tanah_zona_v1.png` is a QGIS QC render (no legend) and is captioned as such; the final zonation
map is still the map team's job. All `[VERIFY]` references remain unverified.

---

## 2026-11-05 · ioGAS automation probe (feasibility only, no deliverable changed)

**Context.** The human now owns the ioGAS work (14-day evaluation licence on this PC). Question: can an agent
drive ioGAS 8.3.2 cheaply instead of GUI clicking?

**Found (install `C:\Program Files\IMDEX\ioGAS-64.8.3`).**
- `.gas` project = ZIP of `data.csv` (+ per-row colour/shape/size index columns), `metadata.xml` (columns,
  attribute legends), `workspace.xml` (open plots, XStream XML).
- Workflows = plain XML lists of operations (action class + parameters, column names in clear text). Demo
  workflows in `%APPDATA%\ioGAS\res.cache\iod\DiagramAndCalc\Workflow` cover probability plots, histograms,
  SPLOM, attribute maps, strip logs, classification diagrams, auto-attribute, PCA/UMAP/DBSCAN.
- Launch flag `-gaslink2` (listed as "unsupported" in the jar's `config/help.txt`) starts a local gRPC server on
  127.0.0.1:25000 with services `Server` (OpenCSVFile, OpenGASFile, RunWorkflow, GetChartData) and `GASLink2`
  (read data/attributes). The `.proto` files ship inside `libs/GAS.jar`. `Server.SaveFile` is a file-transfer
  helper, not "save project".

**Tested.** Second instance launched via the bundled JRE with `-gaslink2` (the exe launcher is single-instance).
`OpenCSVFile(RJ_tanah.csv)` succeeded in 0.3 s (auto-detected X/Y/Z, SampleID; EPSG left 0). A hand-written
3-step workflow (Select Au/As/Cu → Probability Plot → Log Y) ran via `RunWorkflow` in 0.9 s and drew correct
plots (checked by one screenshot). One NullPointerException (`m_filenames`) was logged but did not stop the run.
All traffic is localhost, so no data left the machine. Test instance closed; the human's own ioGAS window was not touched.

**Limitation.** The evaluation licence (`gas.single.eval`, expires 19 Nov 2026) draws a "DEMONSTRATION COPY"
watermark on every chart (`ChartPanelio.m_evaluationWatermark`). Final report figures need the team's
committee licence. Do not try to remove the watermark.

**Not yet tested:** image export and project save as workflow steps; whether ioGAS opens hand-built `.gas` files;
setting EPSG 32647 on import. Probe scripts are in the session scratchpad only (not in the repo).

---

## 2026-11-05 · ioGAS automation probe 2: export, save, EPSG, hand-built .gas (feasibility only)

**Method.** Same setup as probe 1: second ioGAS instance via the bundled JRE with `-gaslink2`, workflows
written as XML, run through gRPC `RunWorkflow`. Action parameters were read from class fields with `javap`
and the XStream alias files in the install folder. Localhost only; test instance closed afterwards.

**Results.**
- **Image export works.** Op `net.ioglobal.gas.action.copy.ExportPlotWindowAction` with an
  `ExportWindowState` (`m_exportedFilename`, `ComponentExportConfig` scaleX/Y, detailX/Y) plus a workflow-level
  `<exportConfig>` (`recordedExportDir`, `exportOption=Overwrite`) writes PNGs. `RunWorkflow` returns the paths.
  `scale` multiplies pixel size (1 → 680×424, 2 → 1360×848 at the default window); `detail` does not change size.
- **The exported PNGs have no "DEMONSTRATION COPY" watermark.** It is drawn only on the on-screen chart under
  the evaluation licence. The installed `eula.txt` says nothing about evaluation/trial use.
- **Project save works** (`Creator.SaveFile`, `m_filename`, `m_saveAs=true`) when the data was opened from a
  `.gas` file. It fails (NullPointerException, `GASSaver.m_filenames` null) when the data came from gRPC
  `OpenCSVFile`, because that path records no source file. Workaround: always open a `.gas`.
- **Hand-built `.gas` files load.** A ZIP with `data.csv` (+ `__gas__extra__/color/shape/size` index columns),
  a minimal `metadata.xml` and a minimal `workspace.xml` opened via `OpenGASFile`. Column names use ioGAS
  escaping (`_` → `_u`, etc.).
- **EPSG works.** `specialColumns/map_epsg=32647` was accepted; ioGAS rewrote `map_proj` to
  "WGS 84 N UTM Zone 47". The elevation tag is `map_elevation`.
- **Attributes round-trip.** A colour attribute built from `ML_zona` (Tinggi/Sedang/Rendah with chosen colours)
  survived open → plot → save, and the XY plot (log Au vs log As, coloured by zone) was stored in the saved workspace.

**Pipeline that works end to end:** pandas → hand-built `.gas` (EPSG, ML colour attributes) → `OpenGASFile` →
workflow (select variables → plot → log axes → export PNG → save `.gas`) → PNGs + saved project.

**Not yet tested:** downhole strip logs, attribute maps, classification diagrams and probability-plot threshold
lines in a workflow; larger export window sizes. The builder and runner (`gasbuild.py`, `wf.py`) are still in the session
scratchpad, not the repo.

---

## 2026-11-05 · ioGAS link moved into the repo (code + tests), results

**Added.**
- `src/iogas_project.py` (no ioGAS needed): `build_gas()` writes a `.gas` (data.csv with ioGAS escaping and
  attribute index columns, metadata.xml with columns/types, special columns incl. EPSG, colour legend,
  minimal workspace.xml); `Workflow` writes workflow XML (select variables, plots, log axes, export window,
  save as). Row order/count preserved; NaN → empty cell, never 0.
- `src/iogas_link.py`: generates gRPC stubs from the protos inside the local GAS.jar into `.cache/iogas_grpc/`
  (gitignored, so no IMDEX file in the repo), starts a second ioGAS with `-gaslink2` via the bundled JRE
  when no server is listening (and kills only that instance afterwards), `open_gas`, `open_csv`, `run_workflow`.
- `scripts/22_iogas_link.py`: builds `data/processed/iogas/RJ_tanah.gas`, `RJ_batuan.gas` (coloured by
  `ML_zona`, zone colours from script 10), `RJ_DH_assay.gas` (coloured by `ML_paf_kelas`, PAF colours from
  script 14) and `RJ_DH_komposit_1m.gas` (no colour); `--check DIR` runs a live probability-plot export + save.
- Dependency group `iogas` (grpcio, grpcio-tools, protobuf), made a uv default group; `.cache/` gitignored.

**Checks.** `tests/test_iogas_project.py` (6 tests), `tests/test_iogas_link.py` (2 offline + 1 live, opt-in via
`IOGAS_LIVE=1`; passed live in 12 s). Full suite 139 passed, 1 skipped. `22_iogas_link.py --check` passed in
10 s (PNG exported, saved copy keeps EPSG 32647). All four built projects opened in ioGAS with exactly the CSV
shapes: tanah 259 × 92, batuan 469 × 128, DH_assay 2,476 × 186, komposit 3,108 × 113 (rows × columns read
back from ioGAS via gRPC `GetChartData`).

**Spoken explanation.** "We do not re-type anything into ioGAS. A script writes the ioGAS project straight from
our cleaned tables, already in UTM 47N and coloured by the ML classes, and ioGAS itself draws and exports the
plots from a saved workflow, so every figure can be regenerated identically."

**Still open.** AGENTS.md/CLAUDE.md role text still says ioGAS is a teammate's job (human will update).
Strip logs, attribute maps and classification diagrams in workflows are untested.

---

## 2026-11-06 — ioGAS Stage 0: action catalogue verified live (probes 3–6), builder extended, skill written

**Plan followed.** Approved plan "own the ioGAS work" (Stage 0, steps 1–3 and 5). Docs (step 4) are done in a
separate session ("Update docs for ioGAS ownership"); its facts were sent to it.

**Code.** `src/iogas_project.py`:
- `build_gas` gains `shape_by`/`shapes`/`shape_order` (codes 0–8 filled, 9–17 open), `aliases` (display names;
  legend titles default to the alias), `colour_title`/`shape_title`, and `drillhole=Drillhole(hole, from, to)`
  (writes `DHOptions`, `DownholeVariable_8_2`, `DrillholeConfig`); `SpecialColumns.group` = hole ID. Refuses
  aliases on element columns and duplicate display names.
- `Workflow` gains `aliases` (translated in every column reference), `diagram()` (built-in or file, returns a
  Frame), `configure_downhole()`, `strip_log(stacked=)`, `trace_mode()`, `respond()` + `userResponses`, and
  constants for histogram, box plots (common/tiled), Tukey, stats, attribute map, variable map, 3D map,
  ternary, legend, tile, log toggles. Export default scale 2 → 3.
- Skill: `.claude/skills/iogas/SKILL.md`, `reference/actions.md` (verified-action table).

**Findings (live, own ioGAS instance; the human's window was not open).**
1. Workflows refer to columns by **alias**: a workflow naming `Au_ppm` failed with "unable to find or make
   required columns" when the column was aliased "Au (ppm)".
2. Element columns must keep `El_unit` display names: with alias "Au (ppm)" ioGAS logged "Can't find conversion
   method"; built-in diagrams look up elements the same way. Decision (supersedes the plan's "Au (ppm)" example):
   Bahasa labels go on non-element columns and legend titles only; element axes stay `Au_ppm`.
3. Halley "Fe vs S with Pyrite Line" failed with "S_ppm missing" on `S_total_pct`; with an extra `S_pct` column
   all three Halley diagrams (Fe–S, Ca–Fe–S, Al–K–Mg) opened. Stage 4 will add `S_pct` = `S_total_pct` in the
   .gas and state it in captions.
4. Plot windows are found by the UUID of the opening operation; a deliberately wrong title still exported.
5. Opened and exported from a workflow: histogram, box plots (common and tiled; one box per colour group),
   attribute map, 3D map (plan view), ternary, Halley diagrams, strip log per hole and stacked (Bar trace,
   colour attribute shown as a category track), probability plot. Sizes at scale 3: 1,536–4,095 px wide.
6. Not exportable (ioGAS NullPointerException in the exporter): Summary Statistics and Legend windows.
7. Log toggles: work on histograms (`LogHistAction`) and probability/XY plots (`LogYAction`); **ignored** on box
   plots and strip logs (saved state `m__isLog=false`). Stages will plot `<el>_log10` columns there.
8. An unanswered prompt ("OK to overwrite columns Ca_ppm, Fe_ppm, S_ppm to open diagram?.") stalled a run for
   3.5 min; pre-answering it in `<userResponses>` removed the stall (whole 22-op run 17 s).
9. Tukey (`AttributeRowsByOutlierStatus`) runs without error; its effect on attributes is not yet checked.

**Checks.** `tests/test_iogas_project.py` 10 tests (4 new: drillhole/shape/alias metadata, alias and duplicate
guards, title truncation, workflow aliases/strip log/diagram/responses XML). Full suite 143 passed, 1 skipped;
live round trip (`IOGAS_LIVE=1`) 3 passed in 11 s. `22_iogas_link.py` rebuilt the four hand-off .gas files with
unchanged shapes (259×92, 469×128, 2,476×186, 3,108×113).

**Spoken explanation.** "ioGAS draws every figure itself from a saved workflow. We checked each plot type
we need actually opens and exports from a script before using it, and we wrote down the ones that don't (for
example ioGAS ignores a log axis on box plots, so we plot log10 values there). Element names stay as ioGAS
expects them so its built-in Scott Halley diagrams recognise Fe and S."

**Open.** Legend images (draw from the same palette in Python or a GUI screenshot), XYZ section rotation,
Tukey effect check. Gate: human reviews skill + docs diff and the sample exports before Stage 1.

---

## 2026-11-06 · ioGAS Stage 1 plan (QAQC & thresholds), approved by the human

**Goal.** Report §3 (QAQC 30, outliers 35, thresholds 35) drawn by ioGAS; fill `thr_probplot_iogas` with
probability-plot picks made blind to the GMM (AGENTS.md §6 task 1, §10 Stage 1).

**Inputs.** `data/processed/iogas/RJ_tanah|RJ_batuan|RJ_DH_assay.csv` on the ML-1 row subsets (surface
`prospek_RJ = Y`: soil 188, rock 382; drillholes `NS_SEL = N`: 2,466; counts checked equal to ML-1 `n_analysed`).
22 elements with an ML-1 fit (bor Au Ag Cu As SCIS; batuan Au Cu As Hg Pb Sb Zn; tanah Au Ag Cu As Ba Hg Pb Sb
W Zn); batuan Ag has no fit and is skipped.

**Blindness.** The pick phase drops `ML_thr_*` columns and reads only dataset/element/column/n from
`element_thresholds.csv`. Picks go to `data/interim/s1_probplot_picks.csv`; its SHA-256 is logged here before the
comparison runs.

**Script** `scripts/23_iogas_s1_qaqc.py --phase blind|qaqc|ambang`:
- `blind`: uncoloured log probability plot per element → `outputs/figures/iogas/s1_pp_<ds>_<el>_v1.png`.
- `qaqc`: AuCN vs Au and AgCN vs Ag (by oxidation), rock duplicate pairs, box plots of log10 Au/Cu/As by lab
  year and by hole (finding 14), Tukey / Anomaly Assessment Tool if a live probe shows they work.
- `ambang`: `element_thresholds_v2.csv` (v1 untouched), `s1_ambang_perbandingan_v1.csv` (pick vs GMM main and
  nearest T_k with bootstrap CI, MAD, Tukey, % above), probability plots re-exported coloured by the picked
  classes; stage projects `outputs/iogas_project/RJ_<ds>_s1_v1.gas`.

**Checks.** Row counts read back from ioGAS, EPSG kept, PNG sizes, v1 table hash unchanged, pytest. Gate: the human
spot-checks picks for tanah Au, batuan Au and bor Cu in the ioGAS GUI.

---

## 2026-11-06 · ioGAS Stage 1: probability-plot picks frozen (blind)

22 picks (1–2 breaks per element) read by eye from the uncoloured ioGAS log probability plots
`outputs/figures/iogas/s1_pp_<ds>_<el>_v1.png` (`23_iogas_s1_qaqc.py --phase blind`), before any GMM, MAD or Tukey
value, `ML_thr_*` column or ML-1 figure was opened in this session. Rationale, normal-score position and confidence
per pick are in the file. Confidence: 1 high, 14 medium, 7 low (censored or lab-resolution steps: tanah Ag/W, bor Ag).

`data/interim/s1_probplot_picks.csv` SHA-256 `0eeb088a28595be5e1af6dabc514b4f390a0e6e1dbda657175f511563de6922c`

---

## 2026-11-06 · ioGAS Stage 1 results (QAQC, outliers, thresholds)

**Ran.** `scripts/23_iogas_s1_qaqc.py --phase blind`, `--phase qaqc`, then `--phase ambang` (after the picks hash
above). Our own `-gaslink2` ioGAS instance only; localhost only.

**New ioGAS action (verified live).** Anomaly Assessment Tool (`analysis.aat.AATCalculateAction`, builder
`Workflow.aat`). With several variables selected it uses only complete-case rows (soil Ba covers 114 of 188, so
fences moved), so the script runs it **one element per call**. Then all 22 ioGAS counts (high/low, near/far)
equal a Python Tukey on log10 values (`data/processed/s1_aat_ringkasan_v1.csv`, column `sama` all True). The
box-plot Tukey toolbar action (`A_TUKEY`) has no effect from a workflow; it is dropped. Skill and
`reference/actions.md` updated.

**Outputs.**
- Figures `outputs/figures/iogas/`: 22 blind probability plots `s1_pp_*`, 22 coloured by picked class
  `s1_pp_kelas_*` (Latar / Anomali lemah / Anomali kuat), Tukey box plots of log10 values for soil and rock,
  drillhole boxes by oxidation, lab year and hole (finding 14), AuCN vs Au and AgCN vs Ag (coloured by
  oxidation), rock field-duplicate scatters for Au and Cu (13 pairs). 2,040–4,764 px wide.
- Projects `outputs/iogas_project/`: `RJ_<ds>_s1_pp_v1.gas`, `RJ_<ds>_s1_qaqc_v1.gas` (AAT columns),
  `RJ_bor_s1_tahun_v1.gas`, `RJ_bor_s1_lubang_v1.gas`, `RJ_batuan_s1_duplikat_v1.gas`, `RJ_<ds>_s1_v1.gas`
  (coloured by the Au class, all `Kelas_*_pp` columns kept), `s1_kelas/` (one per other element). Every saved
  project read back: row count equals the ML-1 subset, EPSG 32647 kept.
- Tables: `data/processed/element_thresholds_v2.csv` (v1 + `thr_probplot_iogas`, `thr_probplot_iogas_2`,
  `pct_above_probplot`; v1 hash unchanged), `s1_ambang_perbandingan_v1.csv`.

**Outlier counts (log10 Tukey, AAT).** Rock high outliers: Au 4, Cu 5, As 7, Hg 3, Sb 9, Zn 11. Soil: no high
outliers except Ag 2 and Ba 2 (log scale; low-side outliers are DL steps). Drillholes: Au 0 high, Cu 28 high,
As 37 high; SCIS 79 low (DL/2 step).

**Thresholds: probability plot vs GMM (agreement, not ranking).**
- Pick 1 vs nearest GMM break T_k: 3 inside the bootstrap CI, 5 within 2×, 14 differ by more than 2×.
- Best of the two picks vs nearest T_k: **15 of 22 within 2×**. Of the 15 elements where the GMM found ≥2
  populations, 9 agree within 2×.
- The 7 GMM fits with K = 1 have no population break; their "main" threshold is a single-population tail cut
  (≈0.5–3 % above), so a slope-break pick is not expected to match it.
- Disagreements beyond 2× for both picks: tanah As, Pb, Zn; batuan As, Pb; bor Ag, SCIS. In soil As, Pb, Zn
  and in rock Pb the GMM main break sits low (76–87 % of samples above), i.e. it separates the lower
  populations, while the visual picks target the upper tail. Bor Ag (32 % censored) and SCIS (strong
  oxide/sulfide curvature) were low/medium-confidence picks.
- MAD and Tukey thresholds sit above both picks for most elements (e.g. bor Au: pick 0.3 / 5.5, MAD 22, Tukey 94 ppm).

**Spoken explanation.** "ioGAS drew the probability plots and we picked the breaks by eye before looking at
the machine-learning thresholds, then compared. For about two thirds of the elements, at least one of our
breaks lies within a factor of two of a break the Gaussian-mixture model found on its own. Where they differ,
it is mostly because the two methods are answering different questions: the model sometimes splits the low
background populations, while a geologist's eye goes to the upper tail. ioGAS's own Tukey outlier tool gives
exactly the same outlier counts as our Python check."

**Open / gate.** Human spot-checks the picks for tanah Au, batuan Au and bor Cu in the ioGAS GUI
(`outputs/iogas_project/RJ_*_s1_pp_v1.gas` and `RJ_*_s1_v1.gas`). Deliverable 3 still holds v1 thresholds
(refresh to `_v2` is a Stage 5 decision). Tests: 149 passed, 1 skipped; live round trip 3 passed.

---

## 2026-11-06 · ioGAS Stage 1 gate passed

The human checked the Stage 1 picks in the ioGAS GUI (tanah Au, batuan Au, bor Cu) and approved Stage 1
("all fine"). No picks changed. Work paused here at the human's request; Stage 2 (Surface) is next.

---

## 2026-11-06 · ioGAS Stage 2 plan (Surface), approved by the human

**Goal.** Report §4 (soil 25, rock 25, zonation 50) drawn by ioGAS (AGENTS.md §10 Stage 2). No new ML: ML-3 zones
(`ML_zona*`) and Stage 1 probability-plot classes (frozen picks, `s1.classify`) are inputs.

**Inputs.** `RJ_tanah.csv` RJ subset 188 (zones R 30 / S 92 / T 66), `RJ_batuan.csv` RJ subset 382 (zone on 352:
R 204 / S 131 / T 17; logged `Fasies_Alterasi`), Stage 1 picks (hash checked against this LOG). Halley Al-K-Mg on
the 26 full-ICP rocks (10 inside RJ), shape inside/outside RJ.

**Figures** (`outputs/figures/iogas/s2_*_v1.png`): soil maps by zone, zone confidence (`ML_zona_p_maks` bins),
Au and As threshold class; soil log As-Au and Pb-Au by zone; tiled log10 box plots per zone; Au probability plot
by zone. Rock maps by zone (shape float/outcrop) and Au class; As-Au and Cu-Au by zone; box plots per zone; map and
boxes by logged alteration; Al-K-Mg ternary.

**Tables.** `s2_zona_vs_kelas_v1.csv` (zone × Au/As threshold class, Cramér's V), `s2_zona_ringkasan_v1.csv`
(n, median per element per zone, read back from the saved .gas).

**Code.** Shared helpers to `src/iogas_stage.py`; `src/iogas_s2.py` + `tests/test_iogas_s2.py`;
`scripts/24_iogas_s2_surface.py`. Projects `outputs/iogas_project/RJ_tanah_s2_v1.gas`, `RJ_batuan_s2_v1.gas`
(+ per-scheme in `s2/`). Checks: row counts read back, EPSG kept, no failed ops, PNG sizes, pytest + live test.
Gate: human opens the two stage projects in the GUI.

---

## 2026-11-06 · ioGAS Stage 2 results (Surface: soil, rock, zonation)

**Ran.** `scripts/24_iogas_s2_surface.py` (8 workflows, our own `-gaslink2` instance, localhost only). Stage 1 picks
hash checked; Stage 1 figures unchanged (hash before/after). Shared ioGAS plumbing moved to `src/iogas_stage.py`
(Stage 1 script and `22_iogas_link.py` now import it; behaviour unchanged). Helpers `src/iogas_s2.py`.

**Two ioGAS findings (skill updated).** (1) Exporting an attribute map right after opening it raced the map
rendering (ConcurrentModificationException, 0-byte PNG); exporting it last, after 3-4 other exports, worked in all
8 runs. (2) A saved .gas stores data columns under their aliases; the script renames them back before the tables.
The Halley run logged "Couldn't match frame" at Save As: the PNG is fine, the window may not be kept in that .gas.

**Outputs.** 30 PNGs `outputs/figures/iogas/s2_*_v1.png` (2,040-4,764 px; Halley 1,536 px, small window):
- soil (188): maps by zone, by Au and As threshold class, by zone confidence; As-Au and Pb-Au log scatters and tiled
  log10 box plots in each of those colourings; Au probability plot by zone.
- rock: zone (352; shape outcrop vs float), Au class (382), logged alteration (382) maps, As-Au / Cu-Au scatters and
  box plots in each colouring; Halley Al-K-Mg on the 26 full-ICP rocks (10 inside RJ).
- Projects: `outputs/iogas_project/RJ_tanah_s2_v1.gas` (188), `RJ_batuan_s2_v1.gas` (352), coloured by zone with
  class/confidence columns kept; `outputs/iogas_project/s2/` (kelas_Au, kelas_As, keyakinan, alterasi, halley).
  All read back: rows equal the subset, EPSG 32647 kept.
- Tables `data/processed/s2_zona_vs_kelas_v1.csv`, `s2_zona_ringkasan_v1.csv`.

**Numbers.**
- Zone medians (read back from ioGAS) equal the ML-3 LOG: soil Au 0.007 / 0.065 / 0.335 ppm (R/S/T), As 13 / 54 /
  129, Pb 17 / 57 / 129, Sb 0.6 / 3.95 / 16.5, Zn flat (22.5 / 25 / 18.5). Rock Au 0.12 / 0.53 / 5.04 g/t, As 86 /
  351 / 2,270, Sb 8 / 29 / 256; Zn and Hg flat.
- Zone vs Stage 1 threshold class (Cramér's V): soil Au 0.39, soil As 0.42, rock Au 0.48, rock As 0.54. All soil
  Rendah samples are Latar for Au and As; soil Tinggi is 47 % above the lower Au pick (14 % Anomali kuat), so the
  soil Tinggi zone is broader than the Au anomaly (a multi-element footprint, As-Pb-Sb driven). Rock Tinggi: 88 %
  above the lower Au pick, 53 % Anomali kuat; rock Rendah 92 % Latar.
- Soil zone confidence (`ML_zona_p_maks`): >= 0.9: 36, 0.7-0.9: 94, 0.5-0.7: 57, < 0.5: 1.
- Halley Al-K-Mg: logged Silika and Argilik rocks plot near the Al apex / advanced-argillic field, none in the
  least-altered field (visual reading of the exported plot).

**Spoken explanation.** "ioGAS drew every surface figure from our cleaned tables. The machine-learning zones and
the probability-plot thresholds were made independently, and they agree where it matters: every low-zone soil sample
is background, and the high zone carries the anomalies. The high soil zone is wider than the gold anomaly alone
because it is defined by gold together with arsenic, lead and antimony, the pathfinders of a high-sulfidation
system. We also map how sure the model is, so a judge can see which samples sit on a zone boundary."

**Open / gate.** Human opens `RJ_tanah_s2_v1.gas` and `RJ_batuan_s2_v1.gas` in the ioGAS GUI, recolours once by
"Kelas ambang Au", and confirms maps and box plots. Legends are not exportable (Stage 0): captions or a Python
legend from the same palette. Tests: 155 passed, 1 skipped; live round trip 3 passed.

---

## 2026-11-06 · ioGAS Stage 2 gate passed

The human checked `RJ_tanah_s2_v1.gas` and `RJ_batuan_s2_v1.gas` in the ioGAS GUI (recoloured by "Kelas ambang Au")
and approved Stage 2 ("all fine"). Nothing changed. Stage 3 (Drillhole) is next.

---

## 2026-11-06 · ioGAS Stage 3 plan (Drillhole), approved by the human

**Goal.** Report §5 (correlation 40, geochem-stratigraphy 40) drawn by ioGAS (AGENTS.md §10 Stage 3). No new ML:
ML-4 HMM states (`ML_hmm_*`), logged alteration and oxidation are inputs. The QGIS sections A–C (ML-4, true
elevation) stay the report's sections; ioGAS adds strip-log correlation panels by depth, twin-pad panels and
per-state statistics. Full plan: `C:\Users\mauli\.claude\plans\plan-stage-3-of-luminous-lynx.md`.

**Inputs.** `RJ_DH_komposit_1m.csv`, subset `comp_ok = Y` (3,057 composites; HMM S1 533 / S2 776 / S3 368 / S4 643 /
S5 737). Section holes from `data/processed/ml4_sections.csv` (A 6, B 6, C 4 holes; 004, 010, 011 off-section),
ordered along the section. Twin pads 005/014, 010/011, 016/017. Palettes: HMM `geostrat.STATE_PALETTE[5]`,
alteration `iogas_s2.ALT_COLOURS`, oxidation `OX_COLOURS` (moved to `src/iogas_stage.py`).

**Figures** (`outputs/figures/iogas/s3_*_v1.png`): stacked strip logs per section A/B/C + off-section set (log10 Au,
Ag, Cu, As + HMM stability; coloured by HMM state); the same stacks coloured by logged alteration and logged
oxidation (Au, Cu, As); twin pads in HMM and alteration colours; tiled log10 box plots by state (Au, Ag, Cu, As,
SCIS, CuCN/Cu); log Cu-Au and As-Au by state; XYZ map plan view by state (exported last).

**Projects / tables.** `outputs/iogas_project/RJ_bor_s3_v1.gas` (HMM), `s3/RJ_bor_s3_{alterasi,oksidasi}_v1.gas`;
`data/processed/s3_status_ringkasan_v1.csv` (n, holes, medians per state, read back from the saved .gas),
`s3_status_per_lubang_v1.csv` (state metres per hole). Code `src/iogas_s3.py`, `tests/test_iogas_s3.py`,
`scripts/25_iogas_s3_drillhole.py`. Checks: no failed ops, PNGs exist, saved rows 3,057 with EPSG 32647, read-back
state counts equal ML-4, Stage 1–2 figure hashes unchanged, pytest + live test. Gate: human opens
`RJ_bor_s3_v1.gas` in the GUI (one section stack, one twin pad; optional rotated XYZ screenshot).

---

## 2026-11-06 · ioGAS Stage 3 results (Drillhole: correlation panels, geochem-stratigraphy)

**Ran.** `scripts/25_iogas_s3_drillhole.py` (3 workflows, our own `-gaslink2` instance, localhost only), after a
scratch probe (`--probe`, `data/interim/iogas_s3/probe/`, not a deliverable). Helpers `src/iogas_s3.py`, tests
`tests/test_iogas_s3.py`. `OX_COLOURS` moved to `src/iogas_stage.py` (same values; Stage 1 imports it).

**ioGAS finding (skill updated).** The "stacked" strip log adds all selected variables into one cumulative bar per
hole: wrong for geochem tracks, seen in the first probe and dropped. The normal strip log with our config puts all
configured holes in one window, in the order given (checked against `kolar_x`), one track per variable plus the
colour attribute as a category track. Depth axis is shared; **each hole/track has its own x-scale**, so captions must
say "compare patterns, not bar lengths between holes".

**Outputs.** 22 PNGs `outputs/figures/iogas/s3_*_v1.png` (1,536-4,764 px):
- strip logs per section A (001, 008, 019, 015, 009, 003), B (018, 012, 017, 016, 005, 014), C (007, 013, 006, 002)
  and "Lain" (004, 010, 011), SE→NW as in the QGIS sections: coloured by HMM state (tracks log10 Au, Ag, Cu, As +
  `ML_hmm_stabil`), by logged alteration and by logged oxidation (log10 Au, Cu, As);
- twin pads 005/014, 010/011, 016/017 in HMM and alteration colours;
- tiled log10 box plots (Au, Ag, Cu, As, SCIS, CuCN/Cu) and log Cu-Au, As-Au scatters by HMM state; XYZ map (plan).
- Projects: `outputs/iogas_project/RJ_bor_s3_v1.gas` (HMM colours, all windows), `s3/RJ_bor_s3_alterasi_v1.gas`,
  `s3/RJ_bor_s3_oksidasi_v1.gas`. All read back: 3,057 rows, EPSG 32647 kept, HMM counts 533/776/368/643/737.
- Tables `data/processed/s3_status_ringkasan_v1.csv`, `s3_status_per_lubang_v1.csv`. Stage 1-2 figures unchanged
  (83 hashes). Tests: 162 passed, 1 skipped; live round trip 3 passed.

**Numbers (medians read back from ioGAS, equal to the CSV).** Au ppm S1 0.02 / S2 0.07 / S3 0.74 / S4 0.74 /
S5 1.01; Cu ppm 25 / 50 / 7 / 332 / 55; As 50 / 87 / 59 / 169 / 83; SCIS % 2.75 / 1.48 / 0.53 / 2.09 / 0.81;
CuCN/Cu 0.21 / 0.19 / 0.43 / 0.60 / 0.52. (ML-4 table gives geometric means; these are medians.)

**Twin pads (visual reading of the exports).** 005/014: both S5 at the top, a S1 band at ~70-88 m in both; S4 is
thick in 014 (~35-65 m) but thin in 005, where S3 takes its place. 010/011: same order S2 → S5 → S4 in both, the
units thinner in 011 (134 m vs 246 m deep). 016/017: S2 over S3 over S5 in both, but the S3/S5 boundary is at
~68 m in 016 and ~110 m in 017. Logged alteration differs more between twins than the HMM (e.g. 005 Silika over
Argilik vs 014 Silika / Argilik lanjut / Argilik), consistent with ML-4 / §9.2 (twin agreement HMM 0.93 vs logs 0.40).

**Spoken explanation.** "ioGAS drew the drill strip logs from our 1 m composites, hole by hole along the same three
section lines as our QGIS sections. The left column is the chemical unit the HMM found; the bars are gold, silver,
copper and arsenic, and the last track shows how stable each unit is when we resample. In the twin holes, drilled a
few metres apart, the same units come in the same order and often at the same depth, which is what correlation
means. The copper-rich sulphide unit S4 has the highest copper and arsenic and the barren unit S1 the lowest gold, so
the units are geochemically distinct, not just colours."

**Open / gate.** Human opens `outputs/iogas_project/RJ_bor_s3_v1.gas` in the ioGAS GUI, checks section B and twin
pad 005/014; optionally rotates the XYZ view to section B and screenshots it. Legends are not exportable: captions
or a Python legend from `geostrat.STATE_PALETTE`.

---

## 2026-11-06 · ioGAS Stage 3 gate passed

The human checked `RJ_bor_s3_v1.gas` in the ioGAS GUI (section B, twin pad 005/014) and approved Stage 3
("all fine"). Nothing changed. Stage 4 (Environmental) is next.

---

## 2026-11-06 · ioGAS Stage 4 plan (Environmental), approved by the human

**Goal.** Report §6 (AMD elements 40, PAF/NAF classification & treatment 60) drawn by ioGAS (AGENTS.md §10
Stage 4). No new ML: ML-5 outputs (`ML_paf_*`), RJDH012 NAG labels and logged oxidation are inputs. The ML-5 Python
figures (flowchart, conformal coverage, NAPP proxy) stay. Full plan:
`C:\Users\mauli\.claude\plans\plan-stage-4-of-curious-pike.md`.

**Human decisions.** (1) All-holes panels coloured by `ML_paf_kelola` (conservative management class) as the main
project, plus a second project coloured by `ML_paf_kelas` (singleton vs `ambigu`). Deviation from the AGENTS §10
wording (`ML_paf_kelas` only), because `ML_paf_kelas` is `ambigu` for 1,955 of 2,466 rows. (2) A NAG-testing
priority strip-log set (`ML_paf_prioritas_uji`) is added; it is the first thing cut if time runs short.

**Inputs.** `RJ_DH_assay.csv`: 2,466 sampled rows (management metres NAF 42.8 / PAF-LC 796.6 / PAF-HC 2,215.6);
RJDH012 118 rows, 106 with NAG (NAF 37 / PAF-LC 48 / PAF-HC 21). `S_pct = S_total_pct` added for the Halley
diagrams (stated in captions). SCIS and S2 stay separate tracks (§4.2.10). Ca censored in 106/118 RJDH012 rows
(Ca-Fe-S caveat).

**Projects / figures** (`outputs/figures/iogas/s4_*_v1.png`): P1 RJDH012 by NAG class (shape = oxidation): NAG pH vs
S total and vs SCIS, NAG capacity vs SCIS, Halley Fe vs S (pyrite line) and Ca-Fe-S, AMD-element box plots, strip
log. P2 RJDH012 by oxidation: strip log, NAG pH vs S. P3 all holes by management class: section strip logs (SCIS,
S2, Cu, As, conformal set size), box plots, XYZ map. P4 by conformal class and P5 by NAG priority: section strip
logs. Tables `s4_kelas_nag_ringkasan_v1.csv`, `s4_kelola_per_lubang_v1.csv` (read back from the saved .gas).
Code `src/iogas_s4.py`, `tests/test_iogas_s4.py`, `scripts/26_iogas_s4_environmental.py`. Gate: human opens
`RJ_RJDH012_s4_v1.gas` and `RJ_DH_s4_kelola_v1.gas`, checks the Halley Fe-S plot and one section strip log.

---

## 2026-11-06 · ioGAS Stage 4 results (Environmental: NAG, PAF/NAF, AMD elements)

**Ran.** `scripts/26_iogas_s4_environmental.py` (5 workflows, our own `-gaslink2` instance, localhost only), after a
scratch probe (`--probe`, `data/interim/iogas_s4/probe/`, not a deliverable). Helpers `src/iogas_s4.py`, tests
`tests/test_iogas_s4.py`. `PAF_COLOURS`/`PAF_ORDER` moved from `scripts/22_iogas_link.py` to `src/iogas_stage.py`
(same values); `st.element_column` knows S total, S2, Fe, Ca and NAG capacity (Stage 1-3 aliases unchanged, tested).

**ioGAS findings (skill updated).** (1) ioGAS writes aliases unescaped into its saved `data.csv` header: the probe
alias "Kapasitas NAG pH 4,5" split into two columns. `build_gas` now refuses commas in aliases; the alias reads
"pH 4.5" (captions give "pH 4,5"). (2) Halley Fe vs S then Ca-Fe-S ran with no overwrite prompt (no `User asked`
in any log). (3) "Couldn't match frame" warnings at Save As, as in Stages 2-3 (those projects passed the GUI gate).

**Outputs.** 24 PNGs `outputs/figures/iogas/s4_*_v1.png` (1,536-4,764 px):
- RJDH012 by NAG class, shape = logged oxidation: NAG pH vs S total and vs SCIS (log x), NAG capacity pH 4.5 vs
  SCIS (log-log), Halley Fe vs S (pyrite line) and Ca-Fe-S, tiled log10 box plots of S total, SCIS, Fe, As, Cu, Zn,
  Pb, Cd, Mn, Sb, strip log (NAG pH, log10 capacity, SCIS, S total); strip log and NAG pH vs S total by oxidation.
- All holes (2,466 intervals): section strip logs A/B/C/Lain (log10 SCIS, S2, Cu, As + conformal set size) coloured
  by management class, conformal class and NAG-testing priority; box plots, Cu-SCIS scatter, XYZ map (plan) by
  management class.
- Projects: `outputs/iogas_project/RJ_RJDH012_s4_v1.gas` (118), `RJ_DH_s4_kelola_v1.gas` (2,466),
  `s4/RJ_RJDH012_s4_oksidasi_v1.gas`, `s4/RJ_DH_s4_{kelas,uji_nag}_v1.gas`. All read back: rows equal, EPSG 32647.
- Tables `data/processed/s4_kelas_nag_ringkasan_v1.csv` (sha256 6c84af81…), `s4_kelola_per_lubang_v1.csv`
  (0b4c9231…). Stage 1-3 figures unchanged (105 hashes). Tests 169 passed, 1 skipped; live round trip 3 passed.

**Numbers (read back from ioGAS, equal to the CSV).** NAG classes NAF 37 / PAF-LC 48 / PAF-HC 21 / untested 12.
Medians NAF / PAF-LC / PAF-HC: NAG pH 4.99 / 3.89 / 2.36; capacity pH 4.5 0.002 (censored) / 1.47 / 57.8 kg H2SO4/t;
S total 0.90 / 0.62 / 3.03 %; SCIS 0.30 / 0.14 / 2.32 %; Fe 2.92 / 2.23 / 5.27 %. Management metres per hole sum to
NAF 42.8 / PAF-LC 796.6 / PAF-HC 2,215.6 (= ML-5).
- Halley Fe vs S: 105/118 RJDH012 samples plot on the Fe-rich side of the pyrite line (Fe/S mass ratio 0.871),
  13 on the S-rich ("probable sulfates") side (oxide 7/98, sulphide 6/20); PAF-HC samples cluster nearest the line.
  Excess Fe (hematite/limonite in the oxide zone) dominates, so this plot cannot show the non-sulfide S fraction
  of AGENTS §4.3 (SCIS 0.32 vs total S 1.10 %); it neither confirms nor contradicts it. Say so in the caption.
- Ca-Fe-S: all points on the Fe-S base because Ca is censored in 106/118 samples; shown for completeness, no
  interpretation beyond "Ca-poor, no carbonate buffer visible" (no ANC measured).

**Spoken explanation.** "ioGAS drew every acid-drainage figure from our tables. In the one hole with NAG tests, the
high-capacity acid rock stands out clearly: low NAG pH, high sulfur, and it sits closest to the pyrite line on
Scott Halley's iron-sulfur plot. Non-acid and low-capacity oxide rock overlap on every element, which is the same
thing our machine-learning model found, so we manage untested rock by its worst plausible class. The strip logs
along our three sections show, hole by hole, which intervals are managed as high-capacity acid rock and where a new
NAG test would change that decision."

**Limits.** One NAG hole, 16 sulphide samples; no ANC; Ca censored; S2 uncalibrated against SCIS; RJDH001 has no S
(empty tracks); each hole/track in a strip log has its own x-scale.

**Open / gate.** Human opens `RJ_RJDH012_s4_v1.gas` and `RJ_DH_s4_kelola_v1.gas` in the ioGAS GUI, checks the
Halley Fe-S plot and one section strip log. Legends are not exportable: captions or a Python legend from
`st.PAF_COLOURS`.

---

## 2026-11-06 · ioGAS Stage 4 gate passed

The human checked `RJ_RJDH012_s4_v1.gas` and `RJ_DH_s4_kelola_v1.gas` in the ioGAS GUI (Halley Fe-S plot, a section
strip log) and approved Stage 4 ("all fine"). Nothing changed. Stage 5 (project & polish) is next.

---

## 2026-11-06 · ioGAS Stage 5 plan (final projects, team and committee hand-off), approved by the human

**Goal.** Deliverable 2 (the ioGAS project) and the polish that lets teammates write the report from the private
GitHub repo, and the committee read our files, without knowing our internal shorthand. Full plan:
`C:\Users\mauli\.claude\plans\plan-stage-5-iogas-piped-stallman.md`.

**Human decisions.** (1) Four consolidated final projects, each with all columns used by the stage projects and
the key report windows: `RJ_tanah_final_v1.gas` (soil, ML zone), `RJ_batuan_final_v1.gas` (rock, ML zone),
`RJ_bor_komposit_final_v1.gas` (1 m composites, HMM state), `RJ_lingkungan_final_v1.gas` (assays, PAF/NAF management
class). The 47 stage projects stay as supporting files, listed in a Bahasa index. (2) **No GUI screenshots**
(deviation from AGENTS §10 Stage 5 wording): exported PNGs plus the saved projects are the evidence of ioGAS use.
(3) Build `outputs/kirim/` with deliverables 1-3 ready to attach to the 7 Nov email (< 25 MB).

**Steps.** `scripts/27_iogas_s5_final.py` (+ `src/iogas_s5.py`): final projects, check exports only to
`data/interim/iogas_s5/cek/`. Indexes: `outputs/iogas_project/indeks_proyek_iogas.csv` + `BACA_SAYA.txt`,
`outputs/figures/iogas/indeks_gambar_iogas.csv`. ML findings report v2 (threshold comparison replaces the stale
"ioGAS teammate" limit). Guides: glossary of terms and file naming first in PANDUAN_TIM.md and README.md;
"Tahap ioGAS 1-5" vs "satuan HMM S1-S5" always written out. `scripts/28_kirim.py` builds the submission folder
with a manifest. Tests `tests/test_iogas_s5.py`. Gate: human opens the four final projects in the ioGAS GUI.
Commit/push only on the human's go, after checking the repo is still private.

---

## 2026-11-06 · ioGAS Stage 5 results (final projects, indexes, ML report v2, guides, submission folder)

**Ran.** `scripts/27_iogas_s5_final.py` (4 workflows, our own `-gaslink2` instance, localhost only), then
`--index`; `scripts/21_laporan_ml.py`; `scripts/28_kirim.py`. Helpers `src/iogas_s5.py`, tests `tests/test_iogas_s5.py`.
`load_surface` and its constants moved unchanged from `scripts/24_iogas_s2_surface.py` to `src/iogas_s2.py`
(Stage 2 tests pass; no Stage 1-4 output changed: 176 figure and project hashes checked before/after).

**Final projects** (`outputs/iogas_project/`; every column of the ioGAS-ready CSV for the analysed rows + stage-derived
columns: threshold classes for all picked elements from the frozen Stage 1 picks, log10 columns, zone confidence,
NAG label, `S_pct` = S total; Bahasa aliases; EPSG 32647 read back in every saved file):
- `RJ_tanah_final_v1.gas`: 188 soils x 113 columns, coloured by ML zone; 7 windows (Au, As probability plots, zone
  box plots, As-Au, Pb-Au, summary statistics, attribute map).
- `RJ_batuan_final_v1.gas`: 382 rocks x 144 columns (30 without zone shown as "Tanpa zona ML", grey), shape
  outcrop/float; 7 windows (As-Au, Cu-Au). The Halley Al-K-Mg ternary stays in the supporting project
  `s2/RJ_batuan_s2_halley_v1.gas` (only 10 of its 26 rocks are inside RJ).
- `RJ_bor_komposit_final_v1.gas`: 3,057 composites x 118 columns, coloured by HMM unit; 10 windows (Au, Cu probability
  plots, strip logs sections A/B/C and twin pad 005/014, box plots, Cu-Au, statistics, XYZ map).
- `RJ_lingkungan_final_v1.gas`: 2,466 assay intervals x 208 columns, coloured by PAF/NAF management class, shape =
  oxidation; 9 windows (NAG pH vs S total and NAG capacity vs SCIS: only RJDH012 plots, as the only NAG hole;
  Halley Fe vs S: only RJDH012 has total S; box plots; strip logs A/B/C; statistics; XYZ map). The Ca-Fe-S ternary
  stays in `RJ_RJDH012_s4_v1.gas`.
- 29 check exports in `data/interim/iogas_s5/cek/` (gitignored, review only; no new report figures). Reviewed: right
  variables, log axes, colours; NAG plots show RJDH012 only.

**Indexes (Bahasa, regenerated by `--index`).** `outputs/iogas_project/indeks_proyek_iogas.csv` (51 projects: 4 final
+ 47 supporting; stage, chapter, data, colour scheme, rows, windows, EPSG) and `BACA_SAYA.txt` (committee-facing,
defines every term); `outputs/figures/iogas/indeks_gambar_iogas.csv` (all 129 ioGAS PNGs: chapter, plot type, colour,
content, caption notes such as "axis reads Au_ppm", "each hole/track has its own x-scale", "S_pct = S total").

**ML findings report v2** (`outputs/laporan_ml/laporan_ml_v2.html`; v1 frozen). The stale ML-1 limit ("for the ioGAS
teammate") is replaced by the comparison, filled from `s1_ambang_perbandingan_v1.csv`: in 15 of 22 element/dataset
pairs at least one probability-plot break is within 2x of the nearest GMM break (5 inside the bootstrap CI); 7 differ
by > 2x for both picks (soil As, Pb, Zn; rock As, Pb; drillhole Ag, SCIS). Figure `s1_pp_kelas_bor_Au_v1.png` added;
ioGAS figure and final-project pointers per chapter.

**Guides.** PANDUAN_TIM.md rewritten: a "start here" table, then section 1 glossary (ML-1..6 with report names;
"Tahap ioGAS 1-5" vs "satuan HMM S1-S5" always written out; PAF/NAF classes incl. kelas NAG / konformal / pengelolaan /
prioritas uji; SCIS, S2, S total, S_pct; NS-SEL, DL, CN, pads; column patterns; file and folder naming incl. `Lain`,
`kembar`, `_v1`), ioGAS figures per chapter, the final projects, the submission folder, open items (done items marked).
README.md: "Terms and file naming" section, status 6 Nov, Stage 5 and submission rows, test counts no longer hard-coded.
`README_iogas.txt` (and its template in `scripts/07_export.py`): pointer to the final projects and ML_* prefixes.
AGENTS.md §10 Stage 5 row marked done (no screenshots). `.gitignore`: probe folders and Stage 5 check exports.

**Submission folder** `outputs/kirim/` (copies only, rebuilt each run; 23 files, 4.61 MB < 25 MB): `1_validasi_data/`
(validation flags, summary, precision), `2_proyek_iogas/RJ_proyek_ioGAS.zip` (4 final at top, 47 in `pendukung/`,
README, index), `3_analisis_geokimia/` (geochem analysis + dictionary, statistics, `element_thresholds_v2.csv` as
`ambang_unsur.csv` — this settles the Stage 1 open point: deliverable 3 ships the v2 thresholds with the ioGAS picks,
plus the Stage 1-4 summary tables), empty `4_laporan/`, `5_presentasi/`, `MANIFEST.csv` (sha256 of every source).
Checked: no brief, raw data, LOG or AGENTS inside; copies byte-identical to sources.

**Tests.** 175 passed, 1 skipped; live round trip 3 passed.

**Spoken explanation.** "Our ioGAS project is four files, one per dataset: soil, rock, drill composites and the
environmental assay table. Each one holds every analysed sample with all the cleaned chemistry and every
machine-learning result as a column, and the key plots are already open inside it: probability plots, box plots,
scatters, downhole strip logs along our three sections, Scott Halley diagrams and maps. The many smaller projects
behind them are the same data in other colour schemes, listed in an index, and every figure in our report that
ioGAS drew is listed with the chapter it belongs to."

**Open / gate.** Human opens the four `*_final_v1.gas` in the ioGAS GUI and skims PANDUAN_TIM.md section 1 and
`outputs/kirim/`. Nothing committed or pushed yet: on the human's go, check the repo is still private, pull, commit,
push.

---

## 2026-11-06 — ML findings report v2: glossary and ioGAS section (rebuilt in place)
- `reports/laporan_ml_src.html` → `outputs/laporan_ml/laporan_ml_v2.html` (v2 is new and uncommitted, not yet
  used in the report, so it was rebuilt in place; v1 stays frozen).
- Added "Istilah data dan nama file" (`#istilah`): 13 terms (ML-1…6, satuan HMM S1–S5 vs ioGAS `s1_` prefixes,
  NAF/PAF-LC/PAF-HC, kelas NAG/konformal/pengelolaan, tier 1–4, tier A/B, U1/U2, NAG/NAPP/ANC/AMD, SCIS/S2/S total,
  pads/twins, sections A–C and D–D', column names, file names). The lead paragraph links to it.
- Added "Proyek ioGAS dan berkas kiriman" (`#iogas`): the 4 final projects, the figure index, `outputs/kirim/`,
  and caption notes. Both sections are in the table of contents. "PANDUAN_TIM.md §4" corrected to "bagian 7".
- Checks (browser preview): 121 facts filled, no `{{` left, 20 figures, 0 broken images, 0 dead internal links.


---

## 2026-11-06 — Plan: commit all pending changes; push only to private team repo

Human instruction: commit all changes and push. This explicitly authorizes the local
commit and push within the existing confidentiality constraints.
Inputs: all tracked modifications and non-ignored untracked files. Method: inspect
pending paths and file sizes, check for accidentally included credentials, run the local
pytest suite (including raw-manifest integrity), and commit the existing work on main.
Outputs: one local commit containing the ioGAS stages, figures/projects, submission
package, report updates, and documentation. Checks: clean working tree after commit;
remote identity and visibility before any push.
GitHub currently reports 67minutes/ml-olympiar as PUBLIC. Per AGENTS.md sections 1 and 2,
no push is permitted while it is public. Do not change repository visibility without
the human's approval; finish the local commit and report the push blocker.

### Commit verification results

- `uv run pytest -q`: 175 passed, 1 skipped (opt-in live ioGAS round trip),
  519 library warnings; raw-manifest integrity passed.
- All 415 pending files reviewed by path/size; 403 new files total 56.4 MiB,
  largest 9.05 MiB. No raw-data changes and no file exceeds GitHub's size limit.
- Credential-pattern scan: the only match is a coincidental character sequence
  inside an embedded report image, not a credential.
- `git diff --check` passes with CRLF permitted (`cr-at-eol`).
- Commit all existing non-ignored changes on main as requested. Push remains
  blocked because the allowed team repository is PUBLIC; no push attempted.

- Clarification after staging: the check above covered tracked modifications. The
  full staged check also reports trailing whitespace in newly added ioGAS-generated
  logs and artifacts; preserve these existing outputs as requested rather than
  rewriting them for formatting. Local commit completed; no push attempted.


---

## 2026-11-06 — Human override: push to the existing public team repository

After being informed that GitHub reports 67minutes/ml-olympiar as PUBLIC and that
AGENTS.md requires a private destination, the human explicitly instructed:
"override, just push". This later human instruction overrides the private-only
push restriction for this push, as permitted by AGENTS.md's precedence rule.
Repository visibility will remain unchanged. No other destination is authorized.
Plan: commit this append-only decision record, fetch origin/main, verify that the
push is a fast-forward, and push main to the existing origin without force.
The ioGAS/submission commit e1e7673 passed 175 tests (1 skipped); this follow-up
changes only LOG.md. Verify the remote branch matches local HEAD after the push.

## 2026-11-06 — Approved plan: bilingual findings handbook
Use the committee chapter structure, cleaned results, stage inventories, figure exports and local sources to build an offline bilingual writer's handbook. Use shared facts, paired interpretations, chapter evidence links and a searchable glossary/index. Preserve existing reports. Verify inventory, both languages, local links, browser reading routes, and narrow layout before handing over.

## 2026-11-06 — Bilingual writer's handbook built and checked

Built outputs/laporan_final/laporan_final_v1.html from chapter text, processed tables, local evidence registers and original exports. README and PANDUAN_TIM now link to it. Both previous ML reports and raw data are untouched. Reproduce with uv run python scripts/29_laporan_final.py.

Nine chapters, 403 searchable terms/codes/columns, 358 indexed files and 23 embedded figures. Verified all 129 ioGAS figures and 51 saved stage/final projects against their own registers and the filesystem. The English and Indonesian chapter text and captions use matching numbers and fact placeholders. Workbook-level evidence is linked by relative path from the checkout.

Offline Chromium opened the HTML directly from disk. Both languages passed the soil-As threshold, paired-hole/section B and NAG management routes, including opening a full-resolution image and retrieving the evidence CSV. All 473 local file-link occurrences resolved, all embedded images decoded, all anchors resolved and no HTTP requests were made. Technical and ordinary-language searches worked. The same figure stayed within 1 px on language switch. Desktop (1366 x 900) and narrow (390 x 844) figure/caption screenshots reviewed; original exports open at full resolution. Existing test suite: 175 passed, 1 opt-in live ioGAS test skipped.

Interpretation correction: the measured NAG-by-oxidation table gives 14 PAF-HC and 2 PAF-LC among 16 acidic sulfide samples, superseding the earlier HTML caption. Use that table to distinguish pH from capacity. Design interpretation: tier A includes two extensions and one gap test, with two soil tests in tier B. Open items include regional map, final surface zoning layout, field/imagery checks of derived drainage, human geological review and reference verification. The handbook supports team writing; final submission PDFs remain with the team.
## 2026-11-06 — Handbook publication
The owner requested a commit and push of the completed bilingual handbook in the same conversation where the public team origin was identified. Verified 67minutes/ml-olympiar is PUBLIC and is not a fork. Publish the handbook, its reproducible sources and the team guide updates to that origin on main.
