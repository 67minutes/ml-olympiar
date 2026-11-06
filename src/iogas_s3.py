"""Pure helpers for ioGAS Stage 3 (drillholes: correlation panels, geochem-stratigraphy); no ioGAS needed.

Used by scripts/25_iogas_s3_drillhole.py. No new ML: the ML-4 HMM states, logged alteration and logged oxidation
are inputs. Labels are ASCII/cp1252-safe because ioGAS stores data.csv in windows-1252.
"""
from __future__ import annotations

import pandas as pd

from src import iogas_stage as st
from src.geostrat import STATE_PALETTE

TWIN_PADS = [("RJDH005", "RJDH014"), ("RJDH010", "RJDH011"), ("RJDH016", "RJDH017")]
LOG_EL = ["Au", "Ag", "Cu", "As", "SCIS"]       # log10 columns (strip logs and box plots ignore log toggles)
STRIP_EL = ["Au", "Ag", "Cu", "As"]             # HMM features = strip tracks
STRIP_EL_LOG = ["Au", "Cu", "As"]               # tracks on the alteration / oxidation panels
OX_MISSING = "Tidak dicatat"
OFF_SECTION = "Lain"


def state_order(names: pd.Series) -> list[str]:
    """HMM state names ordered S1..S5 (by the number after 'S')."""
    return sorted(set(names.dropna()), key=lambda s: int(s.split()[0][1:]))


def state_colours(names: pd.Series) -> dict[str, str]:
    """ML-4's validated 5-state palette, S1 -> first colour (same as the ML-4 figures and QGIS sections)."""
    order = state_order(names)
    pal = STATE_PALETTE[len(order)]
    return dict(zip(order, pal))


def load_composites(df: pd.DataFrame) -> pd.DataFrame:
    """Usable 1 m composites (`comp_ok = Y`) with log10 columns and null logged oxidation as 'Tidak dicatat'."""
    d = df[df.comp_ok.eq("Y")].reset_index(drop=True)
    assert d.ML_hmm_nama.notna().all(), "a usable composite has no HMM state"
    d = d.copy()
    d["Status_Oksidasi"] = d.Status_Oksidasi.fillna(OX_MISSING)
    d, _, _ = st.add_log10(d, LOG_EL)
    return d


def log10_aliases() -> dict[str, str]:
    return st.add_log10(pd.DataFrame({st.element_column(e): [1.0] for e in LOG_EL}), LOG_EL)[1]


def section_holes(sections: pd.DataFrame, holes: list[str]) -> dict[str, list[str]]:
    """Holes per ML-4 section, in along-section order (`kolar_x`, as in the QGIS sections); the rest in 'Lain'."""
    out = {s: g.sort_values("kolar_x").SiteID.tolist() for s, g in sections.groupby("penampang", sort=True)}
    on = {h for hs in out.values() for h in hs}
    rest = sorted(h for h in holes if h not in on)
    if rest:
        out[OFF_SECTION] = rest
    return out


def status_ringkasan(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Per HMM state: n composites, n holes, median of each column (element units)."""
    rows = []
    for s in state_order(df.ML_hmm_nama):
        g = df[df.ML_hmm_nama.eq(s)]
        for c in columns:
            v = pd.to_numeric(g[c], errors="coerce")
            rows.append({"status_hmm": s, "kolom": c, "n_komposit": len(g), "n_lubang": g.HoleID.nunique(),
                         "n_nilai": int(v.notna().sum()), "median": v.median()})
    return pd.DataFrame(rows)


def status_per_lubang(df: pd.DataFrame) -> pd.DataFrame:
    """Metres of each HMM state per hole (composite length summed; 1 m composites)."""
    d = df.assign(m=(pd.to_numeric(df.To) - pd.to_numeric(df.From)).astype(float))
    t = d.pivot_table(index="HoleID", columns="ML_hmm_nama", values="m", aggfunc="sum", fill_value=0.0)
    t = t.reindex(columns=state_order(df.ML_hmm_nama), fill_value=0.0)
    t["total_m"] = t.sum(axis=1)
    return t.round(1).reset_index()
