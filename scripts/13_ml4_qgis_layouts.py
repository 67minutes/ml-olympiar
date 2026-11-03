"""ML-4 sections in QGIS: builds outputs/maps/11_ml4_penampang.qgz with three section layouts
and an index map, and exports them at 300 dpi. Plan: LOG.md, 2026-11-03 ML-4 entry.

Runs INSIDE QGIS (PyQGIS), e.g. through the QGIS MCP `execute_code` tool:
    exec(open(r"<repo>/scripts/13_ml4_qgis_layouts.py", encoding="utf-8").read(), {"REPO": r"<repo>"})
Reads gis/ml4_penampang.gpkg, gis/ml4_hmm.gpkg, gis/drillholes.gpkg, gis/hillshade.tif and
data/processed/ml4_states.csv (state names and colours). Section layers are in the local
section frame (x = distance along the section, y = RL), so section maps use that CRS and
plan layers never draw in them. All labels in Bahasa Indonesia.
"""
import csv
from pathlib import Path

from qgis.core import (Qgis, QgsLayoutItemPage, QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem, QgsFillSymbol,
                       QgsLayoutExporter, QgsLayoutItemLabel,
                       QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemMapGrid, QgsLayoutItemScaleBar,
                       QgsLayoutPoint, QgsLayoutSize, QgsLegendStyle, QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings,
                       QgsPrintLayout, QgsProject, QgsRasterLayer, QgsRectangle, QgsRendererCategory,
                       QgsRuleBasedRenderer, QgsSingleSymbolRenderer, QgsTextFormat, QgsUnitTypes, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling, QgsLinePatternFillSymbolLayer)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont

REPO = Path(globals().get("REPO", r"C:\Users\mauli\Documents\ml-olympiar"))
GIS, OUT = REPO / "gis", REPO / "outputs" / "maps"
SEC_GPKG = GIS / "ml4_penampang.gpkg"
SECTIONS = ("A", "B", "C")
SCALE = 2500
DPI = 300
FONT = "Times New Roman"
ALT = {"SI": ("Silika", "#7b3294"), "AA": ("Argilik lanjut", "#c2a5cf"), "AR": ("Argilik", "#a6dba0"),
       "PP": ("Propilitik", "#008837"), "UA": ("Tanpa alterasi", "#e0e0e0")}
OX = {"Oxide": ("Oksida", "#d7301f"), "Transition": ("Transisi", "#fdbb84"), "Sulphide": ("Sulfida", "#525252")}


def text_format(size: float, bold: bool = False) -> QgsTextFormat:
    f = QgsTextFormat()
    font = QFont(FONT)
    font.setBold(bold)
    f.setFont(font)
    f.setSize(size)
    f.setColor(QColor("black"))
    return f


def states():
    with open(globals().get("STATES_CSV", REPO / "data" / "processed" / "ml4_states.csv"), encoding="utf-8") as fh:
        return [(int(r["state"]), r["nama"], r["warna"]) for r in csv.DictReader(fh)]


def vlayer(path: Path, layer: str, name: str, subset: str = "") -> QgsVectorLayer:
    lyr = QgsVectorLayer(f"{path}|layername={layer}", name, "ogr")
    assert lyr.isValid(), f"{path.name}:{layer} did not load"
    if subset:
        assert lyr.setSubsetString(subset), f"{layer}: bad filter {subset}"
    lyr.updateExtents()
    n = lyr.dataProvider().featureCount() if not subset else sum(1 for _ in lyr.getFeatures())
    assert n > 0 and not lyr.extent().isNull(), f"{path.name}:{layer} {subset} has no features"
    return lyr


def fill(colour: str, outline: str = "transparent") -> QgsFillSymbol:
    if outline == "transparent":
        return QgsFillSymbol.createSimple({"color": colour, "outline_style": "no"})
    return QgsFillSymbol.createSimple({"color": colour, "outline_color": outline, "outline_width": "0.2"})


def categorized(lyr, field, cats: dict):
    rc = [QgsRendererCategory(k, fill(c), lab) for k, (lab, c) in cats.items()]
    lyr.setRenderer(QgsCategorizedSymbolRenderer(field, rc))


