"""Build ioGAS 8.3 project files (.gas) and workflow files (.xml) from Python.

No ioGAS needed here: this module only writes files. Running them is in `src/iogas_link.py`.

Formats were read from ioGAS 8.3.2's own files (demo projects, demo workflows, XStream alias files and
class fields in GAS.jar); see LOG.md 2026-11-05 "ioGAS automation probe" 1 and 2.

.gas = ZIP of
  data.csv      header row (ignored by ioGAS) + rows + 4 index columns into the attribute lists
                (__gas__extra__ = filter, colour, shape, size; 0-based)
  metadata.xml  column names/types, special columns (coordinates, EPSG, sample ID), attribute legends
  workspace.xml open plot windows (left empty here; plots come from workflows)
Names and text cells use ioGAS escaping ("_" -> "_u", "," -> "_c", ...), see `gas_escape`.
"""
from __future__ import annotations

import datetime as _dt
import io
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape as _xml

import numpy as np
import pandas as pd

GAS_VERSION = "8.3"
WORKFLOW_BUILD = "300608"  # ioGAS 8.3.2 build that wrote the formats used here

_ESCAPES = [("_", "_u"), ("&", "_a"), ("<", "_l"), (">", "_g"), ('"', "_q"), (",", "_c"), ("\t", "_t")]
DEFAULT_COLOUR = -16777216  # opaque black, ioGAS "Default Colour"
ELEMENT_COLUMN = re.compile(r"^[A-Z][a-z]?(CN)?_(ppm|ppb|pct)$")  # e.g. Au_ppm, Fe_pct, AuCN_ppm


def gas_escape(s: str) -> str:
    """ioGAS escaping for names and text cells ('_' first, as in ioGAS's metadata.xml note)."""
    for a, b in _ESCAPES:
        s = s.replace(a, b)
    return s


def gas_unescape(s: str) -> str:
    for a, b in reversed(_ESCAPES):
        s = s.replace(b, a)
    return s


def argb(hex_rgb: str) -> int:
    """'#rrggbb' -> signed 32-bit opaque ARGB int, the way ioGAS stores colours."""
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected #rrggbb, got {hex_rgb!r}")
    return (0xFF000000 | int(h, 16)) - (1 << 32)


@dataclass
class SpecialColumns:
    east: str | None = None
    north: str | None = None
    elevation: str | None = None
    sample_id: str | None = None
    epsg: int | None = None
    projection: str | None = None  # free text; ioGAS rewrites it from the EPSG code
    group: str | None = None  # drillhole ID column (ioGAS "group")

    def xml(self) -> str:
        out = []
        for tag, col in [("map_east", self.east), ("map_north", self.north),
                         ("map_elevation", self.elevation), ("id", self.sample_id)]:
            if col is not None:
                out.append(f"<{tag}>{_xml(gas_escape(col))}</{tag}>")
        if self.projection is not None:
            out.append(f"<map_proj>{_xml(self.projection)}</map_proj>")
        if self.epsg is not None:
            out.append(f"<map_epsg>{int(self.epsg)}</map_epsg>")
        if self.group is not None:
            out.append(f"<group>{_xml(gas_escape(self.group))}</group>")
        return "<specialColumns>" + "".join(out) + "</specialColumns>"


@dataclass
class Drillhole:
    """Downhole interval columns; lets ioGAS strip logs run without the Configure dialog."""
    hole: str
    from_: str
    to: str

    def xml(self) -> str:
        h, f, t = (_xml(gas_escape(c)) for c in (self.hole, self.from_, self.to))
        return (f"<DHOptions><fromField>{f}</fromField><toField>{t}</toField></DHOptions>\n"
                f'<DownholeVariable_8_2><AbstractVariable type="interval"><DHFromColumn>{f}</DHFromColumn>'
                f"<DHToColumn>{t}</DHToColumn>"
                '<ContinuousVariableFormat type="numeric" key="Depth" displayName="Depth" reverse="true"/>'
                "</AbstractVariable></DownholeVariable_8_2>\n"
                f"<DrillholeConfig><groupColumnName>{h}</groupColumnName><gapThreshold>1.0</gapThreshold>"
                "</DrillholeConfig>\n")


