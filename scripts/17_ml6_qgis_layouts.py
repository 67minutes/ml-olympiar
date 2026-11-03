"""ML-6 maps in QGIS: derived-drainage QC map, the exploration design map (bonus, report §7) and
section D–D' through RJ-U01. Plan: LOG.md, 2026-11-03 ML-6 entry.

Runs INSIDE QGIS (PyQGIS), e.g. through the QGIS MCP `execute_code` tool:
    exec(open(r"<repo>/scripts/17_ml6_qgis_layouts.py", encoding="utf-8").read(), {"REPO": r"<repo>"})
Reads gis/drainage.gpkg, gis/ml6_target.gpkg, gis/ml6_penampang.gpkg, gis/ml6_meter_cutoff.tif,
gis/ml3_tanah_zona.tif, gis/ml5_paf.gpkg, gis/drillholes.gpkg, gis/hillshade.tif and
data/processed/ml4_states.csv. Writes outputs/maps/qc/13_drainage_check.qgz,
outputs/maps/qc/13_drainase_turunan_v1.png, outputs/maps/13_ml6_desain.qgz,
outputs/maps/13_{peta_desain,penampang_desain}_v1.png. Layout helpers follow
scripts/13_ml4_qgis_layouts.py. All labels in Bahasa Indonesia.
"""
import csv
from pathlib import Path

from qgis.core import (Qgis, QgsMapLayerLegendUtils, QgsCategorizedSymbolRenderer, QgsColorRampShader, QgsCoordinateReferenceSystem,
                       QgsFillSymbol, QgsGraduatedSymbolRenderer, QgsLayoutExporter, QgsLayoutItemLabel,
                       QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemMapGrid, QgsLayoutItemPage,
                       QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize, QgsLineSymbol, QgsMarkerSymbol,
                       QgsPalLayerSettings, QgsPrintLayout, QgsProject, QgsRasterLayer, QgsRasterShader,
                       QgsRendererCategory, QgsRendererRange, QgsRuleBasedRenderer, QgsSingleBandPseudoColorRenderer,
                       QgsPalettedRasterRenderer, QgsSingleSymbolRenderer, QgsTextFormat, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont

REPO = Path(globals().get("REPO", r"C:\Users\mauli\Documents\ml-olympiar"))
GIS, OUT = REPO / "gis", REPO / "outputs" / "maps"
DPI = 300
FONT = "Times New Roman"
UTM = QgsCoordinateReferenceSystem("EPSG:32647")
P05_CLASSES = [(0.0, 0.2, "#fee6ce"), (0.2, 0.4, "#fdae6b"), (0.4, 0.6, "#fd8d3c"), (0.6, 0.8, "#e6550d"),
               (0.8, 1.0001, "#a63603")]
METRE_RAMP = [(0, "#f2f0f7"), (20, "#cbc9e2"), (40, "#9e9ac8"), (60, "#756bb1"), (90, "#54278f")]
C_RIVER, C_PAF = "#2c7fb8", "#b2182b"


# --- helpers (as scripts/13_ml4_qgis_layouts.py) ----------------------------------------
def text_format(size: float, bold: bool = False) -> QgsTextFormat:
    f = QgsTextFormat()
    font = QFont(FONT)
    font.setBold(bold)
    f.setFont(font)
    f.setSize(size)
    f.setColor(QColor("black"))
    return f


def vlayer(path: Path, layer: str, name: str, subset: str = "") -> QgsVectorLayer:
    lyr = QgsVectorLayer(f"{path}|layername={layer}", name, "ogr")
    assert lyr.isValid(), f"{path.name}:{layer} did not load"
    if subset:
        assert lyr.setSubsetString(subset), f"{layer}: bad filter {subset}"
    lyr.updateExtents()
    assert sum(1 for _ in lyr.getFeatures()) > 0, f"{path.name}:{layer} {subset} has no features"
    return lyr


def rlayer(path: Path, name: str) -> QgsRasterLayer:
    lyr = QgsRasterLayer(str(path), name)
    assert lyr.isValid(), path.name
    return lyr


def line_sym(colour, width, style="solid"):
    return QgsLineSymbol.createSimple({"color": colour, "width": str(width), "line_style": style})


def single(lyr, sym):
    lyr.setRenderer(QgsSingleSymbolRenderer(sym))


def label(lyr, expr: str, size: float, dist: float = 1.5, buffer: bool = True, placement=None):
    s = QgsPalLayerSettings()
    s.fieldName = expr
    s.isExpression = True
    fmt = text_format(size, bold=True)
    if buffer:
        b = fmt.buffer()
        b.setEnabled(True)
        b.setSize(0.7)
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
                             (Qgis.LegendComponent.Subgroup, 8, True), (Qgis.LegendComponent.SymbolLabel, 7.5, False)):
        lg.rstyle(part).setTextFormat(text_format(size, bold))
    # drop the raster band-name rows ("Band 1 (Gray)"), keep the colour entries
    model = lg.model()
    for nl in root.findLayers():
        if nl.layer().type() == Qgis.LayerType.Raster:
            nodes = model.layerOriginalLegendNodes(nl)
            keep = [i for i, n in enumerate(nodes) if not str(n.data(Qt.ItemDataRole.DisplayRole)).startswith("Band")]
            QgsMapLayerLegendUtils.setLegendNodeOrder(nl, keep)
            model.refreshLayerLegend(nl)
    lg.attemptMove(QgsLayoutPoint(x, y, Qgis.LayoutUnit.Millimeters))
    layout.addLayoutItem(lg)
    lg.adjustBoxSize()
    return lg