def style_status(lyr, st):
    root = QgsRuleBasedRenderer.Rule(None)
    for s, nama, warna in st:
        root.appendChild(QgsRuleBasedRenderer.Rule(fill(warna), 0, 0, f'"status" = {s}', nama))
    hatch = QgsFillSymbol()
    hatch.deleteSymbolLayer(0)
    lp = QgsLinePatternFillSymbolLayer()
    lp.setLineAngle(45)
    lp.setDistance(1.0)
    lp.setLineWidth(0.12)
    lp.setColor(QColor("black"))
    hatch.appendSymbolLayer(lp)
    root.appendChild(QgsRuleBasedRenderer.Rule(hatch, 0, 0, "\"ambigu\" = 'Y'", "Ambigu (p maks < 0,5)"))
    dash = QgsFillSymbol.createSimple({"color": "transparent", "outline_color": "black", "outline_width": "0.2",
                                       "outline_style": "dash"})
    root.appendChild(QgsRuleBasedRenderer.Rule(dash, 0, 0, "\"di_luar_koridor\" = 'Y'", "Di luar koridor ±40 m"))
    lyr.setRenderer(QgsRuleBasedRenderer(root))


def label(lyr, field_expr: str, size: float, placement=None, dist: float = 1.5, buffer: bool = False):
    s = QgsPalLayerSettings()
    s.fieldName = field_expr
    s.isExpression = True
    fmt = text_format(size, bold=True)
    if buffer:
        b = fmt.buffer()
        b.setEnabled(True)
        b.setSize(0.6)
        b.setColor(QColor("white"))
        fmt.setBuffer(b)
    s.setFormat(fmt)
    if placement is not None:
        s.placement = placement
    s.dist = dist
    s.placementSettings().setOverlapHandling(Qgis.LabelOverlapHandling.AllowOverlapIfRequired)
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lyr.setLabelsEnabled(True)


def add_label(layout, text, x, y, w, h, size, bold=False, align=Qt.AlignmentFlag.AlignLeft):
    it = QgsLayoutItemLabel(layout)
    it.setText(text)
    it.setTextFormat(text_format(size, bold))
    it.setHAlign(align)
    it.attemptMove(QgsLayoutPoint(x, y, Qgis.LayoutUnit.Millimeters))
    it.attemptResize(QgsLayoutSize(w, h, Qgis.LayoutUnit.Millimeters))
    layout.addLayoutItem(it)
    return it


def legend(layout, mp, layers, x, y, title="Keterangan"):
    lg = QgsLayoutItemLegend(layout)
    lg.setTitle(title)
    lg.setLinkedMap(mp)
    lg.setAutoUpdateModel(False)
    root = lg.model().rootGroup()
    root.removeAllChildren()
    for lyr in layers:
        root.addLayer(lyr)
    for part, size, bold in ((Qgis.LegendComponent.Title, 10, True), (Qgis.LegendComponent.Group, 8.5, True),
                             (Qgis.LegendComponent.Subgroup, 8.5, True), (Qgis.LegendComponent.SymbolLabel, 7.5, False)):
        lg.rstyle(part).setTextFormat(text_format(size, bold))
    lg.attemptMove(QgsLayoutPoint(x, y, Qgis.LayoutUnit.Millimeters))
    layout.addLayoutItem(lg)
    lg.adjustBoxSize()
    return lg


def page_layout(project, name):
    lay = QgsPrintLayout(project)
    lay.initializeDefaults()
    lay.setName(name)
    pg = lay.pageCollection().page(0)
    pg.setPageSize("A4", QgsLayoutItemPage.Orientation.Landscape)
    project.layoutManager().addLayout(lay)
    return lay


def map_item(layout, layers, crs, extent, x, y, w, h, scale=None, grid=50.0, grid_crs=None):
    mp = QgsLayoutItemMap(layout)
    mp.attemptMove(QgsLayoutPoint(x, y, Qgis.LayoutUnit.Millimeters))
    mp.attemptResize(QgsLayoutSize(w, h, Qgis.LayoutUnit.Millimeters))
    mp.setCrs(crs)
    mp.setLayers(layers)
    mp.setKeepLayerSet(True)
    mp.zoomToExtent(extent)          # keeps the item size (setExtent would resize it)
    if scale:
        mp.setScale(scale)
    mp.setFrameEnabled(True)
    layout.addLayoutItem(mp)
    g = QgsLayoutItemMapGrid("grid", mp)
    g.setIntervalX(grid)
    g.setIntervalY(grid)
    g.setStyle(Qgis.MapGridStyle.LineCrosses)
    g.setCrossLength(1.0)
    g.setGridLineColor(QColor("#9a9a9a"))
    g.setGridLineWidth(0.15)
    g.setAnnotationEnabled(True)
    g.setAnnotationPrecision(0)
    g.setAnnotationTextFormat(text_format(7))
    for side in (Qgis.MapGridBorderSide.Right, Qgis.MapGridBorderSide.Top):
        g.setAnnotationDisplay(Qgis.MapGridComponentVisibility.HideAll, side)
    g.setAnnotationDirection(Qgis.MapGridAnnotationDirection.Vertical, Qgis.MapGridBorderSide.Left)
    mp.grids().addGrid(g)
    return mp


