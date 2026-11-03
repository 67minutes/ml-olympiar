"""Deliverable 3, "Geochemistry analysis (csv format)" (brief slide 12). Plan: LOG.md, 2026-11-04 entry.

Stacks soil, rock and drill-assay samples into one table (one row per sample: keys, coordinates,
harmonised key elements with censoring flags, logged classes, ML-1/2/3/5 outputs; drill rows also
carry the ML-4 HMM state and ML-6 GP from the 1 m composite that holds the assay midpoint), and
writes descriptive statistics with thresholds per dataset × element, medians per group, and a
column dictionary. Reads the merged ioGAS files (rerun scripts/07_export.py first) and
data/processed/element_thresholds.csv; writes data/processed/geochem_analysis.csv,
geochem_statistik.csv, geochem_statistik_kelompok.csv, geochem_analysis_kolom.csv.
Run: uv run python scripts/18_geochem_analysis.py
"""
import numpy as np
import pandas as pd

from src import export, geochem, paths

IOGAS = paths.PROCESSED / "iogas"
KEYS = ["dataset", "SampleID", "HoleID", "From", "To", "X", "Y", "Z"]
ELEMENTS = ["Au_ppm", "Ag_ppm", "Cu_ppm", "As_ppm", "Pb_ppm", "Zn_ppm", "Sb_ppm", "Hg_ppm", "Mo_ppm", "Ba_ppm",
            "Fe_pct", "S_sulfida_SCIS_pct", "S_sulfida_S2_pct", "S_total_pct"]
EXTRA = ["AuCN_Au_rasio", "AgCN_Ag_rasio", "CuCN_Cu_rasio", "NAG_pH", "NAG_pH45_kgH2SO4_t"]
META = ["Prospek", "prospek_RJ", "Tahun", "Tahun_lab", "SampleType", "NS_SEL", "S_metode", "flag_elev"]
LOGGED = ["Kelompok_Litologi", "Fasies_Alterasi", "Status_Oksidasi"]
ML = ["ML_alt_prediksi", "ML_alt_p_maks", "ML_oks_prediksi", "ML_oks_p_maks", "ML_zona", "ML_zona_p_maks",
      "ML_zona_indeks", "ML_paf_set", "ML_paf_kelola", "ML_paf_uji_NAG", "ML_paf_prioritas_uji"]
COMP = {"ML_hmm_nama": "ML_hmm_nama", "ML_hmm_p_maks": "ML_hmm_p_maks", "ML_gp_mu": "ML_gp_mu_log10Au",
        "ML_gp_sd": "ML_gp_sd_log10"}
SOURCES = {"tanah": "RJ_tanah.csv", "batuan": "RJ_batuan.csv", "lubang_bor": "RJ_DH_assay.csv"}
THR_DATASET = {"bor": "lubang_bor", "batuan": "batuan", "tanah": "tanah"}
GROUPS = {"tanah": ["ML_zona"],
          "batuan": ["ML_zona", "Fasies_Alterasi", "Kelompok_Litologi"],
          "lubang_bor": ["Fasies_Alterasi", "Status_Oksidasi", "Kelompok_Litologi", "ML_hmm_nama", "ML_paf_kelola"]}
NEW_COLS = {
    "dataset": ("dataset asal: tanah, batuan atau lubang_bor", "", "deliverable 3"),
    "komposit_From": ("kedalaman atas komposit 1 m yang memuat titik tengah interval assay", "m", "Stage 6"),
    "ML_gp_mu_log10Au": ("rerata GP (kriging) log10 Au pada komposit", "log10 g/t", "ML-6"),
    "ML_gp_sd_log10": ("SD GP (kriging) log10 Au pada komposit", "log10 g/t", "ML-6"),
}
STAGE = {"ML_thr": "ML-1", "ML_alt": "ML-2", "ML_oks": "ML-2", "ML_zona": "ML-3", "ML_hmm": "ML-4",
         "ML_paf": "ML-5", "ML_gp": "ML-6"}


def keep(df: pd.DataFrame) -> list[str]:
    el = [c for e in ELEMENTS for c in (e, f"{e}_cens") if c in df]
    thr = [c for c in df if c.startswith("ML_thr_") and c.endswith("_populasi")]
    return [c for c in META + el + [c for c in EXTRA if c in df] + LOGGED + thr + ML if c in df]


def load() -> dict[str, pd.DataFrame]:
    out = {}
    for name, f in SOURCES.items():
        d = pd.read_csv(IOGAS / f, low_memory=False)
        d.insert(0, "dataset", name)
        out[name] = d
    return out


def attach_composites(a: pd.DataFrame) -> pd.DataFrame:
    c = pd.read_csv(IOGAS / "RJ_DH_komposit_1m.csv", low_memory=False)
    mid = ((a.From + a.To) / 2).to_numpy()
    j = geochem.containing_interval(a.HoleID.to_numpy(), mid, c.HoleID.to_numpy(), c.From.to_numpy(), c.To.to_numpy())
    hit = j >= 0
    a["komposit_From"] = np.where(hit, c.From.to_numpy()[np.clip(j, 0, None)], np.nan)
    for src, dst in COMP.items():
        a[dst] = np.where(hit, c[src].to_numpy()[np.clip(j, 0, None)], np.nan) if c[src].dtype != object \
            else pd.Series(c[src].to_numpy()[np.clip(j, 0, None)]).where(hit).to_numpy()
    ok_used = c.loc[j[hit], "comp_ok"].eq("Y")
    print(f"composite lookup: {hit.sum()} of {len(a)} assay midpoints inside a composite "
          f"({int(ok_used.sum())} in comp_ok); misses {int((~hit).sum())} "
          f"(NS-SEL {int(a.loc[~hit, 'NS_SEL'].eq('Y').sum())})")
    return a