def page_layout(project, name):
    lay = QgsPrintLayout(project)
    lay.initializeDefaults()
    lay.setName(name)
    lay.pageCollection().page(0).setPageSize("A4", QgsLayoutItemPage.Orientation.Landscape)
    project.layoutManager().addLayout(lay)
    return lay


def map_item(layout, layers, crs, extent, x, y, w, h, scale=None, grid=50.0):
    mp = QgsLayoutItemMap(layout)
    mp.attemptMove(QgsLayoutPoint(x, y, Qgis.LayoutUnit.Millimeters))
    mp.attemptResize(QgsLayoutSize(w, h, Qgis.LayoutUnit.Millimeters))
    mp.setCrs(crs)
    mp.setLayers(layers)
    mp.setKeepLayerSet(True)
    mp.zoomToExtent(extent)
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


def scalebar(layout, mp, x, y, seg=25):
    sb = QgsLayoutItemScaleBar(layout)
    sb.setStyle("Single Box")
    sb.setLinkedMap(mp)
    sb.setUnits(Qgis.DistanceUnit.Meters)
    sb.setNumberOfSegments(4)
    sb.setNumberOfSegmentsLeft(0)
    sb.setUnitsPerSegment(seg)
    sb.setUnitLabel("m")
    sb.setTextFormat(text_format(7))
    sb.attemptMove(QgsLayoutPoint(x, y, Qgis.LayoutUnit.Millimeters))
    layout.addLayoutItem(sb)
    sb.update()
    return sb


