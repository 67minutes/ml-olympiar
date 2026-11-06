---
name: iogas
description: Drive the local ioGAS 8.3 install from Python for the OlympiAR report - build .gas projects (coordinates, EPSG, ML colours, Bahasa legend titles, drillhole set-up), run ioGAS workflows over its localhost gRPC server, export HD plot images and save ioGAS projects. Use for any ioGAS plot, export or project-save task in this repo (probability plots, histograms, box plots, Tukey outliers, maps, strip logs, ternaries, Scott Halley diagrams).
---

# ioGAS automation (ml-olympiar)

ioGAS is the repo owner's job (IMDEX 14-day trial on this PC, licence `gas.single.eval`, expires 19 Nov 2026).
Agents drive it; the human checks results. Everything stays on this machine: the gRPC server listens on
127.0.0.1 only, and nothing in this workflow sends data anywhere.

Code: `src/iogas_project.py` (writes .gas and workflow XML, no ioGAS needed), `src/iogas_link.py` (starts ioGAS
and talks gRPC), `scripts/22_iogas_link.py` (hand-off .gas projects). Verified action list with notes:
`reference/actions.md` (this folder). History: `LOG.md` 2026-11-05/06 "ioGAS automation probe" entries.

## Rules
- **Never touch the human's own ioGAS window.** `IoGAS()` starts a second instance only if port 25000 is
  free and kills only the process it started. If the port is already in use by the human's session, stop and
  ask; do not reuse it.
- Never quote the ioGAS licence key or committee contacts from the brief (slide 17).
- Frozen outputs: never overwrite a figure or `.gas` that is in the report; write `_v2`.
- ioGAS figures: Bahasa titles/legends where ioGAS lets us set them (aliases, legend titles); element axes
  stay `Au_ppm` style (see Gotchas).

## Recipe
```python
from src import iogas_project as ip
from src.iogas_link import IoGAS

AL = {"ML_hmm_nama": "Status HMM", "Status_Oksidasi": "Zona oksidasi"}   # Bahasa display names (non-element cols)
gas = ip.build_gas(df, "outputs/iogas_project/RJ_x_v1.gas",
                   special=ip.SpecialColumns(east="X", north="Y", elevation="Z", epsg=32647,
                                             sample_id="SampleID", group="HoleID"),     # group: drillholes only
                   drillhole=ip.Drillhole("HoleID", "From", "To"),                   # drillholes only
                   colour_by="ML_hmm_nama", colours={...}, colour_order=[...],       # legend title = alias
                   shape_by="Status_Oksidasi", aliases=AL)

w = ip.Workflow("s3 strip logs", export_dir=OUTDIR, aliases=AL)   # same aliases as build_gas
w.select(["Au_ppm", "Cu_ppm", "As_ppm"])          # column names; translated to aliases for ioGAS
w.configure_downhole("HoleID", "From", "To", ["RJDH005", "RJDH014"])
fr = w.strip_log()                                # all holes in one window, a track per variable
w.trace_mode(fr, "Bar")
w.export_window(OUTDIR / "s3_strip_v1.png", fr)   # scale 3 -> ~2,000-4,000 px wide
w.save_as(OUTDIR / "RJ_DH_s3_v1.gas")             # keeps windows, EPSG, drillhole set-up
with IoGAS(log=OUTDIR / "iogas.log") as g:
    g.open_gas(gas)                               # always a .gas (Save As fails after open_csv)
    g.run_workflow(w.write(OUTDIR / "s3.xml"))    # raises IoGASError if any operation failed
```
Then **look at every exported PNG** (Read it; make a downsized contact sheet for many) before reporting.

## Gotchas (all verified live, 5-6 Nov 2026)
- **Workflows refer to columns by alias.** Pass the same `aliases` to `Workflow`; it translates.
- **Do not alias element columns** (`Au_ppm`, `Fe_pct`, `AuCN_ppm`). ioGAS reads element and unit from the
  display name for unit conversion and built-in diagrams; `build_gas` refuses such aliases.
