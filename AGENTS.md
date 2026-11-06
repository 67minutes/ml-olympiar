# AGENTS.md — OlympiAR 2026 Round 2: Ramba Joring (Martabe) Geochem + ML

Single source of truth for every coding agent on this repo (Codex, Claude Code, others).
Read this whole file before doing anything. If something here conflicts with a later
instruction from the human, the human wins. Record the change in `LOG.md`.

---

## 1. Mission

Produce the ML and data-analysis backbone for an OlympiAR 2026 (PT Agincourt Resources /
IAGI / MGEI) Round 2 submission: a comprehensive **exploration + environmental** report on
the **Ramba Joring (RJ) prospect, Martabe gold district, North Sumatra**. RJ is a
**high-sulfidation epithermal Au-Cu** system (vuggy silica, quartz-alunite advanced argillic,
enargite/covellite Cu, oxide-dominant gold).

Judges are **mining engineers/geologists**. Optimise for: geological defensibility,
transparent uncertainty, decision relevance (where to drill, how to handle waste).
Novelty matters only if it stays accurate and reliable.

### Source documents
- **`Technical Meeting 2nd Round OlympiAR 2026.pdf`** (repo root, 21 slides): the
  committee's own explanation of Round 2. It sets the theme ("Orebody to Ecosystem:
  Integrating Mining Performance and Environmental Resilience"), the data package, the
  report structure and sub-items, the formatting rules, the deliverables, the grading
  rubric, ioGAS licensing, example ioGAS outputs (slide 19) and the reference papers
  (slide 20). When this file and the brief disagree, **the brief wins on competition
  rules**; flag the difference to the human and log it.
- `data/raw/Geological Resume_OlympiAR_2026.pdf`: geology (see §3).
- Points from the brief not stated elsewhere in this file:
  - Machine Learning is the main theme, weighted **5%** of the score (technical, 100).
  - The bonus counts only **if all sub-parameters are complete**.
  - Every reference must be linked and attached in the reference list.
  - The presentation is a PowerPoint exported to PDF.
  - ioGAS v8.3.1; **one licence per team, on one laptop/PC**. The team's ioGAS machine
    is now the repo owner's PC (see "Roles" below).
- The brief contains the ioGAS licence key and committee contacts. Never copy them into
  logs, code or replies.
- **Shared repo (human instruction, 2026-11-04):** the whole repo, data and brief included,
  lives in the team's **PRIVATE** GitHub repo `67minutes/ml-olympiar`, shared only with
  teammates. This supersedes the earlier "never push" rule. Push only to that private repo,
  never to a public remote or a fork; check it is still private before any push
  (`gh repo view 67minutes/ml-olympiar --json visibility`).

### Roles
- **This repo's owner (the human agents work with) is responsible for the ML, the data
  analysis and the ioGAS work:** cleaning, validation flags, the ML in §6, the CSV/GIS
  outputs that feed the report, and the ioGAS project (deliverable 2).
- **ioGAS (human decision, 2026-11-05).** The owner runs ioGAS on this PC with an IMDEX
  14-day trial licence (expires **19 Nov 2026**; the committee brief does not forbid a
  trial). The old "ioGAS teammate" role is retired: nothing is handed off any more.
- **Agents drive ioGAS** through the project skill `.claude/skills/iogas/SKILL.md`
  (local gRPC server, workflow XML, `.gas` projects built in Python; see §2.3 and §10).
  Agents never click through the GUI by default and never touch the human's own ioGAS
  window.
- Where an ML step compares against ioGAS output (e.g. probability-plot breaks in §6
  task 1), the ioGAS side is produced in this repo by the §10 stages. Keep the ML side
  independent of it, so neither result is tuned to the other.

### Deadlines
- Submission: **7 Nov 2026, 23:59 WIB** by email to the committee.
- Presentation: 14–15 Nov 2026. Grading is **60% presentation, 40% report**, so every
  result must be explainable out loud by the team.

### Required deliverables
1. Data validation (CSV)
2. ioGAS project (built by the repo owner in ioGAS on this PC, driven by agents through
   the ioGAS skill; staged plan in §10; see "Roles")
3. Geochemistry analysis (CSV)
4. Comprehensive report (PDF)
5. Presentation (PDF)