def export(layout, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    s = QgsLayoutExporter.ImageExportSettings()
    s.dpi = DPI
    res = QgsLayoutExporter(layout).exportToImage(str(path), s)
    assert res == QgsLayoutExporter.ExportResult.Success, f"export failed: {path.name} ({res})"


def add(project, group, layers):
    for lyr in layers:
        project.addMapLayer(lyr, False)
        group.addLayer(lyr)


# --- styled layers ------------------------------------------------------------------------
def hillshade():
    hs = rlayer(GIS / "hillshade.tif", "Bayangan bukit (lidar)")
    hs.renderer().setOpacity(0.6)
    return hs


def rivers():
    lyr = vlayer(GIS / "drainage.gpkg", "sungai_turunan", "Drainase turunan (lidar)")
    root = QgsRuleBasedRenderer.Rule(None)
    for expr, lab, sym in (('NOT "ragu"', "Alur turunan", line_sym(C_RIVER, 0.6)),
                           ('"ragu"', "Alur ragu (DEM jarang kontur, cek lapangan)", line_sym(C_RIVER, 0.6, "dash"))):
        root.appendChild(QgsRuleBasedRenderer.Rule(sym, 0, 0, expr, lab))
    lyr.setRenderer(QgsRuleBasedRenderer(root))
    return lyr


def buffer50():
    lyr = vlayer(GIS / "drainage.gpkg", "sempadan_50m", "Sempadan alur 50 m (Permen PUPR 28/2015)")
    single(lyr, QgsFillSymbol.createSimple({"color": "44,127,184,40", "outline_color": "44,127,184,160",
                                            "outline_width": "0.15"}))
    return lyr


def drill():
    tr = vlayer(GIS / "drillholes.gpkg", "traces", "Jejak lubang bor eksisting")
    single(tr, line_sym("#3a3a3a", 0.3))
    co = vlayer(GIS / "drillholes.gpkg", "collars", "Kolar lubang bor eksisting")
    single(co, QgsMarkerSymbol.createSimple({"name": "circle", "size": "1.4", "color": "white",
                                             "outline_color": "black", "outline_width": "0.3"}))
    label(co, "replace(\"SiteID\", 'RJDH', 'DH')", 6, dist=1.0)
    return tr, co


# --- maps -----------------------------------------------------------------------------------
def drainage_qc(project):
    project.clear()
    project.setCrs(UTM)
    grp = project.layerTreeRoot().addGroup("QC drainase turunan")
    riv = rivers()
    label(riv, "'S' || \"strahler\"", 6, dist=0.5, placement=Qgis.LabelPlacement.Line)
    das = vlayer(GIS / "drainage.gpkg", "das", "DAS 2 ha (r.watershed)")
    single(das, QgsFillSymbol.createSimple({"color": "transparent", "outline_color": "#555555", "outline_width": "0.2"}))
    hs = hillshade()
    tr, co = drill()
    add(project, grp, [co, tr, riv, das, hs])
    lay = page_layout(project, "QC drainase")
    ext = das.extent()
    ext.grow(20)
    mp = map_item(lay, [co, tr, riv, das, hs], UTM, ext, 10, 22, 215, 168, grid=200.0)
    add_label(lay, "QC: drainase turunan dari DEM lidar (GRASS r.watershed + r.stream.extract, ambang 2 ha)",
              10, 6, 277, 12, 12, bold=True)
    legend(lay, mp, [riv, das, co, tr], 230, 22)
    scalebar(lay, mp, 230, 165, seg=100)
    add_label(lay, "Label S1–S3: orde Strahler. Garis putus: alur pada DEM dengan jarak dukungan kontur > 30 m "
                   "(ragu). Bandingkan dengan citra satelit sebelum dipakai sebagai batasan.", 230, 178, 60, 30, 7)
    export(lay, OUT / "qc" / "13_drainase_turunan_v1.png")
    project.write(str(OUT / "qc" / "13_drainage_check.qgz"))
    return {"reaches": riv.featureCount(), "basins": das.featureCount()}


def design(project):
    project.clear()
    project.setCrs(UTM)
    tree = project.layerTreeRoot()
    plan = tree.addGroup("Peta desain eksplorasi")
    hs = hillshade()
    met = rlayer(GIS / "ml6_meter_cutoff.tif", "Meter harapan Au ≥ 0,5 g/t per kolom (GP)")
    sh = QgsColorRampShader(0, 90)
    sh.setColorRampType(QgsColorRampShader.Type.Interpolated)
    sh.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, QColor(c), f"{v} m") for v, c in METRE_RAMP])
    rs = QgsRasterShader()
    rs.setRasterShaderFunction(sh)
    rend = QgsSingleBandPseudoColorRenderer(met.dataProvider(), 1, rs)
    rend.setOpacity(0.75)
    met.setRenderer(rend)
    zona = rlayer(GIS / "ml3_tanah_zona.tif", "Zona tanah ML-3")
    zona.setRenderer(QgsPalettedRasterRenderer(zona.dataProvider(), 1, [
        QgsPalettedRasterRenderer.Class(3, QColor(230, 120, 30, 60), "Zona tanah Tinggi (ML-3)")]))
    paf = vlayer(GIS / "ml5_paf.gpkg", "interval_paf", "Interval PAF-HC (ML-5, proyeksi)",
                 "\"ML_paf_kelola\" = 'PAF-HC' AND (\"ML_paf_label\" = 'PAF-HC' OR \"ML_paf_set\" = 'PAF-HC')")
    single(paf, QgsMarkerSymbol.createSimple({"name": "circle", "size": "0.8", "color": C_PAF, "outline_style": "no"}))
    riv, buf = rivers(), buffer50()
    tr, co = drill()
    sec = vlayer(GIS / "ml6_penampang.gpkg", "garis_penampang", "Garis penampang D–D'")
    single(sec, line_sym("#000000", 0.5, "dash"))
    label(sec, "'D – D'''", 8)
    jej = vlayer(GIS / "ml6_target.gpkg", "jejak_usulan", "Jejak lubang usulan (200 m)")
    single(jej, line_sym("#000000", 0.9))
    kol = vlayer(GIS / "ml6_target.gpkg", "kolar_usulan", "Kolar usulan")
    cats = [QgsRendererCategory("A", QgsMarkerSymbol.createSimple(
                {"name": "star", "size": "4.0", "color": "#ffd92f", "outline_color": "black", "outline_width": "0.4"}),
                "Tingkat A: GP kriging (perluasan / penutup celah)"),
            QgsRendererCategory("B", QgsMarkerSymbol.createSimple(
                {"name": "triangle", "size": "3.6", "color": "#ffffff", "outline_color": "black", "outline_width": "0.5"}),
                "Tingkat B: uji anomali tanah ML-3")]
    kol.setRenderer(QgsCategorizedSymbolRenderer("tingkat", cats))
    label(kol, "\"usulan\"", 8.5, dist=2.0)
    layers = [kol, jej, sec, co, tr, paf, riv, buf, zona, met, hs]
    add(project, plan, layers)

    lay = page_layout(project, "Peta desain eksplorasi")
    ext = kol.extent()
    ext.combineExtentWith(tr.extent())
    ext.combineExtentWith(met.extent())
    ext.grow(40)
    mp = map_item(lay, layers, UTM, ext, 10, 22, 205, 170, grid=200.0)
    add_label(lay, "Desain eksplorasi lanjutan Ramba Joring: lubang bor usulan dengan batasan lingkungan "
                   "(UTM WGS84 Zona 47N)", 10, 6, 277, 12, 12, bold=True)
    legend(lay, mp, [kol, jej, co, tr, paf, met, zona, riv, buf, sec], 220, 20)
    scalebar(lay, mp, 220, 170, seg=100)
    add_label(lay, "Tingkat A dipilih berurutan (greedy) dengan pembaruan varians kriging; hanya batuan baru "
                   "(≥ 20 m dari sampel) yang dihitung. Validasi silang per pad: GP tidak lebih baik dari rata-rata "
                   "antar-pad, sehingga meter harapan sahih hanya dekat lubang eksisting. Tingkat B tanpa prediksi kadar. "
                   "Kolar di luar sempadan 50 m dan lereng pad ≤ 25°. Drainase turunan (lidar).", 220, 180, 67, 26, 6.5)
    export(lay, OUT / "13_peta_desain_v1.png")

    sgrp = tree.addGroup("Penampang D–D'")
    gpkg = GIS / "ml6_penampang.gpkg"
    cells = vlayer(gpkg, "sel_gp", "P(Au ≥ 0,5 g/t), GP kriging (sel 5 m)")
    rng = [QgsRendererRange(lo, hi, QgsFillSymbol.createSimple({"color": c, "outline_style": "no"}),
                            f"{lo:.1f}–{min(hi, 1):.1f}".replace(".", ",")) for lo, hi, c in P05_CLASSES]
    cells.setRenderer(QgsGraduatedSymbolRenderer("p05", rng))
    with open(REPO / "data" / "processed" / "ml4_states.csv", encoding="utf-8") as fh:
        st = [(int(r["state"]), r["nama"], r["warna"]) for r in csv.DictReader(fh)]
    hmm = vlayer(gpkg, "status_hmm", "Status HMM (ML-4), lubang ±40 m")
    hmm.setRenderer(QgsCategorizedSymbolRenderer("status", [
        QgsRendererCategory(s, QgsFillSymbol.createSimple({"color": w, "outline_style": "no"}), n) for s, n, w in st]))
    topo = vlayer(gpkg, "topografi", "Topografi (lidar)")
    single(topo, line_sym("black", 0.4))
    sj = vlayer(gpkg, "jejak_usulan", "Lubang usulan (proyeksi ±50 m)")
    single(sj, line_sym("black", 0.8, "dash"))
    sk = vlayer(gpkg, "kolar_usulan", "Kolar usulan")
    single(sk, QgsMarkerSymbol.createSimple({"name": "star", "size": "3.2", "color": "#ffd92f", "outline_color": "black"}))
    label(sk, "\"label\"", 8, dist=1.5)
    slayers = [sk, sj, hmm, topo, cells]
    add(project, sgrp, slayers)
    lay = page_layout(project, "Penampang D-D'")
    ext = cells.extent()
    ext.combineExtentWith(topo.extent())
    ext.grow(10)
    mp = map_item(lay, slayers, cells.crs(), ext, 10, 22, 215, 168, scale=2500)
    add_label(lay, "Penampang D–D' (azimut 135°, pandangan ke timur laut) melalui RJ-U01: peluang Au ≥ 0,5 g/t "
                   "dari GP (kriging) dan status HMM lubang eksisting", 10, 6, 277, 12, 12, bold=True)
    add_label(lay, "D (BL)", 12, 24, 30, 6, 10, bold=True)
    add_label(lay, "D' (TG)", 193, 24, 30, 6, 10, bold=True, align=Qt.AlignmentFlag.AlignRight)
    legend(lay, mp, [cells, hmm, sj, topo], 230, 22)
    scalebar(lay, mp, 230, 170)
    add_label(lay, "Skala 1:2.500, tanpa pembesaran vertikal; sumbu tegak elevasi (m dpl). Sel GP hanya dalam "
                   "domain model (≤ 100 m horizontal dari komposit). Peluang memakai SD prediktif (termasuk nugget). "
                   "Validasi silang: tanpa keterampilan antar-pad, jadi sel jauh dari lubang mendekati rata-rata.",
              230, 182, 60, 26, 6.5)
    export(lay, OUT / "13_penampang_desain_v1.png")
    project.write(str(OUT / "13_ml6_desain.qgz"))
    return {"usulan": kol.featureCount(), "jejak": jej.featureCount(), "sel_gp": cells.featureCount(),
            "status_hmm": hmm.featureCount(), "paf_hc": sum(1 for _ in paf.getFeatures()),
            "alur": riv.featureCount()}


PROJECT = QgsProject.instance()
QC = drainage_qc(PROJECT)
RESULT = design(PROJECT)
print("QC", QC, "RESULT", RESULT)
