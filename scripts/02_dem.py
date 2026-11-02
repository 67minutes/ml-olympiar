"""Stage 2: lidar DEM (AGENTS.md §3). Plan: LOG.md, 2026-11-02 Stage 2 entry.

Reads the raw contours, writes gis/*.tif, data/interim/02_dem_cv.csv and a QC preview.
Prints counts and scores only. Run: uv run python scripts/02_dem.py
"""
import time

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src import dem, loaders, paths

CELL = 2.0
TIN_SPACING = 2.0        # m between points along contours for the TIN
TPS_SPACING = 5.0        # coarser for the local spline, so 64 neighbours span several contours
TPS_SMOOTHING = [0.0, 1.0, 10.0]
CV_TEST_EVERY = 5        # use every 5th held-out point when scoring
FLAT_DEG = 1.0
WEAK_SUPPORT_M = 30.0
Z_RANGE = (255.0, 675.0)
BLOCK_M = 100.0          # spatial-block CV: removing a 100 m block mimics the real contour gaps
BLOCK_FOLDS = 5


def _score_pair(rows, scheme, preds, truth):
    """Score all methods on the points where every method has a prediction (TIN cannot
    extrapolate beyond its training hull)."""
    common = np.all([np.isfinite(p) for p in preds.values()], axis=0)
    for (method, smoothing), p in preds.items():
        rows.append(dict(scheme=scheme, method=method, smoothing=smoothing,
                         **dem.cv_scores(p[common], truth[common])))


def run_cv(contours):
    rows = []
    # (a) whole contour lines: fit 10 m contours, predict every 5 m contour in between
    train, test = dem.holdout_split(contours)
    txy, tz = dem.resample_points(test, TIN_SPACING)
    txy, tz = txy[::CV_TEST_EVERY], tz[::CV_TEST_EVERY]
    bxy, bz = dem.resample_points(train, TIN_SPACING)
    preds = {("tin", np.nan): dem.fit_tin(bxy, bz)(txy)}
    xy, z = dem.resample_points(train, TPS_SPACING)
    for sm in TPS_SMOOTHING:
        preds[("tps", sm)] = dem.fit_tps(xy, z, sm)(txy)
        preds[("tps_clip", sm)] = dem.bracket_clip(preds[("tps", sm)], txy, bxy, bz)[0]
    _score_pair(rows, "contour_lines", preds, tz)

    # (b) spatial blocks: hold out every contour point inside whole BLOCK_M blocks
    xy2, z2 = dem.resample_points(contours, TIN_SPACING)
    xy5, z5 = dem.resample_points(contours, TPS_SPACING)
    f2 = dem.block_folds(xy2, BLOCK_M, BLOCK_FOLDS)
    f5 = dem.block_folds(xy5, BLOCK_M, BLOCK_FOLDS)
    preds, truth = {}, []
    for k in range(BLOCK_FOLDS):
        test_i = np.flatnonzero(f2 == k)[::CV_TEST_EVERY]
        truth.append(z2[test_i])
        q, trxy, trz = xy2[test_i], xy2[f2 != k], z2[f2 != k]
        fold_preds = {("tin", np.nan): dem.fit_tin(trxy, trz)(q)}
        for sm in TPS_SMOOTHING:
            fold_preds[("tps", sm)] = dem.fit_tps(xy5[f5 != k], z5[f5 != k], sm)(q)
            fold_preds[("tps_clip", sm)] = dem.bracket_clip(fold_preds[("tps", sm)], q, trxy, trz)[0]
        for key, p in fold_preds.items():
            preds.setdefault(key, []).append(p)
    _score_pair(rows, f"blocks_{BLOCK_M:g}m", {k: np.concatenate(v) for k, v in preds.items()},
                np.concatenate(truth))
    return pd.DataFrame(rows)


