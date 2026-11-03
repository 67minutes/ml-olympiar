"""Step D (ML-6): finish the derived drainage from the raw GRASS outputs of scripts/15_drainage_qgis.py.

Per reach (2 ha network): Strahler order from the line topology (reaches run downstream; a reach
whose end touches another's start flows into it), length, DEM at both ends (downhill check, 0.5 m
tolerance), mean DEM support distance along the reach and the flag `ragu` (> 30 m, the Stage 2
rule: contours far apart, interpolated terrain). Basins (2 ha) dissolved per id; a 50 m buffer of
all reaches (Permen PUPR 28/PRT/M/2015, small non-embanked river outside urban areas [VERIFY]).
1 and 5 ha networks are summarised as a sensitivity. Lines GRASS wrote with a single vertex are
dropped and counted.
Reads data/interim/drainage/*, gis/lidar_dem.tif, gis/dem_support_dist.tif; writes gis/drainage.gpkg
(sungai_turunan, das, sempadan_50m), data/processed/drainase_ringkasan.csv.
Run: uv run python scripts/15b_drainage_post.py
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
import shapely

from src import dem as dm, paths

RAW = paths.INTERIM / "drainage"
MAIN = "2ha"
SUPPORT_MAX = 30.0
BUFFER_M = 50.0
SNAP = 1.0       # m: end-to-start tolerance for the topology
DOWNHILL_TOL = 0.5


def read_raster(path):
    with rasterio.open(path) as r:
        a = r.read(1).astype(float)
        if r.nodata is not None:
            a[a == r.nodata] = np.nan
        return a, r.transform


def read_streams(name):
    g = pyogrio.read_dataframe(RAW / f"alur_{name}.gpkg", on_invalid="ignore")
    bad = int(g.geometry.isna().sum())
    g = g[g.geometry.notna()].reset_index(drop=True)
    return gpd.GeoDataFrame(g, geometry="geometry", crs=paths.CRS).explode(index_parts=False).reset_index(drop=True), bad


def strahler(lines: gpd.GeoSeries) -> np.ndarray:
    start = np.array([l.coords[0][:2] for l in lines])
    end = np.array([l.coords[-1][:2] for l in lines])
    up = {i: [j for j in range(len(lines)) if j != i and np.hypot(*(end[j] - start[i])) <= SNAP]
          for i in range(len(lines))}
    order = {}

    def visit(i, stack=()):
        if i in order:
            return order[i]
        assert i not in stack, "cycle in stream topology"
        o = [visit(j, stack + (i,)) for j in up[i]]
        if not o:
            order[i] = 1
        else:
            m = max(o)
            order[i] = m + 1 if o.count(m) >= 2 else m
        return order[i]

    return np.array([visit(i) for i in range(len(lines))])


def along(line, step=2.0):
    n = max(int(line.length // step), 1)
    p = [line.interpolate(t) for t in np.linspace(0, line.length, n + 1)]
    return np.array([q.x for q in p]), np.array([q.y for q in p])


def main():
    dem, dem_tr = read_raster(paths.GIS / "lidar_dem.tif")
    sup, sup_tr = read_raster(paths.GIS / "dem_support_dist.tif")
    rows = []
    for name in ("1ha", "2ha", "5ha"):
        g, bad = read_streams(name)
        rows.append({"ambang": name, "ruas": len(g), "panjang_m": round(g.length.sum(), 1), "garis_1_titik_dibuang": bad})
        if name != MAIN:
            continue
        g["strahler"] = strahler(g.geometry)
        g["panjang_m"] = g.length.round(1)
        xs = np.array([l.coords[0][:2] for l in g.geometry])
        xe = np.array([l.coords[-1][:2] for l in g.geometry])
        g["z_awal"] = dm.sample_bilinear(dem, dem_tr, xs[:, 0], xs[:, 1]).round(2)
        g["z_akhir"] = dm.sample_bilinear(dem, dem_tr, xe[:, 0], xe[:, 1]).round(2)
        g["menurun"] = (g.z_awal >= g.z_akhir - DOWNHILL_TOL) | g.z_akhir.isna()
        g["dukungan_rerata_m"] = [float(np.nanmean(dm.sample_bilinear(sup, sup_tr, *along(l)))) for l in g.geometry]
        g["ragu"] = g.dukungan_rerata_m > SUPPORT_MAX
        g["label"] = "drainase turunan (lidar)"
        reach = g[["cat", "strahler", "panjang_m", "z_awal", "z_akhir", "menurun", "dukungan_rerata_m", "ragu",
                   "label", "geometry"]]
    das = pyogrio.read_dataframe(RAW / f"das_{MAIN}.gpkg").dissolve("das_id").reset_index()
    das["luas_ha"] = (das.area / 1e4).round(2)
    buf = gpd.GeoDataFrame({"jarak_m": [BUFFER_M], "dasar": ["Permen PUPR 28/PRT/M/2015 [VERIFY]"]},
                           geometry=[reach.geometry.buffer(BUFFER_M).union_all()], crs=paths.CRS)

    out = paths.GIS / "drainage.gpkg"
    for layer, gdf in (("sungai_turunan", reach), ("das", das), ("sempadan_50m", buf)):
        gdf.to_file(out, layer=layer, driver="GPKG", engine="pyogrio", mode="w")   # "w" replaces this layer only
        assert len(pyogrio.read_dataframe(out, layer=layer)) == len(gdf), layer
    summ = pd.DataFrame(rows)
    summ.to_csv(paths.PROCESSED / "drainase_ringkasan.csv", index=False)
    print(summ.to_string(index=False))
    print(f"2 ha: {len(reach)} reaches, Strahler {reach.strahler.value_counts().sort_index().to_dict()}; "
          f"ragu {int(reach.ragu.sum())} ({reach.loc[reach.ragu, 'panjang_m'].sum():.0f} m); "
          f"not downhill {int((~reach.menurun).sum())}; basins {len(das)} ({das.luas_ha.sum():.1f} ha); "
          f"buffer {buf.area.iloc[0] / 1e4:.1f} ha")
    if (~reach.menurun).any():
        print(reach.loc[~reach.menurun, ["cat", "panjang_m", "z_awal", "z_akhir", "dukungan_rerata_m"]].to_string(index=False))


if __name__ == "__main__":
    main()
