"""ML-6: drill targeting by Gaussian process = kriging (AGENTS.md §6 task 6, bonus). Plan: LOG.md,
2026-11-03 ML-6 entry.

Stage `gp`: log10 Au on 1 m composites (censored spread on [DL/3, DL], others dequantised, averaged
over 20 draws), regularised to 2 m within contiguous segments; anisotropic Matérn(1.5) + nugget in a
strike frame; strike θ by profile likelihood; leave-one-pad-out CV of NE 45°, ENE 75°, best θ and
isotropic (plus a mean-only baseline); kriging equivalence check; 10 × 10 × 5 m block model with
μ, σ, P(Au ≥ 0.5 g/t) and UCB.
Stage `design`: Tier A portfolio (two extension holes by expected metres ≥ 0.5 g/t, one gap-closing hole
by kriging variance where UCB κ = 2 ≥ cutoff; new rock only; greedy with posterior-variance update), Tier B step-out holes (ML-3
soil-index UCB), environmental columns (derived drainage, slope, ML-5 PAF), and section D–D' through
RJ-U01 (gis/ml6_penampang.gpkg).

Reads data/interim/06_composites.csv, 03_collar.csv, 01_element_summary.csv, gis/lidar_dem.tif,
gis/slope_deg.tif, gis/drainage.gpkg, gis/ml3_tanah_indeks{,_sd}.tif, gis/ml5_paf.gpkg,
data/processed/ml/assay__ml5_paf.csv; writes data/processed/ml/komposit__ml6_gp.csv,
data/processed/ml6_{summary,cv,profil_theta,kandidat,usulan_lubang}.csv, data/interim/ml6_blok.csv,
gis/ml6_{ucb_maks,meter_cutoff,sd_rerata}.tif, gis/ml6_target.gpkg, outputs/figures/13_*_v1.png.
Run: uv run python scripts/16_ml6_targeting.py [--stage gp|design|all]  (then scripts/07_export.py)
"""
import argparse
import json
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
import rasterio
import shapely
import geopandas as gpd
from joblib import Parallel, delayed
from rasterio.transform import from_origin
from scipy.spatial import cKDTree
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor

from src import classify, dem as dm, desurvey, geostrat as gs, paths, targeting as tg

SEED = 0
N_DRAWS = 20
THETAS = list(range(0, 180, 15))
RESTARTS = 3
RESTARTS_CV = 2
CUT = np.log10(0.5)
CUT_ALT = np.log10(0.3)
KAPPA = 2.0
KAPPAS = (0.0, 1.0, 2.0, 3.0)
CENS_SHARE = 0.5
NE, ENE = 45, 75
# block model
CELL_XY, CELL_Z = 10.0, 5.0
DOMAIN_H = 100.0      # m horizontal from a composite
Z_BELOW = 50.0        # m below the deepest composite
# design
COLLAR_STEP = 20.0
NEAR_DRILL = 150.0
SLOPE_MAX = 25.0
DIPS = (-60, -75)
HOLE_LEN = 200.0
STEP = 2.0
N_B = 2
# Tier A portfolio (human decision 2026-11-03, after pad CV showed no between-pad skill):
# two extension holes by expected metres ≥ 0.5 g/t, one gap-closing hole by kriging variance where
# μ + 2σ ≥ 0.5 g/t (optimistic metres saturate at 200 m far from data, so they cannot rank).
PORTFOLIO = ("harap", "harap", "ucb")
PORTFOLIO_NAME = {"harap": "perluasan (meter harapan ≥ 0,5 g/t)", "ucb": "penutup celah (varians kriging di batuan dengan UCB ≥ 0,5 g/t)"}
MIN_NEW = 20.0        # m: only trace points this far from every sample count as new rock
TIE_TOL = 0.01        # gap-closing round: designs within 1% of the best score are tied (prior saturation)
B_RADIUS, B_SEP = 50.0, 150.0
PAF_R = 25.0
BUFFER_M = 50.0       # Permen PUPR 28/PRT/M/2015 small river [VERIFY]

CACHE = paths.INTERIM / "ml6_gp.joblib"   # written by stage gp of this script on this machine only
C_INK, C_INK2, C_NULL, C_ACC = "#0b0b0b", "#52514e", "#b9b8b2", "#b2182b"


# --- data ---------------------------------------------------------------------------
def load_data():
    c = pd.read_csv(paths.INTERIM / "06_composites.csv", low_memory=False)
    c = c.sort_values(["SiteID", "DepthFrom"]).reset_index(drop=True)
    collar = pd.read_csv(paths.INTERIM / "03_collar.csv")
    summ = pd.read_csv(paths.INTERIM / "01_element_summary.csv")
    ok = c.comp_ok.to_numpy(bool) & c.AuPPM_ml.notna().to_numpy()
    seg_all = gs.segments(c.SiteID.to_numpy(), ok)
    rows = np.flatnonzero(ok)
    V = c.loc[rows, ["AuPPM_ml"]].to_numpy(float)
    cens = (c.loc[rows, "AuPPM_cens_frac"].fillna(0).to_numpy() >= CENS_SHARE)[:, None]
    h = float(summ.loc[summ.dataset.eq("assay") & summ.column.eq("AuPPM"), "harmonised_dl"].iloc[0])
    assert np.isclose(np.nanmin(V), h / 2), "Au floor is not DL/2"
    dl = np.full_like(V, h)
    L = np.mean([gs.log_features(V, cens, dl, np.random.default_rng(SEED + d))[:, 0]
                 for d in range(N_DRAWS)], axis=0)
    block = tg.regularise(seg_all[rows])
    y = tg.block_mean(block, L).ravel()
    xyz = tg.block_mean(block, c.loc[rows, ["X_mid", "Y_mid", "Z_mid"]].to_numpy(float))
    pad_of = c.SiteID.map(classify.pad_groups(collar)).to_numpy()[rows]
    pads = pd.Series(pad_of).groupby(block).first().to_numpy()
    site = pd.Series(c.SiteID.to_numpy()[rows]).groupby(block).first().to_numpy()
    assert len(y) == len(xyz) == len(pads) and np.isfinite(y).all()
    return c, collar, rows, block, y, xyz, pads, site, float(cens.mean())


# --- GP jobs ------------------------------------------------------------------------
def frame_X(xyz, az, origin):
    return tg.rotate3d(xyz, az, origin)


def make_kernel(kind: str, az):
    """kind: 'matern' (main), 'rbf' or 'nested' (sensitivities)."""
    return tg.kernel(az is not None, None if kind == "rbf" else 1.5, nested=kind == "nested")


def fit_theta(xyz, y, az, origin, kind="matern"):
    gp = tg.fit(frame_X(xyz, az, origin), y, make_kernel(kind, az), RESTARTS, SEED)
    return az, gp.log_marginal_likelihood_value_, gp.kernel_