def main() -> None:
    t0 = time.time()
    assert not loaders.verify_raw(), "raw files changed"
    all_lines = loaders.load_contours()
    contours = dem.load_clean_contours()
    print(f"contours: {len(all_lines)} lines, kept {len(contours)} real, "
          f"dropped {len(all_lines) - len(contours)} construction fragments")

    cv = run_cv(contours)
    print(f"\nhold-out CV: whole contour lines, and {BLOCK_M:g} m spatial blocks "
          f"[{time.time() - t0:.0f}s]")
    print(cv.round(3).to_string(index=False))

    gx, gy, transform = dem.make_grid(contours.total_bounds, CELL)
    mask = dem.hull_mask(contours, gx, gy)
    xy2, z2 = dem.resample_points(contours, TIN_SPACING)
    xy5, z5 = dem.resample_points(contours, TPS_SPACING)

    # Method (human decision 2026-11-02): spline clipped to its framing contours +/- one
    # interval far from contours. It must beat the TIN in every CV scheme, else stop.
    tin = dem.fit_tin(xy2, z2)
    clip_cv = cv[cv.method == "tps_clip"]
    sm = clip_cv.groupby("smoothing").rmse.mean().idxmin()
    wins = {}
    for scheme, g in cv.groupby("scheme"):
        t = g[g.method == "tin"].rmse.iloc[0]
        c = g[(g.method == "tps_clip") & (g.smoothing == sm)].rmse.iloc[0]
        wins[scheme] = round(t - c, 3)
    assert all(v > 0 for v in wins.values()), f"clipped spline does not beat TIN everywhere {wins}"
    cv["chosen"] = (cv.method == "tps_clip") & (cv.smoothing == sm)
    tps = dem.fit_tps(xy5, z5, sm)
    grids = {"tin": dem.evaluate_on_grid(tin, gx, gy, mask),
             "tps": dem.evaluate_on_grid(tps, gx, gy, mask)}
    out = grids["tps"].copy()
    out[mask], was_clipped = dem.bracket_clip(out[mask], np.c_[gx[mask], gy[mask]], xy2, z2)
    clipped = np.full(out.shape, np.nan)
    clipped[mask] = was_clipped
    grids["tps_clip"] = out
    model = lambda q: dem.bracket_clip(tps(q), q, xy2, z2)[0]
    flat = {k: float(np.nanmean(dem.slope_deg(g, CELL)[mask] < FLAT_DEG)) for k, g in grids.items()}
    cv["flat_cell_frac"] = np.where(cv.method == "tin", flat["tin"],
                                    np.where(cv.smoothing == sm, cv.method.map(flat), np.nan))
    print(f"\nflat cells (<{FLAT_DEG} deg): " + ", ".join(f"{k} {v:.3f}" for k, v in flat.items()))
    print(f"chosen: tps_clip (smoothing {sm:g}); RMSE gain over TIN per scheme {wins}; "
          f"clipped {int(was_clipped.sum())} cells ({was_clipped.mean():.2%}) [{time.time() - t0:.0f}s]")

    # --- clamp -------------------------------------------------------------------
    # No 675 m contour exists, so the summit inside the closed 670 m ring must stay
    # below 675 m (same logic below the lowest contour). A spline can overshoot slightly.
    zmin, zmax = np.nanmin(out[mask]), np.nanmax(out[mask])
    outside = mask & ((out < Z_RANGE[0]) | (out > Z_RANGE[1]))
    print(f"\nDEM before clamp: z {zmin:.2f}-{zmax:.2f} m; {outside.sum()} cells outside "
          f"[{Z_RANGE[0]:g}, {Z_RANGE[1]:g}] m, max excess "
          f"{max(zmax - Z_RANGE[1], Z_RANGE[0] - zmin, 0):.2f} m -> clamped")
    assert outside.sum() <= 1e-4 * mask.sum(), "overshoot too large to clamp silently: stop and report"
    out = np.clip(out, *Z_RANGE)

    # --- checks -----------------------------------------------------------------
    print(f"DEM: {out.shape[1]} x {out.shape[0]} cells, {mask.sum()} inside hull, "
          f"z {np.nanmin(out[mask]):.1f}-{np.nanmax(out[mask]):.1f} m, "
          f"NaN inside hull {np.isnan(out[mask]).sum()}")
    assert not np.isnan(out[mask]).any(), "holes inside the hull"

    res = model(xy2) - z2
    res_raster = dem.sample_bilinear(out, transform, xy2[:, 0], xy2[:, 1]) - z2
    print(f"residual at contour points: model p95 |res| {np.nanpercentile(np.abs(res), 95):.3f} m; "
          f"raster (bilinear) p95 {np.nanpercentile(np.abs(res_raster), 95):.3f} m")
    assert np.nanpercentile(np.abs(res), 95) < 0.5, "DEM does not honour the contours"

    support = dem.support_distance(xy2, gx, gy, mask)
    print(f"support distance: median {np.nanmedian(support):.1f} m, "
          f"{np.nanmean(support[mask] > WEAK_SUPPORT_M):.1%} of cells > {WEAK_SUPPORT_M:g} m from a contour")
    print("cells where TIN and spline differ by > 5 m (one contour interval), by support distance:")
    for lo, hi in [(0, 10), (10, 30), (30, 60), (60, np.inf)]:
        sel = mask & (support >= lo) & (support < hi)
        big = sel & (np.abs(grids["tin"] - grids["tps"]) > 5)
        print(f"  {lo:>3g}-{hi:<4g} m: {big.sum():>6} of {sel.sum():>7} ({big.sum() / max(sel.sum(), 1):.1%})")

    # overshoot across contour gaps: more than one interval beyond every nearby contour
    grids["tps_clip"] = out
    over = {k: dem.gap_overshoot(np.clip(g, *Z_RANGE), support, xy2, z2, gx, gy)
            for k, g in grids.items()}
    print("gap overshoot cells (> 1 interval outside the enclosing contour triangle): "
          + ", ".join(f"{k} {v.sum()} ({v.sum() / mask.sum():.3%})" for k, v in over.items()))
    assert over["tps_clip"].sum() == 0, "final DEM overshoots gaps: stop and report"

    # AGENTS.md §4.1 / §4.2.8 numbers were computed on a TIN-like DEM (human decision,
    # 2026-11-02). Only the method-stable facts are asserted; the rest are reported.
    print("\nAGENTS.md checks (chosen DEM | TIN reference)")
    col = loaders.load_dh("collar")
    dz = {k: col.RLUTM.to_numpy() - dem.sample_bilinear(g, transform, col.EastUTM, col.NorthUTM)
          for k, g in [("chosen", out), ("tin", grids["tin"])]}
    col["dz"] = dz["chosen"]
    pads = col.SiteID.isin(["RJDH002", "RJDH006"]).to_numpy()
    for k, v in dz.items():
        print(f"  {k:6s} RJDH002 / RJDH006 RL - DEM = {v[col.SiteID.eq('RJDH002')][0]:.1f} / "
              f"{v[col.SiteID.eq('RJDH006')][0]:.1f} m (AGENTS: -7.8 / -5.1, method-dependent: "
              f"595/600 m contours missing at both pads); other 17 max |dz| {np.abs(v[~pads]).max():.2f} m")
    ok_others = np.abs(dz["chosen"][~pads]).max() <= 2.5
    print(f"  {'OK  ' if ok_others else 'FAIL'} other 17 collars within 2.5 m of the chosen DEM")

    expected30 = {"rock": 13, "soil": 6}
    ok_surface = True
    for name, df in [("rock", loaders.load_rock()), ("soil", loaders.load_soil())]:
        got = {}
        for k, g in [("chosen", out), ("tin", grids["tin"])]:
            d = (df.Elevation - dem.sample_bilinear(g, transform, df.Easting, df.Northing)).abs()
            got[k] = (int((d > 10).sum()), int((d > 30).sum()), int(d.isna().sum()))
        ok = got["chosen"][1] == expected30[name]
        ok_surface &= ok
        print(f"  {'OK  ' if ok else 'FAIL'} {name}: >30 m = {got['chosen'][1]} (AGENTS {expected30[name]}, "
              f"stable); >10 m = {got['chosen'][0]} chosen / {got['tin'][0]} TIN "
              f"(AGENTS {dict(rock=40, soil=15)[name]}, DEM-dependent); no DEM value {got['chosen'][2]}")
    assert ok_others and ok_surface, "method-stable AGENTS.md fact not reproduced: stop and report"
    gap_panels(out, transform, contours, support)

    # --- outputs ----------------------------------------------------------------
    dem.write_geotiff(paths.GIS / "lidar_dem.tif", out, transform)
    dem.write_geotiff(paths.GIS / "hillshade.tif", dem.hillshade(out, CELL), transform)
    dem.write_geotiff(paths.GIS / "slope_deg.tif", dem.slope_deg(out, CELL), transform)
    dem.write_geotiff(paths.GIS / "dem_support_dist.tif", support, transform)
    dem.write_geotiff(paths.GIS / "dem_clipped.tif", clipped, transform)
    paths.INTERIM.mkdir(parents=True, exist_ok=True)
    cv.to_csv(paths.INTERIM / "02_dem_cv.csv", index=False)
    preview(out, transform, contours, col)
    print(f"\nwrote gis/lidar_dem.tif, hillshade.tif, slope_deg.tif, dem_support_dist.tif, "
          f"dem_clipped.tif, 02_dem_cv.csv, qc preview [{time.time() - t0:.0f}s]")
    print("all checks passed")


