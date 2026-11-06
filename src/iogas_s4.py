"""Pure helpers for ioGAS Stage 4 (environmental: NAG, PAF/NAF, AMD elements); no ioGAS needed.

Used by scripts/26_iogas_s4_environmental.py. No new ML: ML-5 outputs (`ML_paf_*`), the RJDH012 NAG labels and
logged oxidation are inputs. SCIS and S2 sulfur stay in separate columns (AGENTS §4.2.10). Labels are
ASCII/cp1252-safe because ioGAS stores data.csv in windows-1252.
"""
from __future__ import annotations

import pandas as pd

from src import iogas_stage as st

NAG_HOLE = "RJDH012"
NO_NAG = "Tanpa uji NAG"
NO_TEST = "Tidak perlu uji"
NAG_CLASSES = ["PAF-HC", "PAF-LC", "NAF"]
NAG_COLOURS = {**{k: st.PAF_COLOURS[k] for k in NAG_CLASSES}, NO_NAG: "#bdbdbd"}
KELOLA_COLOURS = {k: st.PAF_COLOURS[k] for k in NAG_CLASSES}
KELAS_COLOURS = {k: st.PAF_COLOURS[k] for k in ["PAF-HC", "PAF-LC", "ambigu"]}
PRIORITY_COLOURS = {"1_HC_tidak_pasti": "#b2182b", "2_NAF_atau_LC": "#f4a582", "3_luar_domain": "#762a83",
                    NO_TEST: "#d9d9d9"}
OX_SHAPES = {"Oksida": 0, "Transisi": 1, "Sulfida": 2, "Tidak dicatat": 10}  # filled circle/square/triangle, open

# log10 columns (strip logs and box plots ignore log toggles)
RJ12_LOG = ["Stot", "SCIS", "NAGkap", "Fe", "As", "Cu", "Zn", "Pb", "Cd", "Mn", "Sb"]
RJ12_BOX = ["Stot", "SCIS", "Fe", "As", "Cu", "Zn", "Pb", "Cd", "Mn", "Sb"]
DH_LOG = ["SCIS", "S2", "Cu", "As", "Zn", "Pb"]
DH_STRIP = ["SCIS", "S2", "Cu", "As"]
SUMMARY_COLS = ["NAG_pH", "NAG_pH45_kgH2SO4_t", "S_total_pct", "S_sulfida_SCIS_pct", "Fe_pct", "Ca_pct",
                "As_ppm", "Cu_ppm", "Zn_ppm", "Pb_ppm", "Cd_ppm", "Mn_ppm", "Ni_ppm", "Co_ppm", "Sb_ppm"]


def _ox(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["Status_Oksidasi"] = d.Status_Oksidasi.fillna("Tidak dicatat")
    return d


def load_rjdh012(assay: pd.DataFrame) -> pd.DataFrame:
    """RJDH012 rows (the only NAG hole): NAG label ('Tanpa uji NAG' if untested), `S_pct` = `S_total_pct` for the
    built-in Halley diagrams (they need an element-named S column), log10 columns."""
    d = _ox(assay[assay.HoleID.eq(NAG_HOLE)].reset_index(drop=True))
    d["Kelas_NAG"] = d.ML_paf_label.fillna(NO_NAG)
    d["S_pct"] = d.S_total_pct
    d, _, _ = st.add_log10(d, RJ12_LOG)
    return d


def load_assays(assay: pd.DataFrame) -> pd.DataFrame:
    """Sampled assay intervals (ML-5 management class present; NS-SEL rows have none), log10 columns,
    NAG priority with 'Tidak perlu uji' for runs not on the NAG-testing list."""
    d = _ox(assay[assay.ML_paf_kelola.notna()].reset_index(drop=True))
    d["Prioritas_uji_NAG"] = d.ML_paf_prioritas_uji.fillna(NO_TEST)
    d, _, _ = st.add_log10(d, DH_LOG)
    return d


def log10_aliases(elements: list[str]) -> dict[str, str]:
    return st.add_log10(pd.DataFrame({st.element_column(e): [1.0] for e in elements}), elements)[1]


def ringkasan_nag(d: pd.DataFrame, columns: list[str] = SUMMARY_COLS) -> pd.DataFrame:
    """Per NAG class x logged oxidation (and per class over all zones): n and median of each column."""
    rows = []
    for (k, ox), g in pd.concat([d, d.assign(Status_Oksidasi="Semua")]).groupby(["Kelas_NAG", "Status_Oksidasi"]):
        r = {"kelas_nag": k, "zona_oksidasi": ox, "n": len(g)}
        for c in columns:
            r[f"median_{c}"] = pd.to_numeric(g[c], errors="coerce").median()
        rows.append(r)
    return pd.DataFrame(rows)


def kelola_per_lubang(d: pd.DataFrame) -> pd.DataFrame:
    """Metres per management class and per NAG-testing priority, per hole."""
    d = d.assign(m=(pd.to_numeric(d.To) - pd.to_numeric(d.From)).astype(float))
    a = d.pivot_table(index="HoleID", columns="ML_paf_kelola", values="m", aggfunc="sum", fill_value=0.0)
    a = a.reindex(columns=NAG_CLASSES, fill_value=0.0).add_prefix("m_kelola_")
    b = d.pivot_table(index="HoleID", columns="Prioritas_uji_NAG", values="m", aggfunc="sum", fill_value=0.0)
    b = b.reindex(columns=list(PRIORITY_COLOURS), fill_value=0.0).add_prefix("m_uji_")
    t = a.join(b)
    t["total_m"] = a.sum(axis=1)
    return t.round(1).reset_index()