def scalebar(layout, mp, x, y, units_label="m"):
    sb = QgsLayoutItemScaleBar(layout)
    sb.setStyle("Single Box")
    sb.setLinkedMap(mp)
    sb.setUnits(Qgis.DistanceUnit.Meters)
    sb.setNumberOfSegments(4)
    sb.setNumberOfSegmentsLeft(0)
    sb.setUnitsPerSegment(25)
    sb.setUnitLabel(units_label)
    sb.setTextFormat(text_format(7))
    sb.attemptMove(QgsLayoutPoint(x, y, Qgis.LayoutUnit.Millimeters))
    layout.addLayoutItem(sb)
    sb.update()
    return sb


def export(layout, path: Path):
    ex = QgsLayoutExporter(layout)
    s = QgsLayoutExporter.ImageExportSettings()
    s.dpi = DPI
    res = ex.exportToImage(str(path), s)
    assert res == QgsLayoutExporter.ExportResult.Success, f"export failed: {path.name} ({res})"


def build():
    project = QgsProject.instance()
    project.clear()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:32647"))
    st = states()
    tree = project.layerTreeRoot()
    sec_layers = {}
    for s in SECTIONS:
        grp = tree.addGroup(f"Penampang {s}-{s}'")
        lyrs = {
            "topo": vlayer(SEC_GPKG, f"topografi_{s}", "Topografi (lidar)"),
            "oks": vlayer(SEC_GPKG, f"oksidasi_log_{s}", "Oksidasi (log)"),
            "alt": vlayer(SEC_GPKG, f"alterasi_log_{s}", "Alterasi (log)"),
            "hmm": vlayer(SEC_GPKG, f"status_hmm_{s}", "Status geokimia HMM"),
            "jejak": vlayer(SEC_GPKG, f"jejak_{s}", "Jejak lubang bor"),
            "kolar": vlayer(SEC_GPKG, f"kolar_{s}", "Kolar / akhir lubang"),
        }
        categorized(lyrs["oks"], "kode", OX)
        categorized(lyrs["alt"], "kode", ALT)
        style_status(lyrs["hmm"], st)
        label(lyrs["hmm"], '"label_run"', 5.5, placement=Qgis.LabelPlacement.OverPoint, dist=0, buffer=True)
        lyrs["topo"].setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "black", "width": "0.4"})))
        lyrs["jejak"].setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#3a3a3a", "width": "0.15"})))
        lyrs["kolar"].setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
            {"name": "circle", "size": "0.8", "color": "black", "outline_color": "black"})))
        label(lyrs["kolar"], '"label"', 7)
        for lyr in lyrs.values():
            project.addMapLayer(lyr, False)
            grp.addLayer(lyr)
        sec_layers[s] = lyrs

    plan = tree.addGroup("Peta indeks")
    hs = QgsRasterLayer(str(GIS / "hillshade.tif"), "Bayangan bukit (lidar)")
    assert hs.isValid()
    hs.renderer().setOpacity(0.6)
    traces = vlayer(GIS / "drillholes.gpkg", "traces", "Jejak lubang bor (proyeksi)")
    collars = vlayer(GIS / "drillholes.gpkg", "collars", "Kolar lubang bor")
    lines = vlayer(SEC_GPKG, "garis_penampang", "Garis penampang")
    corr = vlayer(SEC_GPKG, "koridor", "Koridor ±40 m")
    traces.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "black", "width": "0.3"})))
    collars.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
        {"name": "circle", "size": "1.6", "color": "white", "outline_color": "black", "outline_width": "0.3"})))
    label(collars, "replace(\"SiteID\", 'RJDH', 'DH')", 7)
    lines.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#c8321e", "width": "0.6"})))
    label(lines, "\"label_awal\" || ' – ' || \"label_akhir\"", 9)
    corr.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"color": "200,50,30,45", "outline_color": "200,50,30,200", "outline_width": "0.2"})))
    for lyr in (collars, traces, lines, corr, hs):
        project.addMapLayer(lyr, False)
        plan.addLayer(lyr)

    local = sec_layers["A"]["hmm"].crs()
    for s, lyrs in sec_layers.items():
        lay = page_layout(project, f"Penampang {s}")
        ext = QgsRectangle()
        for k in ("topo", "hmm", "alt", "oks", "kolar"):
            ext.combineExtentWith(lyrs[k].extent())
        ext.grow(15)
        order = [lyrs[k] for k in ("kolar", "jejak", "hmm", "alt", "oks", "topo")]
        mp = map_item(lay, order, local, ext, 10, 22, 215, 168, scale=SCALE)
        add_label(lay, f"Penampang {s}–{s}' (azimut 135°, pandangan ke timur laut): status geokimia HMM "
                       "dibandingkan dengan alterasi dan oksidasi hasil logging", 10, 6, 277, 12, 12, bold=True)
        add_label(lay, f"{s} (BL)", 12, 24, 30, 6, 10, bold=True)
        add_label(lay, f"{s}' (TG)", 193, 24, 30, 6, 10, bold=True, align=Qt.AlignmentFlag.AlignRight)
        legend(lay, mp, [lyrs[k] for k in ("hmm", "alt", "oks", "topo", "kolar")], 230, 22)
        scalebar(lay, mp, 230, 165)
        add_label(lay, "Sumbu tegak: elevasi (m dpl); sumbu datar: jarak sepanjang penampang (m). Skala "
                       f"1:{SCALE:,}".replace(",", ".") + ", tanpa pembesaran vertikal. Komposit 1 m "
                       "diproyeksikan dari koridor ±40 m. Kolom tengah: status HMM; kanan: alterasi lalu "
                       "oksidasi (log). Arsiran: status ambigu (p maks < 0,5).", 230, 178, 60, 30, 7)
        export(lay, OUT / f"11_penampang_{s}_v1.png")

    lay = page_layout(project, "Peta indeks penampang")
    ext = corr.extent()
    ext.combineExtentWith(traces.extent())
    ext.grow(60)
    mp = map_item(lay, [collars, traces, lines, corr, hs], QgsCoordinateReferenceSystem("EPSG:32647"), ext,
                  10, 22, 215, 168, grid=100.0)
    add_label(lay, "Peta indeks garis penampang geokimia-stratigrafi (UTM WGS84 Zona 47N, EPSG:32647)",
              10, 6, 277, 12, 12, bold=True)
    legend(lay, mp, [lines, corr, collars, traces], 230, 22)
    scalebar(lay, mp, 230, 165)
    add_label(lay, "Lubang RJDH004, RJDH010 dan RJDH011 berada di luar koridor ketiga penampang. "
                   "Dasar: bayangan bukit dari DEM lidar 5 m (Tahap 2). Utara ke atas.", 230, 178, 60, 30, 7)
    export(lay, OUT / "11_peta_indeks_penampang_v1.png")
    project.write(str(OUT / "11_ml4_penampang.qgz"))
    return {s: {k: sum(1 for _ in l.getFeatures()) for k, l in lyrs.items()} for s, lyrs in sec_layers.items()}