def gap_panels(out, transform, contours, support, n: int = 4) -> None:
    """QC: hillshade of the largest weakly supported patches, with the original contours
    (black) and contours re-drawn from the DEM (red dashed). Overshoot shows up as red
    closed loops or red lines with no black partner."""
    from scipy import ndimage
    lab, k = ndimage.label(np.nan_to_num(support) > WEAK_SUPPORT_M)
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, k + 1))
    biggest = np.argsort(sizes)[::-1][:n] + 1
    hs = dem.hillshade(out, CELL)
    cell = transform.a
    xs = transform.c + cell * (np.arange(out.shape[1]) + 0.5)
    ys = transform.f - cell * (np.arange(out.shape[0]) + 0.5)
    fig, axes = plt.subplots(2, 2, figsize=(12, 12))
    for ax, b in zip(axes.ravel(), biggest):
        rr, cc = np.nonzero(lab == b)
        pad = int(40 / cell)
        r0, r1 = max(rr.min() - pad, 0), min(rr.max() + pad, out.shape[0] - 1)
        c0, c1 = max(cc.min() - pad, 0), min(cc.max() + pad, out.shape[1] - 1)
        ext = [xs[c0], xs[c1], ys[r1], ys[r0]]
        ax.imshow(hs[r0:r1 + 1, c0:c1 + 1], cmap="gray", extent=ext)
        ax.contour(xs[c0:c1 + 1], ys[r0:r1 + 1], out[r0:r1 + 1, c0:c1 + 1],
                   levels=np.arange(260, 676, 5), colors="red", linewidths=0.8, linestyles="--")
        contours.cx[ext[0]:ext[1], ext[2]:ext[3]].plot(ax=ax, color="k", linewidth=0.8)
        ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
        ax.set_title(f"Celah kontur #{b} ({int(sizes[b - 1]) * cell ** 2 / 1e4:.2f} ha > {WEAK_SUPPORT_M:g} m)")
    fig.suptitle("QC: kontur asli (hitam) vs kontur dari DEM (merah putus-putus)")
    path = paths.FIGURES / "qc" / "02_dem_gaps_v1.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def preview(out, transform, contours, col) -> None:
    hs = dem.hillshade(out, CELL)
    ext = [transform.c, transform.c + transform.a * out.shape[1],
           transform.f - transform.a * out.shape[0], transform.f]
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(hs, cmap="gray", extent=ext)
    ax.imshow(out, cmap="terrain", alpha=0.35, extent=ext)
    contours.plot(ax=ax, color="k", linewidth=0.25, alpha=0.5)
    ax.scatter(col.EastUTM, col.NorthUTM, c="red", s=12, label="Collar lubang bor")
    ax.set_title("Pratinjau DEM lidar 2 m (QC, bukan gambar laporan)")
    ax.set_xlabel("Easting UTM 47N (m)")
    ax.set_ylabel("Northing UTM 47N (m)")
    ax.legend(loc="lower right")
    path = paths.FIGURES / "qc" / "02_dem_preview_v1.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