def cv_job(name, az, kind, pad, xyz, y, pads, origin):
    tr, te = pads != pad, pads == pad
    if name == "rata-rata":
        mu = np.full(te.sum(), y[tr].mean())
        return name, pad, np.flatnonzero(te), mu, np.zeros(te.sum()), float(y[tr].var())
    gp = tg.fit(frame_X(xyz[tr], az, origin), y[tr], make_kernel(kind, az), RESTARTS_CV, SEED)
    mu, sd = tg.latent_predict(gp, frame_X(xyz[te], az, origin))
    return name, pad, np.flatnonzero(te), mu, sd, tg.nugget(gp)


def cv_table(res, y, pads):
    per = []
    for name, pad, idx, mu, sd, nug in res:
        s = tg.predictive_scores(y[idx], mu, sd, nug)
        per.append({"model": name, "pad": pad, **s})
    per = pd.DataFrame(per)
    agg = per.groupby("model").agg(mlpd=("mlpd", "mean"), mlpd_se=("mlpd", lambda v: v.std(ddof=1) / np.sqrt(len(v))),
                                   rmse=("rmse", "mean"), cov90=("cov90", "mean"), n_pad=("pad", "size"))
    pooled = {}
    for name in per.model.unique():
        r = [x for x in res if x[0] == name]
        idx = np.concatenate([x[2] for x in r])
        pooled[name] = tg.predictive_scores(y[idx], np.concatenate([x[3] for x in r]),
                                            np.concatenate([x[4] for x in r]),
                                            np.concatenate([np.full(len(x[2]), x[5]) for x in r]))
    agg["rmse_pooled"] = [pooled[m]["rmse"] for m in agg.index]
    agg["cov90_pooled"] = [pooled[m]["cov90"] for m in agg.index]
    return per, agg.reset_index()


def choose(agg: pd.DataFrame, names: dict) -> str:
    """Best mean held-out log density; within 1 SE of the best prefer NE (resume), then
    isotropic (simplest), then the best."""
    a = agg[agg.model.isin(names)].set_index("model")
    best = a.mlpd.idxmax()
    tie = a.index[a.mlpd >= a.mlpd[best] - a.mlpd_se[best]]
    for pref in (f"NE {NE}°", "isotropik"):
        if pref in tie:
            return pref
    return best


def cv_predictions(res, name, n):
    mu, sd, nug = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    for nm, _, idx, m, s, g in res:
        if nm == name:
            mu[idx], sd[idx], nug[idx] = m, s, g
    return mu, sd, nug


def experimental_variogram(X, y, axis, edges, tol=22.5):
    i, j = np.triu_indices(len(X), 1)
    d = X[j] - X[i]
    h = np.linalg.norm(d, axis=1)
    cosang = np.abs(d[:, axis]) / np.maximum(h, 1e-9)
    sel = cosang >= np.cos(np.deg2rad(tol))
    sq = 0.5 * (y[j] - y[i]) ** 2
    lag = np.digitize(h[sel], edges) - 1
    nl = len(edges) - 1
    keep = (lag >= 0) & (lag < nl)
    cnt = np.bincount(lag[keep], minlength=nl)
    s = np.bincount(lag[keep], weights=sq[sel][keep], minlength=nl)
    hm = np.bincount(lag[keep], weights=h[sel][keep], minlength=nl)
    ok = cnt >= 30
    return pd.DataFrame({"h": np.where(ok, hm / np.maximum(cnt, 1), np.nan),
                         "gamma": np.where(ok, s / np.maximum(cnt, 1), np.nan), "pairs": cnt})


# --- block model ----------------------------------------------------------------------
def read_raster(path):
    with rasterio.open(path) as r:
        a = r.read(1).astype(float)
        if r.nodata is not None:
            a[a == r.nodata] = np.nan
        return a, r.transform


def block_model(gp, az, origin, xyz, nug, dem, dem_tr):
    lo = np.floor((xyz[:, :2].min(0) - DOMAIN_H) / CELL_XY) * CELL_XY
    hi = np.ceil((xyz[:, :2].max(0) + DOMAIN_H) / CELL_XY) * CELL_XY
    gx = np.arange(lo[0] + CELL_XY / 2, hi[0], CELL_XY)
    gy = np.arange(hi[1] - CELL_XY / 2, lo[1], -CELL_XY)
    xx, yy = np.meshgrid(gx, gy)
    d, _ = cKDTree(xyz[:, :2]).query(np.column_stack([xx.ravel(), yy.ravel()]))
    zt = dm.sample_bilinear(dem, dem_tr, xx.ravel(), yy.ravel())
    col = (d <= DOMAIN_H) & np.isfinite(zt)
    z_floor = xyz[:, 2].min() - Z_BELOW
    zs = np.arange(np.floor(z_floor / CELL_Z) * CELL_Z + CELL_Z / 2, np.nanmax(zt[col]), CELL_Z)
    ci = np.flatnonzero(col)
    C, Z = np.meshgrid(ci, zs, indexing="ij")
    keep = Z <= zt[C] - CELL_Z / 2
    nodes = pd.DataFrame({"col": C[keep], "X": xx.ravel()[C[keep]], "Y": yy.ravel()[C[keep]], "Z": Z[keep]})
    mu, sd = tg.latent_predict(gp, frame_X(nodes[["X", "Y", "Z"]].to_numpy(), az, origin))
    s_pred = np.sqrt(sd ** 2 + nug)
    nodes = nodes.assign(mu=mu, sd=sd, p05=norm.sf((CUT - mu) / s_pred), p03=norm.sf((CUT_ALT - mu) / s_pred),
                         ucb=mu + KAPPA * sd)
    grid = {"gx": gx, "gy": gy, "shape": xx.shape, "transform": from_origin(lo[0], hi[1], CELL_XY, CELL_XY)}
    return nodes, grid


def column_rasters(nodes, grid):
    n = grid["shape"][0] * grid["shape"][1]
    g = nodes.groupby("col")
    out = {}
    for name, ser in (("ucb_maks", 10 ** g.ucb.max()), ("meter_cutoff", g.p05.sum() * CELL_Z),
                      ("sd_rerata", g.sd.mean())):
        a = np.full(n, np.nan)
        a[ser.index.to_numpy()] = ser.to_numpy()
        out[name] = a.reshape(grid["shape"])
        dm.write_geotiff(paths.GIS / f"ml6_{name}.tif", out[name], grid["transform"])
    return out