def profile_check(section: str = "B", out: Path = OUT / "qc" / "11_profil_elevasi_B_v1.png"):
    """QC with QGIS's own elevation-profile engine: the 3D composite midpoints (gis/ml4_hmm.gpkg,
    EPSG:32647, black dots) and the lidar DEM (yellow) along the section's plan line, corridor
    ±40 m. (3D line features return no profile in this QGIS build, so midpoints are used.)
    Returns the profile's length and elevation range, to compare with the projected section."""
    from qgis.core import QgsProfilePlotRenderer, QgsProfileRequest
    project = QgsProject.instance()
    pts = vlayer(GIS / "ml4_hmm.gpkg", "komposit_status", "QC komposit 3D")
    props = pts.elevationProperties()
    props.setClamping(Qgis.AltitudeClamping.Absolute)
    props.setRespectLayerSymbology(False)
    props.setProfileMarkerSymbol(QgsMarkerSymbol.createSimple(
        {"name": "circle", "size": "1.0", "color": "black", "outline_style": "no"}))
    dem_l = QgsRasterLayer(str(GIS / "lidar_dem.tif"), "QC DEM")
    dem_l.elevationProperties().setEnabled(True)
    lines = vlayer(SEC_GPKG, "garis_penampang", "QC garis")
    line = next(f.geometry() for f in lines.getFeatures() if f["penampang"] == section)
    req = QgsProfileRequest(line.constGet().clone())
    req.setCrs(lines.crs())
    req.setTolerance(40.0)
    req.setTransformContext(project.transformContext())
    r = QgsProfilePlotRenderer([pts], req)
    r.startGeneration()
    r.waitForFinished()
    zp = r.zRange()
    r2 = QgsProfilePlotRenderer([pts, dem_l], req)
    r2.startGeneration()
    r2.waitForFinished()
    zr = r2.zRange()
    length = line.length()
    img = r2.renderToImage(2400, 1000, 0, length, zr.lower() - 10, zr.upper() + 10)
    out.parent.mkdir(parents=True, exist_ok=True)
    assert img.save(str(out)), out
    return {"length_m": length, "z_points": (zp.lower(), zp.upper()), "z_all": (zr.lower(), zr.upper())}


RESULT = build()
PROFILE = profile_check()
