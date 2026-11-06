"""Pure helpers for ioGAS Stage 1 (QAQC & thresholds); no ioGAS needed. Used by scripts/23_iogas_s1_qaqc.py.

Blindness rule (AGENTS.md §6 task 1): nothing here that runs before the picks are frozen reads GMM values.
`compare_thresholds` is only called by the `ambang` phase, after the picks file is hashed in LOG.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# dataset -> (ioGAS CSV stem, subset column, subset value, elements with an ML-1 fit)
DATASETS = {
    "tanah": ("RJ_tanah", "prospek_RJ", "Y", ["Au", "Ag", "Cu", "As", "Ba", "Hg", "Pb", "Sb", "W", "Zn"]),
    "batuan": ("RJ_batuan", "prospek_RJ", "Y", ["Au", "Cu", "As", "Hg", "Pb", "Sb", "Zn"]),
    "bor": ("RJ_DH_assay", "NS_SEL", "N", ["Au", "Ag", "Cu", "As", "SCIS"]),
}
KELAS = ["Anomali kuat", "Anomali lemah", "Latar"]
KELAS_COLOURS = {"Latar": "#4575b4", "Anomali lemah": "#fdae61", "Anomali kuat": "#d73027"}


def column(element: str) -> str:
    """ioGAS CSV column for an ML-1 element name."""
    return "S_sulfida_SCIS_pct" if element == "SCIS" else f"{element}_ppm"


def subset(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    """Rows used by ML-1 (`08_ml1_thresholds.py`): Ramba Joring surface samples / sampled drill intervals."""
    _, col, val, _ = DATASETS[dataset]
    return df[df[col].eq(val)].reset_index(drop=True)


def tukey_counts(values: pd.Series, log: bool = True) -> dict[str, int]:
    """Tukey fence counts (inner 1.5 IQR, outer 3 IQR) with linear-interpolated quartiles."""
    v = values.dropna()
    v = np.log10(v[v > 0]) if log else v
    q1, q3 = v.quantile([0.25, 0.75])
    iqr = q3 - q1
    return {"atas": int((v > q3 + 1.5 * iqr).sum()), "atas_jauh": int((v > q3 + 3 * iqr).sum()),
            "bawah": int((v < q1 - 1.5 * iqr).sum()), "bawah_jauh": int((v < q1 - 3 * iqr).sum())}


def aat_counts(labels: pd.Series, col: str) -> dict[str, int]:
    """Count ioGAS AAT labels for one variable: '+col' high, '-col' low, trailing '*' = far outlier.

    Labels are read from a saved .gas, so they may still carry ioGAS escaping ('_u' for '_'): unescape first.
    """
    from src.iogas_project import gas_unescape

    s = labels.dropna().astype(str).str.strip().map(gas_unescape)
    hi, lo = s[~s.str.startswith("-")], s[s.str.startswith("-")]
    assert (set(hi.str.lstrip("+").str.rstrip("*")) <= {col}
            and set(lo.str.lstrip("-").str.rstrip("*")) <= {col}), s.unique()
    return {"atas": len(hi), "atas_jauh": int(hi.str.endswith("*").sum()),
            "bawah": len(lo), "bawah_jauh": int(lo.str.endswith("*").sum())}


def duplicate_pairs(df: pd.DataFrame, elements: list[str]) -> pd.DataFrame:
    """Rock samples sharing XY (`dupxy_group`): first sample (by SampleID) vs each other one, one row per pair."""
    rows = []
    d = df[df.dupxy_group.notna()].sort_values(["dupxy_group", "SampleID"], kind="stable")
    for g, grp in d.groupby("dupxy_group", sort=True):
        first = grp.iloc[0]
        for _, other in grp.iloc[1:].iterrows():
            r = {"Pasangan": f"G{int(g)}-{other.SampleID}", "Grup": int(g), "Sampel_1": first.SampleID,
                 "Sampel_2": other.SampleID, "Jenis": other.dupxy_type, "X": first.X, "Y": first.Y}
            for el in elements:
                r[f"{el}_1"], r[f"{el}_2"] = first[f"{el}_ppm"], other[f"{el}_ppm"]
            rows.append(r)
    return pd.DataFrame(rows)


def classify(values: pd.Series, pick1: float, pick2: float | None = None) -> pd.Series:
    """Latar < pick1 <= Anomali lemah < pick2 <= Anomali kuat; one pick -> Latar / Anomali kuat. NaN stays NaN."""
    out = pd.Series(pd.NA, index=values.index, dtype="string")
    v = values
    out[v < pick1] = "Latar"
    if pick2 is None or pd.isna(pick2):
        out[v >= pick1] = "Anomali kuat"
    else:
        if not pick2 > pick1:
            raise ValueError(f"pick2 {pick2} must exceed pick1 {pick1}")
        out[(v >= pick1) & (v < pick2)] = "Anomali lemah"
        out[v >= pick2] = "Anomali kuat"
    return out


def pct_above(values: pd.Series, thr: float) -> float:
    v = values.dropna()
    return float("nan") if pd.isna(thr) or v.empty else round(100 * float((v > thr).mean()), 1)


def _agreement(pick: float, ref: float, lo: float, hi: float) -> str:
    if pd.isna(pick) or pd.isna(ref):
        return "tidak ada"
    if pd.notna(lo) and pd.notna(hi) and lo <= pick <= hi:
        return "dalam CI bootstrap"
    return "dekat (<= 2x)" if abs(np.log10(pick / ref)) <= np.log10(2) else "berbeda (> 2x)"


def compare_thresholds(thr: pd.DataFrame, picks: pd.DataFrame, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per element: probability-plot picks vs GMM (main and nearest T_k with its bootstrap CI), MAD and Tukey.

    `data[dataset]` is the ML-1 subset table with ioGAS column names. No ranking of methods: agreement only.
    """
    rows = []
    t = thr.set_index(["dataset", "element"])
    for p in picks.itertuples(index=False):
        r = t.loc[(p.dataset, p.element)]
        v = data[p.dataset][column(p.element)]
        out = {"dataset": p.dataset, "element": p.element, "kolom": column(p.element), "n": int(v.notna().sum()),
               "pp_ambang_1": p.pick1, "pp_ambang_2": p.pick2, "pp_keyakinan": p.confidence,
               "gmm_utama": r.thr_gmm_main, "gmm_K": r.K, "mad": r.thr_mad, "tukey": r.thr_tukey}
        for i, pick in ((1, p.pick1), (2, p.pick2)):
            ts = [(k, r[f"T{k}"], r[f"T{k}_ci05"], r[f"T{k}_ci95"]) for k in range(1, 5) if pd.notna(r[f"T{k}"])]
            if pd.isna(pick) or not ts:
                out.update({f"pp{i}_T_terdekat": pd.NA, f"pp{i}_T_nilai": np.nan, f"pp{i}_T_ci05": np.nan,
                            f"pp{i}_T_ci95": np.nan, f"pp{i}_log10_beda_T": np.nan,
                            f"pp{i}_kesesuaian_T": "tidak ada"})
                continue
            k, tv, lo, hi = min(ts, key=lambda x: abs(np.log10(pick / x[1])))
            out.update({f"pp{i}_T_terdekat": f"T{k}", f"pp{i}_T_nilai": tv, f"pp{i}_T_ci05": lo,
                        f"pp{i}_T_ci95": hi, f"pp{i}_log10_beda_T": round(float(np.log10(pick / tv)), 3),
                        f"pp{i}_kesesuaian_T": _agreement(pick, tv, lo, hi)})
        out["pp1_log10_beda_gmm_utama"] = (round(float(np.log10(p.pick1 / r.thr_gmm_main)), 3)
                                           if pd.notna(r.thr_gmm_main) else np.nan)
        out["pp1_kesesuaian_gmm_utama"] = _agreement(p.pick1, r.thr_gmm_main, np.nan, np.nan)
        for name, val in (("pp1", p.pick1), ("pp2", p.pick2), ("gmm_utama", r.thr_gmm_main),
                          ("mad", r.thr_mad), ("tukey", r.thr_tukey)):
            out[f"pct_di_atas_{name}"] = pct_above(v, val)
        rows.append(out)
    return pd.DataFrame(rows)
