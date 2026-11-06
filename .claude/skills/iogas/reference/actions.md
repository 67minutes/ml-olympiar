# ioGAS 8.3.2 workflow actions: what is verified

Constants live in `src/iogas_project.py`. "Live" = run through `IoGAS.run_workflow` on RJ data, image checked.
Probe scripts and logs: LOG.md 2026-11-06 "ioGAS automation probe 3-6".

| What | Builder call | Constant / class | Live result |
|---|---|---|---|
| Select variables | `w.select(cols)` | `A_SELECT` | OK (uses aliases) |
| Probability plot | `w.plot("Probability Plot", A_PROB_PLOT)` | `DisplayPP$Combined` | OK; log via `A_LOG_Y` |
| XY scatter | `w.plot("XY Plot", A_XY)` | `DisplayScatter$XY` | OK (5 Nov) |
| Histograms | `w.plot("Histograms", A_HIST)` | `DisplayHistogramAction` | OK; log via `A_LOG_HIST`; bars stacked by colour attribute |
| Box plots, common axis | `w.plot("Box Plots", A_BOX)` | `DisplayBWAction` | OK; one box per colour group; log toggle ignored -> log10 columns |
| Box plots, tiled | `w.plot("Box Plots", A_BOX_TILED)` | `DisplayTiledBWAction` | OK; same log note |
| Tukey outliers -> attributes | `w.action("Tukey", A_TUKEY)` | `DisplayBWAction$AttributeRowsByOutlierStatus` | **no effect from a workflow** (6 Nov: colour attribute unchanged); use AAT instead |
| Anomaly Assessment Tool (Tukey per variable) | `w.aat(prefix, log=True, tails="both")` | `analysis.aat.AATCalculateAction` | OK (6 Nov); adds `<prefix><col>-Tukey` text ("+col"/"-col", "*" = far), `TukeySummary`, `AAT Totals`; counts equal a Python Tukey on log10 values. **Select one variable per call**: with several selected it uses only complete-case rows |
| Summary statistics | `w.plot("Summary Statistics", A_STATS)` | `DisplayStatsAction` | opens; **cannot export** (table) |
| Attribute map (plan) | `w.plot("Attribute Map", A_MAP)` | `DisplayAttributeMap` | OK |
| Attribute map 3D | `w.plot("Attribute Map 3D", A_MAP_XYZ)` | `DisplayXYZMap` | OK, plan view only |
| Ternary | `w.plot("Ternary", A_TERNARY)` | `DisplayTernary` | OK (first 3 selected) |
| Built-in diagram | `w.diagram("Exploration/.../Fe vs S with Pyrite Line.xml", overwrite=[...])` | `DiagramAction` + `OpenResourceActionCreator` | OK: Halley Fe vs S, Ca-Fe-S, Al-K-Mg |
| Strip-log set-up | `w.configure_downhole(hole, from, to, holes)` | `RecordablePanelAction` + `MultiLineFieldPanel$Params` | OK; needs `Drillhole` in .gas |
| Strip log, window per hole | `w.strip_log()` | `DisplayStripLog` | OK; with our config all configured holes land in **one window**, in the `configure_downhole` order, one track per variable plus the colour attribute as a category track; depth axis shared, x-scale per hole and track (scripts/25_…) |
| Strip log, stacked | `w.strip_log(stacked=True)` | `DisplayStackedStripLog` | runs, but **sums all selected variables into one cumulative bar per hole** (6 Nov): not for geochem tracks |
| Trace style | `w.trace_mode(frame, "Bar")` | `TracePlotDisplayModeAction` | OK (Line, Bar, OpenBar, Midpoint) |
| Legend window | `w.plot("Legend", A_LEGEND)` | `DisplayLegendAction` | opens; **cannot export** |
| Tile / close all | `w.action("Tile", A_TILE)` / `A_CLOSE_ALL` | `ArrangeWindowsAction$...` | OK |
| Export window image | `w.export_window(path, frame, scale=3)` | `ExportPlotWindowAction` | OK; PNG 1,500-4,100 px at scale 3; no watermark |
| Save project | `w.save_as(path)` | `SaveAction` + `Creator.SaveFile` | OK after `open_gas` (not `open_csv`) |
| Pre-answer a prompt | `w.respond(message, True)` | `<userResponses>` | OK (overwrite-columns prompt) |

Built-in diagram paths are relative to `ip.PROVIDED`; list them under
`%APPDATA%\ioGAS\res.cache\iod\DiagramAndCalc\GAS Diagrams\`. Halley diagrams are in
`Exploration/Porphyry Cu Exploration/Scott Halley/` and need full ICP (RJDH012, 26 rock samples).

Other action classes seen in IMDEX demo workflows (not verified here): `DisplayScatter$YX`, `DisplaySPLOM`,
`DisplayVariableMap`, `DisplayCrosstabAction`, `CalcAction`, `MakeFilterVariableAction`,
`AttributeManagerPanel$AutoAttributeAction`, `ShowHidePointDensityAction`. Copy their XML from
`%APPDATA%\ioGAS\res.cache\iod\DiagramAndCalc\Workflow\*` and verify live before relying on them.

## .gas details used by build_gas
- `specialColumns`: `map_east`, `map_north`, `map_elevation`, `map_epsg` (32647), `id`, `group` (hole ID).
- Drillholes: `<DHOptions>`, `<DownholeVariable_8_2>`, `<DrillholeConfig>` after `extraAttributes2`.
- Shapes: codes 0-8 filled, 9-17 open (`shape = code % 9`).
- Text cells and names use ioGAS escaping (`_`->`_u`, `,`->`_c`, ...); data.csv is cp1252.
