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