def _levels(vals: pd.Series, order: list[str] | None) -> list[str]:
    levels = list(order) if order is not None else [v for v in pd.unique(vals.dropna())]
    unknown = set(vals.dropna().unique()) - set(levels)
    if unknown:
        raise ValueError(f"values not in order: {sorted(unknown)}")
    return levels


def colour_index(values: pd.Series, colours: dict[str, str] | None = None,
                 order: list[str] | None = None) -> tuple[list[tuple[str, int]], np.ndarray]:
    """Legend entries [(name, argb)] (entry 0 = Default Colour) and a per-row index into them.

    Missing values keep index 0 (Default Colour). Levels not in `colours` are grey.
    """
    vals = values.astype("string")
    legend = [("Default Colour", DEFAULT_COLOUR)]
    idx = np.zeros(len(vals), dtype=int)
    for i, lv in enumerate(_levels(vals, order), start=1):
        legend.append((str(lv), argb((colours or {}).get(lv, "#808080"))))
        idx[(vals == lv).fillna(False).to_numpy()] = i
    return legend, idx


def shape_index(values: pd.Series, shapes: dict[str, int] | None = None,
                order: list[str] | None = None) -> tuple[list[tuple[str, int]], np.ndarray]:
    """Legend entries [(name, shapeCode)] (entry 0 = Default Shape) and a per-row index into them.

    ioGAS shape codes 0-8 are filled symbols (0 = circle), 9-17 the same symbols open.
    Without `shapes`, levels get codes 1, 2, 3, ... in order.
    """
    vals = values.astype("string")
    legend = [("Default Shape", 0)]
    idx = np.zeros(len(vals), dtype=int)
    for i, lv in enumerate(_levels(vals, order), start=1):
        legend.append((str(lv), int((shapes or {}).get(lv, i % 18))))
        idx[(vals == lv).fillna(False).to_numpy()] = i
    return legend, idx


def _metadata_xml(df: pd.DataFrame, numeric: set[str], special: SpecialColumns,
                  colour_title: str, legend: list[tuple[str, int]],
                  shape_title: str = "", shape_legend: list[tuple[str, int]] | None = None,
                  aliases: dict[str, str] | None = None, drillhole: Drillhole | None = None) -> str:
    aliases = aliases or {}
    cols = "".join(
        f"<column><origonalName>{_xml(gas_escape(c))}</origonalName>"
        f"<aliasName>{_xml(gas_escape(aliases.get(c, c)))}</aliasName>"
        f"<type>{'Numeric' if c in numeric else 'Text'}</type><derived>false</derived></column>\n"
        for c in df.columns)
    colour = "".join(f"<colourAttribute><name>{_xml(gas_escape(n))}</name><colour>{v}</colour>"
                     f"<visible>true</visible></colourAttribute>" for n, v in legend)
    shape = "".join(f"<shapeAttribute><name>{_xml(gas_escape(n))}</name><shape>{code % 9}</shape>"
                    f"<filled>{'true' if code < 9 else 'false'}</filled><shapeCode>{code}</shapeCode>"
                    f"<visible>true</visible></shapeAttribute>"
                    for n, code in (shape_legend or [("Default Shape", 0)]))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<GASMetaData>\n<columns>\n' + cols + "</columns>\n"
        + special.xml() + "\n<variableSelectionHistory></variableSelectionHistory><labelSelection></labelSelection>\n"
        f"<colourAttributes><title>{_xml(gas_escape(colour_title))}</title>{colour}</colourAttributes>\n"
        f"<shapeAttributes><title>{_xml(gas_escape(shape_title))}</title>{shape}</shapeAttributes>\n"
        "<sizeAttributes><title></title><sizeAttribute><name>Default Size</name><size>6</size>"
        "<visible>true</visible></sizeAttribute></sizeAttributes>\n"
        "<extraAttributes2><title></title><extraAttribute><name>Default Filter</name>"
        "<visible>true</visible></extraAttribute></extraAttributes2>\n"
        + (drillhole.xml() if drillhole else "") + "</GASMetaData>\n")


