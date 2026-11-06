"""Pure helpers for ioGAS Stage 2 (surface: soil, rock, zonation); no ioGAS needed.

Used by scripts/24_iogas_s2_surface.py. No new ML: ML-3 zones and Stage 1 threshold classes are inputs.
Labels are ASCII/cp1252-safe because ioGAS stores data.csv in windows-1252.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from src import iogas_s1 as s1
from src import iogas_stage as st
from src.paths import PROCESSED

ZONES = ["Tinggi", "Sedang", "Rendah"]
# ML_zona_p_maks bins: lower edges inclusive; < 0.5 is ML-3's "ambigu" rule
KEYAKINAN = [("Tinggi (>= 0.9)", 0.9), ("Sedang (0.7-0.9)", 0.7), ("Rendah (0.5-0.7)", 0.5), ("Ambigu (< 0.5)", 0.0)]
KEYAKINAN_COLOURS = {"Tinggi (>= 0.9)": "#1a9850", "Sedang (0.7-0.9)": "#a6d96a",
                     "Rendah (0.5-0.7)": "#fdae61", "Ambigu (< 0.5)": "#d73027"}
JENIS = {"Y": "Bongkah lepas (float)", "N": "Singkapan"}
ALT_COLOURS = {"Silika": "#7b3294", "Argilik lanjut": "#c2a5cf", "Argilik": "#f4a582", "Propilitik": "#1b7837"}


def keyakinan_zona(p_maks: pd.Series) -> pd.Series:
    """Confidence class of the most probable ML-3 zone; NaN stays NaN."""
    out = pd.Series(pd.NA, index=p_maks.index, dtype="string")
    for label, lo in reversed(KEYAKINAN):  # highest bin written last wins
        out[p_maks >= lo] = label
    return out


def jenis_sampel(float_flag: pd.Series) -> pd.Series:
    """Rock `ML_zona_float` Y/N -> float vs outcrop label; anything else -> NaN."""
    return float_flag.map(JENIS).astype("string")


def cramers_v(table: pd.DataFrame) -> float:
    """Cramér's V of a contingency table (no continuity correction); NaN if a margin has < 2 levels."""
    t = table.loc[table.sum(axis=1) > 0, table.sum(axis=0) > 0]
    if min(t.shape) < 2:
        return float("nan")
    chi2 = chi2_contingency(t.to_numpy(), correction=False)[0]
    return float(np.sqrt(chi2 / (t.to_numpy().sum() * (min(t.shape) - 1))))


def zona_vs_kelas(df: pd.DataFrame, dataset: str, element: str, kelas_col: str,
                  kelas_order: list[str]) -> pd.DataFrame:
    """Long table: zone × threshold class counts and % of the zone, plus Cramér's V (same for all rows)."""
    d = df[df.ML_zona.notna() & df[kelas_col].notna()]
    t = pd.crosstab(d.ML_zona, d[kelas_col]).reindex(index=ZONES, columns=kelas_order, fill_value=0)
    v = cramers_v(t)
    rows = []
    for z in ZONES:
        nz = int(t.loc[z].sum())
        for k in kelas_order:
            n = int(t.loc[z, k])
            rows.append({"dataset": dataset, "element": element, "zona": z, "kelas_ambang": k, "n": n,
                         "pct_zona": round(100 * n / nz, 1) if nz else np.nan, "n_zona": nz,
                         "n_total": int(t.to_numpy().sum()), "cramers_v": round(v, 3)})
    return pd.DataFrame(rows)


def zona_ringkasan(df: pd.DataFrame, dataset: str, columns: list[str]) -> pd.DataFrame:
    """n and median per zone for each column (values as plotted; NaN = not analysed is skipped)."""
    rows = []
    for c in columns:
        for z in ZONES:
            v = df.loc[df.ML_zona.eq(z), c].dropna()
            rows.append({"dataset": dataset, "kolom": c, "zona": z, "n": len(v),
                         "median": float(v.median()) if len(v) else np.nan,
                         "p25": float(v.quantile(0.25)) if len(v) else np.nan,
                         "p75": float(v.quantile(0.75)) if len(v) else np.nan})
    return pd.DataFrame(rows)


# ---- surface loading (moved unchanged from scripts/24_iogas_s2_surface.py; reused by Stage 5)
BOX_EL = {"tanah": ["Au", "As", "Pb", "Sb", "Hg", "Cu", "Zn"], "batuan": ["Au", "Cu", "As", "Sb", "Hg", "Pb", "Zn"]}
XY_PAIRS = {"tanah": [("Au", "As"), ("Au", "Pb")], "batuan": [("Au", "As"), ("Au", "Cu")]}
KELAS_EL = {"tanah": ["Au", "As"], "batuan": ["Au", "As"]}
BASE_AL = {"ML_zona": "Zona ML", "Keyakinan_zona": "Keyakinan zona", "Jenis_sampel": "Jenis sampel",
           "Fasies_Alterasi": "Fasies alterasi", "Posisi_RJ": "Posisi terhadap RJ"}


def kelas_alias(el: str) -> str:
    return f"Kelas ambang {el}"


def load_surface(ds: str, picks: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str], dict[str, list[str]]]:
    """RJ subset with log10 columns, threshold classes, zone confidence (and rock sample type)."""
    df = s1.subset(pd.read_csv(PROCESSED / "iogas" / f"{s1.DATASETS[ds][0]}.csv", low_memory=False), ds)
    key = picks.set_index(["dataset", "element"])
    for el in KELAS_EL[ds]:
        p = key.loc[(ds, el)]
        df[f"Kelas_{el}_pp"] = s1.classify(df[st.element_column(el)], p.pick1, p.pick2)
    df["Keyakinan_zona"] = keyakinan_zona(df.ML_zona_p_maks)
    if ds == "batuan":
        df["Jenis_sampel"] = jenis_sampel(df.ML_zona_float)
    els = sorted({e for e in BOX_EL[ds]} | {e for pr in XY_PAIRS[ds] for e in pr})
    keep = (["SampleID", "X", "Y", "Z", "ML_zona", "ML_zona_p_maks", "Keyakinan_zona"]
            + [f"Kelas_{el}_pp" for el in KELAS_EL[ds]]
            + (["Jenis_sampel", "Fasies_Alterasi", "Kelompok_Litologi", "ML_alt_prediksi"] if ds == "batuan" else [])
            + [st.element_column(e) for e in els])
    d, al, _ = st.add_log10(df[keep], els)
    al = {**BASE_AL, **al, **{f"Kelas_{el}_pp": kelas_alias(el) for el in KELAS_EL[ds]}}
    al = {k: v for k, v in al.items() if k in d.columns}
    lcols = {"box": [f"{e}_log10" for e in BOX_EL[ds]]}
    return d, al, lcols