### Mandatory report structure
1. Pendahuluan (Introduction)
2. Location and Regional Geology
3. QAQC & Data Validation: surface + subsurface QAQC, outlier treatment, element
   threshold values, lithology/alteration/mineralisation from supervised/unsupervised ML,
   and ML vs logged comparison.
4. Surface Data: soil, rock, geochemical zonation map, targeting, H/M/L grade zonation via
   unsupervised ML, zone comparison.
5. Drilling Data: database variation, drillhole correlation, geochem-stratigraphy
   (max 3 sections).
6. Environmental Analysis: AMD, PAF/NAF classification **with flowchart**, impact and
   treatment, PAF/NAF clustering via unsupervised ML.
7. Exploration Synthesis: prospect synthesis, next stage (max 4 sections).
   **Bonus:** exploration design map or section.
8. Conclusion
9. References

### Rubric weights (where the points are)
- QAQC & Validation: QAQC 30, Outlier treatment 35, Thresholds 35
- Surface: soil 25, rock 25, zonation 50
- Drillhole: validation 20, correlation 40, geochem-stratigraphy 40
- Environmental: AMD elements 40, PAF/NAF classification & treatment 60
- Synthesis: prospecting 50, further exploration 50
- Report output: format 10, visualisation 30, **software 25**, style/grammar 25,
  references 10
- Main theme **Machine Learning: 100**. Bonus (next exploration design): 100.

---

## 2. Hard constraints (non-negotiable)

1. **Data is CONFIDENTIAL.** Never upload, paste, or send any data to an external
   service: no cloud ML APIs, no `tabpfn-client` (cloud), no hosted notebooks with data, no
   public git remotes, no pastebins. Local compute only. The only allowed remote is the
   team's private GitHub repo (§1 "Shared repo"); `data/` is committed there and nowhere else.
2. **Allowed software:** Microsoft Office, IMDEX ioGAS, QGIS, and other software only if it
   is **free and not pirated**. Python and its open-source libraries are fine. Every
   output must be reproducible locally.
3. **ioGAS must visibly do real work** (Software is worth 25 points). The plots, probability
   plots, downhole strip logs, classification diagrams and outlier tools are drawn by ioGAS
   itself, not by Python. How it works:
   - `src/iogas_project.py` builds the `.gas` projects straight from the cleaned tables
     (same rows and columns, EPSG 32647, ML colour attributes, Bahasa aliases on non-element
     columns and legend titles) and writes the workflow XML.
   - `src/iogas_link.py` runs those workflows through ioGAS's own gRPC server: a second
     ioGAS instance launched with `-gaslink2` on 127.0.0.1 only, so no data leaves the PC.
   - ioGAS exports the figures (PNG, no watermark in exports) and saves the `.gas`
     projects with their plot windows, which form the ioGAS project deliverable.
   - The ioGAS-ready CSVs in `data/processed/iogas/` stay as the source tables.
   See §10 and the skill `.claude/skills/iogas/SKILL.md`.
4. **Report language is Bahasa Indonesia (EYD), Times New Roman** (16 heading /
   14 subheading / 12 body and captions), black text, portrait, one column, HD figures.
   Some maps or sections may be landscape if needed (allowed by the committee brief, §1).
   Figure titles, axis labels and legends go in **Bahasa Indonesia**. Code, comments and
   logs stay in English.
5. **Plagiarism is punished.** Never invent references, DOIs, or quotes. Every claim
   from literature needs a real, verifiable source; mark `[VERIFY]` if unsure.
6. **Never modify `data/raw/`.** Raw files are read-only and frozen.

---

## 3. Data inventory

