"""Stage 5: joins (AGENTS.md §5.4). Plan: LOG.md, 2026-11-03 Stage 5 entry.

Attaches the Stage 4 lithology, alteration, oxidation and mineralisation labels to every
assay interval by midpoint, with join-quality columns and length-weighted percentages.
Reads data/interim/03_assay.csv and 04_*.csv; writes data/interim/05_assay_joined.csv and
the assay_mid_logs layer in gis/drillholes.gpkg. Prints counts only.
Run: uv run python scripts/05_joins.py
"""
import geopandas as gpd
import pandas as pd

from src import joins, loaders, paths

MIN_FLAGS = joins.MIN_FLAGS
LOGS = joins.LOGS
# profiled 3 Nov: the mineralisation log does not reach these assay stretches
MIN_UNCOVERED = {"RJDH002", "RJDH003", "RJDH004", "RJDH005", "RJDH007"}
N_MIN_MISSING = 14
GPKG_COLS = ["SiteID", "SampleID", "DepthFrom", "DepthTo", "AuPPM", "AgPPM", "AsPPM", "CuPPM", "no_sample",
             "Lith_group", "AltFacies", "alt_ml_label", "ox_state", "ox_state_derived", "WRAltOxidPcnt_lw",
             "DomMin1_h", "min_logged", *MIN_FLAGS, "lith_mixed", "alt_mixed", "ox_mixed", "min_mixed"]


def nag_check(t: pd.DataFrame) -> dict:
    """AGENTS §4.3, reproduced from the joined table."""
    nag = t[t.NAGpH.notna()]
    acid = nag.NAGpH < 4.5
    by = nag.groupby("ox_state").NAGpH.agg(n="size", acid=lambda s: (s < 4.5).mean())
    print("\nRJDH012 NAG by joined ox_state (n, share NAG pH < 4.5)")
    print("  " + by.round(3).to_string().replace("\n", "\n  "))
    return {
        "AGENTS 4.3: NAG pH available for 106 samples, 69 < 4.5": len(nag) == 106 and acid.sum() == 69,
        "AGENTS 4.3: Sulphide zone 16 samples, 100% < 4.5":
            by.loc["Sulphide", "n"] == 16 and by.loc["Sulphide", "acid"] == 1.0,
        "AGENTS 4.3: Oxide zone 90 samples, 59% < 4.5": by.loc["Oxide", "n"] == 90 and round(by.loc["Oxide", "acid"], 2) == 0.59,
    }


def sanity(t: pd.DataFrame) -> None:
    s = t[~t.no_sample].assign(CN_Cu=t.CuCNPPM / t.CuPPM)
    for by in ["alt_ml_label", "ox_state", "Lith_group"]:
        g = s.groupby(by).agg(n=("AuPPM", "size"), Au=("AuPPM", "median"), Cu=("CuPPM", "median"),
                              CN_Cu=("CN_Cu", "median"))
        print(f"\nMedians by {by} (sampled intervals)")
        print("  " + g.round(3).to_string().replace("\n", "\n  "))
    g = s.groupby(s.min_cu.astype(object).fillna("not logged")).CuPPM.agg(["size", "median"])
    print("\nCuPPM by joined min_cu")
    print("  " + g.round(1).to_string().replace("\n", "\n  "))


def main() -> None:
    bad = loaders.verify_raw()
    assert not bad, f"raw files changed: {bad}"
    assay = pd.read_csv(paths.INTERIM / "03_assay.csv", low_memory=False)
    logs = {n: pd.read_csv(paths.INTERIM / f"04_{n}.csv", low_memory=False) for n in LOGS}
    t, ties = joins.attach(assay, logs)

    # --- checks -------------------------------------------------------------------
    miss = t[t.min_missing]
    long_enough = {p: (t[f"{p}to"] - t[f"{p}from"]) >= (t.DepthTo - t.DepthFrom) for p, *_ in LOGS.values()}
    facts = {
        "row count unchanged (2,476)": len(t) == len(assay) == 2476,
        "03_assay columns unchanged": t[assay.columns].equals(assay),
        "one lithology / alteration / oxide interval per assay":
            not (t.lith_missing | t.alt_missing | t.ox_missing).any(),
        f"mineralisation misses = {N_MIN_MISSING}, all in {sorted(MIN_UNCOVERED)}":
            len(miss) == N_MIN_MISSING and set(miss.SiteID) <= MIN_UNCOVERED,
        "ox_state null only on RJDH019": set(t.loc[t.ox_state.isna(), "SiteID"]) == {"RJDH019"},
        "ox_state_derived filled everywhere": t.ox_state_derived.notna().all(),
        "frac >= 0.5 where the matched interval is at least as long as the assay":
            all((t.loc[long_enough[p], f"{p}frac"] >= 0.5).all() for p in long_enough),
        "RJDH001 mineral flags are NA (not logged)": t.loc[t.SiteID.eq("RJDH001"), "min_py"].isna().all(),
        **nag_check(t),
    }
    print("\nAGENTS.md / plan checks")
    for k, ok in facts.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {k}")
    assert all(facts.values()), "check failed: stop and report"

    # --- summary ------------------------------------------------------------------
    print("\nJoin quality per log (assays: midpoint on a boundary | spanning >1 label | frac < 0.5 | missing)")
    for name, (p, key, *_) in LOGS.items():
        print(f"  {name:15s} {ties[name]:4d} | {int(t[f'{p}mixed'].sum()):4d} | "
              f"{int((t[f'{p}frac'] < 0.5).sum()):4d} | {int(t[f'{p}missing'].sum()):3d}   (key {key})")
    print(f"min_logged False: {int((~t.min_logged).sum())} assays "
          f"({t.loc[~t.min_logged, 'SiteID'].value_counts().to_dict()})")
    d = (t.WRAltOxidPcnt_lw - t.WRAltOxidPcnt).abs()
    print(f"WRAltOxidPcnt length-weighted vs midpoint: differ in {int((d > 0).sum())} assays, "
          f"by >= 25 points in {int((d >= 25).sum())}")
    sanity(t)

    # --- outputs ----------------------------------------------------------------
    t.to_csv(paths.INTERIM / "05_assay_joined.csv", index=False)
    g = gpd.GeoDataFrame(t[GPKG_COLS], crs=paths.CRS, geometry=gpd.points_from_xy(t.X_mid, t.Y_mid, t.Z_mid))
    for c in g.columns.drop("geometry"):
        if str(g[c].dtype) == "boolean":
            g[c] = g[c].astype("Int8")  # OGR has no nullable bool: 1/0, NA stays null (object writes "<NA>")
    assert g.min_py.isna().sum() == t.min_py.isna().sum(), "NA mineral flags lost on the gpkg write"
    g.to_file(paths.GIS / "drillholes.gpkg", layer="assay_mid_logs", driver="GPKG", engine="pyogrio", mode="w")
    print("\nOutputs")
    print(f"  05_assay_joined.csv: {t.shape[0]} rows x {t.shape[1]} cols")
    print(f"  gis/drillholes.gpkg layer assay_mid_logs: {len(g)} points")
    print("\nall checks passed")


if __name__ == "__main__":
    main()
