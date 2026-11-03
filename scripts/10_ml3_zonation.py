"""ML-3: surface H/M/L grade zonation (AGENTS.md §6 task 3). Plan: LOG.md, 2026-11-03 ML-3 entry.

Soil first, rock second, each on its own (RJ only). Dequantised log10 → median/MAD scale →
PCA (Horn) → PC1 mineralisation index → GMM K=3 zones (Rendah/Sedang/Tinggi), with BIC over
K 1–5 reported. Uncertainty: posterior averaged over dequantisation draws, bootstrap
stability of the whole pipeline. Soil index kriged by an anisotropic GP (θ by profile
likelihood, spatial block CV) and an NE-trend test against isotropic simulations on the
same sample layout. Reads data/interim/03_soil.csv, 04_rock.csv, data/processed/ml/*ml1*,
element_thresholds.csv; writes data/processed/ml/{tanah,batuan}__ml3_zonation.csv,
data/processed/ml3_{summary,model,comparisons}.csv, gis/ml3_zonasi.gpkg,
gis/ml3_tanah_*.tif, outputs/figures/10_*_v1.png. Prints summaries only.
Run: uv run python scripts/10_ml3_zonation.py  (then rerun scripts/07_export.py)
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
from joblib import Parallel, delayed
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.spatial import cKDTree
from scipy.stats import mannwhitneyu, norm
from sklearn.metrics import adjusted_rand_score, cohen_kappa_score
from sklearn.model_selection import GroupKFold

from src import classify, dem, paths, zonation as zn

SEED = 0
N_DRAWS = 20          # dequantisation draws (BIC average, posterior average)
N_BOOT = 200
N_PERM = 200          # Horn permutations
KMAX = 5
N_INIT = 10
N_INIT_BOOT = 5
P_AMBIG = 0.5
CELL = 10.0           # GP grid (m)
MASK_M = 60.0         # surface only within this distance of a soil sample
BLOCK_M = 150.0       # spatial CV blocks
CV_FOLDS = 5
NEIGH_M = 60.0        # lab-job neighbour test
ANGLES = np.arange(0, 180, 15)
TOL = 22.5
EDGES = 20 + 40 * np.arange(11)   # lag bins centred on 40, 80, ... 400 m
N_SIM = 200
NE = (30, 60)          # NE strike window (resume)

DATASETS = {  # name: (file, Bahasa label, main features, sensitivity extra features)
    "tanah": ("03_soil.csv", "Tanah (RJ)", ["AuPPM", "CuPPM", "AsPPM", "HgPPM", "PbPPM", "SbPPM", "ZnPPM"], []),
    "batuan": ("04_rock.csv", "Batuan (grab, RJ)", ["AuPPM", "CuPPM", "AsPPM"], ["HgPPM", "PbPPM", "SbPPM", "ZnPPM"]),
}
ML1_POP = {"tanah": ["As", "Pb", "Zn"], "batuan": ["Hg", "Pb", "Sb"]}
ZCOL = {1: "#2a78d6", 2: "#e8a33d", 3: "#c8321e"}     # Rendah, Sedang, Tinggi
C_INK, C_INK2, C_NULL = "#0b0b0b", "#52514e", "#b9b8b2"


def el(c: str) -> str:
    return c.removesuffix("PPM")


# --- pipeline ----------------------------------------------------------------------------
def pipeline(V: np.ndarray, transform=None, n_draws: int = N_DRAWS) -> dict:
    """Index, BIC curve, K=3 zones (posterior averaged over draws) and the K=2 partition."""
    tf = transform or (lambda L: L)
    L0 = tf(zn.log_matrix(V))
    idx = zn.Index(L0)
    reg = idx.reg_covar()
    draws = [idx.score(tf(zn.log_matrix(V, np.random.default_rng(SEED + d)))) for d in range(n_draws)]
    bic = pd.concat([zn.bic_curve(s, reg, KMAX, 5, SEED) for s in draws], axis=1).mean(axis=1)
    g3 = zn.fit_gmm(draws[0], 3, reg, N_INIT, SEED)
    g2 = zn.fit_gmm(draws[0], 2, reg, N_INIT, SEED)
    P3 = np.mean([zn.posterior(g3, s) for s in draws], axis=0)
    P2 = np.mean([zn.posterior(g2, s) for s in draws], axis=0)
    index = idx.score(L0)
    span = (index.min() - 0.5, index.max() + 0.5)
    return dict(idx=idx, reg=reg, index=index, span=span, bic=bic, k_bic=int(bic.idxmin()), g3=g3, P=P3,
                zone=zn.zone_ids(P3), zone2=zn.zone_ids(P2), t=zn.boundaries(g3, *span), L0=L0)


def boot_one(V: np.ndarray, full_idx: zn.Index, full_reg: float, span: tuple, b: int):
    """One bootstrap: (zones of all rows from a full refit, zone boundaries and BIC-K at the
    fixed full-data transform; boundaries NaN if that refit's zones are not ordered)."""
    rng = np.random.default_rng(SEED + 1000 + b)
    i = rng.integers(0, len(V), len(V))
    Lb = zn.log_matrix(V[i], rng)
    ib = zn.Index(Lb)
    gb = zn.fit_gmm(ib.score(Lb), 3, ib.reg_covar(), N_INIT_BOOT, SEED)
    zones = zn.zone_ids(zn.posterior(gb, ib.score(zn.log_matrix(V, rng))))
    sf = full_idx.score(Lb)
    try:
        t = zn.boundaries(zn.fit_gmm(sf, 3, full_reg, N_INIT_BOOT, SEED), *span)
    except ValueError:
        t = [np.nan, np.nan]
    k = int(zn.bic_curve(sf, full_reg, KMAX, 3, SEED).idxmin())
    return zones, t, k


def run_dataset(name: str, d: pd.DataFrame, feats: list[str]) -> dict:
    sub = d.is_RJ.astype(bool) & d[[f"{c}_ml" for c in feats]].notna().all(axis=1)
    V = d.loc[sub, [f"{c}_ml" for c in feats]].to_numpy(float)
    r = pipeline(V)
    n_pc, eig, null = zn.horn((r["L0"] - r["idx"].med) / r["idx"].mad, N_PERM, SEED)
    boots = Parallel(n_jobs=-1)(delayed(boot_one)(V, r["idx"], r["reg"], r["span"], b) for b in range(N_BOOT))
    Z = np.array([b[0] for b in boots])
    T = np.array([b[1] for b in boots], dtype=float)
    kb = pd.Series([b[2] for b in boots]).value_counts(normalize=True).sort_index()
    r.update(name=name, feats=feats, rows=d.index[sub], V=V, n_pc=n_pc, eig=eig, null=null,
             stabil=zn.stability(r["zone"], Z), ari=zn.boot_ari(r["zone"], Z), tboot=T,
             kfreq={int(k): float(f) for k, f in kb.items()})
    return r


def sensitivity(r: dict, d: pd.DataFrame, extra: list[str]) -> dict:
    """ARI vs the main zones: CLR transform, censored rows excluded, extra elements."""
    out = {}
    c = pipeline(r["V"], transform=zn.clr, n_draws=5)
    out["clr"] = (adjusted_rand_score(r["zone"], c["zone"]), len(r["V"]))
    cens = d.loc[r["rows"], [f"{x}_cens_h" for x in r["feats"]]].astype("boolean").fillna(False).any(axis=1).to_numpy()
    if cens.any():
        s = pipeline(r["V"][~cens], n_draws=5)
        out["no_censored"] = (adjusted_rand_score(r["zone"][~cens], s["zone"]), int((~cens).sum()))
    if extra:
        cols = [f"{x}_ml" for x in r["feats"] + extra]
        ok = d.loc[r["rows"], cols].notna().all(axis=1).to_numpy()
        e = pipeline(d.loc[r["rows"][ok], cols].to_numpy(float), n_draws=5)
        out["plus_" + "_".join(el(x) for x in extra)] = (adjusted_rand_score(r["zone"][ok], e["zone"]), int(ok.sum()))
    return out


# --- spatial (soil) ----------------------------------------------------------------------
def gp_surface(xy: np.ndarray, z: np.ndarray, t: list[float]) -> dict:
    x0 = xy.mean(axis=0)
    xc = xy - x0
    iso = zn.fit_gp(xc, z, None, SEED)
    prof = {}
    for a in ANGLES:
        g = zn.fit_gp(xc, z, float(a), SEED)
        prof[float(a)] = (g.log_marginal_likelihood_value_, g)
    best = max(prof, key=lambda a: prof[a][0])
    gp = prof[best][1]
    ls = gp.kernel_.k1.k2.length_scale
    major = best if ls[0] >= ls[1] else (best + 90) % 180
    # grid
    b = (xy[:, 0].min() - MASK_M, xy[:, 1].min() - MASK_M, xy[:, 0].max() + MASK_M, xy[:, 1].max() + MASK_M)
    gx, gy, transform = dem.make_grid(b, CELL)
    mask = zn.grid_mask(xy, gx[0], gy[:, 0], MASK_M)
    G = np.column_stack([gx[mask], gy[mask]]) - x0
    mu, sd = zn.latent_predict(gp, zn.rotate(G, best))
    P = zn.zone_probs(mu, sd, t[0], t[1])
    rasters = {}
    for key, vals in {"indeks": mu, "indeks_sd": sd, "p_tinggi": P[:, 2], "p_rendah": P[:, 0],
                      "zona": zn.zone_ids(P).astype(float)}.items():
        a = np.full(gx.shape, np.nan)
        a[mask] = vals
        rasters[key] = a
    # spatial block CV (θ fixed at the chosen azimuth, hyperparameters refitted per fold)
    blocks = classify.spatial_blocks(pd.Series(xy[:, 0]), pd.Series(xy[:, 1]), BLOCK_M).to_numpy(object)
    pred = {k: np.full(len(z), np.nan) for k in ("aniso", "aniso_sd", "iso", "iso_sd", "mean")}
    for tr, te in GroupKFold(CV_FOLDS).split(xc, z, blocks):
        for key, az in (("aniso", best), ("iso", None)):
            g = zn.fit_gp(xc[tr], z[tr], az, SEED, restarts=1)
            Xt = zn.rotate(xc[te], az) if az is not None else xc[te]
            pred[key][te], pred[key + "_sd"][te] = g.predict(Xt, return_std=True)
        pred["mean"][te] = z[tr].mean()
    cv = {}
    for key in ("aniso", "iso", "mean"):
        e = z - pred[key]
        cv[f"rmse_{key}"] = float(np.sqrt(np.mean(e ** 2)))
        if key != "mean":
            cv[f"cover90_{key}"] = float((np.abs(e) <= 1.645 * pred[key + "_sd"]).mean())
    return dict(x0=x0, iso=iso, prof={a: v[0] for a, v in prof.items()}, best=best, gp=gp, ls=ls, major=major,
                ratio=float(min(ls) / max(ls)), rasters=rasters, transform=transform, cv=cv, pred=pred,
                n_blocks=len(set(blocks)))


def ne_test(xy: np.ndarray, z: np.ndarray, iso, job: np.ndarray) -> dict:
    """Observed direction of greatest continuity vs isotropic simulations on the same points.
    Lab jobs sit on separate E-W lines, so a per-job offset would also look like E-W
    continuity: the statistic is repeated on the index centred per job (jobs with ≥ 5
    samples), which removes any batch offset but also part of the geology."""
    geom = zn.pair_geometry(xy)
    zc = z.copy()
    for j in np.unique(job):
        m = job == j
        if m.sum() >= 5:
            zc[m] -= np.median(z[m])
    gam_c, _ = zn.dir_variogram(geom, (zc - zc.mean()) / zc.std(), ANGLES, TOL, EDGES)
    az_c, ratio_c = zn.anisotropy(gam_c, ANGLES)
    gam, cnt = zn.dir_variogram(geom, (z - z.mean()) / z.std(), ANGLES, TOL, EDGES)
    az, ratio = zn.anisotropy(gam, ANGLES)
    sims = zn.simulate_isotropic(xy, iso.kernel_, N_SIM, SEED)
    sg = [zn.dir_variogram(geom, (s - s.mean()) / s.std(), ANGLES, TOL, EDGES)[0] for s in sims]
    st = np.array([zn.anisotropy(g, ANGLES) for g in sg])
    return dict(gam=gam, cnt=cnt, az=az, ratio=ratio, gam_c=gam_c, az_jobcentred=az_c, ratio_jobcentred=ratio_c,
                p_ratio_jobcentred=float((st[:, 1] <= ratio_c).mean()), sim_gam=np.array(sg), sim_az=st[:, 0], sim_ratio=st[:, 1],
                p_ratio=float((st[:, 1] <= ratio).mean()),
                p_az_same=float((st[:, 0] == az).mean()),
                p_ne_geometry=float(np.mean([zn.angle_in(a, *NE) for a in st[:, 0]])))


# --- tables ------------------------------------------------------------------------------
def ml_table(d: pd.DataFrame, r: dict, extra_cols: dict | None = None) -> pd.DataFrame:
    m = pd.DataFrame({"SampleID": d.SampleID})
    P, rows = r["P"], r["rows"]
    pm = P.max(axis=1)
    put = {"ML_zona": np.array(zn.ZONES, dtype=object)[r["zone"] - 1], "ML_zona_id": r["zone"],
           "ML_zona_p_T": P[:, 2].round(4), "ML_zona_p_S": P[:, 1].round(4), "ML_zona_p_R": P[:, 0].round(4),
           "ML_zona_p_maks": pm.round(4), "ML_zona_ambigu": np.where(pm < P_AMBIG, "Y", "N"),
           "ML_zona_stabil": r["stabil"].round(3), "ML_zona_indeks": r["index"].round(4), "ML_zona_K2": r["zone2"]}
    for k, v in put.items():
        m[k] = pd.Series(v, index=rows).reindex(d.index)
    for k in ("ML_zona_id", "ML_zona_K2"):
        m[k] = m[k].astype("Int64")
    for k, v in (extra_cols or {}).items():
        m[k] = v
    return m


def summary_rows(d: pd.DataFrame, r: dict, label_cols: list[str]) -> list[dict]:
    rows = []
    sub = d.loc[r["rows"]]
    for zid, zname in enumerate(zn.ZONES, start=1):
        s = sub[r["zone"] == zid]
        row = dict(dataset=r["name"], zone=zname, zone_id=zid, n=len(s),
                   mean_p_maks=round(float(r["P"][r["zone"] == zid].max(axis=1).mean()), 3),
                   mean_stabil=round(float(r["stabil"][r["zone"] == zid].mean()), 3),
                   n_ambigu=int((r["P"][r["zone"] == zid].max(axis=1) < P_AMBIG).sum()))
        for c in label_cols:
            v = s[f"{c}_ml"].dropna()
            row[f"{el(c)}_median"], row[f"{el(c)}_q25"], row[f"{el(c)}_q75"] = (
                v.median(), v.quantile(0.25), v.quantile(0.75)) if len(v) else (np.nan,) * 3
        rows.append(row)
    return rows


def crosstab_rows(name: str, comp: str, zone: np.ndarray, cat) -> list[dict]:
    t = pd.crosstab(pd.Series(np.array(zn.ZONES, dtype=object)[zone - 1], name="zone"),
                    pd.Series(np.asarray(cat, dtype=object), name="cat"))
    return [dict(dataset=name, comparison=comp, zone=z, category=str(c), n=int(t.loc[z, c]))
            for z in t.index for c in t.columns]


# --- figures -----------------------------------------------------------------------------
def fig_pca(res: dict, path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11, 9), gridspec_kw={"width_ratios": [3, 2]})
    for row, (name, r) in zip(axes, res.items()):
        ax, ax2 = row
        S = r["idx"].scores(r["L0"])
        for zid in (1, 2, 3):
            m = r["zone"] == zid
            ax.scatter(S[m, 0], S[m, 1], s=12, color=ZCOL[zid], alpha=0.75, lw=0, label=f"Zona {zn.ZONES[zid - 1]}")
        ld = r["idx"].loadings([el(c) for c in r["feats"]])
        lv = ld[["PC1", "PC2"]].to_numpy()
        room = np.where(lv > 0, S[:, :2].max(axis=0), -S[:, :2].min(axis=0))   # space on each arrow's side
        sc = 0.8 * np.min(room[np.abs(lv) > 0.05] / np.abs(lv[np.abs(lv) > 0.05]))
        for e, (a, b) in ld[["PC1", "PC2"]].iterrows():
            ax.annotate("", (a * sc, b * sc), (0, 0), arrowprops=dict(arrowstyle="->", color=C_INK, lw=1))
            ax.text(a * sc * 1.08, b * sc * 1.08, e, fontsize=8, ha="center", va="center")
        for t in r["t"]:
            if np.isfinite(t):
                ax.axvline(t, color=C_INK2, lw=1, ls=(0, (4, 2)))
        v = r["idx"].pca.explained_variance_ratio_
        ax.set_xlabel(f"PC1 = indeks mineralisasi ({100 * v[0]:.0f}% varians)", fontsize=8.5)
        ax.set_ylabel(f"PC2 ({100 * v[1]:.0f}% varians)", fontsize=8.5)
        ax.set_title(f"{DATASETS[name][1]}: skor PCA dan muatan unsur (n={len(S)})", fontsize=9.5)
        ax.legend(fontsize=7.5, frameon=False)
        k = np.arange(1, len(r["eig"]) + 1)
        ax2.plot(k, r["eig"], "o-", color=C_INK, label="Nilai eigen data")
        ax2.plot(k, r["null"], "s--", color=C_NULL, label="Persentil 95% data acak (Horn)")
        ax2.set_xticks(k)
        ax2.set_xlabel("Komponen utama", fontsize=8.5)
        ax2.set_ylabel("Nilai eigen", fontsize=8.5)
        ax2.set_title(f"Analisis paralel: {r['n_pc']} komponen dipertahankan", fontsize=9.5)
        ax2.legend(fontsize=7.5, frameon=False)
        for a in row:
            for s in ("top", "right"):
                a.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_bic(res: dict, path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.5))
    for row, (name, r) in zip(axes, res.items()):
        ax, ax2, ax3 = row
        b = r["bic"] - r["bic"].min()
        ax.bar(b.index, np.where(np.isfinite(b), b, 0), color=[C_INK if k == 3 else C_NULL for k in b.index])
        for k, v in b.items():
            ax.text(k, (v if np.isfinite(v) else 0) + 0.5, "tidak sah" if not np.isfinite(v) else f"{v:.1f}",
                    ha="center", fontsize=7)
        ax.set_xlabel("Jumlah populasi K", fontsize=8.5)
        ax.set_ylabel("ΔBIC terhadap model terbaik", fontsize=8.5)
        kf = ", ".join(f"K{k}: {f:.2f}" for k, f in r["kfreq"].items())
        ax.set_title(f"{DATASETS[name][1]}: BIC memilih K={r['k_bic']}\n(bootstrap {kf})", fontsize=9)
        s = r["index"]
        bins = np.linspace(s.min(), s.max(), 35)
        ax2.hist([s[r["zone"] == z] for z in (1, 2, 3)], bins=bins, stacked=True, color=[ZCOL[z] for z in (1, 2, 3)],
                 edgecolor="white", lw=0.4)
        grid = np.linspace(bins[0], bins[-1], 400)
        g = r["g3"]
        scale = len(s) * (bins[1] - bins[0])
        for j in zn.order(g):
            ax2.plot(grid, g.weights_[j] * norm.pdf(grid, g.means_[j, 0], np.sqrt(g.covariances_[j].ravel()[0])) * scale,
                     color=C_INK, lw=0.9, ls=(0, (3, 2)))
        for i, t in enumerate(r["t"]):
            if np.isfinite(t):
                lo, hi = np.nanpercentile(r["tboot"][:, i], [5, 95])
                ax2.axvspan(lo, hi, color=C_INK2, alpha=0.15, lw=0)
                ax2.axvline(t, color=C_INK, lw=1.4)
        ax2.set_xlabel("Indeks mineralisasi (PC1)", fontsize=8.5)
        ax2.set_ylabel("Jumlah sampel", fontsize=8.5)
        ax2.set_title("Zona K=3, ambang dan selang bootstrap 5–95%", fontsize=9)
        ax3.hist([r["stabil"][r["zone"] == z] for z in (1, 2, 3)], bins=np.linspace(0, 1, 21), stacked=True,
                 color=[ZCOL[z] for z in (1, 2, 3)], edgecolor="white", lw=0.4)
        ax3.set_xlabel("Stabilitas zona (proporsi bootstrap sama)", fontsize=8.5)
        ax3.set_ylabel("Jumlah sampel", fontsize=8.5)
        ax3.set_title(f"ARI bootstrap median {np.median(r['ari']):.2f} "
                      f"(5–95%: {np.percentile(r['ari'], 5):.2f}–{np.percentile(r['ari'], 95):.2f})", fontsize=9)
        for a in row:
            for sp in ("top", "right"):
                a.spines[sp].set_visible(False)
    fig.legend(handles=[Patch(color=ZCOL[z], label=f"Zona {zn.ZONES[z - 1]}") for z in (1, 2, 3)]
               + [Line2D([], [], color=C_INK, lw=0.9, ls=(0, (3, 2)), label="Komponen GMM")],
               loc="lower center", ncol=4, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_elements(res: dict, tables: dict, path) -> None:
    cols = {"tanah": DATASETS["tanah"][2], "batuan": DATASETS["batuan"][2] + DATASETS["batuan"][3]}
    ncol = 7
    fig, axes = plt.subplots(2, ncol, figsize=(15, 6))
    for row, (name, r) in zip(axes, res.items()):
        sub = tables[name].loc[r["rows"]]
        for ax, c in zip(row, cols[name]):
            data = [np.log10(sub.loc[r["zone"] == z, f"{c}_ml"].dropna()) for z in (1, 2, 3)]
            bp = ax.boxplot(data, patch_artist=True, widths=0.6, showfliers=False)
            for p, z in zip(bp["boxes"], (1, 2, 3)):
                p.set_facecolor(ZCOL[z])
                p.set_alpha(0.8)
            for m in bp["medians"]:
                m.set_color(C_INK)
            lo, hi = np.floor(min(x.min() for x in data if len(x))), np.ceil(max(x.max() for x in data if len(x)))
            ticks = np.arange(lo, hi + 1)
            ax.set_yticks(ticks)
            ax.set_yticklabels([f"{10 ** t:g}" for t in ticks], fontsize=7)
            ax.set_xticks([1, 2, 3])
            ax.set_xticklabels(["R", "S", "T"], fontsize=8)
            used = c in r["feats"]
            ax.set_title(f"{el(c)} (ppm)" + ("" if used else "*"), fontsize=9)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
        for ax in row[len(cols[name]):]:
            ax.axis("off")
        row[0].set_ylabel(f"{DATASETS[name][1]}\nkonsentrasi (log)", fontsize=8.5)
    fig.suptitle("Sebaran unsur per zona (R = Rendah, S = Sedang, T = Tinggi); "
                 "* = tidak dipakai dalam model, hanya pembanding", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_variogram(ne: dict, gp: dict, path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.3))
    ax = axes[0]
    obs = np.nanmean(ne["gam"][:, :3], axis=1)
    sim = np.nanmean(ne["sim_gam"][:, :, :3], axis=2)
    lo, hi = np.nanpercentile(sim, [5, 95], axis=0)
    ax.fill_between(ANGLES, lo, hi, color=C_NULL, alpha=0.5, lw=0, label="Medan isotropik simulasi (5–95%)")
    ax.plot(ANGLES, obs, "o-", color=C_INK, label="Indeks tanah (teramati)")
    ax.plot(ANGLES, np.nanmean(ne["gam_c"][:, :3], axis=1), "^:", color=C_INK2, ms=4,
            label="Indeks dikoreksi per job lab")
    ax.axvspan(*NE, color=ZCOL[3], alpha=0.12, lw=0, label="Arah struktur NE (30–60°)")
    ax.set_xlabel("Azimut (°)", fontsize=8.5)
    ax.set_ylabel("Semivarians ternormalisasi (lag 40–120 m)", fontsize=8.5)
    p = f"p<{1 / N_SIM:.3f}" if ne["p_ratio"] == 0 else f"p={ne['p_ratio']:.2f}"
    ax.set_title(f"Kontinuitas terbesar {ne['az']:.0f}°, rasio {ne['ratio']:.2f} ({p})", fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    ax = axes[1]
    ax.hist(ne["sim_az"], bins=np.arange(-7.5, 180, 15), color=C_NULL, edgecolor="white")
    ax.axvline(ne["az"], color=C_INK, lw=2)
    ax.axvspan(*NE, color=ZCOL[3], alpha=0.12, lw=0)
    ax.set_xlabel("Azimut kontinuitas terbesar (°)", fontsize=8.5)
    ax.set_ylabel("Jumlah simulasi", fontsize=8.5)
    ax.set_title(f"Geometri sampel saja: {100 * ne['p_ne_geometry']:.0f}% simulasi jatuh di NE", fontsize=9)
    ax = axes[2]
    a = np.array(list(gp["prof"]))
    ax.plot(a, list(gp["prof"].values()), "o-", color=C_INK)
    ax.axvline(gp["best"], color=ZCOL[3], lw=1.5)
    ax.set_xlabel("Azimut rotasi kernel GP (°)", fontsize=8.5)
    ax.set_ylabel("Log-likelihood marginal", fontsize=8.5)
    ax.set_title(f"GP: sumbu utama {gp['major']:.0f}°, rasio panjang {gp['ratio']:.2f}", fontsize=9)
    for x in axes:
        for s in ("top", "right"):
            x.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_cv(z: np.ndarray, gp: dict, path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3))
    for ax, key, lab in zip(axes, ("aniso", "iso"), ("GP anisotropik", "GP isotropik")):
        p = gp["pred"][key]
        ax.errorbar(p, z, xerr=1.645 * gp["pred"][key + "_sd"], fmt="o", ms=3, color=C_INK, ecolor=C_NULL, elinewidth=0.6)
        lim = [min(z.min(), p.min()) - 0.5, max(z.max(), p.max()) + 0.5]
        ax.plot(lim, lim, color=ZCOL[3], lw=1)
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel("Indeks prediksi (validasi silang blok 150 m)", fontsize=8.5)
        ax.set_ylabel("Indeks teramati", fontsize=8.5)
        ax.set_title(f"{lab}: RMSE {gp['cv']['rmse_' + key]:.2f} (rata-rata saja {gp['cv']['rmse_mean']:.2f}); "
                     f"cakupan 90% = {100 * gp['cv']['cover90_' + key]:.0f}%", fontsize=8.5)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


# --- main --------------------------------------------------------------------------------
def main() -> None:
    I, P, ml_dir = paths.INTERIM, paths.PROCESSED, paths.PROCESSED / "ml"
    tables = {n: pd.read_csv(I / f, low_memory=False) for n, (f, *_) in DATASETS.items()}
    thr = pd.read_csv(P / "element_thresholds.csv").set_index(["dataset", "element"])
    problems, model, comps, summ = [], [], [], []

    def rec(ds, section, item, value):
        model.append(dict(dataset=ds, section=section, item=item, value=value))

    res = {}
    for name, (_f, _l, feats, extra) in DATASETS.items():
        d = tables[name]
        print(f"{name}: fitting pipeline + {N_BOOT} bootstraps on {', '.join(el(c) for c in feats)}")
        r = run_dataset(name, d, feats)
        res[name] = r
        sub = d.loc[r["rows"]]
        au = [sub.AuPPM_ml[r["zone"] == z].median() for z in (1, 2, 3)]
        if not au[0] < au[1] < au[2]:
            problems.append(f"{name}: median Au not increasing over zones {au}")
        if not np.allclose(r["P"].sum(axis=1), 1):
            problems.append(f"{name}: posteriors do not sum to 1")
        rec(name, "data", "n_samples", len(r["V"]))
        rec(name, "data", "features", ";".join(el(c) for c in feats))
        for e, row in r["idx"].loadings([el(c) for c in feats]).iterrows():
            rec(name, "pca_loading_PC1", e, round(row.PC1, 4))
            rec(name, "pca_loading_PC2", e, round(row.PC2, 4))
        for i, v in enumerate(r["idx"].pca.explained_variance_ratio_):
            rec(name, "pca_var_ratio", f"PC{i + 1}", round(float(v), 4))
        rec(name, "horn", "n_pc_kept", r["n_pc"])
        for i, (a, b) in enumerate(zip(r["eig"], r["null"])):
            rec(name, "horn", f"PC{i + 1}_eig_vs_null95", f"{a:.3f} / {b:.3f}")
        rec(name, "pca", "corr_PC1_logAu", round(float(np.corrcoef(r["index"], r["L0"][:, 0])[0, 1]), 3))
        for k, v in (r["bic"] - r["bic"].min()).items():
            rec(name, "dBIC", f"K{k}", round(float(v), 2) if np.isfinite(v) else "inadmissible")
        rec(name, "dBIC", "K_bic", r["k_bic"])
        rec(name, "bootstrap", "K_bic_freq", ";".join(f"{k}:{f:.2f}" for k, f in r["kfreq"].items()))
        rec(name, "bootstrap", "ARI_median", round(float(np.median(r["ari"])), 3))
        rec(name, "bootstrap", "ARI_05_95", f"{np.percentile(r['ari'], 5):.3f} / {np.percentile(r['ari'], 95):.3f}")
        rec(name, "gmm", "reg_covar", round(r["reg"], 5))
        comp = zn.th.components(r["g3"])
        for i, c in comp.iterrows():
            rec(name, "gmm", f"zone{i + 1}_mean_sd_weight", f"{c['mean']:.3f} / {c.sd:.3f} / {c.weight:.3f}")
        for i, t in enumerate(r["t"]):
            lo, hi = np.nanpercentile(r["tboot"][:, i], [5, 95])
            rec(name, "threshold", f"T{i + 1}{i + 2}", round(t, 4))
            rec(name, "threshold", f"T{i + 1}{i + 2}_ci05_95", f"{lo:.3f} / {hi:.3f}")
            rec(name, "threshold", f"T{i + 1}{i + 2}_boot_nan_share", round(float(np.isnan(r["tboot"][:, i]).mean()), 3))
            rec(name, "threshold", f"D_{i + 1}{i + 2}", round(zn.th.ashman_d(comp["mean"][i], comp.sd[i],
                                                                            comp["mean"][i + 1], comp.sd[i + 1]), 3))
        rec(name, "K2_vs_K3", "ARI", round(adjusted_rand_score(r["zone"], r["zone2"]), 3))
        comps += crosstab_rows(name, "K2_partition", r["zone"], r["zone2"])
        for k, (a, n) in sensitivity(r, d, extra).items():
            rec(name, "sensitivity_ARI", k, f"{a:.3f} (n {n})")
        # ML-1 comparison
        m1 = pd.read_csv(ml_dir / f"{name}__ml1_thresholds.csv").set_index("SampleID").loc[sub.SampleID]
        au_thr = thr.loc[(name, "Au"), "thr_gmm_main"]
        au_hi = np.where(sub.AuPPM_ml.to_numpy() > au_thr, f"Au>{au_thr:.3g}", f"Au<={au_thr:.3g}")
        comps += crosstab_rows(name, "ML1_Au_thr_gmm_main", r["zone"], au_hi)
        rec(name, "cramers_v", "ML1_Au_thr_gmm_main", round(zn.cramers_v(r["zone"], au_hi), 3))
        for e in ML1_POP[name]:
            pop = m1[f"ML_thr_{e}_populasi"].to_numpy()
            ok = ~pd.isna(pop)
            comps += crosstab_rows(name, f"ML1_{e}_populasi", r["zone"][ok], pop[ok].astype(int))
            rec(name, "cramers_v", f"ML1_{e}_populasi", round(zn.cramers_v(r["zone"][ok], pop[ok]), 3))
        # lab job
        job = sub.LabJobNo.astype(str).to_numpy()
        comps += crosstab_rows(name, "LabJobNo", r["zone"], job)
        rec(name, "cramers_v", "LabJobNo", round(zn.cramers_v(r["zone"], job), 3))
        xy = sub[["Easting", "Northing"]].to_numpy(float)
        pairs = np.array(sorted(cKDTree(xy).query_pairs(NEIGH_M)))
        same = job[pairs[:, 0]] == job[pairs[:, 1]]
        dd = np.abs(r["index"][pairs[:, 0]] - r["index"][pairs[:, 1]])
        if same.any() and (~same).any():
            p = mannwhitneyu(dd[~same], dd[same], alternative="greater").pvalue
            rec(name, "labjob_neighbour", f"median_dIndex_same_vs_diff_lt{NEIGH_M:.0f}m",
                f"{np.median(dd[same]):.3f} (n {same.sum()}) / {np.median(dd[~same]):.3f} (n {(~same).sum()})")
            rec(name, "labjob_neighbour", "mannwhitney_p_diff_gt_same", round(float(p), 4))
        if name == "batuan":
            for c, lab in (("Alt_facies_name", "alteration_logged"), ("RKOutcropT", "outcrop_type")):
                cat = sub[c].fillna("(kosong)").astype(str).to_numpy()
                comps += crosstab_rows(name, lab, r["zone"], cat)
                rec(name, "cramers_v", lab, round(zn.cramers_v(r["zone"], cat), 3))
        summ += summary_rows(d, r, DATASETS[name][2] + DATASETS[name][3])

    # soil surface + NE test
    soil, rs = tables["tanah"], res["tanah"]
    xy = soil.loc[rs["rows"], ["Easting", "Northing"]].to_numpy(float)
    print("tanah: GP profile over azimuths, spatial CV, NE test")
    gp = gp_surface(xy, rs["index"], rs["t"])
    ne = ne_test(xy, rs["index"], gp["iso"], soil.loc[rs["rows"], "LabJobNo"].astype(str).to_numpy())
    k = gp["gp"].kernel_
    rec("tanah", "gp", "kernel", str(k))
    rec("tanah", "gp", "kernel_isotropic", str(gp["iso"].kernel_))
    rec("tanah", "gp", "lml_isotropic", round(gp["iso"].log_marginal_likelihood_value_, 2))
    for a, v in gp["prof"].items():
        rec("tanah", "gp_lml_profile", f"az{a:.0f}", round(v, 2))
    rec("tanah", "gp", "rotation_az_best", gp["best"])
    rec("tanah", "gp", "major_axis_az", gp["major"])
    rec("tanah", "gp", "length_scale_major_minor_m", f"{max(gp['ls']):.1f} / {min(gp['ls']):.1f}")
    rec("tanah", "gp", "anisotropy_ratio", round(gp["ratio"], 3))
    for kk, v in gp["cv"].items():
        rec("tanah", "gp_cv", kk, round(v, 4))
    rec("tanah", "gp_cv", "n_blocks", gp["n_blocks"])
    for kk in ("az", "ratio", "p_ratio", "p_az_same", "p_ne_geometry", "az_jobcentred", "ratio_jobcentred",
               "p_ratio_jobcentred"):
        rec("tanah", "ne_test", kk, round(float(ne[kk]), 4))
    rec("tanah", "ne_test", "obs_in_NE_window", zn.angle_in(ne["az"], *NE))
    rec("tanah", "ne_test", "sim_ratio_05_50_95", "/".join(f"{x:.3f}" for x in np.percentile(ne["sim_ratio"], [5, 50, 95])))
    rec("tanah", "ne_test", "pairs_per_direction_first3lags_min", int(ne["cnt"][:, :3].min()))
    for key, a in gp["rasters"].items():
        dem.write_geotiff(paths.GIS / f"ml3_tanah_{key}.tif", a, gp["transform"])
    ras_area = int(np.isfinite(gp["rasters"]["zona"]).sum())
    for zid in (1, 2, 3):
        rec("tanah", "gp_surface_area_ha", zn.ZONES[zid - 1],
            round(float((gp["rasters"]["zona"] == zid).sum()) * CELL ** 2 / 1e4, 2))

    # rock vs soil surface at rock locations
    rr, rock = res["batuan"], tables["batuan"]
    rxy = rock.loc[rr["rows"], ["Easting", "Northing"]].to_numpy(float)
    dist, _ = cKDTree(xy).query(rxy)
    inside = dist <= MASK_M
    mu, sd = zn.latent_predict(gp["gp"], zn.rotate(rxy[inside] - gp["x0"], gp["best"]))
    zs = zn.zone_ids(zn.zone_probs(mu, sd, rs["t"][0], rs["t"][1]))
    comps += crosstab_rows("batuan", "soil_gp_zone_at_rock", rr["zone"][inside], np.array(zn.ZONES, dtype=object)[zs - 1])
    rec("batuan", "vs_soil_gp", "n_inside_mask", int(inside.sum()))
    rec("batuan", "vs_soil_gp", "kappa", round(cohen_kappa_score(rr["zone"][inside], zs), 3))
    rec("batuan", "vs_soil_gp", "kappa_linear", round(cohen_kappa_score(rr["zone"][inside], zs, weights="linear"), 3))
    rec("batuan", "vs_soil_gp", "agreement", round(float((rr["zone"][inside] == zs).mean()), 3))

    # ML files, tables, GIS
    float_flag = pd.Series(np.where(rock.RKOutcropT.eq("Float"), "Y", "N"), index=rock.index).where(
        rock.index.isin(rr["rows"]))
    ml = {"tanah": ml_table(soil, rs), "batuan": ml_table(rock, rr, {"ML_zona_float": float_flag})}
    for name, m in ml.items():
        d = tables[name]
        assert len(m) == len(d) and m.SampleID.is_unique
        notfit = ~d.index.isin(res[name]["rows"])
        if not m.loc[notfit, [c for c in m if c.startswith("ML_")]].isna().all().all():
            problems.append(f"{name}: ML columns filled outside the fitted rows")
        if not (~d.loc[notfit, "is_RJ"].astype(bool) | d.loc[notfit, [f"{c}_ml" for c in res[name]["feats"]]].isna().any(axis=1)).all():
            problems.append(f"{name}: an RJ row with complete features was left out")
        m.to_csv(ml_dir / f"{name}__ml3_zonation.csv", index=False)
    pd.DataFrame(summ).to_csv(P / "ml3_summary.csv", index=False)
    pd.DataFrame(model).astype({"value": str}).to_csv(P / "ml3_model.csv", index=False)
    pd.DataFrame(comps).to_csv(P / "ml3_comparisons.csv", index=False)
    gpkg = paths.GIS / "ml3_zonasi.gpkg"
    for name, layer in (("tanah", "tanah_zona"), ("batuan", "batuan_zona")):
        d, r = tables[name], res[name]
        sub = d.loc[r["rows"], ["SampleID", "Easting", "Northing", "LabJobNo"] + [f"{c}_ml" for c in r["feats"]]]
        g = sub.merge(ml[name], on="SampleID", how="left")
        g = gpd.GeoDataFrame(g, geometry=gpd.points_from_xy(g.Easting, g.Northing), crs=paths.CRS)
        g.to_file(gpkg, layer=layer, driver="GPKG", engine="pyogrio", mode="w")   # "w" replaces this layer only
        n_file = pyogrio.read_info(gpkg, layer=layer)["features"]
        if not len(g) == n_file == len(r["rows"]):
            problems.append(f"{layer}: {n_file} features in file vs {len(r['rows'])} rows")

    fig_pca(res, paths.FIGURES / "10_pca_biplot_v1.png")
    fig_bic(res, paths.FIGURES / "10_bic_stabilitas_v1.png")
    fig_elements(res, tables, paths.FIGURES / "10_zona_unsur_v1.png")
    fig_variogram(ne, gp, paths.FIGURES / "10_variogram_arah_v1.png")
    fig_cv(rs["index"], gp, paths.FIGURES / "10_gp_cv_v1.png")

    # print summaries
    with pd.option_context("display.width", 250, "display.max_columns", 40, "display.max_rows", 400):
        s = pd.DataFrame(summ)
        print(s[["dataset", "zone", "n", "mean_p_maks", "mean_stabil", "n_ambigu", "Au_median", "Cu_median",
                 "As_median", "Pb_median", "Zn_median"]].to_string(index=False, float_format=lambda x: f"{x:.3g}"))
        print(pd.DataFrame(model).to_string(index=False))
    print(f"\nGP surface: {ras_area} cells of {CELL:.0f} m within {MASK_M:.0f} m of soil samples")
    print("outputs: data/processed/ml/{tanah,batuan}__ml3_zonation.csv; data/processed/ml3_{summary,model,comparisons}.csv;"
          " gis/ml3_zonasi.gpkg; gis/ml3_tanah_*.tif; outputs/figures/10_*_v1.png")
    if problems:
        print("\nCHECK FAILURES:\n  " + "\n  ".join(problems))
        raise SystemExit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