_WORKSPACE_XML = (
    '<?xml version="1.0" encoding="UTF-8" ?>\n<net.ioglobal.gas.workspace.Workspace>\n  <m__creatorList/>\n'
    "  <m__checkpoints>\n    <m__list/>\n  </m__checkpoints>\n"
    "  <m__desktopSize>\n    <width>1600</width>\n    <height>900</height>\n  </m__desktopSize>\n"
    "</net.ioglobal.gas.workspace.Workspace>\n")


def build_gas(df: pd.DataFrame, out: str | Path, *, special: SpecialColumns | None = None,
              colour_by: str | None = None, colours: dict[str, str] | None = None,
              colour_order: list[str] | None = None, colour_title: str | None = None,
              shape_by: str | None = None, shapes: dict[str, int] | None = None,
              shape_order: list[str] | None = None, shape_title: str | None = None,
              aliases: dict[str, str] | None = None, drillhole: Drillhole | None = None,
              numeric: list[str] | None = None, source_note: str = "") -> Path:
    """Write `df` as an ioGAS project. Row order and row count are preserved; NaN -> empty cell.

    `aliases` maps column -> display name (ioGAS "alias": shown on axes and in lists; Bahasa labels go here).
    Legend titles default to the attribute column's alias.
    """
    out = Path(out)
    special = special or SpecialColumns()
    aliases = aliases or {}
    need = [special.east, special.north, special.elevation, special.sample_id, special.group, colour_by, shape_by,
            *aliases]
    if drillhole:
        need += [drillhole.hole, drillhole.from_, drillhole.to]
    for col in need:
        if col is not None and col not in df.columns:
            raise KeyError(f"column not in data: {col}")
    elem = [c for c in aliases if ELEMENT_COLUMN.match(c) and aliases[c] != c]
    if elem:  # ioGAS reads element and unit from the alias (unit conversion, built-in diagrams)
        raise ValueError(f"do not alias element columns: {elem}")
    commas = [a for a in aliases.values() if "," in a]
    if commas:  # ioGAS writes aliases unescaped into its saved data.csv header, so a comma splits the column
        raise ValueError(f"no commas in aliases: {commas}")
    shown = pd.Series([aliases.get(c, c) for c in df.columns])
    if shown.duplicated().any():
        raise ValueError(f"duplicate column display names: {sorted(set(shown[shown.duplicated()]))}")
    num = set(numeric) if numeric is not None else {c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}
    if colour_by:
        legend, cidx = colour_index(df[colour_by], colours, colour_order)
    else:
        legend, cidx = [("Default Colour", DEFAULT_COLOUR)], np.zeros(len(df), dtype=int)
    if shape_by:
        slegend, sidx = shape_index(df[shape_by], shapes, shape_order)
    else:
        slegend, sidx = [("Default Shape", 0)], np.zeros(len(df), dtype=int)

    data = df.copy()
    for c in data.columns:
        if c not in num:
            data[c] = data[c].map(lambda v: v if pd.isna(v) else gas_escape(str(v)))
    data["__gas__extra__"] = 0
    data[" __gas__color__"] = cidx
    data[" __gas__shape__"] = sidx
    data[" __gas__size__"] = 0
    buf = io.StringIO()
    data.to_csv(buf, index=False, lineterminator="\n", na_rep="")
    stamp = _dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    log = f"{stamp} built by src/iogas_project.py ({len(df)} rows) {source_note}\n"
    ctitle = colour_title if colour_title is not None else aliases.get(colour_by, colour_by or "")
    stitle = shape_title if shape_title is not None else aliases.get(shape_by, shape_by or "")

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("version.txt", GAS_VERSION)
        z.writestr("changelog.txt", log)
        z.writestr("metadata.xml", _metadata_xml(df, num, special, ctitle, legend, stitle, slegend, aliases,
                                                 drillhole))
        z.writestr("data.csv", buf.getvalue().encode("cp1252"))  # ioGAS itself writes windows-1252
        z.writestr("workspace.xml", _WORKSPACE_XML)
    return out


# ---------------------------------------------------------------- workflows

