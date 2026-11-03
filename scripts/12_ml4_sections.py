"""ML-4 sections: three NW–SE geochem-stratigraphy cross-sections (report §5). Plan: LOG.md,
2026-11-03 ML-4 entry.

Each section is a vertical plane of azimuth 135° placed midway across its holes' traces (minimax
offset),
viewed looking NE (NW on the left), 1:1. Composites within ±40 m are projected into the plane:
x = distance along the section from its NW end, y = RL. Per composite, three strips sit side by
side along the trace: the HMM state (centred), logged alteration and logged oxidation (to the
right of the trace's downhole direction). Topography is the lidar DEM sampled along the line.
Layers are written in a local engineering CRS for the QGIS section layouts; the section lines
and corridors are also written in EPSG:32647 for the index map.
Reads data/interim/06_composites.csv, 03_collar.csv, data/processed/ml/komposit__ml4_hmm.csv,
gis/lidar_dem.tif; writes gis/ml4_penampang.gpkg, data/processed/ml4_sections.csv.
Run: uv run python scripts/12_ml4_sections.py  (after scripts/11_ml4_hmm.py)
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
import shapely

from src import dem, geostrat as gs, paths

AZ = 135.0              # section azimuth: x grows towards SE
CORRIDOR_M = 40.0
MARGIN_M = 40.0         # topography extends this far beyond the outermost trace
DEM_STEP_M = 2.0
STRIPS = {"status": (-3.0, 3.0), "alterasi": (3.5, 7.0), "oksidasi": (7.5, 11.0)}   # m from the trace
SECTIONS = {
    "A": ["RJDH001", "RJDH003", "RJDH008", "RJDH009", "RJDH015", "RJDH019"],
    "B": ["RJDH005", "RJDH012", "RJDH014", "RJDH016", "RJDH017", "RJDH018"],
    "C": ["RJDH002", "RJDH006", "RJDH007", "RJDH013"],
}
LOCAL_CRS = ('ENGCRS["Penampang lokal RJ",EDATUM["Bidang penampang"],CS[Cartesian,2],'
             'AXIS["jarak (x)",east,ORDER[1],LENGTHUNIT["metre",1]],'
             'AXIS["elevasi (y)",north,ORDER[2],LENGTHUNIT["metre",1]]]')
OX_ID = {"Oxide": "Oksida", "Transition": "Transisi", "Sulphide": "Sulfida"}
ALT_ID = {"AA": "Argilik lanjut", "SI": "Silika", "AR": "Argilik", "PP": "Propilitik", "UA": "Tanpa alterasi"}


def strip_quads(p0: np.ndarray, p1: np.ndarray, w0: float, w1: float) -> list:
    """Quads between w0 and w1 m from each segment p0→p1 (section frame), on the side that a
    downward trace has towards +x (to the right on the page)."""
    d = p1 - p0
    n = np.column_stack([-d[:, 1], d[:, 0]]) / np.linalg.norm(d, axis=1, keepdims=True)
    return [shapely.Polygon([a + w0 * v, b + w0 * v, b + w1 * v, a + w1 * v]) for a, b, v in zip(p0, p1, n)]


def main():
    c = pd.read_csv(paths.INTERIM / "06_composites.csv", low_memory=False)
    ml = pd.read_csv(paths.PROCESSED / "ml" / "komposit__ml4_hmm.csv", low_memory=False)
    c = c.merge(ml, left_on=["SiteID", "DepthFrom"], right_on=["HoleID", "From"], how="left", validate="one_to_one")
    collar = pd.read_csv(paths.INTERIM / "03_collar.csv").set_index("SiteID")
    with rasterio.open(paths.GIS / "lidar_dem.tif") as r:
        dem_arr = r.read(1).astype(float)
        dem_arr[dem_arr == r.nodata] = np.nan
        tf = r.transform

    gpkg = paths.GIS / "ml4_penampang.gpkg"
    layers = {k: [] for k in ("status_hmm", "alterasi_log", "oksidasi_log", "jejak", "kolar", "topografi",
                              "garis_penampang", "koridor")}
    report = []
    for name, holes in SECTIONS.items():
        col = collar.loc[holes]
        g = c[c.SiteID.isin(holes)].sort_values(["SiteID", "DepthFrom"]).copy()
        # line through the middle of the traces' offset range (minimax), shifted along the normal (NE)
        centre = (col.EastUTM.mean(), col.NorthUTM.mean())
        _, off = gs.section_coords(g.X_mid, g.Y_mid, centre, AZ)
        mid = (off.min() + off.max()) / 2
        n_ne = np.array([np.sin(np.deg2rad(AZ - 90)), np.cos(np.deg2rad(AZ - 90))])
        centre = (centre[0] + mid * n_ne[0], centre[1] + mid * n_ne[1])
        a_f, o_f = gs.section_coords(g.X_from, g.Y_from, centre, AZ)
        a_t, o_t = gs.section_coords(g.X_to, g.Y_to, centre, AZ)
        a_m, o_m = gs.section_coords(g.X_mid, g.Y_mid, centre, AZ)
        x0 = min(a_f.min(), a_t.min()) - MARGIN_M
        x1 = max(a_f.max(), a_t.max()) + MARGIN_M
        g["x_from"], g["x_to"], g["x_mid"], g["offset_m"] = a_f - x0, a_t - x0, a_m - x0, o_m
        g["di_luar_koridor"] = np.where(np.abs(o_m) > CORRIDOR_M, "Y", "N")
        # in-plane length cannot exceed true length
        L3 = np.sqrt((g.X_to - g.X_from) ** 2 + (g.Y_to - g.Y_from) ** 2 + (g.Z_to - g.Z_from) ** 2)
        L2 = np.sqrt((g.x_to - g.x_from) ** 2 + (g.Z_to - g.Z_from) ** 2)
        assert (L2 <= L3 + 1e-6).all()
        p0 = g[["x_from", "Z_from"]].to_numpy()
        p1 = g[["x_to", "Z_to"]].to_numpy()
        base = pd.DataFrame({"penampang": name, "SiteID": g.SiteID.str.replace("RJDH", "DH"),
                             "dari_m": g.DepthFrom, "ke_m": g.DepthTo, "offset_m": g.offset_m.round(1),
                             "di_luar_koridor": g.di_luar_koridor}).reset_index(drop=True)
        okk = g.ML_hmm_status.notna().to_numpy()
        # state number written on the middle composite of runs ≥ 6 m (secondary encoding for colour)
        lab_run = np.full(len(g), "", dtype=object)
        sub = g[okk]
        seg_r = np.cumsum(np.r_[True, (sub.SiteID.to_numpy()[1:] != sub.SiteID.to_numpy()[:-1])
                                | (np.diff(sub.DepthFrom.to_numpy()) > 1)])
        mark = gs.run_label_rows(sub.ML_hmm_status.astype(int).to_numpy(), seg_r, 6)
        lab_run[np.flatnonzero(okk)[mark]] = ["S" + str(int(v)) for v in sub.ML_hmm_status[mark]]
        st = base.assign(label_run=lab_run, status=g.ML_hmm_status.to_numpy(), nama=g.ML_hmm_nama.to_numpy(),
                         p_maks=g.ML_hmm_p_maks.to_numpy(), ambigu=g.ML_hmm_ambigu.to_numpy(),
                         stabil=g.ML_hmm_stabil.to_numpy())
        quads = strip_quads(p0, p1, *STRIPS["status"])
        layers["status_hmm"].append(gpd.GeoDataFrame(st[okk], geometry=np.array(quads, dtype=object)[okk]))
        alt = base.assign(kode=g.AltFacies.to_numpy(), alterasi=g.AltFacies.map(ALT_ID).to_numpy())
        has = alt.kode.notna().to_numpy()
        layers["alterasi_log"].append(gpd.GeoDataFrame(alt[has], geometry=np.array(
            strip_quads(p0, p1, *STRIPS["alterasi"]), dtype=object)[has]))
        ox = base.assign(kode=g.ox_state.to_numpy(), oksidasi=g.ox_state.map(OX_ID).to_numpy())
        has = ox.kode.notna().to_numpy()
        layers["oksidasi_log"].append(gpd.GeoDataFrame(ox[has], geometry=np.array(
            strip_quads(p0, p1, *STRIPS["oksidasi"]), dtype=object)[has]))
        for h, gh in g.groupby("SiteID"):
            xy = np.r_[gh[["x_from", "Z_from"]].to_numpy(), gh[["x_to", "Z_to"]].to_numpy()[-1:]]
            layers["jejak"].append(gpd.GeoDataFrame({"penampang": [name], "SiteID": [h.replace("RJDH", "DH")],
                                                     "offset_maks_m": [float(np.abs(gh.offset_m).max())]},
                                                    geometry=[shapely.LineString(xy)]))
            cx, _ = gs.section_coords([collar.loc[h, "EastUTM"]], [collar.loc[h, "NorthUTM"]], centre, AZ)
            layers["kolar"].append(gpd.GeoDataFrame(
                {"penampang": [name, name], "SiteID": [h.replace("RJDH", "DH")] * 2, "jenis": ["kolar", "akhir"],
                 "label": [h.replace("RJDH", "DH"), f"{collar.loc[h, 'EndDepth']:.1f} m"]},
                geometry=[shapely.Point(cx[0] - x0, collar.loc[h, "RLUTM"]), shapely.Point(xy[-1])]))
            report.append({"penampang": name, "SiteID": h, "offset_kolar_m": float(gh.offset_m.iloc[0]),
                           "offset_maks_m": float(np.abs(gh.offset_m).max()),
                           "m_luar_koridor": float(gh.di_luar_koridor.eq("Y").sum()),
                           "kolar_x": float(cx[0] - x0), "RL": float(collar.loc[h, "RLUTM"])})
        # topography along the line (x from x0 to x1)
        s = np.arange(0, x1 - x0 + DEM_STEP_M, DEM_STEP_M)
        a = np.deg2rad(AZ)
        px, py = centre[0] + (s + x0) * np.sin(a), centre[1] + (s + x0) * np.cos(a)
        z = dem.sample_bilinear(dem_arr, tf, px, py)
        ok = np.isfinite(z)
        layers["topografi"].append(gpd.GeoDataFrame({"penampang": [name], "n_titik": [int(ok.sum())]},
                                                    geometry=[shapely.LineString(np.c_[s[ok], z[ok]])]))
        # plan view (EPSG:32647): line ends labelled A / A'
        e0 = (centre[0] + x0 * np.sin(a), centre[1] + x0 * np.cos(a))
        e1 = (centre[0] + x1 * np.sin(a), centre[1] + x1 * np.cos(a))
        line = shapely.LineString([e0, e1])
        layers["garis_penampang"].append(gpd.GeoDataFrame(
            {"penampang": [name], "label_awal": [name], "label_akhir": [f"{name}'"], "panjang_m": [line.length],
             "lubang": [", ".join(h.replace("RJDH", "DH") for h in holes)]}, geometry=[line]))
        layers["koridor"].append(gpd.GeoDataFrame({"penampang": [name], "lebar_m": [2 * CORRIDOR_M]},
                                                  geometry=[line.buffer(CORRIDOR_M, cap_style="flat")]))
        # the profile is along the line; collars off the line sit above or below it on steep ground.
        # Check the DEM at the collar itself instead (AGENTS §4.1: within ~2 m except two pads).
        cz = dem.sample_bilinear(dem_arr, tf, col.EastUTM.to_numpy(), col.NorthUTM.to_numpy())
        line_z = np.interp([r["kolar_x"] for r in report if r["penampang"] == name], s[ok], z[ok])
        for r_, zl in zip([r for r in report if r["penampang"] == name], line_z):
            r_["RL_minus_profile_m"] = r_["RL"] - float(zl)
        print(f"section {name}: {len(holes)} holes, {x1 - x0:.0f} m long; collar RL - DEM at collar "
              f"{np.round(col.RLUTM.to_numpy() - cz, 1).tolist()}")

    plan_layers = {"garis_penampang", "koridor"}
    for k, parts in layers.items():
        gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True)).set_crs(
            paths.CRS if k in plan_layers else LOCAL_CRS, allow_override=True)
        # section layers one per section (k_A, k_B, k_C): no attribute filters needed in QGIS
        out = {k: gdf} if k in plan_layers else {f"{k}_{s}": gdf[gdf.penampang.eq(s)] for s in SECTIONS}
        for name, part in out.items():
            part.to_file(gpkg, layer=name, driver="GPKG", mode="w")
            assert pyogrio.read_info(gpkg, layer=name)["features"] == len(part) > 0, name
        print(f"  {k}: {len(gdf)}")
    rep = pd.DataFrame(report)
    rep.to_csv(paths.PROCESSED / "ml4_sections.csv", index=False)
    print(rep.round(1).to_string(index=False))
    n_out = rep.m_luar_koridor.sum()
    print(f"composites outside ±{CORRIDOR_M:.0f} m: {n_out:.0f} (drawn, flagged)")


if __name__ == "__main__":
    main()