# --- figures --------------------------------------------------------------------------
def clean_axes(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def fig_theta(prof, lml_iso, path):
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    ax.plot(prof.theta, prof.lml, marker="o", ms=5, lw=1.5, color=C_INK)
    ax.axhline(lml_iso, color=C_INK2, lw=1.2, ls=(0, (4, 2)))
    ax.text(prof.theta.max(), lml_iso, " isotropik", va="center", ha="left", fontsize=7.5, color=C_INK2)
    for t, lab in ((NE, "NE (resume)"), (ENE, "ENE (ML-3 tanah)")):
        ax.axvline(t, color=C_NULL, lw=5, alpha=0.5, zorder=0)
        ax.text(t, ax.get_ylim()[1], lab, rotation=90, va="top", ha="right", fontsize=7.5, color=C_INK2)
    ax.set_xticks(THETAS)
    ax.set_xlabel("Arah jurus sumbu kontinuitas terpanjang θ (°)", fontsize=8.5)
    ax.set_ylabel("Log marginal likelihood", fontsize=8.5)
    ax.set_title("Profil likelihood arah anisotropi GP (log Au, komposit 2 m)", fontsize=9.5)
    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_cv(agg, winner, path):
    a = agg.sort_values("mlpd")
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.6), sharey=True, gridspec_kw={"width_ratios": [1.4, 1, 1]})
    yy = np.arange(len(a))
    base = a.loc[a.model == "rata-rata"]
    ax = axes[0]
    if len(base):
        ax.axvline(base.mlpd.iloc[0], color=C_INK2, lw=0.8, ls=":")
    ax.errorbar(a.mlpd, yy, xerr=a.mlpd_se, fmt="o", ms=6, color=C_INK, capsize=3, lw=1.2)
    ax.set_xlabel("Log densitas prediktif uji\n(lebih tinggi lebih baik; ± 1 SE)", fontsize=8.5)
    ax = axes[1]
    if len(base):
        ax.axvline(base.rmse.iloc[0], color=C_INK2, lw=0.8, ls=":")
    ax.plot(a.rmse, yy, "o", ms=6, color=C_INK)
    ax.set_xlabel("RMSE log10 Au\n(lebih rendah lebih baik)", fontsize=8.5)
    ax = axes[2]
    ax.axvline(0.9, color=C_INK2, lw=0.8, ls=":")
    ax.plot(a.cov90, yy, "o", ms=6, color=C_INK)
    ax.set_xlim(0.75, 1.0)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("Cakupan interval 90%\n(ideal 90%)", fontsize=8.5)
    axes[0].set_yticks(yy, [f"{m}{'  ◄ dipilih' if m == winner else ''}" for m in a.model], fontsize=8)
    for ax in axes:
        clean_axes(ax)
        ax.tick_params(axis="x", labelsize=8)
        ax.locator_params(axis="x", nbins=4)
    fig.suptitle("Validasi silang tinggalkan-satu-pad (12 pad); garis titik = model rata-rata saja", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_variogram(ev, gp, theta, path):
    names = [f"Searah jurus ({theta}°)" if theta is not None else "Horizontal (sumbu X)",
             "Tegak lurus jurus" if theta is not None else "Horizontal (sumbu Y)", "Vertikal"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=True)
    for ax, axis, nm in zip(axes, range(3), names):
        e = ev[axis]
        ax.scatter(e.h, e.gamma, s=np.clip(e.pairs / e.pairs.max() * 60, 8, 60), color=C_INK2, zorder=3,
                   label="Eksperimental (ukuran = jumlah pasangan)")
        h = np.linspace(0.5, e.h.max() * 1.05, 200)
        ax.plot(h, tg.implied_variogram(gp, h, axis), color=C_ACC, lw=2, label="Tersirat dari GP (kovarians kriging)")
        ax.axhline(tg.nugget(gp), color=C_NULL, lw=1, ls=(0, (2, 2)))
        ax.set_title(nm, fontsize=9.5)
        ax.set_xlabel("Jarak h (m)", fontsize=8.5)
        clean_axes(ax)
    axes[0].set_ylabel("Semivariogram γ(h) (log10 Au)²", fontsize=8.5)
    axes[0].legend(fontsize=7, frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


# --- stage gp ---------------------------------------------------------------------------
def stage_gp():
    c, collar, rows, block, y, xyz, pads, site, cens_share = load_data()
    origin = np.round(xyz.mean(0), 0)
    print(f"2 m blocks {len(y)} from {len(rows)} composites; pads {len(np.unique(pads))}; "
          f"Au censored share {cens_share:.3f}; log10 Au mean {y.mean():.3f} SD {y.std():.3f}")

    prof = Parallel(n_jobs=-1)(delayed(fit_theta)(xyz, y, t, origin) for t in THETAS + [None])
    lml_iso = [p[1] for p in prof if p[0] is None][0]
    prof = pd.DataFrame([{"theta": p[0], "lml": p[1], "kernel": str(p[2])} for p in prof if p[0] is not None])
    best_theta = int(prof.theta[prof.lml.idxmax()])
    print(prof[["theta", "lml"]].round(1).to_string(index=False), f"\nisotropic LML {lml_iso:.1f}; best θ {best_theta}")

    configs = {f"NE {NE}°": NE, f"ENE {ENE}°": ENE, "isotropik": None}
    if best_theta not in (NE, ENE):
        configs[f"terbaik {best_theta}°"] = best_theta
    jobs = [(nm, az, "matern", p) for nm, az in configs.items() for p in np.unique(pads)]
    jobs += [("rata-rata", None, None, p) for p in np.unique(pads)]
    res = Parallel(n_jobs=-1)(delayed(cv_job)(nm, az, nu, p, xyz, y, pads, origin) for nm, az, nu, p in jobs)
    per, agg = cv_table(res, y, pads)
    winner = choose(agg, configs)
    theta = configs[winner]
    # kernel sensitivities at the winning orientation: RBF (ML-3) and a nested short + long Matérn
    sens = {f"RBF {winner}": "rbf", f"bersarang {winner}": "nested"}
    res_s = Parallel(n_jobs=-1)(delayed(cv_job)(nm, theta, kind, p, xyz, y, pads, origin)
                                for nm, kind in sens.items() for p in np.unique(pads))
    per_s, agg_s = cv_table(res_s, y, pads)
    per, agg = pd.concat([per, per_s]), pd.concat([agg, agg_s], ignore_index=True)
    # the nested kernel replaces the single one only if it is better by more than 1 SE
    a = agg.set_index("model")
    nest = f"bersarang {winner}"
    kind = "nested" if a.mlpd[nest] > a.mlpd[winner] + a.mlpd_se[winner] else "matern"
    model_name = nest if kind == "nested" else winner
    res = res + res_s
    w = per.pivot(index="pad", columns="model", values="mlpd")
    dif = w[model_name] - w["rata-rata"]
    skill = {"delta_mlpd_vs_mean": float(dif.mean()), "se": float(dif.std(ddof=1) / np.sqrt(len(dif))),
             "pads_better": int((dif > 0).sum()), "n_pads": int(len(dif))}
    print(agg.round(3).to_string(index=False), f"\norientation: {winner}; kernel: {kind}; GP vs mean per pad {skill}")

    gp = tg.fit(frame_X(xyz, theta, origin), y, make_kernel(kind, theta), RESTARTS, SEED)
    nug = tg.nugget(gp)
    print(f"final kernel {gp.kernel_}; LML {gp.log_marginal_likelihood_value_:.1f}; nugget {nug:.4f}, "
          f"sill {tg.sill(gp):.4f} (log10²); length scales {tg.length_scales(gp)}")

    # kriging equivalence: simple-kriging system vs GP mean on 300 held points
    rng = np.random.default_rng(SEED)
    Q = frame_X(xyz[rng.choice(len(y), 300, replace=False)] + rng.normal(0, 5, (300, 3)), theta, origin)
    sk_diff = float(np.abs(tg.sk_mean(gp, Q) - tg.latent_predict(gp, Q)[0]).max())
    assert sk_diff < 1e-6, sk_diff
    print(f"simple kriging vs GP mean: max |Δ| {sk_diff:.2e}")

    # experimental vs implied variograms in the model frame
    X = frame_X(xyz, theta, origin)
    edges = [np.arange(0, 205, 10), np.arange(0, 205, 10), np.arange(0, 102, 4)]
    ev = [experimental_variogram(X, y, a, edges[a]) for a in range(3)]

    # composite-level outputs
    mu_in, sd_in = tg.latent_predict(gp, X)
    cv_mu, cv_sd, cv_nug = cv_predictions(res, model_name, len(y))
    s_cv = np.sqrt(cv_sd ** 2 + cv_nug)
    b = block[block >= 0]
    out = pd.DataFrame({"HoleID": c.SiteID.to_numpy()[rows], "From": c.DepthFrom.to_numpy()[rows],
                        "ML_gp_mu": mu_in[b], "ML_gp_sd": sd_in[b], "ML_gp_cv_mu": cv_mu[b],
                        "ML_gp_cv_sd": s_cv[b], "ML_gp_cv_resid": (y - cv_mu)[b],
                        "ML_gp_cv_p05": norm.sf((CUT - cv_mu) / s_cv)[b]}).round(4)
    out["ML_gp_blok2m"] = b
    assert len(out) == len(rows) and out.ML_gp_cv_mu.notna().all()
    (paths.PROCESSED / "ml").mkdir(parents=True, exist_ok=True)
    out.to_csv(paths.PROCESSED / "ml" / "komposit__ml6_gp.csv", index=False)

    dem, dem_tr = read_raster(paths.GIS / "lidar_dem.tif")
    nodes, grid = block_model(gp, theta, origin, xyz, nug, dem, dem_tr)
    rast = column_rasters(nodes, grid)
    nodes.drop(columns="col").round(4).to_csv(paths.INTERIM / "ml6_blok.csv", index=False)
    print(f"block model: {len(nodes)} nodes in {nodes.col.nunique()} columns; "
          f"P(≥0.5 g/t) ≥ 0.5 in {(nodes.p05 >= 0.5).sum()} nodes; σ median {nodes.sd.median():.3f}")

    paths.FIGURES.mkdir(parents=True, exist_ok=True)
    fig_theta(prof, lml_iso, paths.FIGURES / "13_profil_theta_v1.png")
    fig_cv(agg, model_name, paths.FIGURES / "13_cv_lopo_v1.png")
    fig_variogram(ev, gp, theta, paths.FIGURES / "13_variogram_gp_v1.png")
    prof.assign(lml_isotropik=lml_iso).to_csv(paths.PROCESSED / "ml6_profil_theta.csv", index=False)
    per.assign(level="pad").to_csv(paths.PROCESSED / "ml6_cv_per_pad.csv", index=False)
    agg.round(4).to_csv(paths.PROCESSED / "ml6_cv.csv", index=False)
    summary = {"n_composites": int(len(rows)), "n_blocks_2m": int(len(y)), "censored_share": cens_share,
               "best_theta_lml": best_theta, "lml_isotropic": float(lml_iso), "winner": winner,
               "kernel_kind": kind, "model_name": model_name, "skill_vs_mean": skill,
               "theta": theta, "kernel": str(gp.kernel_), "lml": float(gp.log_marginal_likelihood_value_),
               "nugget_log10sq": nug, "sill_log10sq": tg.sill(gp),
               "length_scales_m": tg.length_scales(gp), "sk_max_abs_diff": sk_diff,
               "origin": origin.tolist(), "block_nodes": int(len(nodes)),
               "ev": {str(a): ev[a].round(4).to_dict("list") for a in range(3)}}
    joblib.dump({"gp": gp, "theta": theta, "kind": kind, "origin": origin, "xyz": xyz, "y": y, "summary": summary,
                 "grid": grid}, CACHE)
    return summary


# --- stage design -------------------------------------------------------------------------
def collar_grid(lo, hi):
    gx = np.arange(np.ceil(lo[0] / COLLAR_STEP) * COLLAR_STEP, hi[0] + 1e-6, COLLAR_STEP)
    gy = np.arange(np.ceil(lo[1] / COLLAR_STEP) * COLLAR_STEP, hi[1] + 1e-6, COLLAR_STEP)
    xx, yy = np.meshgrid(gx, gy)
    return np.column_stack([xx.ravel(), yy.ravel()])


def pad_slope(slope, tr, xy):
    """Median slope over a 3 × 3 set of points ±8 m around each collar (a ~16 m pad)."""
    off = [(dx, dy) for dx in (-8, 0, 8) for dy in (-8, 0, 8)]
    v = np.column_stack([dm.sample_bilinear(slope, tr, xy[:, 0] + dx, xy[:, 1] + dy) for dx, dy in off])
    return np.nanmedian(v, axis=1)


def load_drainage():
    f = paths.GIS / "drainage.gpkg"
    if not f.exists():
        raise SystemExit("gis/drainage.gpkg missing: run scripts/15_drainage_qgis.py in QGIS first (Step D)")
    reach = pyogrio.read_dataframe(f, layer="sungai_turunan")
    basins = pyogrio.read_dataframe(f, layer="das")
    assert "ragu" in reach, "sungai_turunan needs a 'ragu' column"
    reach["ragu"] = reach.ragu.astype(bool)
    return reach, basins


def drainage_columns(xy, reach, basins):
    pts = gpd.GeoSeries(gpd.points_from_xy(xy[:, 0], xy[:, 1]), crs=paths.CRS)
    sure, doubt = reach[~reach.ragu].geometry.union_all(), reach[reach.ragu].geometry.union_all()
    d_sure = pts.distance(sure).to_numpy() if not sure.is_empty else np.full(len(xy), np.inf)
    d_doubt = pts.distance(doubt).to_numpy() if not doubt.is_empty else np.full(len(xy), np.inf)
    j = gpd.sjoin(gpd.GeoDataFrame(geometry=pts), basins[["geometry"]].reset_index(names="das_id"),
                  how="left", predicate="within")
    das = j[~j.index.duplicated()].das_id.to_numpy()
    return d_sure, d_doubt, das


def screen(xy, dem, dem_tr, slope, sl_tr, reach, basins):
    """Pad checks per collar: inside the DEM, pad slope, 50 m buffer of sure and doubtful reaches."""
    z = dm.sample_bilinear(dem, dem_tr, xy[:, 0], xy[:, 1])
    sl = pad_slope(slope, sl_tr, xy)
    d_sure, d_doubt, das = drainage_columns(xy, reach, basins)
    why = np.select([~np.isfinite(z), sl > SLOPE_MAX, d_sure <= BUFFER_M, d_doubt <= BUFFER_M],
                    ["di luar DEM", f"lereng > {SLOPE_MAX:.0f}°", "sempadan 50 m",
                     "sempadan 50 m (alur ragu, cek lapangan)"], "")
    return pd.DataFrame({"X": xy[:, 0], "Y": xy[:, 1], "Z": z, "lereng_pad": sl,
                         "jarak_alur": np.minimum(d_sure, d_doubt), "jarak_alur_pasti": d_sure,
                         "das_id": das, "lolos": why == "", "alasan": why})


def designs(theta):
    azs = [315, 135]
    if theta is not None:
        azs += [a for a in ((theta + 90) % 360, (theta + 270) % 360) if a not in azs]
    return [(a, d) for a in azs for d in DIPS] + [(0, -90)]


def across_az(theta):
    """Across-strike azimuth closest to 315 (the direction of most existing holes)."""
    if theta is None:
        return 315
    c = [(theta + 90) % 360, (theta + 270) % 360]
    return min(c, key=lambda a: abs((a - 315 + 180) % 360 - 180))


def paf_lookup():
    g = pyogrio.read_dataframe(paths.GIS / "ml5_paf.gpkg", layer="interval_paf")
    a = pd.read_csv(paths.PROCESSED / "ml" / "assay__ml5_paf.csv", usecols=["SampleID", "ML_paf_prioritas_uji"])
    g = g.merge(a, on="SampleID", how="left", validate="one_to_one")
    xyz = np.column_stack([g.geometry.x, g.geometry.y, shapely.get_z(g.geometry.values)])
    hc = g.ML_paf_kelola.eq("PAF-HC").to_numpy()
    hc_sure = (g.ML_paf_label.eq("PAF-HC") | g.ML_paf_set.eq("PAF-HC")).to_numpy()
    p1 = g.ML_paf_prioritas_uji.astype(str).str.startswith("1").to_numpy()
    return cKDTree(xyz), hc, hc_sure, p1


def paf_metres(pts, tree, hc, hc_sure, p1):
    d, i = tree.query(pts)
    near = d <= PAF_R
    return {"m_paf_hc": float((near & hc[i]).sum() * STEP), "m_paf_hc_pasti": float((near & hc_sure[i]).sum() * STEP),
            "m_prioritas_nag1": float((near & p1[i]).sum() * STEP), "m_dekat_ml5": float(near.sum() * STEP)}


def fig_rank(holes, prop, path):
    """Left: top 10 Tier A designs by expected metres (round 1). Right: at the gap-closing round, the
    designs tied on plausible variance (within TIE_TOL), ranked by the tie-break (nearest to data)."""
    pick = dict(zip(prop.kandidat, prop.usulan))
    rnd = PORTFOLIO.index("ucb") + 1
    sc = holes[f"skor_putaran{rnd}"]
    tied = holes[sc >= (1 - TIE_TOL) * sc.max()]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, data, col, asc, colour, xl, title in (
            (axes[0], holes, "meter_harap_05", False, C_INK2, "Meter harapan Au ≥ 0,5 g/t (batuan baru)",
             "Perluasan: meter harapan (putaran 1)"),
            (axes[1], tied, f"jarak_baru_putaran{rnd}", True, C_NULL, "Jarak rerata batuan baru ke sampel terdekat (m)",
             f"Penutup celah (putaran {rnd}): {len(tied)} desain seri pada varians kriging\n"
             f"(≤ {TIE_TOL:.0%} dari maks.), dipilih yang terdekat ke data")):
        t = data.sort_values(col, ascending=asc).head(10).iloc[::-1]
        yy = np.arange(len(t))
        ax.barh(yy, t[col], height=0.6, color=colour)
        ax.set_yticks(yy, [f"{r.hole_id}  az {r.az:.0f}° / {r.dip:.0f}°" + (f"  ◄ {pick[r.hole_id]}" if r.hole_id in pick else "")
                           for r in t.itertuples()], fontsize=7.5)
        ax.set_xlabel(xl, fontsize=8.5)
        ax.set_title(title, fontsize=9.5)
        clean_axes(ax)
    fig.suptitle("Peringkat kandidat Tingkat A (lubang 200 m; batuan baru = ≥ 20 m dari sampel)",
                 fontsize=9.5)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def tier_a(gp, theta, origin, xyz, dem, dem_tr, slope, sl_tr, reach, basins):
    nug = tg.nugget(gp)
    z_floor = xyz[:, 2].min() - Z_BELOW
    xy = collar_grid(xyz[:, :2].min(0) - NEAR_DRILL, xyz[:, :2].max(0) + NEAR_DRILL)
    d, _ = cKDTree(xyz[:, :2]).query(xy)
    col = screen(xy[d <= NEAR_DRILL], dem, dem_tr, slope, sl_tr, reach, basins).assign(tingkat="A")
    print("Tier A collars:", len(col), "pass:", int(col.lolos.sum()), col.alasan.value_counts().to_dict())
    ok = col[col.lolos].reset_index(drop=True)
    holes, pts, hid = [], [], []
    for ci, r in ok.iterrows():
        for az, dip in designs(theta):
            P = tg.trace([r.X, r.Y, r.Z], dip, az, HOLE_LEN, STEP)
            holes.append({"collar": ci, "X": r.X, "Y": r.Y, "Z": r.Z, "az": az, "dip": dip,
                          "lereng_pad": r.lereng_pad, "jarak_alur": r.jarak_alur, "das_id": r.das_id})
            pts.append(P)
            hid.append(np.full(len(P), len(holes) - 1))
    holes = pd.DataFrame(holes)
    P, hid = np.vstack(pts), np.concatenate(hid)
    valid = tg.in_domain(P, xyz, DOMAIN_H, z_floor) & (P[:, 2] <= dm.sample_bilinear(dem, dem_tr, P[:, 0], P[:, 1]))
    Qv, hv = frame_X(P[valid], theta, origin), hid[valid]
    X_obs = frame_X(xyz, theta, origin)
    mu, sd = tg.latent_predict(gp, Qv)
    new = cKDTree(X_obs).query(Qv)[0] >= MIN_NEW
    nh = len(holes)
    holes["m_domain"] = np.bincount(hv, minlength=nh) * STEP
    holes["m_baru"] = np.bincount(hv, weights=new.astype(float), minlength=nh) * STEP
    for k in KAPPAS:
        holes[f"skor_k{k:.0f}"] = tg.optimistic_metres(mu + k * sd, hv, new, CUT, STEP, nh)
    holes["meter_k0"] = holes.skor_k0
    holes["meter_harap_05"] = tg.expected_metres(mu, sd, nug, hv, new, CUT, STEP, nh)
    holes["meter_harap_03"] = tg.expected_metres(mu, sd, nug, hv, new, CUT_ALT, STEP, nh)
    holes["varians_berpotensi"] = tg.plausible_variance(mu, sd, hv, new, CUT, KAPPA, STEP, nh)
    holes["sd_rerata"] = np.bincount(hv, weights=np.where(new, sd, 0), minlength=nh) / np.maximum(
        np.bincount(hv, weights=new.astype(float), minlength=nh), 1)
    print(f"Tier A: {nh} designs, {len(Qv)} in-domain trace points ({new.mean():.0%} new rock ≥ {MIN_NEW:.0f} m)")
    picks, rounds, ties = tg.greedy_portfolio(gp, X_obs, Qv, hv, mu, CUT, KAPPA, STEP, PORTFOLIO, MIN_NEW, nh,
                                              tie_tol=TIE_TOL)
    for r_i, (sc, (n_tied, dist)) in enumerate(zip(rounds, ties)):
        holes[f"skor_putaran{r_i + 1}"] = sc
        holes[f"jarak_baru_putaran{r_i + 1}"] = dist
        print(f"round {r_i + 1} ({PORTFOLIO[r_i]}): {n_tied} tied within {TIE_TOL:.0%}; "
              f"pick new-rock mean distance {dist[picks[r_i]]:.1f} m")
    holes["hole_id"] = [f"A{i:05d}" for i in range(nh)]
    return col, holes, picks, rounds, [t[0] for t in ties]


def tier_b(xyz, theta, dem, dem_tr, slope, sl_tr, reach, basins):
    idx, idx_tr = read_raster(paths.GIS / "ml3_tanah_indeks.tif")
    isd, _ = read_raster(paths.GIS / "ml3_tanah_indeks_sd.tif")
    zone, _ = read_raster(paths.GIS / "ml3_tanah_zona.tif")
    rr, cc = np.where(np.isfinite(idx))
    cxy = np.column_stack([idx_tr.c + idx_tr.a * (cc + 0.5), idx_tr.f + idx_tr.e * (rr + 0.5)])
    ucb, ival = (idx + KAPPA * isd)[rr, cc], idx[rr, cc]
    ctree = cKDTree(cxy)
    xy = collar_grid(cxy.min(0), cxy.max(0))
    dd, _ = cKDTree(xyz[:, :2]).query(xy)
    xy = xy[(dd > NEAR_DRILL) & (ctree.query(xy)[0] <= idx_tr.a * np.sqrt(0.5))]
    colb = screen(xy, dem, dem_tr, slope, sl_tr, reach, basins).assign(tingkat="B")
    nb = ctree.query_ball_point(colb[["X", "Y"]].to_numpy(), B_RADIUS)
    colb["skor_tanah"] = [float(np.mean(ucb[n])) if len(n) else np.nan for n in nb]
    colb["indeks_tanah"] = [float(np.mean(ival[n])) if len(n) else np.nan for n in nb]
    zid = dm.sample_bilinear(np.nan_to_num(zone, nan=0), idx_tr, colb.X, colb.Y).round()
    colb["zona_tanah"] = [{1: "Rendah", 2: "Sedang", 3: "Tinggi"}.get(int(v), "") if np.isfinite(v) else "" for v in zid]
    print("Tier B collars:", len(colb), "pass:", int(colb.lolos.sum()), colb.alasan.value_counts().to_dict())
    cand = colb[colb.lolos].sort_values("skor_tanah", ascending=False)
    picks = []
    for i, r in cand.iterrows():
        if all(np.hypot(r.X - colb.X[j], r.Y - colb.Y[j]) >= B_SEP for j in picks):
            picks.append(i)
        if len(picks) == N_B:
            break
    return colb, picks, across_az(theta)


def stage_design():
    cache = joblib.load(CACHE)
    gp, theta, origin, xyz = cache["gp"], cache["theta"], cache["origin"], cache["xyz"]
    dem, dem_tr = read_raster(paths.GIS / "lidar_dem.tif")
    slope, sl_tr = read_raster(paths.GIS / "slope_deg.tif")
    reach, basins = load_drainage()
    tree, hc, hc_sure, p1 = paf_lookup()
    print(f"drainage: {len(reach)} reaches ({int(reach.ragu.sum())} ragu), {len(basins)} basins; θ {theta}")

    col, holes, picks, rounds, n_tied = tier_a(gp, theta, origin, xyz, dem, dem_tr, slope, sl_tr, reach, basins)
    top_by_k = {f"{k:.0f}": holes.hole_id[holes[f"skor_k{k:.0f}"].idxmax()] for k in KAPPAS}
    print("picks:", [(holes.hole_id[p], round(rounds[i][p], 1)) for i, p in enumerate(picks)], "top by κ:", top_by_k)
    colb, pick_b, az_b = tier_b(xyz, theta, dem, dem_tr, slope, sl_tr, reach, basins)

    rows = []
    for n, p in enumerate(picks, 1):
        h = holes.loc[p]
        rows.append({"usulan": f"RJ-U{n:02d}", "tingkat": "A", "basis": PORTFOLIO_NAME[PORTFOLIO[n - 1]],
                     "X": h.X, "Y": h.Y, "Z": h.Z, "az": h.az, "dip": h.dip, "kandidat": h.hole_id,
                     "skor_saat_dipilih": rounds[n - 1][p], "meter_harap_05": h.meter_harap_05,
                     "meter_harap_03": h.meter_harap_03, "varians_berpotensi": h.varians_berpotensi, "skor_k2": h.skor_k2, "meter_k0": h.meter_k0,
                     "m_domain": h.m_domain, "m_baru": h.m_baru,
                     "jarak_baru_saat_dipilih": h[f"jarak_baru_putaran{n}"], "seri_saat_dipilih": n_tied[n - 1]})
    for n, i in enumerate(pick_b, len(picks) + 1):
        r = colb.loc[i]
        rows.append({"usulan": f"RJ-U{n:02d}", "tingkat": "B", "basis": "UCB indeks tanah ML-3 (uji anomali tanah)",
                     "X": r.X, "Y": r.Y, "Z": r.Z, "az": az_b, "dip": DIPS[0], "kandidat": f"B{i:05d}",
                     "skor_tanah": r.skor_tanah, "indeks_tanah": r.indeks_tanah, "zona_tanah": r.zona_tanah})
    prop = pd.DataFrame(rows)
    env = screen(prop[["X", "Y"]].to_numpy(), dem, dem_tr, slope, sl_tr, reach, basins)
    prop = pd.concat([prop, env[["lereng_pad", "jarak_alur", "jarak_alur_pasti", "das_id"]]], axis=1)
    traces = [tg.trace([r.X, r.Y, r.Z], r.dip, r.az, HOLE_LEN, STEP) for r in prop.itertuples()]
    prop = pd.concat([prop, pd.DataFrame([paf_metres(t, tree, hc, hc_sure, p1) for t in traces])], axis=1)
    prop.loc[prop.tingkat.eq("B"), ["m_paf_hc", "m_paf_hc_pasti", "m_prioritas_nag1"]] = np.nan
    prop["catatan_lingkungan"] = np.where(
        prop.tingkat.eq("A"),
        "Sump berlapis; cutting PAF-HC dikantongi; uji NAG pada inti baru (masuk daftar ML-5)",
        "Anggap PAF sampai diuji; sump berlapis; uji NAG pada inti baru")
    prop["EastUTM"], prop["NorthUTM"], prop["RLUTM"] = prop.X.round(1), prop.Y.round(1), prop.Z.round(1)
    prop["EndDepth"], prop["Dip"], prop["AzimUTM"] = HOLE_LEN, prop.dip, prop.az
    assert prop.lereng_pad.le(SLOPE_MAX).all() and prop.jarak_alur.gt(BUFFER_M).all()
    print(prop.drop(columns=["basis", "catatan_lingkungan"]).round(2).T.to_string())

    holes.round(3).to_csv(paths.PROCESSED / "ml6_kandidat.csv", index=False)
    allc = pd.concat([col, colb], ignore_index=True)
    prop.round(3).to_csv(paths.PROCESSED / "ml6_usulan_lubang.csv", index=False)
    gpkg = paths.GIS / "ml6_target.gpkg"
    kol = gpd.GeoDataFrame(prop.drop(columns=["catatan_lingkungan", "X", "Y", "Z", "az", "dip"]),   # GPKG names are case-insensitive
                           geometry=gpd.points_from_xy(prop.X, prop.Y, prop.Z), crs=paths.CRS)
    ends = [np.asarray([r.X, r.Y, r.Z]) + HOLE_LEN * desurvey_unit(r.dip, r.az) for r in prop.itertuples()]
    jej = gpd.GeoDataFrame(prop[["usulan", "tingkat", "az", "dip"]],
                           geometry=[shapely.LineString([(r.X, r.Y, r.Z), tuple(e)]) for r, e in zip(prop.itertuples(), ends)],
                           crs=paths.CRS)
    best = holes.loc[holes.groupby("collar").meter_harap_05.idxmax()]
    kand = gpd.GeoDataFrame(best[["hole_id", "az", "dip", "meter_harap_05", "skor_k2", "meter_k0", "m_baru",
                                  "sd_rerata"]], geometry=gpd.points_from_xy(best.X, best.Y), crs=paths.CRS)
    sar = gpd.GeoDataFrame(allc[["tingkat", "lolos", "alasan", "lereng_pad", "jarak_alur"]],
                           geometry=gpd.points_from_xy(allc.X, allc.Y), crs=paths.CRS)
    for name, g in (("kolar_usulan", kol), ("jejak_usulan", jej), ("kandidat", kand), ("kolar_saring", sar)):
        g.to_file(gpkg, layer=name, driver="GPKG", engine="pyogrio", mode="w")   # "w" replaces this layer only
        assert len(pyogrio.read_dataframe(gpkg, layer=name)) == len(g), name
    fig_rank(holes, prop, paths.FIGURES / "13_peringkat_kandidat_v1.png")
    s = cache["summary"] | {"n_collar_A": int(len(col)), "n_collar_A_pass": int(col.lolos.sum()),
                            "n_designs_A": int(len(holes)), "n_collar_B": int(len(colb)),
                            "n_collar_B_pass": int(colb.lolos.sum()), "top_by_kappa": top_by_k,
                            "picks_A": [holes.hole_id[p] for p in picks], "n_seri_putaran": n_tied,
                            "drainage_reaches": int(len(reach)), "drainage_ragu": int(reach.ragu.sum())}
    pd.Series({k: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v for k, v in s.items() if k != "ev"}
              ).rename_axis("item").rename("nilai").to_csv(paths.PROCESSED / "ml6_summary.csv")


def desurvey_unit(dip, az):
    return desurvey.unit_vectors(np.array([float(dip)]), np.array([float(az)]))[0]


# --- design section ------------------------------------------------------------------------
SEC_CORRIDOR = 40.0
SEC_TRACE = 50.0      # m: proposed traces are projected from this far (labelled with the offset)
SEC_BACK, SEC_AHEAD = 250.0, 260.0   # m behind / ahead of the RJ-U01 collar along its drilling direction
SEC_CELL = 5.0
SEC_STRIP = (-3.0, 3.0)
LOCAL_CRS = ('ENGCRS["Penampang lokal RJ",EDATUM["Bidang penampang"],CS[Cartesian,2],'
             'AXIS["jarak (x)",east,ORDER[1],LENGTHUNIT["metre",1]],'
             'AXIS["elevasi (y)",north,ORDER[2],LENGTHUNIT["metre",1]]]')


def strip_quads(p0, p1, w0, w1):
    """Quads between w0 and w1 m from each segment p0→p1 in the section frame (as scripts/12)."""
    d = p1 - p0
    n = np.column_stack([-d[:, 1], d[:, 0]]) / np.linalg.norm(d, axis=1, keepdims=True)
    return [shapely.Polygon([a + w0 * v, b + w0 * v, b + w1 * v, a + w1 * v]) for a, b, v in zip(p0, p1, n)]


def stage_section():
    """Vertical section in the plane of RJ-U01: GP P(Au ≥ 0.5 g/t) on 5 m cells in the model domain,
    HMM states of existing composites within ±40 m, proposed traces within ±50 m, topography. x grows towards
    the eastern half (az 0–180°, e.g. 135° for a 315° hole), so the view looks NE as in the ML-4
    sections. Writes gis/ml6_penampang.gpkg (local frame: x = m from the D end, y = RL)."""
    cache = joblib.load(CACHE)
    gp, theta, origin, xyz = cache["gp"], cache["theta"], cache["origin"], cache["xyz"]
    nug = tg.nugget(gp)
    prop = pd.read_csv(paths.PROCESSED / "ml6_usulan_lubang.csv")
    u1 = prop.iloc[0]
    hole_az = float(u1.az) if u1.dip > -89 else float(across_az(theta))
    az = hole_az % 180
    a = np.deg2rad(az)
    dirv = np.array([np.sin(a), np.cos(a)])
    before = SEC_AHEAD if az != hole_az else SEC_BACK   # the hole runs towards −x when flipped
    start = np.array([u1.X, u1.Y]) - before * dirv
    length = SEC_BACK + SEC_AHEAD

    def to_sec(x, y):
        d = np.column_stack([np.asarray(x) - start[0], np.asarray(y) - start[1]])
        return d @ dirv, d @ np.array([dirv[1], -dirv[0]])

    dem, dem_tr = read_raster(paths.GIS / "lidar_dem.tif")
    s = np.arange(0, length + STEP, STEP)
    zt = dm.sample_bilinear(dem, dem_tr, start[0] + s * dirv[0], start[1] + s * dirv[1])
    topo = gpd.GeoDataFrame({"n_titik": [int(np.isfinite(zt).sum())]},
                            geometry=[shapely.LineString(np.c_[s, zt][np.isfinite(zt)])])
    # GP cells on the plane
    xs = np.arange(SEC_CELL / 2, length, SEC_CELL)
    z_floor = xyz[:, 2].min() - Z_BELOW
    zs = np.arange(np.floor(z_floor / SEC_CELL) * SEC_CELL + SEC_CELL / 2, np.nanmax(zt), SEC_CELL)
    XX, ZZ = np.meshgrid(xs, zs)
    px, py = start[0] + XX.ravel() * dirv[0], start[1] + XX.ravel() * dirv[1]
    pts = np.column_stack([px, py, ZZ.ravel()])
    ztop = np.interp(XX.ravel(), s[np.isfinite(zt)], zt[np.isfinite(zt)])
    keep = tg.in_domain(pts, xyz, DOMAIN_H, z_floor) & (ZZ.ravel() <= ztop - SEC_CELL / 2)
    mu, sd = tg.latent_predict(gp, frame_X(pts[keep], theta, origin))
    sp = np.sqrt(sd ** 2 + nug)
    h = SEC_CELL / 2
    cells = gpd.GeoDataFrame({"p05": norm.sf((CUT - mu) / sp).round(3), "au_mu_gt": (10 ** mu).round(3),
                              "sd_log": sd.round(3), "ucb_gt": (10 ** (mu + KAPPA * sd)).round(3)},
                             geometry=[shapely.box(x - h, z - h, x + h, z + h)
                                       for x, z in zip(XX.ravel()[keep], ZZ.ravel()[keep])])
    # existing composites with HMM states
    c = pd.read_csv(paths.INTERIM / "06_composites.csv", low_memory=False)
    ml = pd.read_csv(paths.PROCESSED / "ml" / "komposit__ml4_hmm.csv", low_memory=False)
    c = c.merge(ml, left_on=["SiteID", "DepthFrom"], right_on=["HoleID", "From"], how="left", validate="one_to_one")
    xm, om = to_sec(c.X_mid, c.Y_mid)
    g = c[(np.abs(om) <= SEC_CORRIDOR) & (xm >= 0) & (xm <= length) & c.ML_hmm_status.notna()].copy()
    xf, _ = to_sec(g.X_from, g.Y_from)
    xt, _ = to_sec(g.X_to, g.Y_to)
    quads = strip_quads(np.c_[xf, g.Z_from], np.c_[xt, g.Z_to], *SEC_STRIP)
    hmm = gpd.GeoDataFrame({"SiteID": g.SiteID.str.replace("RJDH", "DH").to_numpy(),
                            "status": g.ML_hmm_status.astype(int).to_numpy(), "nama": g.ML_hmm_nama.to_numpy(),
                            "ambigu": g.ML_hmm_ambigu.to_numpy()}, geometry=quads)
    # proposed traces and labels
    tr_rows, lab_rows = [], []
    for r in prop.itertuples():
        P = np.vstack([[r.X, r.Y, r.Z], np.asarray([r.X, r.Y, r.Z]) + HOLE_LEN * desurvey_unit(r.dip, r.az)])
        x, o = to_sec(P[:, 0], P[:, 1])
        off = float(np.abs(o).max())
        if off <= SEC_TRACE and 0 <= x[0] <= length:
            tr_rows.append({"usulan": r.usulan, "tingkat": r.tingkat, "offset_maks_m": off,
                            "geometry": shapely.LineString(np.c_[x, P[:, 2]])})
            label = r.usulan if off <= SEC_CORRIDOR else f"{r.usulan} (proyeksi {off:.0f} m)"
            lab_rows.append({"label": label, "geometry": shapely.Point(x[0], P[0, 2])})
    usul = gpd.GeoDataFrame(tr_rows, geometry="geometry")
    lab = gpd.GeoDataFrame(lab_rows, geometry="geometry")
    gpkg = paths.GIS / "ml6_penampang.gpkg"
    line = shapely.LineString([start, start + length * dirv])
    plan = {"garis_penampang": gpd.GeoDataFrame({"azimut": [az], "panjang_m": [length], "label_awal": ["D"],
                                                 "label_akhir": ["D'"]}, geometry=[line], crs=paths.CRS),
            "koridor": gpd.GeoDataFrame({"lebar_m": [2 * SEC_CORRIDOR]},
                                        geometry=[line.buffer(SEC_CORRIDOR, cap_style="flat")], crs=paths.CRS)}
    local = {"sel_gp": cells, "status_hmm": hmm, "jejak_usulan": usul, "kolar_usulan": lab, "topografi": topo}
    for name, gdf in list(local.items()) + list(plan.items()):
        gdf = gdf if name in plan else gdf.set_crs(LOCAL_CRS, allow_override=True)
        gdf.to_file(gpkg, layer=name, driver="GPKG", engine="pyogrio", mode="w")   # "w" replaces this layer only
        assert pyogrio.read_info(gpkg, layer=name)["features"] == len(gdf) > 0, name
    print(f"section D–D' az {az:.0f}°, {length:.0f} m: {len(cells)} GP cells, {len(hmm)} composites "
          f"({hmm.SiteID.nunique()} holes: {sorted(hmm.SiteID.unique())}), proposed traces {list(usul.usulan)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["gp", "design", "section", "all"], default="all")
    stage = ap.parse_args().stage
    if stage in ("gp", "all"):
        s = stage_gp()
        print(json.dumps({k: v for k, v in s.items() if k != "ev"}, indent=1, default=str))
    if stage in ("design", "all"):
        stage_design()
    if stage in ("design", "section", "all"):
        stage_section()


if __name__ == "__main__":
    main()
