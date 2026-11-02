"""ML-1: element thresholds (AGENTS.md §6 task 1). Plan: LOG.md, 2026-11-03 ML-1 entry.

GMM on dequantised log10 values with BIC-selected K (admissible models only), thresholds
at adjacent-population density crossings, bootstrap K frequency and threshold CI, and the
median+2·MAD / Tukey comparators. Drillhole: raw sampled assays; surface: RJ only.
Reads data/interim/05_assay_joined.csv, 04_rock.csv, 03_soil.csv, 01_element_summary.csv;
writes data/processed/element_thresholds.csv, data/processed/ml/<target>__ml1_thresholds.csv
and outputs/figures/08_*_v1.png. Prints summaries only.
Run: uv run python scripts/08_ml1_thresholds.py  (then rerun scripts/07_export.py)
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.stats import norm

from src import export, paths, thresholds as th

SEED = 0
N_DRAWS = 20        # dequantisation draws averaged in the BIC
N_INIT_SELECT = 5
N_INIT_FINAL = 10
N_BOOT = 200
N_INIT_BOOT = 3
MAX_T = th.KMAX - 1
CENS_WARN_PCT = 25  # above this, Q1 sits on the DL and the Tukey fence is affected

DATASETS = {  # name: (file, summary dataset, ML target, Bahasa label, elements)
    "bor": ("05_assay_joined.csv", "assay", "assay", "Bor (assay mentah)",
            ["AuPPM", "AgPPM", "CuPPM", "AsPPM", "SCIS_PCT"]),
    "batuan": ("04_rock.csv", "rock", "batuan", "Batuan (grab, RJ)",
               ["AuPPM", "CuPPM", "AsPPM", "HgPPM", "PbPPM", "SbPPM", "ZnPPM"]),
    "tanah": ("03_soil.csv", "soil", "tanah", "Tanah (RJ)",
              ["AuPPM", "AgPPM", "CuPPM", "AsPPM", "BaPPM", "HgPPM", "PbPPM", "SbPPM", "WPPM", "ZnPPM"]),
}
NOT_DETERMINABLE = {("batuan", "AgPPM"): "not ML-usable: 65.7% censored after DL harmonisation (Stage 1)"}
CONF_ID = {"high": "tinggi", "medium": "sedang", "low": "rendah"}
# reference palette (dataviz skill): blue = data, orange = GMM threshold, inks for comparators
C_DATA, C_CENS, C_THR, C_INK, C_INK2 = "#2a78d6", "#b9b8b2", "#eb6834", "#0b0b0b", "#52514e"


def unit(col: str) -> str:
    return "%" if col.endswith("PCT") else "ppm"


def tag(col: str) -> str:
    """`AuPPM` -> `Au`, `SCIS_PCT` -> `S_sulfida_SCIS` (ioGAS-style element name, no unit)."""
    return export.iogas_name(col + "_ml").rsplit("_", 1)[0]


def label_el(col: str) -> str:
    return "S sulfida (SCIS)" if col == "SCIS_PCT" else tag(col)


def subset(name: str, d: pd.DataFrame) -> pd.Series:
    return ~d.no_sample.astype(bool) if name == "bor" else d.is_RJ.astype(bool)


def fit_element(name: str, col: str, v: pd.Series, cens: pd.Series) -> dict:
    """Everything for one dataset × element; pure function of its inputs (seeded)."""
    fit = v[v.notna() & ~cens].to_numpy()
    k, bic = th.select_k(fit, th.KMAX, N_DRAWS, SEED, N_INIT_SELECT)
    g = th.fit_gmm(th.dequantise(fit, np.random.default_rng(SEED)), k, N_INIT_FINAL, SEED)
    kfreq, tb = th.bootstrap(fit, k, th.KMAX, N_BOOT, SEED, N_INIT_BOOT)
    return dict(name=name, col=col, k=k, bic=bic, gmm=g, kfreq=kfreq, tboot=tb, n_fit=len(fit),
                n_distinct=int(pd.Series(fit).nunique()))


def summarise(r: dict, v: pd.Series, cens: pd.Series, n_rows: int) -> tuple[dict, list[float]]:
    """One element_thresholds row and the thresholds (log10) used for classification."""
    comp = th.components(r["gmm"])
    k = r["k"]
    t = th.crossings(comp)
    resolved = [x for x in t if np.isfinite(x)]
    kind = "crossing" if resolved else ("fallback: one population (K=1)" if k == 1
                                        else "fallback: populations nested, no crossing")
    t_used = resolved if resolved else [th.fallback(comp)]
    tb = r["tboot"]
    lo, hi = np.nanpercentile(tb, 5, axis=0), np.nanpercentile(tb, 95, axis=0)
    nan_share = np.isnan(tb).mean(axis=0)
    d = [th.ashman_d(*comp.loc[i, ["mean", "sd"]], *comp.loc[i + 1, ["mean", "sd"]]) for i in range(k - 1)]
    n_an = int(v.notna().sum())
    n_cens = int((v.notna() & cens).sum())
    pct_cens = 100 * n_cens / n_an
    mad, tukey = th.robust_thresholds(v)
    bic = r["bic"] - r["bic"].min()
    main = 10 ** max(t_used)
    pk = r["kfreq"].get(k, 0.0)
    min_d = min(d) if d else np.nan
    row = dict(dataset=r["name"], element=r["col"].removesuffix("PPM").removesuffix("_PCT"), column=r["col"],
               unit=unit(r["col"]), n_rows=n_rows, n_analysed=n_an, n_cens=n_cens, pct_cens=round(pct_cens, 1),
               n_fit=r["n_fit"], n_distinct=r["n_distinct"], K=k, K_boot_share=round(pk, 3),
               K_boot_freq=";".join(f"{kk}:{f:.2f}" for kk, f in r["kfreq"].items()),
               dBIC_Kminus1=round(bic.get(k - 1, np.nan), 1), dBIC_Kplus1=round(bic.get(k + 1, np.nan), 1),
               threshold_type=kind, n_thresholds=len(t_used))
    for i in range(th.KMAX):
        has = i < k
        row[f"pop{i + 1}_gmean"] = 10 ** comp["mean"][i] if has else np.nan
        row[f"pop{i + 1}_sd_log"] = comp["sd"][i] if has else np.nan
        row[f"pop{i + 1}_weight"] = comp["weight"][i] if has else np.nan
    for i in range(MAX_T):
        if kind == "crossing":
            ok = i < len(t) and np.isfinite(t[i])
            val, l, h, ns = (t[i], lo[i], hi[i], nan_share[i]) if ok else (np.nan,) * 4
        else:  # fallback: bootstrap CI only exists for K = 1
            ok = i == 0
            val = t_used[0] if ok else np.nan
            l, h, ns = (lo[0], hi[0], nan_share[0]) if ok and k == 1 else (np.nan,) * 3
        row[f"T{i + 1}"] = 10 ** val if ok else np.nan
        row[f"T{i + 1}_ci05"] = 10 ** l if np.isfinite(l) else np.nan
        row[f"T{i + 1}_ci95"] = 10 ** h if np.isfinite(h) else np.nan
        row[f"T{i + 1}_boot_nan_share"] = ns
    for i in range(MAX_T):
        row[f"D_{i + 1}{i + 2}"] = d[i] if i < len(d) else np.nan
    a = v.dropna()
    row.update(thr_gmm_main=main, thr_mad=mad, thr_tukey=tukey, thr_probplot_iogas=np.nan,
               pct_above_gmm_main=round(100 * (a > main).mean(), 1),
               pct_above_mad=round(100 * (a > mad).mean(), 1),
               pct_above_tukey=round(100 * (a > tukey).mean(), 1),
               confidence=th.confidence(pk, min_d, r["n_distinct"], pct_cens))
    notes = []
    if pct_cens > CENS_WARN_PCT:
        notes.append(f"{pct_cens:.0f}% censored: Tukey/MAD affected, GMM fitted above DL only")
    if any(np.isnan(x) for x in t) and resolved:
        notes.append("some adjacent populations nested (no crossing); merged")
    if r["name"] == "bor":
        notes.append("grade populations within a mineralised system, not background vs anomaly")
    row["note"] = "; ".join(notes)
    return row, t_used


def dl_effective(v: pd.Series, cens: pd.Series, dl_h: float) -> float:
    if np.isfinite(dl_h):
        return dl_h
    c = v[cens & v.notna()]
    return 2 * c.max() if len(c) else np.nan


def plot_dataset(name: str, label: str, items: list, path) -> None:
    """Small multiples: log histogram, GMM fit, thresholds and comparators per element."""
    n = len(items) + 1  # last panel holds the legend
    ncol = 4 if n > 6 else 3
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.2 * ncol, 2.6 * nrow))
    axes = axes.ravel()
    for ax, (row, r, v, cens) in zip(axes, items):
        lx = np.log10(v.dropna())
        lc = np.log10(v[cens & v.notna()])
        bins = np.linspace(lx.min() - 0.05, lx.max() + 0.05, 40)
        ax.hist([lx[~lx.index.isin(lc.index)], lc], bins=bins, stacked=True, color=[C_DATA, C_CENS],
                edgecolor="white", linewidth=0.4)
        comp = th.components(r["gmm"])
        grid = np.linspace(bins[0], bins[-1], 400)
        scale = r["n_fit"] * (bins[1] - bins[0])
        dens = [c.weight * norm.pdf(grid, c["mean"], c.sd) * scale for _, c in comp.iterrows()]
        for dd in dens if len(dens) > 1 else []:
            ax.plot(grid, dd, color=C_INK, lw=0.8, ls=(0, (3, 2)))
        ax.plot(grid, np.sum(dens, axis=0), color=C_INK, lw=1.6)
        for i in range(MAX_T):
            t = row[f"T{i + 1}"]
            if np.isfinite(t):
                lo, hi = row[f"T{i + 1}_ci05"], row[f"T{i + 1}_ci95"]
                if np.isfinite(lo) and np.isfinite(hi):
                    ax.axvspan(np.log10(lo), np.log10(hi), color=C_THR, alpha=0.18, lw=0)
                ax.axvline(np.log10(t), color=C_THR, lw=1.8,
                           ls="-" if row.threshold_type == "crossing" else (0, (1, 1)))
        ax.axvline(np.log10(row.thr_mad), color=C_INK2, lw=1.2, ls=(0, (5, 2)))
        ax.axvline(np.log10(row.thr_tukey), color=C_INK2, lw=1.2, ls=(0, (1, 1.5)))
        ticks = np.arange(np.floor(bins[0]), np.ceil(bins[-1]) + 1)
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{10 ** t:g}" for t in ticks], fontsize=7)
        ax.set_xlim(bins[0] - 0.1, max(bins[-1], np.log10(row.thr_tukey)) + 0.1)
        ax.tick_params(axis="y", labelsize=7)
        ax.set_title(f"{label_el(row.column)} ({row.unit}) · K={row.K} · keyakinan {CONF_ID[row.confidence]}",
                     fontsize=8.5)
        ax.set_xlabel(f"Konsentrasi ({row.unit}, skala log)", fontsize=7.5)
        ax.set_ylabel("Jumlah sampel", fontsize=7.5)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    leg = axes[len(items)]
    leg.axis("off")
    leg.legend(handles=[
        Patch(color=C_DATA, label="Sampel terukur"),
        Patch(color=C_CENS, label="Di bawah batas deteksi (DL/2)"),
        Line2D([], [], color=C_INK, lw=1.6, label="Model campuran GMM"),
        Line2D([], [], color=C_INK, lw=0.8, ls=(0, (3, 2)), label="Populasi (komponen GMM)"),
        Line2D([], [], color=C_THR, lw=1.8, label="Ambang GMM (perpotongan populasi)"),
        Line2D([], [], color=C_THR, lw=1.8, ls=(0, (1, 1)), label="Ambang GMM cadangan μ+2σ"),
        Patch(color=C_THR, alpha=0.18, label="Selang bootstrap 5–95%"),
        Line2D([], [], color=C_INK2, lw=1.2, ls=(0, (5, 2)), label="Median + 2·MAD"),
        Line2D([], [], color=C_INK2, lw=1.2, ls=(0, (1, 1.5)), label="Pagar atas Tukey"),
    ], loc="center", fontsize=7.5, frameon=False)
    for ax in axes[len(items) + 1:]:
        ax.axis("off")
    fig.suptitle(f"Ambang batas unsur (GMM, log10) — {label}", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_bic(results: list, path) -> None:
    """ΔBIC (mean over dequantisation draws) per element × K; selected K outlined."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), gridspec_kw={"width_ratios": [5, 7, 10]})
    for ax, (name, (*_, label, cols)) in zip(axes, DATASETS.items()):
        rs = [r for r in results if r["name"] == name]
        m = np.array([(r["bic"] - r["bic"].min()).to_numpy() for r in rs]).T  # K × element
        shown = np.log10(1 + np.where(np.isfinite(m), m, np.nan))
        ax.imshow(shown, cmap="Blues", vmin=0, vmax=3.5, aspect="auto")
        for j, r in enumerate(rs):
            for i in range(th.KMAX):
                val = m[i, j]
                txt = "—" if not np.isfinite(val) else (f"{val:.1f}" if val < 10 else f"{val:.0f}")
                ax.text(j, i, txt, ha="center", va="center", fontsize=7,
                        color="white" if np.isfinite(val) and shown[i, j] > 2 else C_INK)
            ax.add_patch(plt.Rectangle((j - 0.5, r["k"] - 1.5), 1, 1, fill=False, ec=C_THR, lw=2))
        ax.set_xticks(range(len(rs)))
        ax.set_xticklabels([label_el(r["col"]).replace("S sulfida (SCIS)", "S (SCIS)") for r in rs], fontsize=8)
        ax.set_yticks(range(th.KMAX))
        ax.set_yticklabels([str(k) for k in range(1, th.KMAX + 1)], fontsize=8)
        ax.set_ylabel("Jumlah populasi K", fontsize=8)
        ax.set_title(label, fontsize=9)
    fig.suptitle("ΔBIC terhadap model terbaik (kotak jingga = K terpilih; — = model tidak sah, "
                 "komponen < 5 sampel)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    I, ml_dir = paths.INTERIM, paths.PROCESSED / "ml"
    ml_dir.mkdir(exist_ok=True)
    es = pd.read_csv(I / "01_element_summary.csv").set_index(["dataset", "column"])
    tables = {name: pd.read_csv(I / f, low_memory=False) for name, (f, *_) in DATASETS.items()}

    jobs = []
    for name, (_f, ds, _t, _l, cols) in DATASETS.items():
        d = tables[name]
        sub = d[subset(name, d)]
        for c in cols:
            assert bool(es.loc[(ds, c), "ml_usable"]), f"{name} {c} not ML-usable"
            jobs.append((name, c, sub[f"{c}_ml"], sub[f"{c}_cens_h"].astype("boolean").fillna(False).astype(bool)))
    print(f"fitting {len(jobs)} dataset × element GMMs (K 1-{th.KMAX}, {N_DRAWS} draws, B={N_BOOT})")
    results = Parallel(n_jobs=-1)(delayed(fit_element)(*j) for j in jobs)

    rows, problems, plots = [], [], {n: [] for n in DATASETS}
    ml = {n: pd.DataFrame({"SampleID": tables[n].SampleID}) for n in DATASETS}
    for (name, c, v, cens), r in zip(jobs, results):
        d = tables[name]
        row, t_used = summarise(r, v, cens, len(v))
        rows.append(row)
        plots[name].append((pd.Series(row), r, v, cens))
        # checks
        dl = dl_effective(v, cens, es.loc[(DATASETS[name][1], c), "harmonised_dl"])
        if np.isfinite(dl) and 10 ** min(t_used) <= dl:
            problems.append(f"{name} {c}: lowest threshold {10 ** min(t_used):.4g} <= DL {dl:.4g}")
        if list(t_used) != sorted(t_used):
            problems.append(f"{name} {c}: thresholds not increasing")
        for i in range(MAX_T):
            t, lo, hi = row[f"T{i + 1}"], row[f"T{i + 1}_ci05"], row[f"T{i + 1}_ci95"]
            if np.isfinite(t) and np.isfinite(lo) and not lo <= t <= hi:
                problems.append(f"{name} {c}: T{i + 1} {t:.4g} outside bootstrap CI [{lo:.4g}, {hi:.4g}]")
        # per-sample ML columns: fitted subset only, NaN elsewhere
        pop, p_top = th.classify(r["gmm"], t_used, v, cens)
        if row["threshold_type"] != "crossing":  # nested or K=1: no distinct top population
            p_top[:] = np.nan
        el = tag(c)
        ml[name][f"ML_thr_{el}_populasi"] = pop.reindex(d.index).astype("Int64")
        ml[name][f"ML_thr_{el}_p_atas"] = p_top.reindex(d.index).round(4)
    for (name, c), why in NOT_DETERMINABLE.items():
        rows.append(dict(dataset=name, element=c.removesuffix("PPM"), column=c, unit=unit(c),
                         threshold_type="not determinable", confidence="none", note=why))

    out = pd.DataFrame(rows)
    out.to_csv(paths.PROCESSED / "element_thresholds.csv", index=False)
    for name, (*_, target, _l, _c) in DATASETS.items():
        m = ml[name]
        assert len(m) == len(tables[name]) and m.SampleID.is_unique
        notfit = ~subset(name, tables[name])
        assert m.loc[notfit, [x for x in m if x.startswith("ML_")]].isna().all().all()
        m.to_csv(ml_dir / f"{target}__ml1_thresholds.csv", index=False)
    for name, (*_, label, _c) in DATASETS.items():
        plot_dataset(name, label, plots[name], paths.FIGURES / f"08_ambang_{name}_v1.png")
    plot_bic(results, paths.FIGURES / "08_bic_v1.png")

    show = ["dataset", "element", "unit", "n_fit", "pct_cens", "n_distinct", "K", "K_boot_freq", "threshold_type",
            "T1", "T1_ci05", "T1_ci95", "T2", "T3", "thr_mad", "thr_tukey", "pct_above_gmm_main", "confidence"]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(out[show].to_string(index=False, float_format=lambda x: f"{x:.4g}"))
        pops = out[["dataset", "element"] + [f"pop{i}_gmean" for i in range(1, 6)] + ["D_12", "D_23", "D_34"]]
        print(pops.to_string(index=False, float_format=lambda x: f"{x:.3g}"))
    print("\noutputs: data/processed/element_thresholds.csv; data/processed/ml/{assay,batuan,tanah}__ml1_thresholds.csv;"
          " outputs/figures/08_ambang_{bor,batuan,tanah}_v1.png, 08_bic_v1.png")
    if problems:
        print("\nCHECK FAILURES:\n  " + "\n  ".join(problems))
        raise SystemExit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