Original location (Windows):
`C:\Users\mauli\Downloads\Data Peserta Round 2_Olympiar 2026\Data Peserta Round 2_Olympiar 2026\`
(note the doubled folder name). It was copied into `data/raw/` once, untouched, and is committed
in the private team repo, so a clone already has it. `RAW_MANIFEST.sha256` and
`tests/test_raw.py` check it byte for byte; `.gitattributes` keeps git from changing its CRLF
line endings.

CRS everywhere: **UTM WGS84 Zone 47N (EPSG:32647)**. All CSVs have CRLF line endings.

| File | Rows | Key content |
|---|---|---|
| `RJ_DH_OlympiAR_2026/DhCollar.csv` | 19 | `SiteID` RJDH001–RJDH019, `EastUTM`, `NorthUTM`, `RLUTM`, `EndDepth`, `Dip`, `AzimUTM` |
| `RJ_DH_OlympiAR_2026/DhSurvey.csv` | 99 | `DepthAt`, `Dip`, `AzimUTM`, `Method` (REFLEX 80, CC 19) |
| `RJ_DH_OlympiAR_2026/DhAssay.csv` | 2,476 × 78 | Interval assays (see §4.3 for coverage) |
| `RJ_DH_OlympiAR_2026/DhLithology.csv` | 286 | `Lith1Interp` (VANh, VDA, XUS, BFZ, BPM, XUS-l, SCR, XUV-mn, …) |
| `RJ_DH_OlympiAR_2026/DhAlteration.csv` | 707 | `AltFacies` (AA 442, SI 158, AR 77, UA 18, PP 12), `SilicaInt`, `AluniteInt`, `KaolinInt`, `AltMin1/2` |
| `RJ_DH_OlympiAR_2026/DhMineralisation.csv` | 2,684 | `DomMin1` (hm, py, Hm, Py, lm, UM, …), `SecMin1` |
| `RJ_DH_OlympiAR_2026/DhAlterationOxide.csv` | 3,017 | Oxidation state stored in **`Comments`** (Oxide / Sulphide / Transition; 127 null), `WRAltOxidPcnt` |
| `RJ_SF_OlympiAR_2026/PTRockSampling.csv` | 469 × 92 | Rock grabs: `Easting`, `Northing`, `Elevation`, `Lithology`, `IntrpAltFa`, `RKOutcropT`, assays |
| `RJ_SF_OlympiAR_2026/PTSoilSampling.csv` | 259 × 85 | Soil grabs: `Easting`, `Northing`, `Elevation`, assays (lithology/alteration empty) |
| `RJ_TOPO_OlympiAR_2026/ConTour Lidar 5m.TAB` (+ .DAT/.MAP/.ID/.IND) | 1,309 lines | MapInfo 5 m lidar contours. **Elevation field is `Z_Avg`** (NOT `String_Num`). Readable with `geopandas`/`pyogrio`. |
| `Geological Resume_OlympiAR_2026.pdf` | — | Martabe/RJ stratigraphy, structure (NE-striking sub-vertical mineralised zones), alteration zoning, oxidation 40–100 m+ |

**Missing vs the technical-meeting brief:** River `.shp`, DEMNAS `.tiff`, and Topography
`.dxf` are listed in the brief but not in the package. None of them blocks the work.
Handle them as follows:

- **Topography `.dxf`: not needed.** The 5 m lidar contours (MapInfo TAB) cover the
  prospect (bounds ≈ E 506433–507790, N 167638–169000); only one rock sample falls
  outside. Interpolate the contours (`Z_Avg`) into a **lidar DEM** (TIN or similar, ~2–5 m
  cell) and use it for maps, sections, hillshade and the surface-Z re-drape. Save it as
  `data/interim/lidar_dem.tif` and record the interpolation method in `LOG.md`.
- **DEMNAS: optional, regional context only.** Use it for the location / regional
  geology map (report §2) and for hillshade beyond the lidar extent. It is public data
  from BIG (Badan Informasi Geospasial), so the human can download it and it must be
  cited. Do not use it inside the prospect where the lidar DEM is better.
- **Rivers: derive them, don't wait.** Needed for the environmental section (AMD flow
  paths and receptors) and the bonus drill design (buffers). Build a stream network from
  the lidar DEM: fill sinks → flow direction/accumulation → stream extraction (QGIS
  GRASS `r.watershed` / `r.stream.extract`). Caveat: contour-derived DEMs produce
  artifacts on flat ground, so check the network against satellite imagery and flag
  doubtful reaches. Label it "derived drainage (lidar)" in every figure. If the
  committee later supplies the official river layer, swap it in, compare, and log the
  differences.
- The human may ask the committee for the river layer. Treat it as a bonus, not a
  dependency.

Date formats differ: assay `LabJobDate` is `d/mm/yyyy` (dayfirst), rock `DateCollec` is an
integer `yyyymmdd`, soil `DateCollected` is `dd/mm/yyyy`.

---

## 4. Verified findings (already checked, do not rediscover; DO cite in report)

### 4.1 Clean
- No interval overlaps, gaps, zero/negative lengths, or depths past `EndDepth` in any of
  the five downhole tables.
- No duplicate `SampleID` in assays or surface files.
- Collar `Dip`/`AzimUTM` match the first survey station for every hole.
- Collar RL vs lidar: all within ~2 m except RJDH002 (−7.8 m) and RJDH006 (−5.1 m),
  probably pad cuts. Flag, don't change.

### 4.2 Problems to fix or flag
1. **Surface zeros mean "not analysed", not 0 ppm.** Example: 443/469 rock samples show
   Ca = 0. Convert 0 → NaN for all surface assay columns before any statistic or ML,
   otherwise clusters will separate *lab batches*, not geology.
2. **Sparse multi-element coverage.**
   - Drillholes: Au, Ag, As, Cu complete (2,466; 10 null rows are `SampleType=NS-SEL`,
     i.e. not sampled). Fe/Ba/Pb/Sb/Zn/Mo/Mn only 397 rows (RJDH001 + RJDH012). Full ICP
     suite plus `S_PCT` only in **RJDH012** (118 rows). Many columns are entirely empty:
     Cs, Hf, Ge, In, B, Be, Pd, Se, P, Rb, Re, Tl, U, Th, `Au_Rpt1_PPM`,
     `Au_Split1_PPM`, `SizingPCT`.
   - Rock: Au/Ag/Cu complete, As 426, Zn/Pb 350, Sb 343, Hg 332, full ICP only 26.
   - Soil: Au, Ag, Cu, As, Zn, Hg, Sb, Pb complete (W 251, Ba 158). **Soil is the
     cleanest dataset for surface clustering.**
3. **No QAQC samples.** Repeat and split columns are empty: no standards, blanks or
   duplicates. State this explicitly. Use internal checks instead (items 4, 5, 6).
4. **Cyanide-soluble > total.** `AuCNPPM` > 1.1 × `AuPPM` in 125/979 pairs; Ag in
   173/1,267. This is the nugget effect / aliquot heterogeneity. Use it as a gold
   precision estimate, not a deletion criterion.
5. **CN/total Cu median ≈ 0.17.** Not an error. The CN-soluble/total ratio is an
   oxide-vs-sulfide (supergene) indicator, so keep it as a feature where available.
6. **Duplicate rock coordinates:** 13 rows share XY with another sample. Example:
   507056.195 / 168744.408 has four samples at 25.8–58 g/t Au across lab jobs. Treat genuine
   re-samples as field duplicates and compute relative precision. Flag possible
   coordinate copy errors.
7. **Mixed detection limits across eras** (lab jobs 1998–2017). Ag bottoms at 0.25 in
   2015–2016 jobs vs 0.5 otherwise. For ML, harmonise to the highest DL per element
   (values below it set to DL/2) and record this. Heavily censored: Sb (~50% at min),
   Te (~92%). Exclude these from clustering.
8. **Surface elevations.** Soil `SampleID 1009765` = 36,076 m and `SA-2009751-MPB` = 0 m.
   Versus lidar: rock 40 samples >10 m off (13 >30 m), soil 15 >10 m (6 >30 m).
   Re-drape all surface samples onto lidar `Z_Avg`, keeping the original value in
   `Elev_orig` plus a flag. The rock `Z_Average` field looks unpopulated (0); verify,
   then ignore it in favour of `Elevation`.
9. **Inconsistent codes.** Mineral: `hm`/`Hm`, `py`/`Py`, `lm`/`Lm`, `cy`/`Cy`. Map to
   one case. Lithology: map to the resume groups (VANh/VDA coherent dacite-andesite;
   XUS, XUS-l, BPM, sBPM phreatomagmatic breccia; XUQ-w/b, XUQ-ms, XUIO, XUlo
   hydrothermal breccia; BFZ fault zone; etc.). Keep the original code column.
10. **Sulfur methods are inconsistent.** `SCIS_PCT` in most holes; `S2_SPCT` in RJDH004
    (all), RJDH019 (all), and parts of RJDH006/007/009. No row has both, so no
    cross-calibration is possible. **RJDH001 has no sulfur.** In RJDH012, `SCIS_PCT`
    median 0.32% vs total `S_PCT` 1.10%: a large non-sulfide (sulfate/alunite) S fraction.
    Add `S_method` and never mix methods silently.
11. **Surveys stop short of EOH:** RJDH001 by 82.4 m, RJDH012 51.2 m, RJDH011 34.5 m,
    RJDH014 15.7 m, RJDH003 2.0 m. Extrapolate the last station and flag the extrapolated
    depth range.
12. **Azimuth swings in near-vertical holes** (RJDH001, RJDH019 at about −89°). This is
    instrument behaviour, since azimuth is ill-defined near vertical. Explain it, do NOT
    "fix" it.
13. **Sample lengths 0.1–25.1 m** (median 1.0; the long ones are NS-SEL). Composite to
    1 m, length-weighted, for downhole ML.
14. **Era/location check:** RJDH002/003 (2004 jobs) have median Au 0.04 vs ~0.45
    elsewhere. Probably location, but show boxplots by lab year and by hole to rule out
    lab bias.
15. **Twin-ish pads** (near-identical collars): 005/014, 007/013, 010/011, 016/017,
    008/019. Useful for correlation sections and short-range continuity checks.

### 4.3 Key environmental finding (RJDH012, the only hole with NAG data)
- NAG pH available for 106 samples; 69 have NAG pH < 4.5.
- Joined to oxidation logs: **Sulphide** zone 16 samples, 100% NAG pH < 4.5, high acid
  capacity (~50–90 kg H₂SO₄/t at pH 4.5). **Oxide** zone 90 samples, 59% NAG pH < 4.5, but
  mostly very low capacity (~1–2 kg/t).
- Sulfur barely separates PAF from NAF in the oxide zone (ROC AUC ≈ 0.51 for both
  `SCIS_PCT` and `S_PCT`). Likely stored acidity (jarosite/alunite) rather than sulfide.
- ⇒ Working hypothesis: **three classes**, NAF / PAF low-capacity / PAF high-capacity,
  rather than binary. Check cutoffs and terminology against the AMIRA ARD Test Handbook
  (2002) and cite it `[VERIFY exact thresholds]`.
- Caveats that must appear in the report: one hole, 16 sulfide samples, no ANC measured
  (so NAPP cannot be computed directly; Ca/Mg proxies exist only in RJDH012).

---

## 5. Cleaning pipeline (strict order)

Each stage reads the previous stage's output and writes to `data/interim/`.

1. **Semantics:** surface 0 → NaN; NS-SEL → no-sample; DL harmonisation; censoring
   flags per value (`<el>_cens`).
2. **Coordinates:** re-drape surface Z on lidar; survey extrapolation flags; desurvey
   holes (minimum curvature) to XYZ per interval midpoint.
3. **Codes:** harmonise mineral, lithology and alteration codes; keep originals.
4. **Joins:** attach lithology, alteration, oxidation and mineralisation to assay
   intervals by **midpoint**.
5. **Compositing:** 1 m length-weighted composites for downhole ML.

**Rule: flag, don't delete.** Every issue gets a boolean or text flag column, and
`data/processed/validation_flags.csv` is a required deliverable (it's the audit trail
judges score). Rows are only excluded inside a specific analysis, with the exclusion
logged.

**Outliers come in two kinds.** *Error outliers* (impossible elevation, impossible
values) get fixed or flagged. *Geological outliers* (e.g. 36.5 g/t Au in RJDH015) are
ore: never cut them for interpretation. For ML, use log or log-ratio transforms plus
robust scaling instead of capping.

---

## 6. ML plan (mapped to rubric)

Theme: **ML that knows what it doesn't know.** Every map and class carries an
uncertainty or confidence measure. Feature spaces are small (4–8 elements), so classic
statistical ML is the right tool. No deep learning.

| # | Task (report §) | Method | Validation and must-haves |
|---|---|---|---|
| 1 | Element thresholds (§3) | Gaussian mixture on log10 values per element (BIC to pick components), the objective analogue of Sinclair probability plots | Compare against probability-plot breaks (ioGAS), median+2·MAD, and Tukey fences. Table of thresholds per element per dataset. `thr_probplot_iogas` is filled by Claude's visual picks on ioGAS probability plots, made **blind to the GMM values** (never open `thr_gmm_*` before picking), written back into ioGAS as colour ranges and re-exported; the human spot-checks 3 elements in the ioGAS GUI (§10 Stage 1). |
| 2 | Alteration / oxidation / mineralisation from chemistry (§3) | Random Forest or LightGBM; optional **local** TabPFN (never the cloud client) | **GroupKFold by `SiteID`** (no hole in both train and test). Confusion matrices vs logged labels, SHAP in element units. Expect lithology to score poorly: alteration overprint plus no immobile elements outside RJDH012. Report this as a geological finding, not a failure. |
| 3 | Surface H/M/L grade zonation (§4) | Log or log-ratio transform → PCA → **GMM** (BIC); soil first, rock second | Rank clusters by median Au. Map membership probability (uncertainty map) in QGIS. Zone comparison vs threshold-based anomaly classes. Spatial sanity: clusters should honour NE structural trends. |
| 4 | Downhole geochem-stratigraphy (§5) | **Gaussian HMM** (`hmmlearn`) on 1 m composites (log Au, Ag, As, Cu, CN/total ratios where present); one model across all holes so states are comparable | States by BIC plus interpretability. Check continuity across twin-ish pads. Feeds ≤3 sections. |
| 5 | PAF/NAF clustering (§6) | Unsupervised clustering (GMM) on S (per method), Fe, Ca, Mg, oxidation, alteration; evaluate against RJDH012 NAG labels. Supervised classifier with **Mondrian (class-conditional) conformal prediction**, using jackknife+/cross-conformal given n=106 | Outputs per sample: {NAF}, {PAF-LC}, {PAF-HC} or ambiguous set. Ambiguous samples → "send for NAG testing" list. State the exchangeability limit: valid for RJDH012-like material. RJDH004/019 (S2) and RJDH001 (no S) get lower-confidence flags. Flowchart required. |
| 6 | Drill targeting, bonus (§7) | **Gaussian process = kriging**: anisotropic kernel aligned NE (from resume) + WhiteKernel nugget, on log Au; UCB acquisition to rank candidate collars | Spatial block CV. Present the kriging equivalence explicitly. Proposed holes must respect environmental constraints (buffers on the derived drainage network, PAF-HC zones) and target high value plus high uncertainty. |

General ML rules:
- Fixed random seeds; log every hyperparameter and score to `LOG.md`.
- Transform choice (log10, CLR on a subcomposition, or ilr) must be documented and
  justified; subcomposition CLR is acceptable only with that caveat stated.
- Never claim performance from leaky validation (random K-fold on downhole data is leaky).
- Every model output exported as an ioGAS-ready CSV column (`ML_*` prefix) for plotting.
- Stretch comparators against published workflows: see §9 (gated, not core).

---

## 7. Repo layout

```
data/raw/          # frozen copy of the committee package (read-only; committed to the private repo)
data/interim/      # stage outputs from §5 (ml6_gp.joblib is gitignored: rebuild with 16_… --stage gp)
data/processed/    # final tables: validation_flags.csv, geochem_analysis.csv, ioGAS inputs
                   #   (data/processed/iogas/: ioGAS-ready CSVs + .gas projects built by 22_iogas_link.py)
