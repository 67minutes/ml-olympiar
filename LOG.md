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