def stack(src: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    for name, d in src.items():
        cols = [k for k in KEYS if k in d] + keep(d)
        p = d[cols].copy()
        if name == "lubang_bor":
            p = attach_composites(p)
        parts.append(p)
    out = pd.concat(parts, ignore_index=True)
    first = [k for k in KEYS if k in out] + [c for c in META if c in out]
    return out[first + [c for c in out if c not in first]]


def statistics(g: pd.DataFrame) -> pd.DataFrame:
    thr = pd.read_csv(paths.PROCESSED / "element_thresholds.csv")
    thr["dataset"] = thr.dataset.map(THR_DATASET)
    thr["kolom"] = thr.column.map(export.iogas_name)
    tcols = ["K", "threshold_type", "T1", "T2", "thr_gmm_main", "thr_mad", "thr_tukey", "thr_probplot_iogas", "pct_above_gmm_main", "pct_above_mad",
             "pct_above_tukey"]
    rows = []
    for name, d in g.groupby("dataset", sort=False):
        subsets = {"semua": d}
        if "prospek_RJ" in d and d.prospek_RJ.notna().any():
            subsets["RJ"] = d[d.prospek_RJ.eq("Y")]
        for sub, s in subsets.items():
            for e in ELEMENTS:
                if e not in s or s[e].notna().sum() == 0:
                    continue
                cens = s[f"{e}_cens"] if f"{e}_cens" in s else None
                rows.append({"dataset": name, "subset": sub, "kolom": e} | geochem.describe(s[e], cens))
    st = pd.DataFrame(rows).merge(thr[["dataset", "kolom"] + tcols], on=["dataset", "kolom"], how="left")
    return st


def group_table(g: pd.DataFrame) -> pd.DataFrame:
    out = []
    for name, bys in GROUPS.items():
        d = g[g.dataset.eq(name)]
        if "prospek_RJ" in d and name != "lubang_bor":
            d = d[d.prospek_RJ.eq("Y")]
        cols = [e for e in ELEMENTS if d[e].notna().any()]
        for by in bys:
            out.append(geochem.group_medians(d, name, by, cols))
    return pd.concat(out, ignore_index=True)


def dictionary(g: pd.DataFrame) -> pd.DataFrame:
    k = pd.read_csv(IOGAS / "kolom_iogas.csv").drop_duplicates("column")
    k = k.set_index("column")
    rows = []
    for c in g.columns:
        if c in NEW_COLS:
            mid, unit, stage = NEW_COLS[c]
        elif c in k.index:
            mid, unit = k.at[c, "meaning_id"], k.at[c, "unit"]
            stage = next((v for p, v in STAGE.items() if c.startswith(p)), "Stage 1-7")
        else:
            raise KeyError(f"no dictionary entry for {c}")
        rows.append({"kolom": c, "arti": mid, "satuan": "" if pd.isna(unit) else unit, "sumber": stage,
                     "terisi_tanah": int(g.loc[g.dataset.eq("tanah"), c].notna().sum()),
                     "terisi_batuan": int(g.loc[g.dataset.eq("batuan"), c].notna().sum()),
                     "terisi_lubang_bor": int(g.loc[g.dataset.eq("lubang_bor"), c].notna().sum())})
    return pd.DataFrame(rows)


def check(g: pd.DataFrame, src: dict[str, pd.DataFrame]):
    for name, d in src.items():
        part = g[g.dataset.eq(name)].reset_index(drop=True)
        assert len(part) == len(d), name
        key = ["HoleID", "From"] if name == "lubang_bor" else ["SampleID"]
        assert not part.duplicated(key).any(), f"{name}: duplicate keys"
        m = part.merge(d, on=key, how="left", suffixes=("", "_src"), validate="one_to_one")
        for c in part.columns:
            if f"{c}_src" in m:
                a, b = m[c], m[f"{c}_src"]
                if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
                    same = (a.isna() & b.isna()) | np.isclose(a, b, rtol=0, atol=0)   # ints widen to float on stacking
                else:
                    same = (a.isna() & b.isna()) | (a.astype(str) == b.astype(str))
                assert same.all(), f"{name}.{c}: {int((~same).sum())} values differ from the ioGAS file"
        for c in [c for c in part if c in d]:
            assert part[c].isna().sum() == d[c].isna().sum(), f"{name}.{c}: NaN count changed"
    print("checks: counts, unique keys, round-trip values and NaN counts equal the ioGAS files")


def main():
    src = load()
    g = stack(src)
    check(g, src)
    st = statistics(g)
    grp = group_table(g)
    dic = dictionary(g)
    g.to_csv(paths.PROCESSED / "geochem_analysis.csv", index=False)
    st.round(6).to_csv(paths.PROCESSED / "geochem_statistik.csv", index=False)
    grp.round(6).to_csv(paths.PROCESSED / "geochem_statistik_kelompok.csv", index=False)
    dic.to_csv(paths.PROCESSED / "geochem_analysis_kolom.csv", index=False)
    print(f"geochem_analysis.csv: {len(g)} rows x {g.shape[1]} cols "
          f"{g.dataset.value_counts().to_dict()}")
    print(f"geochem_statistik.csv: {len(st)} rows; kelompok: {len(grp)} rows; kolom: {len(dic)}")
    show = st[st.kolom.isin(["Au_ppm", "Cu_ppm", "As_ppm"])][["dataset", "subset", "kolom", "n_analisis",
                                                               "pct_tersensor", "P50", "P95", "max", "thr_gmm_main"]]
    print(show.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
