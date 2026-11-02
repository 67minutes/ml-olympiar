"""Stage 6: 1 m composites (AGENTS.md §5.5). Plan: LOG.md, 2026-11-03 Stage 6 entry.

Fixed 1 m length-weighted composites of the DL-harmonised `_ml` analytes, CN ratios as
ratios of sums, log labels at the composite midpoint (Stage 5 rules), quality flags and
XYZ. Reads data/interim/05_assay_joined.csv, 03_collar.csv, 03_survey.csv and 04_*.csv;
writes data/interim/06_composites.csv, the composites layer in gis/drillholes.gpkg and
outputs/figures/qc/06_composite_v1.png. Prints counts only.
Run: uv run python scripts/06_composite.py
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import composite, desurvey, joins, loaders, paths

NOT_ADDITIVE = ("NAGpH",)  # NAGpH and both NAG kg/t columns: ML-5 uses the original samples
CENS = ["AuPPM", "AgPPM", "CuPPM", "AsPPM", "SCIS_PCT", "AgCNPPM", "CuCNPPM"]
RATIOS = {"AuCN_ratio": ("AuCNPPM", "AuPPM"), "AgCN_ratio": ("AgCNPPM", "AgPPM"),
          "CuCN_ratio": ("CuCNPPM", "CuPPM")}
CORE = ["AuPPM_ml", "AgPPM_ml", "CuPPM_ml", "AsPPM_ml"]
QC_HOLES = ["RJDH008", "RJDH012"]
GPKG_COLS = ["SiteID", "DepthFrom", "DepthTo", "comp_len", "comp_cov_m", "comp_ok", "comp_shared_src", *CORE,
             "CuCN_ratio", "Lith_group", "AltFacies", "alt_ml_label", "ox_state", "ox_state_derived",
             "DomMin1_h", "min_logged", *joins.MIN_FLAGS, "lith_mixed", "alt_mixed"]


def check_tiling(c: pd.DataFrame, collar: pd.DataFrame) -> bool:
    ok = True
    for site, g in c.groupby("SiteID", sort=False):
        eoh = collar.loc[collar.SiteID.eq(site), "EndDepth"].iloc[0]
        ok &= g.DepthFrom.iloc[0] == 0 and np.isclose(g.DepthTo.iloc[-1], eoh)
        ok &= np.allclose(g.DepthFrom.iloc[1:].to_numpy(), g.DepthTo.iloc[:-1].to_numpy())
    return bool(ok and set(c.SiteID) == set(collar.SiteID))


def metal_balance(a: pd.DataFrame, comp: pd.DataFrame, cols: list[str]) -> tuple[bool, pd.Series]:
    """Σ(cov·value) over composites == Σ(L·value) over sampled assays, per hole and column
    (no minimum coverage). Also returns the share of metal·m in composites the 0.5 m rule
    blanks."""
    v, cov = composite.composite(a, comp, cols, min_cov=0.0, return_cov=True)
    s = a[~a.no_sample]
    ok = True
    for site in comp.SiteID.unique():
        ci, si = comp.SiteID.eq(site), s.SiteID.eq(site)
        lhs = (v[ci] * cov[ci]).sum()
        rhs = s.loc[si, cols].mul(s.loc[si].DepthTo - s.loc[si].DepthFrom, axis=0).sum()
        ok &= bool(np.allclose(lhs, rhs, rtol=1e-6, atol=1e-9))
    blanked = cov.lt(composite.MIN_COV_M - 1e-9) & cov.gt(0)
    dropped = (v * cov).where(blanked).sum() / (v * cov).sum()
    return ok, dropped


def source_checks(a: pd.DataFrame, comp: pd.DataFrame, t: pd.DataFrame) -> tuple[bool, bool]:
    """Single-source full-cover composites equal their source; values within source min-max."""
    ov = joins.overlap_table(comp, a)
    ov = ov[~a.no_sample.loc[ov.l_idx].to_numpy()]
    eq_ok = rng_ok = True
    for col in CORE:
        src = a[col].loc[ov.l_idx].to_numpy()
        p = ov.assign(v=src).dropna(subset=["v"])
        g = p.groupby("a_idx")
        lo, hi, n, cov = g.v.min(), g.v.max(), g.size(), g.ov.sum()
        val = t[col].loc[lo.index]
        rng_ok &= bool(((val >= lo - 1e-9) & (val <= hi + 1e-9) | val.isna()).all())
        one = (n == 1) & np.isclose(cov, comp.comp_len.loc[cov.index])
        kept = cov >= composite.MIN_COV_M - 1e-9  # final partials < 0.5 m are blanked by rule
        eq_ok &= bool(np.allclose(val[one & kept], lo[one & kept])) and val[one & ~kept].isna().all()
    return eq_ok, rng_ok


def qc_figure(a: pd.DataFrame, t: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, len(QC_HOLES), figsize=(9, 10), sharex=True)
    for ax, site in zip(axes, QC_HOLES):
        s = a[a.SiteID.eq(site) & ~a.no_sample]
        c = t[t.SiteID.eq(site)]
        for r in s.itertuples():
            ax.plot([r.AuPPM_ml] * 2, [r.DepthFrom, r.DepthTo], color="0.6", lw=2.5, solid_capstyle="butt")
        ax.step(c.AuPPM_ml, c.DepthFrom, where="post", color="#b2182b", lw=1)
        ax.plot([], [], color="0.6", lw=2.5, label="Assay asli")
        ax.plot([], [], color="#b2182b", lw=1, label="Komposit 1 m")
        ax.set_xscale("log")
        ax.invert_yaxis()
        ax.set_title(site)
        ax.set_xlabel("Au (ppm, skala log)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Kedalaman (m)")
    axes[0].legend(loc="lower right", fontsize=8)
    fig.suptitle("Komposit 1 m terhadap assay asli (Au)")
    path = paths.FIGURES / "qc" / "06_composite_v1.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    bad = loaders.verify_raw()
    assert not bad, f"raw files changed: {bad}"
    a = pd.read_csv(paths.INTERIM / "05_assay_joined.csv", low_memory=False)
    collar = pd.read_csv(paths.INTERIM / "03_collar.csv")
    stations = pd.read_csv(paths.INTERIM / "03_survey.csv")
    logs = {n: pd.read_csv(paths.INTERIM / f"04_{n}.csv", low_memory=False) for n in joins.LOGS}
    cols = [c for c in a.columns if c.endswith("_ml") and not c.startswith(NOT_ADDITIVE) and a[c].notna().any()]

    comp = composite.grid(collar)
    vals = composite.composite(a, comp, cols)
    rat = pd.DataFrame({k: composite.ratio(a, comp, cn, tot, a[k].notna()) for k, (cn, tot) in RATIOS.items()})
    cf = pd.DataFrame({f"{c}_cens_frac": composite.cens_frac(a, comp, c, f"{c}_cens_h") for c in CENS})
    q = composite.quality(a, comp)
    t = pd.concat([comp, q, vals, rat, cf], axis=1)
    t, ties = joins.attach(t, logs)
    t = desurvey.add_interval_xyz(t, stations)

    # --- checks -------------------------------------------------------------------
    bal_ok, dropped = metal_balance(a, comp, cols)
    eq_ok, rng_ok = source_checks(a, comp, t)
    facts = {
        "composites tile 0-EOH in every hole": check_tiling(t, collar),
        "total composite length = summed EndDepth": np.isclose(t.comp_len.sum(), collar.EndDepth.sum()),
        "metal balance per hole and element (rtol 1e-6)": bal_ok,
        "single-source full-cover composites equal their source (Au/Ag/Cu/As)": eq_ok,
        "composite values within source min-max (Au/Ag/Cu/As)": rng_ok,
        "ox_state null only on RJDH019": set(t.loc[t.ox_state.isna(), "SiteID"]) == {"RJDH019"},
        "oxide and mineral labels never mixed (grid aligned)": not (t.ox_mixed.any() or t.min_mixed.any()),
        "no NAG columns composited": not any(c.startswith("NAG") for c in t.columns),
    }
    print("Plan checks")
    for k, ok in facts.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {k}")
    assert all(facts.values()), "check failed: stop and report"

    # --- summary ------------------------------------------------------------------
    print(f"\nComposites: {len(t)} ({t.SiteID.nunique()} holes, {t.comp_len.sum():.1f} m); "
          f"comp_ok {int(t.comp_ok.sum())}, not ok {int((~t.comp_ok).sum())}; "
          f"final partials < 0.5 m {int((t.comp_len < 0.5).sum())}")
    print(f"Sources per composite: {t.comp_nsrc.value_counts().sort_index().to_dict()}; "
          f"comp_shared_src {int(t.comp_shared_src.sum())}; S_method_c {t.S_method_c.value_counts().to_dict()}")
    print(f"Composited `_ml` columns: {len(cols)}; filled (non-null) per core element: "
          + ", ".join(f"{c} {int(t[c].notna().sum())}" for c in CORE)
          + "; ratios: " + ", ".join(f"{k} {int(t[k].notna().sum())}" for k in RATIOS))
    print("Share of metal x length blanked by the 0.5 m rule (core): "
          + ", ".join(f"{c} {100 * dropped[c]:.2f}%" for c in CORE))
    print(f"Labels: midpoint on a boundary {ties}; lith_mixed {int(t.lith_mixed.sum())}, "
          f"alt_mixed {int(t.alt_mixed.sum())}; min_logged False {int((~t.min_logged).sum())}")
    s = a[~a.no_sample]
    L = s.DepthTo - s.DepthFrom
    print("\nRaw assays vs composites (comp_ok): n | mean | length-weighted raw mean | CV")
    for c in CORE:
        r, k = s[c].dropna(), t.loc[t.comp_ok, c].dropna()
        lw = (s[c] * L).sum() / L[s[c].notna()].sum()
        print(f"  {c:9s} raw {len(r):5d} | {r.mean():8.3f} | {lw:8.3f} | {r.std() / r.mean():5.2f}   "
              f"comp {len(k):5d} | {k.mean():8.3f} | {'':8s} | {k.std() / k.mean():5.2f}")

    # --- outputs ----------------------------------------------------------------
    t.to_csv(paths.INTERIM / "06_composites.csv", index=False)
    g = gpd.GeoDataFrame(t[GPKG_COLS], crs=paths.CRS, geometry=gpd.points_from_xy(t.X_mid, t.Y_mid, t.Z_mid))
    for c in g.columns.drop("geometry"):
        if str(g[c].dtype) == "boolean":
            g[c] = g[c].astype("Int8")  # OGR has no nullable bool: 1/0, NA stays null
    assert g.min_py.isna().sum() == t.min_py.isna().sum(), "NA mineral flags lost on the gpkg write"
    g.to_file(paths.GIS / "drillholes.gpkg", layer="composites", driver="GPKG", engine="pyogrio", mode="w")
    qc_figure(a, t)
    print("\nOutputs")
    print(f"  06_composites.csv: {t.shape[0]} rows x {t.shape[1]} cols")
    print(f"  gis/drillholes.gpkg layer composites: {len(g)} points")
    print("  outputs/figures/qc/06_composite_v1.png")
    print("\nall checks passed")


if __name__ == "__main__":
    main()
