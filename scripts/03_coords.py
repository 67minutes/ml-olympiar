"""Stage 3: coordinates (AGENTS.md §5.2). Plan: LOG.md, 2026-11-02 Stage 3 entry.

Surface re-drape on the lidar DEM, survey extrapolation to EOH, minimum-curvature desurvey.
Reads data/interim/01_*.csv, raw downhole tables and gis/*.tif; writes data/interim/03_*.csv,
gis/drillholes.gpkg, gis/surface_samples.gpkg and a QC figure. Prints counts only.
Run: uv run python scripts/03_coords.py
"""
import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import LineString

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src import coords, dem, loaders, paths
from src import desurvey as ds

LOGS = ["lithology", "alteration", "mineralisation", "oxide"]
EXPECTED_ROWS = {"rock": 469, "soil": 259, "assay": 2476, "lithology": 286, "alteration": 707,
                 "mineralisation": 2684, "oxide": 3017, "collar": 19, "survey": 99}
# Stage 2 human decision: both pads sit in a contour gap, RL - DEM is -3 to -8 m
# depending on the DEM method, so they are flagged by name rather than by threshold.
PAD_HOLES = {"RJDH002", "RJDH006"}
PAD_NOTE = "pad area, contour gap, RL - DEM -3 to -8 m depending on DEM"
AGENTS_GAPS = {"RJDH001": 82.4, "RJDH012": 51.2, "RJDH011": 34.5, "RJDH014": 15.7, "RJDH003": 2.0}
TRACE_STEP = 1.0


def read_raster(name: str):
    with rasterio.open(paths.GIS / name) as src:
        arr = src.read(1).astype(float)
        arr[arr == src.nodata] = np.nan
        return arr, src.transform


def surface(name: str, dem_arr, support, transform) -> pd.DataFrame:
    df = pd.read_csv(paths.INTERIM / f"01_{name}.csv", low_memory=False)
    if "Z_Average" in df:
        assert (df.Z_Average == 0).all(), "rock Z_Average is populated after all: report"
        df = df.drop(columns="Z_Average")
    out = coords.duplicate_xy(coords.redrape(df, dem_arr, support, transform))
    assert len(out) == EXPECTED_ROWS[name] and out.SampleID.equals(df.SampleID)
    assert out.Elev_orig.equals(df.Elevation), f"{name}: original elevation changed"
    assert out.Z.notna().all(), f"{name}: Z missing"
    assert (out.Z_dem.isna() == out.flag_elev.eq("no_dem")).all()
    return out


def check_stations(st: pd.DataFrame, collar: pd.DataFrame) -> None:
    c = collar.set_index("SiteID")
    for site, g in st.groupby("SiteID"):
        assert np.allclose(g[["X", "Y", "Z"]].iloc[0], c.loc[site, ["EastUTM", "NorthUTM", "RLUTM"]])
        assert (np.diff(g.Z) < 0).all(), f"{site}: Z not decreasing downhole"
        chord = np.linalg.norm(np.diff(g[["X", "Y", "Z"]].to_numpy(), axis=0), axis=1)
        arc = np.diff(g.DepthAt.to_numpy())
        assert (chord <= arc + 1e-9).all() and (chord >= 0.999 * arc).all(), f"{site}: chord/arc"


def tangential_eoh(st: pd.DataFrame, site: str, balanced: bool = False) -> np.ndarray:
    """EOH by the tangential method (lower station's direction) or the balanced
    tangential method (mean of both directions); sanity comparisons only."""
    g = st[st.SiteID.eq(site)]
    t = ds.unit_vectors(g.Dip.to_numpy(), g.AzimUTM.to_numpy())
    seg = (t[:-1] + t[1:]) / 2 if balanced else t[1:]
    return g[["X", "Y", "Z"]].iloc[0].to_numpy() + (np.diff(g.DepthAt)[:, None] * seg).sum(axis=0)