# Action class names (ioGAS 8.3.2), from the demo workflows and GAS.jar. Plots use the current variable selection.
A_SELECT = "net.ioglobal.gas.ui.select.SelectVariablesAction"
A_PROB_PLOT = "net.ioglobal.gas.chart.xy.pp.DisplayPP$Combined"
A_XY = "net.ioglobal.gas.chart.xy.xy.DisplayScatter$XY"
A_HIST = "net.ioglobal.gas.chart.histogram.DisplayHistogramAction"
A_BOX = "net.ioglobal.gas.chart.boxPlot.DisplayBWAction"
A_BOX_TILED = "net.ioglobal.gas.chart.boxPlot.DisplayTiledBWAction"
A_TUKEY = "net.ioglobal.gas.chart.boxPlot.DisplayBWAction$AttributeRowsByOutlierStatus"
A_TERNARY = "net.ioglobal.gas.chart.xy.ternary.DisplayTernary"
A_STATS = "net.ioglobal.gas.chart.stat.DisplayStatsAction"
A_MAP = "net.ioglobal.gas.chart.xy.map.DisplayAttributeMap"
A_MAP_VARIABLE = "net.ioglobal.gas.chart.xy.map.DisplayVariableMap"
A_MAP_XYZ = "net.ioglobal.gas.chart.xy.map.xyz.DisplayXYZMap"
A_DIAGRAM = "net.ioglobal.gas.chart.xy.diagram.menu.DiagramAction"
A_STRIP_LOG = "net.ioglobal.gas.chart.line.DisplayStripLog"
A_STRIP_LOG_STACKED = "net.ioglobal.gas.chart.line.DisplayStackedStripLog"
A_TRACE_MODE = "net.ioglobal.gas.chart.line.TracePlotDisplayModeAction"
A_STRIP_COLOUR = "net.ioglobal.gas.chart.line.ChangeMultiLineColourMode"
A_LEGEND = "net.ioglobal.gas.ui.legend.DisplayLegendAction"
A_LOG_X = "net.ioglobal.gas.chart.xy.LogXAction"
A_LOG_Y = "net.ioglobal.gas.chart.xy.LogYAction"
A_LOG_HIST = "net.ioglobal.gas.chart.histogram.LogHistAction"
A_TILE = "net.ioglobal.gas.action.ArrangeWindowsAction$Tile"
A_CLOSE_ALL = "net.ioglobal.gas.action.ArrangeWindowsAction$CloseAll"
A_EXPORT_WINDOW = "net.ioglobal.gas.action.copy.ExportPlotWindowAction"
A_SAVE = "net.ioglobal.gas.action.file.SaveAction"
A_PANEL = "net.ioglobal.gas.ui.RecordablePanelAction"
A_AAT = "net.ioglobal.gas.analysis.aat.AATCalculateAction"  # Anomaly Assessment Tool (Tukey per variable + totals)
AAT_TAILS = {"both": ("$1", "Upper and Lower Outliers"), "upper": ("$2", "Upper Outliers Only"),
             "lower": ("$3", "Lower Outliers Only")}

PROVIDED = "__provided.resource.cache__/DiagramAndCalc/GAS Diagrams/"  # prefix of ioGAS's built-in diagrams
TRACE_MODES = ("Line", "Bar", "OpenBar", "Midpoint")


def title_list(items: list[str], limit: int = 10) -> str:
    """How ioGAS lists variables/holes in a window title: first 10, then '(+n)'."""
    shown = list(items[:limit]) + ([f"(+{len(items) - limit})"] if len(items) > limit else [])
    return "[" + ", ".join(shown) + "]"


@dataclass
class Frame:
    """Reference to the plot window an earlier operation opened (ioGAS 'actionFrameID')."""
    title: str
    op_uuid: str
    index: int = 0

    def xml(self) -> str:
        return (f"<actionFrameID><title>{_xml(self.title)}</title><id>{self.index}</id>"
                f"<opUUID>{self.op_uuid}</opUUID></actionFrameID>")


