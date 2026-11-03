"""Deliverable 3 (geochemistry analysis CSV): descriptive statistics and interval lookup."""
import numpy as np
import pandas as pd

QUANTILES = (0.25, 0.5, 0.75, 0.90, 0.95, 0.98)


def describe(v: pd.Series, cens: pd.Series | None = None) -> dict:
    """Statistics of one element column (harmonised values; censored ones already DL/2).
    `cens` is the Y/N censoring column when the element has one."""
    x = pd.to_numeric(v, errors="coerce").dropna()
    out = {"n_total": int(len(v)), "n_analisis": int(len(x)),
           "pct_tersensor": float(cens.loc[x.index].eq("Y").mean() * 100) if cens is not None and len(x) else 0.0}
    if not len(x):
        return out
    pos = x[x > 0]
    out |= {"min": float(x.min()), "rerata_geometrik": float(np.exp(np.log(pos).mean())) if len(pos) else np.nan,
            "max": float(x.max())}
    for q in QUANTILES:
        out[f"P{round(q * 100)}"] = float(x.quantile(q))
    return out


def containing_interval(hole: np.ndarray, depth: np.ndarray, c_hole: np.ndarray, c_from: np.ndarray,
                        c_to: np.ndarray) -> np.ndarray:
    """Index of the interval [c_from, c_to) of the same hole that contains each depth, -1 if none."""
    out = np.full(len(depth), -1)
    c_hole = np.asarray(c_hole)
    for h in np.unique(hole):
        ci = np.flatnonzero(c_hole == h)
        if not len(ci):
            continue
        ci = ci[np.argsort(np.asarray(c_from)[ci])]
        f, t = np.asarray(c_from)[ci], np.asarray(c_to)[ci]
        ai = np.flatnonzero(hole == h)
        j = np.searchsorted(f, depth[ai], side="right") - 1
        ok = (j >= 0) & (depth[ai] < t[np.clip(j, 0, None)])
        out[ai[ok]] = ci[j[ok]]
    return out


def group_medians(df: pd.DataFrame, dataset: str, by: str, cols: list[str], min_n: int = 1) -> pd.DataFrame:
    """Median of `cols` per value of `by` (rows with a missing group dropped), plus n."""
    d = df[df[by].notna() & df[by].astype(str).ne("")]
    g = d.groupby(by)
    out = g[cols].median().add_suffix("_median")
    out.insert(0, "n", g.size())
    out = out[out.n >= min_n].reset_index().rename(columns={by: "nilai_kelompok"})
    out.insert(0, "kelompok", by)
    out.insert(0, "dataset", dataset)
    return out