def interval_table(name: str, st: pd.DataFrame) -> pd.DataFrame:
    if name == "assay":
        df = pd.read_csv(paths.INTERIM / "01_assay.csv", low_memory=False)
    else:
        df = loaders.load_dh(name)
    out = ds.add_interval_xyz(df, st)
    assert len(out) == EXPECTED_ROWS[name] and out.index.equals(df.index)
    xyz = out.filter(regex="^[XYZ]_(from|mid|to)$")
    assert xyz.shape[1] == 9 and xyz.notna().all().all(), f"{name}: XYZ missing"
    assert (out.Z_from >= out.Z_to).all(), f"{name}: interval Z not decreasing"
    return out


def write_gpkg(path, layers: dict) -> None:
    path.unlink(missing_ok=True)
    for name, gdf in layers.items():
        gdf.to_file(path, layer=name, driver="GPKG", engine="pyogrio")


def qc_figure(st, traces, rock, soil, transform) -> None:
    hs, _ = read_raster("hillshade.tif")
    ext = [transform.c, transform.c + transform.a * hs.shape[1],
           transform.f - transform.a * hs.shape[0], transform.f]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(16, 8), gridspec_kw={"width_ratios": [1.3, 1]})
    ax.imshow(hs, cmap="gray", extent=ext)
    for flag, colour in [("ok", "tab:green"), ("dem_uncertain", "orange"), ("elev_error", "red"),
                         ("no_dem", "magenta")]:
        s = pd.concat([rock, soil])
        s = s[s.flag_elev.eq(flag)]
        ax.scatter(s.Easting, s.Northing, s=6, c=colour, label=f"Sampel permukaan: {flag} ({len(s)})")
    traces.plot(ax=ax, color="blue", linewidth=1.2)
    for site, g in st.groupby("SiteID"):
        if g.survey_extrap.any():
            ax.plot(g.X.iloc[-2:], g.Y.iloc[-2:], color="cyan", linewidth=2.5)
        ax.annotate(site[-3:], (g.X.iloc[0], g.Y.iloc[0]), fontsize=7)
    ax.plot([], [], color="blue", label="Lintasan lubang bor (minimum curvature)")
    ax.plot([], [], color="cyan", linewidth=2.5, label="Bagian diekstrapolasi (setelah survei terakhir)")
    ax.set_title("Lintasan bor dan flag elevasi sampel permukaan (QC, bukan gambar laporan)")
    ax.set_xlabel("Easting UTM 47N (m)")
    ax.set_ylabel("Northing UTM 47N (m)")
    ax.legend(loc="lower right", fontsize=7)
    for site, colour in [("RJDH001", "tab:blue"), ("RJDH019", "tab:red")]:
        g = st[st.SiteID.eq(site)]
        d = np.r_[np.arange(0, g.DepthAt.max(), TRACE_STEP), g.DepthAt.max()]
        p = ds.hole_positions(st, site, d)
        ax2.plot(np.hypot(*(p[:, :2] - p[0, :2]).T), d, color=colour, label=site)
    ax2.invert_yaxis()
    ax2.set_xlabel("Pergeseran horizontal dari collar (m)")
    ax2.set_ylabel("Kedalaman sepanjang lubang (m)")
    ax2.set_title("Lubang hampir vertikal: ayunan azimut hanya menggeser < beberapa meter")
    ax2.legend()
    path = paths.FIGURES / "qc" / "03_traces_v1.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    bad = loaders.verify_raw()
    assert not bad, f"raw files changed: {bad}"
    dem_arr, transform = read_raster("lidar_dem.tif")
    support, _ = read_raster("dem_support_dist.tif")

    # --- surface re-drape ---------------------------------------------------------
    rock = surface("rock", dem_arr, support, transform)
    soil = surface("soil", dem_arr, support, transform)
    print("Surface re-drape (|Elev_orig - DEM|: ok <= 10 m < dem_uncertain <= 30 m < elev_error)")
    for n, df in (("rock", rock), ("soil", soil)):
        print(f"  {n}: {df.flag_elev.value_counts().to_dict()}; DEM weakly supported "
              f"(> 30 m from a contour): {int(df.flag_dem_weak.sum())}; "
              f"duplicate-XY rows {int(df.dupxy_group.notna().sum())} in "
              f"{df.dupxy_group.nunique()} groups {df.dupxy_type[df.dupxy_type != ''].value_counts().to_dict()}")

    # --- collars and surveys --------------------------------------------------------
    collar, survey = loaders.load_dh("collar"), loaders.load_dh("survey")
    off = (survey.AzimUTM - survey.AzimOrig + 180) % 360 - 180
    print(f"\nAzimUTM - AzimOrig: min {off.min():.3f}, max {off.max():.3f} deg "
          f"(GridOrig {survey.GridOrig.unique().tolist()})")
    last = survey.groupby("SiteID").DepthAt.max()
    collar["survey_gap_m"] = (collar.EndDepth - collar.SiteID.map(last)).round(2)
    collar["Z_dem"] = dem.sample_bilinear(dem_arr, transform, collar.EastUTM, collar.NorthUTM)
    collar["RL_dz"] = collar.RLUTM - collar.Z_dem
    collar["dem_support_m"] = dem.sample_bilinear(support, transform, collar.EastUTM, collar.NorthUTM)
    collar["flag_collar_pad"] = collar.SiteID.isin(PAD_HOLES)
    collar["collar_note"] = np.where(collar.flag_collar_pad, PAD_NOTE, "")

    st = ds.desurvey(ds.extrapolate_to_eoh(survey, collar), collar)
    check_stations(st, collar)
    assert len(st) - st.survey_extrap.sum() == EXPECTED_ROWS["survey"]
    drift = ds.desurvey(ds.extrapolate_to_eoh(survey, collar, drift=True), collar)
    eoh = st.groupby("SiteID").tail(1).set_index("SiteID")
    eoh_drift = drift.groupby("SiteID").tail(1).set_index("SiteID")
    collar = collar.set_index("SiteID")
    collar["eoh_extrap_uncert_m"] = np.where(
        collar.survey_gap_m > 0,
        np.linalg.norm(eoh[["X", "Y", "Z"]] - eoh_drift.loc[eoh.index, ["X", "Y", "Z"]], axis=1), 0.0)
    collar["eoh_mincurv_vs_tangential_m"] = [
        np.linalg.norm(eoh.loc[s, ["X", "Y", "Z"]].to_numpy(float) - tangential_eoh(st, s))
        for s in collar.index]
    collar["eoh_mincurv_vs_balanced_m"] = [
        np.linalg.norm(eoh.loc[s, ["X", "Y", "Z"]].to_numpy(float) - tangential_eoh(st, s, balanced=True))
        for s in collar.index]
    collar[["EOH_X", "EOH_Y", "EOH_Z"]] = eoh[["X", "Y", "Z"]]
    collar = collar.reset_index()

    print("\nCollars and surveys")
    print(f"  RL - DEM: max |dz| of the 17 non-pad collars {collar.RL_dz[~collar.flag_collar_pad].abs().max():.2f} m; "
          + ", ".join(f"{r.SiteID} {r.RL_dz:.1f} m (support {r.dem_support_m:.0f} m)"
                      for r in collar[collar.flag_collar_pad].itertuples()))
    print("  extrapolated holes (gap m | EOH shift if the measured drift continued, m):")
    for r in collar[collar.survey_gap_m > 0].sort_values("survey_gap_m", ascending=False).itertuples():
        print(f"    {r.SiteID}: {r.survey_gap_m:5.1f} | {r.eoh_extrap_uncert_m:5.2f}")
    print(f"  min curvature vs tangential at EOH: max {collar.eoh_mincurv_vs_tangential_m.max():.2f} m "
          f"({collar.loc[collar.eoh_mincurv_vs_tangential_m.idxmax(), 'SiteID']}); "
          f"vs balanced tangential: max {collar.eoh_mincurv_vs_balanced_m.max():.3f} m")
    for site in ("RJDH001", "RJDH019"):
        g = st[st.SiteID.eq(site)]
        print(f"  {site} (near-vertical) EOH horizontal offset from collar: "
              f"{np.hypot(g.X.iloc[-1] - g.X.iloc[0], g.Y.iloc[-1] - g.Y.iloc[0]):.2f} m over {g.DepthAt.max():.1f} m")

    # --- interval tables ----------------------------------------------------------
    tables = {n: interval_table(n, st) for n in ["assay", *LOGS]}
    print("\nInterval XYZ (rows | rows reaching below the last measured station)")
    for n, df in tables.items():
        print(f"  {n}: {len(df)} | {int(df.survey_extrap.sum())}")

    # --- AGENTS.md facts ------------------------------------------------------------
    gaps = collar.set_index("SiteID").survey_gap_m
    facts = {
        "survey gaps 82.4/51.2/34.5/15.7/2.0 m (§4.2.11)":
            all(np.isclose(gaps[k], v) for k, v in AGENTS_GAPS.items())
            and set(gaps[gaps >= 1].index) == set(AGENTS_GAPS),
        "surface > 30 m: rock 13, soil 6 (§4.2.8)":
            (rock.flag_elev.eq("elev_error").sum(), soil.flag_elev.eq("elev_error").sum()) == (13, 6),
        "surface 10-30 m: rock 35, soil 13 (Stage 2)":
            (rock.flag_elev.eq("dem_uncertain").sum(), soil.flag_elev.eq("dem_uncertain").sum()) == (35, 13),
        "1 rock sample with no DEM value (§3)": rock.flag_elev.eq("no_dem").sum() == 1
            and soil.flag_elev.eq("no_dem").sum() == 0,
        "13 extra duplicate-XY rock rows, none in soil (§4.2.6)":
            rock.dupxy_group.notna().sum() - rock.dupxy_group.nunique() == 13
            and soil.dupxy_group.notna().sum() == 0,
        "17 non-pad collars within 2.5 m of the DEM (§4.1)":
            (collar.RL_dz[~collar.flag_collar_pad].abs() <= 2.5).all(),
    }
    print("\nAGENTS.md checks")
    for k, ok in facts.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {k}")
    assert all(facts.values()), "AGENTS.md fact not reproduced: stop and report"

    # --- outputs ----------------------------------------------------------------
    out = {"rock": rock, "soil": soil, **tables, "collar": collar, "survey": st}
    for n, df in out.items():
        df.to_csv(paths.INTERIM / f"03_{n}.csv", index=False)

    traces = []
    for site, g in st.groupby("SiteID"):
        d = np.r_[np.arange(0, g.DepthAt.max(), TRACE_STEP), g.DepthAt.max()]
        traces.append({"SiteID": site, "EndDepth": g.DepthAt.max(),
                       "survey_gap_m": gaps[site], "geometry": LineString(ds.hole_positions(st, site, d))})
    traces = gpd.GeoDataFrame(traces, crs=paths.CRS)
    a = tables["assay"]
    write_gpkg(paths.GIS / "drillholes.gpkg", {
        "collars": gpd.GeoDataFrame(collar, crs=paths.CRS, geometry=gpd.points_from_xy(
            collar.EastUTM, collar.NorthUTM, collar.RLUTM)),
        "traces": traces,
        "assay_mid": gpd.GeoDataFrame(a, crs=paths.CRS, geometry=gpd.points_from_xy(a.X_mid, a.Y_mid, a.Z_mid)),
    })
    write_gpkg(paths.GIS / "surface_samples.gpkg", {
        n: gpd.GeoDataFrame(df, crs=paths.CRS, geometry=gpd.points_from_xy(df.Easting, df.Northing, df.Z))
        for n, df in (("rock", rock), ("soil", soil))})
    qc_figure(st, traces, rock, soil, transform)

    print("\nOutputs")
    for n, df in out.items():
        print(f"  03_{n}.csv: {df.shape[0]} rows x {df.shape[1]} cols")
    print("  gis/drillholes.gpkg (collars, traces, assay_mid), gis/surface_samples.gpkg (rock, soil), "
          "outputs/figures/qc/03_traces_v1.png")
    print("\nall checks passed")


if __name__ == "__main__":
    main()
