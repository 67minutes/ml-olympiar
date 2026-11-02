"""Attach downhole logs to assay intervals (Stage 5, AGENTS.md §5.4).

Rule: an assay takes the log interval that contains its midpoint, [DepthFrom, DepthTo),
so a midpoint exactly on a boundary takes the deeper interval. Join-quality columns
record how well that single label describes the assay.
"""
import numpy as np
import pandas as pd

UNLOGGED_MINERAL = "um"


def overlap_table(assay: pd.DataFrame, log: pd.DataFrame) -> pd.DataFrame:
    """Every (assay row, log row) pair in the same hole with a positive overlap (m)."""
    a = assay[["SiteID", "DepthFrom", "DepthTo"]].rename_axis("a_idx").reset_index()
    b = log[["SiteID", "DepthFrom", "DepthTo"]].rename_axis("l_idx").reset_index()
    m = a.merge(b, on="SiteID", suffixes=("", "_l"))
    m["ov"] = np.minimum(m.DepthTo, m.DepthTo_l) - np.maximum(m.DepthFrom, m.DepthFrom_l)
    return m.loc[m.ov > 1e-9, ["a_idx", "l_idx", "ov"]].reset_index(drop=True)


def midpoint_index(assay: pd.DataFrame, log: pd.DataFrame) -> pd.Series:
    """Index of the log row containing each assay midpoint (NA where none)."""
    a = assay[["SiteID"]].assign(mid=(assay.DepthFrom + assay.DepthTo) / 2).rename_axis("a_idx").reset_index()
    b = log[["SiteID", "DepthFrom", "DepthTo"]].rename_axis("l_idx").reset_index()
    m = a.merge(b, on="SiteID")
    m = m[(m.DepthFrom <= m.mid) & (m.mid < m.DepthTo)]
    assert m.a_idx.is_unique, "a midpoint falls in more than one log interval (overlapping log)"
    return m.set_index("a_idx").l_idx.reindex(assay.index).astype("Int64")


def midpoint_join(assay: pd.DataFrame, log: pd.DataFrame, cols: list[str], prefix: str) -> pd.DataFrame:
    """Log columns at each assay midpoint, plus <prefix>from/to/frac/missing."""
    idx = midpoint_index(assay, log)
    hit = idx.notna()
    out = pd.DataFrame(index=assay.index)
    src = log.loc[idx[hit].astype(int)]
    for c in cols:
        out[c] = pd.Series(src[c].to_numpy(), index=idx[hit].index).reindex(assay.index)
    out[f"{prefix}from"] = pd.Series(src.DepthFrom.to_numpy(), index=idx[hit].index).reindex(assay.index)
    out[f"{prefix}to"] = pd.Series(src.DepthTo.to_numpy(), index=idx[hit].index).reindex(assay.index)
    inside = np.minimum(out[f"{prefix}to"], assay.DepthTo) - np.maximum(out[f"{prefix}from"], assay.DepthFrom)
    out[f"{prefix}frac"] = inside / (assay.DepthTo - assay.DepthFrom)
    out[f"{prefix}missing"] = ~hit
    return out


def mixed_labels(assay: pd.DataFrame, log: pd.DataFrame, key: str, ov: pd.DataFrame) -> pd.Series:
    """True where the assay overlaps log intervals with more than one distinct `key`
    label (a null label counts as its own value)."""
    lab = log[key].astype(object).where(log[key].notna(), "<NA>")
    n = ov.assign(lab=lab.loc[ov.l_idx].to_numpy()).groupby("a_idx").lab.nunique()
    return n.reindex(assay.index).fillna(0).gt(1)


def length_weighted(assay: pd.DataFrame, log: pd.DataFrame, col: str, ov: pd.DataFrame) -> pd.Series:
    """Overlap-weighted mean of a numeric log column over every interval the assay
    touches; unlogged or null parts carry no weight."""
    v = ov.assign(val=log[col].loc[ov.l_idx].to_numpy()).dropna(subset=["val"])
    g = v.assign(w=v.ov * v.val).groupby("a_idx")
    return (g.w.sum() / g.ov.sum()).reindex(assay.index)


def mask_unlogged(m: pd.DataFrame, missing: pd.Series, flags: list[str]) -> pd.DataFrame:
    """Mineral presence flags mean nothing where no mineral was logged (`um` or no
    interval): set them to NA rather than False, and add `min_logged`."""
    m = m.copy()
    logged = ~(missing.to_numpy() | m.DomMin1_h.eq(UNLOGGED_MINERAL).to_numpy())
    m["min_logged"] = logged
    for f in flags:
        m[f] = m[f].astype("boolean").where(logged)
    return m