src/               # importable modules (io, cleaning, desurvey, ml_*)
src/iogas_project.py  # builds .gas projects (data, attributes, EPSG) and workflow XML; no ioGAS needed
src/iogas_link.py     # starts/reuses the local ioGAS gRPC server (-gaslink2) and runs workflows
scripts/           # numbered runnable steps: 01_semantics.py, 02_coords.py, …
notebooks/         # exploration only; anything used in the report must live in src/ or scripts/
outputs/figures/   # 300 dpi PNG; Bahasa Indonesia labels; versioned names (_v1, _v2)
outputs/figures/iogas/  # PNGs exported by ioGAS itself (sM_<name>_v1.png, one prefix per §10 stage)
outputs/iogas_project/  # saved ioGAS projects with plot windows (RJ_<dataset>_sM_v1.gas, *_final_v1.gas)
outputs/maps/      # QGIS projects and exports
iogas/workflows/   # ioGAS workflow XML written by the stage scripts (sM_*.xml)
.claude/skills/iogas/  # agent skill for driving ioGAS (SKILL.md + reference/actions.md)
.cache/            # gitignored: gRPC stubs generated from the local GAS.jar (no IMDEX file in the repo)
gis/               # derived layers: lidar_dem.tif, hillshade.tif, drainage.gpkg (all EPSG:32647)
LOG.md             # append-only decision and results log
README.md          # English overview: status, deliverables, how to reproduce
PANDUAN_TIM.md     # Bahasa team guide: files, key numbers and spoken explanations per report chapter
```

### GIS tooling
- QGIS (and a QGIS MCP server) will be installed later by the human, when needed. Until
  then, do GIS preprocessing in Python (`geopandas`/`pyogrio` for the MapInfo contours,
  `scipy`/`rasterio` for DEM interpolation) and write standard GeoTIFF/GeoPackage files
  that QGIS can open directly.
- Once QGIS is available, final maps and sections are made in QGIS (an allowed program
  and part of the Software score). Python-made figures are fine for charts, not for the
  final maps.
- Do not assume a QGIS MCP server exists. Check for it, and if it's absent, prepare the
  layers and a short click-by-click note for the human instead.

---

## 8. Working agreement

- **Plan, then execute.** For any non-trivial step, write the plan (inputs, method,
  outputs, checks) to `LOG.md` first. Execute only after the human approves.
- **`LOG.md` is append-only.** Date, what was done, numbers produced, decisions and why.
  Never rewrite history; supersede with a new entry.
- **Frozen outputs.** Once a figure or table goes into the report, never overwrite it.
  Write a new version.
- **Ask before:** changing a cleaning rule in §5, dropping data, or adding a method not
  in §6.
- **Keep the human able to defend it.** For every ML result, also produce a 3–5 line
  plain-language explanation (in `LOG.md`) that a teammate could say aloud in the
  presentation.
- When unsure whether something is an error or geology, flag it and ask. Don't guess.

---

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

---

## 10. ioGAS work (staged)

Approved plan (2026-11-05): the repo owner does all ioGAS work on this PC (§1 "Roles"), with
agents driving ioGAS through `.claude/skills/iogas/SKILL.md`. Every agent (Codex included: the
skill is plain Markdown) reads it and `reference/actions.md` before any ioGAS step. Why it matters (brief slides 8–10, 12, 14, 19): ioGAS is the named tool for plotting,
statistics and downhole plots; deliverable 2 is the ioGAS project; Software is worth 25 points,
and ioGAS figures feed QAQC, Surface, Drillhole and Environmental (100 points each).

Stages are ordered by report need. Every stage saves its own `.gas`, so a usable deliverable
exists after each one.

| Stage | Report § / rubric | ioGAS content |
|---|---|---|
| 0 Foundation | (all) | Action catalogue in `src/iogas_project.py` and `.claude/skills/iogas/reference/actions.md`. Verified live from workflows (6 Nov): probability plot, XY, histogram (log ok), box plots common/tiled, summary stats, attribute map, 3D map (plan view only), ternary, Scott Halley Fe-vs-S / Ca-Fe-S / Al-K-Mg diagrams, strip logs per hole and stacked (Bar trace), HD export at scale 3 (1,500–4,100 px wide, no watermark), Save As. Drillhole support in `build_gas`; Bahasa alias rule (below); the skill; these doc updates |
| 1 QAQC & thresholds | §3: QAQC 30, outliers 35, thresholds 35 | Probability-plot grids (soil, rock, DH composites; usable elements only); blind threshold picks → `thr_probplot_iogas` in `element_thresholds.csv` plus a comparison table vs GMM/MAD/Tukey (new versioned file); Tukey outliers + Anomaly Assessment Tool; AuCN vs Au and duplicate-pair scatters (precision); box plots by lab year and by hole (finding 14) |
| 2 Surface | §4: soil 25, rock 25, zonation 50 | Attribute maps of soil/rock coloured by ML zone and by threshold class; Au–As–Cu scatters by zone; box plots per zone (zone comparison); rock by alteration (`IntrpAltFa`); Al-K-Mg ternary (Halley) on the 26 full-ICP rocks |
| 3 Drillhole | §5: correlation 40, geochem-strat 40 | Stacked strip logs per hole (Au, Ag, Cu, As as `*_log10` columns) coloured by HMM state / alteration / oxidation; twin pads 005/014, 010/011, 016/017 side by side; XYZ view of section lines A–C (rotation is not scriptable: plan view from workflows, any rotated view set by hand in the GUI) |
| 4 Environmental | §6: AMD 40, PAF/NAF 60 | RJDH012: NAG pH vs S by oxidation, Halley Fe vs S pyrite line and Ca-Fe-S ternary (need an element-named `S_pct` column, e.g. `S_pct = S_total_pct`, stated in the caption), AMD-element box plots by PAF class, strip log of PAF class + NAG pH; DH assays coloured by `ML_paf_kelas` |
| 5 Project & polish | Deliverable 2, Software 25 | Done 6 Nov (`scripts/27_iogas_s5_final.py`, `src/iogas_s5.py`): four final projects `outputs/iogas_project/RJ_{tanah,batuan,bor_komposit,lingkungan}_final_v1.gas` (all CSV columns + stage-derived columns, key windows); Bahasa indexes `indeks_proyek_iogas.csv`, `BACA_SAYA.txt`, `outputs/figures/iogas/indeks_gambar_iogas.csv`; threshold statement → `laporan_ml_v2.html`; glossary in README/PANDUAN; submission folder `outputs/kirim/` (`scripts/28_kirim.py`). **No GUI screenshots** (human decision 6 Nov) |

**Pattern per stage (1–5).** LOG plan entry → `scripts/2N_iogas_sM_<name>.py` builds the `.gas`
(Bahasa aliases, ML colours, EPSG 32647) and workflow XML into `iogas/workflows/sM_*.xml` → runs them
through `src/iogas_link.py` → exports `outputs/figures/iogas/sM_<name>_v1.png` → saves
`outputs/iogas_project/RJ_<dataset>_sM_v1.gas` (windows kept) → asserts (files exist, row counts read
back from ioGAS equal the CSV, EPSG kept in the saved `.gas`, PNG ≥ 2,000 px wide where scale 3 allows; small windows give ~1,500 px) → the agent reviews
the exported thumbnails (right variables, log axes, Bahasa labels, legend) → LOG results, numbers and a
3–5 line spoken explanation → human gate.

**Gates.**
- Stage 0: the human reviews the skill and docs diff, plus one sample export per new plot type, before
  Stage 1 starts.
- Every later stage ends at a human gate (above). Thresholds: the human spot-checks the picks for
  3 elements in the ioGAS GUI, and the comparison table states agreement with the GMM honestly (no
  "better" claims).

**Rules for all stages.**
- Data only on localhost. Start or kill only our own `-gaslink2` instance; never drive or close the
  human's own ioGAS window. Never quote the brief's licence password or contact numbers.
- Flag, don't delete. Frozen outputs: write `_v2` instead of overwriting.
- Bahasa Indonesia where ioGAS lets us set it: aliases of non-element columns and legend titles (e.g.
  `ML_hmm_nama` → "Status HMM"). **Never alias element columns** (`Au_ppm`, `Fe_pct`, `AuCN_ppm`): ioGAS
  parses element and unit from the display name for unit conversion and built-in diagrams, and
  `build_gas` refuses such aliases. Element axes therefore read `Au_ppm`; explain this in the caption.
  Workflows refer to columns by alias, so pass the same aliases to `Workflow`.
- Known limits: box plots and strip logs ignore log toggles (plot `<el>_log10` columns instead); the
  Summary Statistics and Legend windows cannot be exported as images (keep them in the saved `.gas`);
  ioGAS prompts stall a workflow unless pre-answered (`Workflow.respond`, `diagram(overwrite=...)`).
- No new ML method: Tukey/Anomaly Assessment results are reported as ioGAS outputs, not as replacements
  for the §6 methods.
- Always open data from a `.gas` (`open_gas`), never `open_csv`, when the workflow saves the project.
- If time runs short, cut within a stage (fewer elements); never skip saving that stage's `.gas`.
- Check: `uv run pytest -q` after each stage; `IOGAS_LIVE=1 uv run pytest tests/test_iogas_link.py`
  for the live round trip.
- Nothing is committed or pushed unless the human asks.
