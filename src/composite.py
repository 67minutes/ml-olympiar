"""1 m length-weighted downhole composites (Stage 6, AGENTS.md §5.5 and §4.2.13).

Composites are fixed [k, k+1) intervals from the collar; the last one ends at EOH. Values
are length-weighted over the sampled (not NS-SEL), non-null parts of the source assays.
"""
import numpy as np
import pandas as pd

from src import joins

COMP_LEN = 1.0
MIN_COV_M = 0.5   # an element needs at least this much covered length in a composite


def grid(collar: pd.DataFrame, step: float = COMP_LEN) -> pd.DataFrame:
    """The composite intervals of every hole, 0 to EndDepth."""
    parts = []
    for r in collar.itertuples():
        start = np.arange(0.0, r.EndDepth, step)
        parts.append(pd.DataFrame({"SiteID": r.SiteID, "DepthFrom": start,
                                   "DepthTo": np.round(np.minimum(start + step, r.EndDepth), 6)}))
    g = pd.concat(parts, ignore_index=True)
    g["comp_len"] = (g.DepthTo - g.DepthFrom).round(6)
    return g


def _parts(src: pd.DataFrame, comp: pd.DataFrame) -> pd.DataFrame:
    """Overlaps between composites (a_idx) and sampled source assays (l_idx)."""
    ov = joins.overlap_table(comp, src)
    return ov[~src.no_sample.loc[ov.l_idx].to_numpy()].reset_index(drop=True)


def _weighted(ov: pd.DataFrame, num: np.ndarray, den: np.ndarray, index) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = pd.DataFrame(num).groupby(ov.a_idx.to_numpy()).sum()
    d = pd.DataFrame(den).groupby(ov.a_idx.to_numpy()).sum()
    return n.reindex(index).fillna(0.0), d.reindex(index).fillna(0.0)


def composite(src: pd.DataFrame, comp: pd.DataFrame, cols: list[str], min_cov: float = MIN_COV_M,
              return_cov: bool = False):
    """Length-weighted mean of each column; NaN where the column covers < min_cov m."""
    ov = _parts(src, comp)
    v = src[cols].to_numpy(float)[ov.l_idx.to_numpy()]
    w = ov.ov.to_numpy()[:, None] * ~np.isnan(v)
    num, den = _weighted(ov, w * np.nan_to_num(v), w, comp.index)
    num.columns = den.columns = cols
    out = (num / den).where(den >= min_cov - 1e-9)
    return (out, den) if return_cov else out


def ratio(src: pd.DataFrame, comp: pd.DataFrame, cn: str, tot: str, defined: pd.Series,
          min_cov: float = MIN_COV_M) -> pd.Series:
    """CN-soluble / total as a ratio of length-weighted sums, over the source parts where
    the sample-level ratio is defined (a mean of ratios would be biased)."""
    ov = _parts(src, comp)
    ok = defined.astype(bool).to_numpy()[ov.l_idx.to_numpy()]
    L = ov.ov.to_numpy() * ok
    c = np.nan_to_num(src[cn].to_numpy(float)[ov.l_idx.to_numpy()])
    t = np.nan_to_num(src[tot].to_numpy(float)[ov.l_idx.to_numpy()])
    num, den = _weighted(ov, np.c_[L * c, L * t], np.c_[L, L], comp.index)
    return (num[0] / num[1]).where(den[0] >= min_cov - 1e-9)


def cens_frac(src: pd.DataFrame, comp: pd.DataFrame, col: str, cens: str) -> pd.Series:
    """Share of the analysed covered length that is censored."""
    ov = _parts(src, comp)
    li = ov.l_idx.to_numpy()
    an = src[col].notna().to_numpy()[li]
    ce = src[cens].fillna(False).astype(bool).to_numpy()[li]
    num, den = _weighted(ov, ov.ov.to_numpy() * an * ce, ov.ov.to_numpy() * an, comp.index)
    return (num[0] / den[0]).where(den[0] > 0)


def quality(src: pd.DataFrame, comp: pd.DataFrame) -> pd.DataFrame:
    """comp_cov_m, comp_nsrc, comp_src_maxlen, comp_shared_src, S_method_c, comp_ok."""
    ov = _parts(src, comp)
    li = ov.l_idx.to_numpy()
    ov = ov.assign(src_len=(src.DepthTo - src.DepthFrom).to_numpy()[li], meth=src.S_method.to_numpy()[li])
    g = ov.groupby("a_idx")
    q = pd.DataFrame(index=comp.index)
    q["comp_cov_m"] = g.ov.sum().reindex(comp.index).fillna(0.0)
    q["comp_nsrc"] = g.size().reindex(comp.index).fillna(0).astype(int)
    q["comp_src_maxlen"] = g.src_len.max().reindex(comp.index)
    # one source supplies the whole covered length and is longer than the composite, so a
    # neighbouring composite repeats its value
    top = ov.loc[g.ov.idxmax()].set_index("a_idx")
    single = (top.ov / q.comp_cov_m.loc[top.index]) >= 0.999
    shared = single & (top.src_len > comp.comp_len.loc[top.index] + 1e-9)
    q["comp_shared_src"] = shared.reindex(comp.index).fillna(False).astype(bool)
    meth = ov[ov.meth.ne("none")].groupby("a_idx").meth.agg(lambda s: s.iloc[0] if s.nunique() == 1 else "mixed")
    q["S_method_c"] = meth.reindex(comp.index).fillna("none")
    q["comp_ok"] = q.comp_cov_m >= MIN_COV_M - 1e-9
    return q