- Built-in diagrams need element-named columns: Halley Fe-S / Ca-Fe-S need `S_pct` or `S_ppm` (our
  `S_total_pct` is not recognised: add `S_pct = S_total_pct` in the .gas and say so in the caption).
- A diagram that recreates converted columns (Fe_ppm, S_ppm...) prompts "OK to overwrite columns ...?";
  pass `overwrite=[...]` to `diagram()`. Any unanswered prompt stalls the run until someone clicks (minutes);
  find the exact text in the log (`User asked : ...`) and add `w.respond(text, True)`.
- Windows are found by the UUID of the operation that opened them; titles are cosmetic.
- Log axes: `A_LOG_Y` works on probability plots (values on Y) and XY; `A_LOG_HIST` on histograms.
  **Box plots and strip logs ignore log toggles** in workflows: add `<el>_log10` columns to the .gas
  (alias e.g. "log10 Au (ppm)") and plot those.
- Not exportable as images (ioGAS NullPointerException): Summary Statistics (table) and the Legend window.
  Keep them open in the saved project; draw a small legend in Python with the same palette if a figure needs one.
- Colour/shape attributes come from `build_gas` (one .gas per colour scheme). ioGAS auto-attribute inside a
  workflow uses ioGAS palettes, not ours.
- The on-screen "DEMONSTRATION COPY" watermark is not in exported PNGs; it is in GUI screenshots.
- The ioGAS launcher is single-instance, so `start_server()` runs the bundled JRE directly with `-gaslink2`.
- `run_workflow` returns `files` (exported paths). Check each exists; ioGAS sometimes reports success for a
  window op that silently did nothing (e.g. log toggles above), so check the image, not just the status.
- XYZ map ("Attribute Map 3D") opens in plan view; rotating it to a section is not scripted yet.
- Outliers: use `w.aat(...)` (Anomaly Assessment Tool), one selected variable per call: with several
  variables it keeps only rows that have all of them. The box-plot "Tukey attribute" toolbar action
  (`A_TUKEY`) does nothing from a workflow. Box plots themselves are Tukey box plots.
- **Attribute maps: export them last in the workflow.** Exporting straight after opening (or after one
  histogram) raced the map rendering: `ConcurrentModificationException`, "Unable to write to file", 0-byte PNG
  (6 Nov). With 3-4 other exports in between it always worked (`scripts/24_iogas_s2_surface.py` `map_open`).
- A saved .gas stores `data.csv` columns under their **aliases** ("Zona ML", "log10 Au (ppm)"): rename back
  with the inverse alias map before analysing read-back data.
- **Strip logs: use `strip_log()` (not `stacked=True`).** The stacked mode adds the selected variables into one
  cumulative bar per hole. `strip_log()` puts every configured hole in one window, in the order passed to
  `configure_downhole`, with one track per variable; each hole/track gets its own x-scale (say so in captions).
  Six holes x 5 tracks export at ~4,750 px wide (`scripts/25_iogas_s3_drillhole.py`, 6 Nov).
- **No commas in aliases.** ioGAS writes aliases unescaped into the saved `data.csv` header, so "pH 4,5" split
  one column into two (6 Nov). `build_gas` now refuses them; write "pH 4.5" and give the Bahasa form in captions.
- Halley Fe vs S then Ca-Fe-S in one workflow ran without an overwrite prompt (RJDH012, 6 Nov); the pre-answers
  in `scripts/26_iogas_s4_environmental.py` stay as a guard. Shape attributes (`shape_by`) show on XY and
  diagrams but not on strip logs (colour track only).
- Text written by ioGAS into a saved .gas keeps its escaping (`Au_uppm`): `gas_unescape` before matching.

## Debugging
Read the log passed to `IoGAS(log=...)`: `Running operation i of n`, `failed`, `EX ...`, `Caused by`,
`User asked`. A missing-column error usually means an alias mismatch.