def _strip_config(stacked: bool) -> str:
    return ("<windowMode><m__mode>1</m__mode></windowMode><tilingMode><m__mode>12</m__mode></tilingMode>"
            f"<traceMode>{'Stacked' if stacked else 'WindowPerGroup'}</traceMode><isGapEnabled>false</isGapEnabled>"
            "<gapThreshold>1.0</gapThreshold><drawAcrossNulls>false</drawAcrossNulls><isDH>true</isDH>"
            f"<isStacked>{'true' if stacked else 'false'}</isStacked><title>Strip Log</title>"
            "<iconName>downholeplot.15.png</iconName><tooltip>Display strip log (downhole plot)</tooltip>"
            "<groupsInSameWindow>true</groupsInSameWindow>")


@dataclass
class Workflow:
    """Minimal ioGAS workflow writer. Operations run in the order added.

    Later operations find their plot window by the UUID of the operation that opened it (`Frame`); the title
    only labels the step (ioGAS style: "Probability Plot [Au_ppm, As_ppm] ", trailing space).
    ioGAS workflows refer to columns by their alias (display name). Pass the same `aliases` given to
    `build_gas` and use column names everywhere; they are translated here.
    """
    name: str
    export_dir: str | Path | None = None
    description: str = ""
    ops: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    selection: list[str] = field(default_factory=list)
    holes: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    responses: list[tuple[str, bool | str]] = field(default_factory=list)

    def _n(self, col: str) -> str:
        return self.aliases.get(col, col)

    def _op(self, name: str, action: str, creator: str = '<actionCreator class="Creator.Default"/>',
            extra: str = "", state: str = "", changed: bool = False) -> str:
        u = str(uuid.uuid4())
        self.ops.append(f'<Operation.Action uuid="{u}"><name>{_xml(name)}</name><actionName>{action}</actionName>'
                        f"{state}{creator}{extra}<m__stateChanged>{'true' if changed else 'false'}</m__stateChanged>"
                        "</Operation.Action>")
        return u

    def select(self, cols: list[str]) -> str:
        cols = [self._n(c) for c in cols]
        self.columns_used += [c for c in cols if c not in self.columns_used]
        self.selection = list(cols)
        s = "".join(f"<string>{_xml(c)}</string>" for c in cols)
        return self._op(f"Select Variables [{', '.join(cols)}]", A_SELECT,
                        f'<actionCreator class="{A_SELECT}$Creator"><columnList><m__colNames>{s}'
                        "</m__colNames></columnList></actionCreator>")

    def plot(self, name: str, action: str, cols: list[str] | None = None, title: str | None = None) -> Frame:
        """Open a plot of the current selection; returns its window for later operations.

        `title` overrides the window title when ioGAS names that plot differently from `name [cols] `.
        """
        u = self._op(name, action)
        shown = [self._n(c) for c in cols] if cols else self.selection
        return Frame(title if title is not None else f"{name} {title_list(shown)} ", u)

    def action(self, name: str, action: str, frame: Frame | None = None, tab: int | None = None) -> str:
        extra = (frame.xml() if frame else "") + (f"<actionFrameTab>{tab}</actionFrameTab>" if tab is not None else "")
        return self._op(name, action, extra=extra)

    def aat(self, prefix: str = "AAT_", log: bool = True, tails: str = "both", near_and_far: bool = True) -> str:
        """Anomaly Assessment Tool on the current selection (Tukey fences per variable, no Mahalanobis).

        Adds text columns `<prefix><col>-Tukey` ("-Au_ppm" = low outlier, "Au_ppm" = high, trailing "*" = far),
        `<prefix>TukeySummary` and numeric `<prefix>AAT Totals` (outlier count per row). `log=True` computes the
        fences on log10 values. Verified live 6 Nov 2026: counts equal a Python Tukey on the same values.
        """
        cls, label = AAT_TAILS[tails]
        cfg = (f"<m__config><m__nearAndFarOutliers>{str(near_and_far).lower()}</m__nearAndFarOutliers>"
               f'<m__upperLowerEntry class="net.ioglobal.gas.analysis.aat.UpperLowerEntry{cls}">'
               f"<m__label>{label}</m__label></m__upperLowerEntry><m__outlierCutoff>0.975</m__outlierCutoff>"
               f"<m__respectVisibility>false</m__respectVisibility><m__logData>{str(log).lower()}</m__logData>"
               "<m__showSummaryStats>false</m__showSummaryStats><m__allData>true</m__allData>"
               "<m__byGroup>false</m__byGroup><m__includeMDist>false</m__includeMDist>"
               f"<m__useLabelInsteadOfCount>true</m__useLabelInsteadOfCount><m__columnPrefix>{_xml(prefix)}"
               "</m__columnPrefix></m__config>")
        return self._op("Anomaly Assessment", A_AAT,
                        f'<actionCreator class="{A_AAT}$AATCalculateActionCreator">{cfg}</actionCreator>', changed=True)

    def respond(self, message: str, answer: bool | str = True) -> None:
        """Pre-answer an ioGAS prompt (exact message text, as in the ioGAS log line 'User asked : ...').

        An unanswered prompt waits for a click in the ioGAS window, so the workflow stalls.
        """
        self.responses.append((message, answer))

    def diagram(self, resource: str, name: str | None = None, overwrite: list[str] | None = None) -> Frame:
        """Open a diagram file: ioGAS built-in (path after `PROVIDED`) or an absolute path to a diagram .xml.

        Diagrams need element columns named like `Fe_pct`/`S_ppm` (no alias) and make unit-converted columns
        (e.g. Fe_ppm, S_ppm). If an earlier diagram already made them, ioGAS asks to overwrite; pass those
        columns as `overwrite` (in ioGAS's order) to answer yes.
        """
        if overwrite:
            self.respond(f"OK to overwrite columns {', '.join(overwrite)} to open diagram?.")
        fn = resource if (resource.startswith("__provided") or Path(resource).is_absolute()) else PROVIDED + resource
        label = name or f"Open Diagram {Path(resource).name}"
        u = self._op(label, A_DIAGRAM, '<actionCreator class="net.ioglobal.gas.workflow.OpenResourceActionCreator">'
                     f"<m__filename>{_xml(fn)}</m__filename></actionCreator>", changed=True)
        return Frame(label + " ", u)

    def configure_downhole(self, hole_col: str, from_col: str, to_col: str, holes: list[str]) -> str:
        """Strip-log set-up (ioGAS 'Select drillholes/Configure downhole plots') for the listed holes."""
        name = "Select drillholes/Configure downhole plots"
        hs = "".join(f"<string>{_xml(h)}</string>" for h in holes)
        st = ('<actionState class="chart.line.MultiLineFieldPanel$Params">'
              f"<m__description>{name}</m__description><configId>Drillhole</configId>"
              f"<groupName>{_xml(self._n(hole_col))}</groupName>"
              f'<varMaker class="chart.line.DHVariableMaker"><m__colNames><string>{_xml(self._n(from_col))}</string>'
              f"<string>{_xml(self._n(to_col))}</string></m__colNames>"
              '<m__format class="chart.line.ContinuousVariableFormat$NumericFormat"><m__displayName>Depth'
              "</m__displayName><m__key>Depth</m__key><m__reverse>true</m__reverse></m__format></varMaker>"
              '<groupProvider class="chart.line.DefaultGroupProvider"><m__groups/></groupProvider>'
              f'<selectedGroups class="list">{hs}</selectedGroups><areAllSelected>false</areAllSelected>'
              f"<config>{_strip_config(False)}</config><showPlots>false</showPlots></actionState>")
        cr = (f'<actionCreator class="Creator.RecordablePanelAction"><m__name>{name}</m__name>'
              '<m__actionFactory class="chart.line.MultiLineFieldPanel$ActionFactory"/></actionCreator>')
        self.holes = list(holes)
        return self._op(name, A_PANEL, cr, state=st, changed=True)

    def strip_log(self, stacked: bool = False, cols: list[str] | None = None, holes: list[str] | None = None,
                  title: str | None = None) -> Frame:
        """Strip log of the current selection for the configured holes (call `configure_downhole` first)."""
        holes = holes if holes is not None else self.holes
        action = A_STRIP_LOG_STACKED if stacked else A_STRIP_LOG
        name = "Stacked Strip Log" if stacked else "Strip Log (window per drillhole)"
        u = self._op(name, action, '<actionCreator class="chart.line.DisplayStripLog$Creator">'
                     f"<m__config>{_strip_config(stacked)}</m__config></actionCreator>")
        return Frame(title if title is not None else
                     f"Strip Log {title_list(holes)} {title_list([self._n(c) for c in cols] if cols else self.selection)} ", u)

    def trace_mode(self, frame: Frame, mode: str = "Bar") -> str:
        """Strip-log trace style: Line, Bar (filled), OpenBar or Midpoint."""
        if mode not in TRACE_MODES:
            raise ValueError(f"mode must be one of {TRACE_MODES}")
        st = ('<actionState class="net.ioglobal.gas.toolbar.AbstractModeChangeAction$State">'
              f'<m__mode class="chart.line.TraceDisplayMode">{mode}</m__mode></actionState>')
        return self._op(f"Change display mode {mode}", A_TRACE_MODE, state=st,
                        extra=frame.xml() + "<actionFrameTab>0</actionFrameTab>")

    def export_window(self, filename: str | Path, frame: Frame, scale: float = 3.0, detail: float = 1.0) -> str:
        """Export a plot window as an image (format from the extension). `scale` multiplies the window's pixel
        size (windows open ~500-1,400 px wide, so 3 gives report-quality images). Windows are found by the
        opening operation's UUID; the title is cosmetic. Table windows (Summary Statistics) cannot be exported."""
        st = (f'<actionState class="{A_EXPORT_WINDOW}$ExportWindowState">'
              f"<m__exportedFilename>{_xml(str(filename))}</m__exportedFilename>"
              '<m__exportConfig class="net.ioglobal.gas.action.copy.ComponentExporter$ComponentExportConfig">'
              f"<scaleX>{scale}</scaleX><scaleY>{scale}</scaleY><detailX>{detail}</detailX><detailY>{detail}</detailY>"
              "</m__exportConfig><m__batch>false</m__batch></actionState>")
        return self._op("Export Window", A_EXPORT_WINDOW,
                        f'<actionCreator class="{A_EXPORT_WINDOW}$Creator"><m__batch>false</m__batch></actionCreator>',
                        frame.xml(), state=st)

    def save_as(self, filename: str | Path) -> str:
        """Save the project. Only works if the data was opened from a .gas file (see LOG.md probe 2)."""
        return self._op("Save As", A_SAVE,
                        f'<actionCreator class="Creator.SaveFile"><m__filename>{_xml(str(filename))}</m__filename>'
                        "<m__saveAs>true</m__saveAs></actionCreator>")

    def xml(self) -> str:
        used = "".join(f"<string>{_xml(c)}</string>" for c in self.columns_used)
        export = ""
        if self.export_dir is not None:
            export = (f"<exportConfig><recordedExportDir>{_xml(str(self.export_dir))}</recordedExportDir>"
                      "<exportOption>Overwrite</exportOption><unique>false</unique></exportConfig>")
        return (f'<?xml version="1.0" encoding="UTF-8" ?>\n<Workflow version="{GAS_VERSION}" build="{WORKFLOW_BUILD}" '
                f'readOnly="false"><name>{_xml(self.name)}</name>'
                f"<description>{_xml(self.description or self.name)}</description>"
                f"<columnsUsed><m__colNames>{used}</m__colNames></columnsUsed>"
                f"<columnsCreated><m__colNames/></columnsCreated>{export}"
                f"<operations>{''.join(self.ops)}</operations><savedWindows/>{self._responses_xml()}</Workflow>\n")

    def _responses_xml(self) -> str:
        if not self.responses:
            return "<userResponses/>"
        out = []
        for msg, ans in self.responses:
            kind, val = ("boolean", "true" if ans else "false") if isinstance(ans, bool) else ("string", _xml(ans))
            out.append(f'<UserResponse><message>{_xml(msg)}</message><response class="{kind}">{val}</response>'
                       "<stepNum>0</stepNum></UserResponse>")
        return "<userResponses>" + "".join(out) + "</userResponses>"

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.xml(), encoding="utf-8")
        return path
