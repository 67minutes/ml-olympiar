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
  - Report pages are portrait, but some maps or sections may be landscape if needed.
  - Every reference must be linked and attached in the reference list.
  - The presentation is a PowerPoint exported to PDF.
  - ioGAS v8.3.1; **one licence per team, on one laptop/PC**. ioGAS work is
    single-machine, so plan the human's ioGAS time early.
- The brief contains the ioGAS licence key and committee contacts. Never copy them into
  logs, code or replies, and never push this repo to any remote.

### Deadlines
- Submission: **7 Nov 2026, 23:59 WIB** by email to the committee.
- Presentation: 14–15 Nov 2026. Grading is **60% presentation, 40% report**, so every
  result must be explainable out loud by the team.

### Required deliverables
1. Data validation (CSV)
2. ioGAS project (built by a human in ioGAS; agents prepare inputs)
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
   public git remotes, no pastebins. Local compute only. Keep `data/` in `.gitignore`.
2. **Allowed software:** Microsoft Office, IMDEX ioGAS, QGIS, and other software only if it
   is **free and not pirated**. Python and its open-source libraries are fine. Every
   output must be reproducible locally.
3. **ioGAS must visibly do real work** (Software is worth 25 points). Prepare
   ioGAS-ready CSVs (clean headers, flag columns, cluster labels) so humans can do the
   plotting, probability plots, downhole plots, and classification diagrams in ioGAS.
   Agents cannot drive ioGAS.
4. **Report language is Bahasa Indonesia (EYD), Times New Roman** (16 heading /
   14 subheading / 12 body and captions), black text, portrait, one column, HD figures.
   Figure titles, axis labels and legends go in **Bahasa Indonesia**. Code, comments and
   logs stay in English.
5. **Plagiarism is punished.** Never invent references, DOIs, or quotes. Every claim
   from literature needs a real, verifiable source; mark `[VERIFY]` if unsure.
6. **Never modify `data/raw/`.** Raw files are read-only and frozen.

---

## 3. Data inventory

Original location (Windows):
`C:\Users\mauli\Downloads\Data Peserta Round 2_Olympiar 2026\Data Peserta Round 2_Olympiar 2026\`
(note the doubled folder name). Copy it into `data/raw/` once, untouched.

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
| 1 | Element thresholds (§3) | Gaussian mixture on log10 values per element (BIC to pick components), the objective analogue of Sinclair probability plots | Compare against probability-plot breaks (ioGAS), median+2·MAD, and Tukey fences. Table of thresholds per element per dataset. |
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
data/raw/          # frozen copy of the committee package (read-only, gitignored)
data/interim/      # stage outputs from §5
data/processed/    # final tables: validation_flags.csv, geochem_analysis.csv, ioGAS inputs
src/               # importable modules (io, cleaning, desurvey, ml_*)
scripts/           # numbered runnable steps: 01_semantics.py, 02_coords.py, …
notebooks/         # exploration only; anything used in the report must live in src/ or scripts/
outputs/figures/   # 300 dpi PNG; Bahasa Indonesia labels; versioned names (_v1, _v2)
outputs/maps/      # QGIS projects and exports
gis/               # derived layers: lidar_dem.tif, hillshade.tif, drainage.gpkg (all EPSG:32647)
LOG.md             # append-only decision and results log
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
