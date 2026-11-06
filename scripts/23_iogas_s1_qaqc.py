"""ioGAS Stage 1 (AGENTS.md Â§10): QAQC, outliers and probability-plot thresholds, drawn by ioGAS itself.

    uv run python scripts/23_iogas_s1_qaqc.py --phase blind    # uncoloured log probability plots, one per element
    uv run python scripts/23_iogas_s1_qaqc.py --phase qaqc     # precision, lab-year/hole boxes, AAT (Tukey) outliers
    uv run python scripts/23_iogas_s1_qaqc.py --phase ambang   # after picks are frozen: comparison + coloured plots

Blind protocol: `blind` reads only the ioGAS CSVs (ML-1 row subsets, no ML_thr_* columns). Picks are written by
hand to data/interim/s1_probplot_picks.csv and its SHA-256 must appear in LOG.md before `ambang` runs; only
`ambang` reads the GMM thresholds. element_thresholds.csv (v1) is never modified; v2 is written next to it.

Outputs: outputs/figures/iogas/s1_*_v1.png, outputs/iogas_project/RJ_*_s1_*_v1.gas (windows kept, EPSG 32647),
data/processed/s1_aat_ringkasan_v1.csv, element_thresholds_v2.csv, s1_ambang_perbandingan_v1.csv.
Workflow XML: iogas/workflows/s1_*.xml. ioGAS logs: data/interim/iogas_s1/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import iogas_project as ip  # noqa: E402
from src import iogas_s1 as s1  # noqa: E402
from src import iogas_stage as st  # noqa: E402
from src.paths import FIGURES, INTERIM, PROCESSED, ROOT  # noqa: E402

IODIR = PROCESSED / "iogas"
FIG = FIGURES / "iogas"
PROJ = ROOT / "outputs" / "iogas_project"
WF = ROOT / "iogas" / "workflows"
WORK = INTERIM / "iogas_s1"
PICKS = INTERIM / "s1_probplot_picks.csv"
THR_V1 = PROCESSED / "element_thresholds.csv"
EPSG = 32647
OX_COLOURS = st.OX_COLOURS  # shared with Stage 3
JENIS_DUP = {"same_day_same_point": "Titik & hari sama", "resample": "Sampel ulang"}
DUP_COLOURS = {"Titik & hari sama": "#1b9e77", "Sampel ulang": "#d95f02"}
LOG_EL = ["Au", "Cu", "As"]


sha256, special, add_log10, check_saved = st.sha256, st.special, st.add_log10, st.check_saved


def load(ds: str) -> pd.DataFrame:
    stem = s1.DATASETS[ds][0]
    return s1.subset(pd.read_csv(IODIR / f"{stem}.csv", low_memory=False), ds)


def id_cols(ds: str) -> list[str]:
    return ["HoleID", "From", "To", "SampleID", "X", "Y", "Z"] if ds == "bor" else ["SampleID", "X", "Y", "Z"]


def run(gas_in: Path, w: ip.Workflow, tag: str) -> dict:
    """Open `gas_in` in our own -gaslink2 ioGAS instance, run the workflow, close the instance."""
    return st.run(gas_in, w, tag, WORK, "s1")


# ---------------------------------------------------------------- phase: blind
def phase_blind():
    for ds, (_stem, _c, _v, els) in s1.DATASETS.items():
        df = load(ds)
        cols = [s1.column(e) for e in els]
        d = df[id_cols(ds) + cols]
        assert not any(c.startswith("ML_thr") for c in d.columns)
        gas_in = ip.build_gas(d, WORK / f"{ds}_pp_masuk.gas", special=special(),
                              source_note=f"s1 blind, ML-1 subset of {s1.DATASETS[ds][0]}.csv")
        w = ip.Workflow(f"s1 plot probabilitas {ds} (buta)", export_dir=FIG)
        for el, c in zip(els, cols):
            w.select([c])
            fr = w.plot("Probability Plot", ip.A_PROB_PLOT, [c])
            w.action("Log Y axis", ip.A_LOG_Y, fr)
            w.export_window(FIG / f"s1_pp_{ds}_{el}_v1.png", fr)
        out = PROJ / f"RJ_{ds}_s1_pp_v1.gas"
        w.save_as(out)
        print(f"{ds}: {len(d)} rows, {len(els)} probability plots")
        run(gas_in, w, f"pp_{ds}")
        check_saved(out, len(d))


# ---------------------------------------------------------------- phase: qaqc
def aat_each(w: ip.Workflow, els: list[str]) -> None:
    """AAT one element at a time: with several variables selected, AAT uses only rows that have all of them
    (complete cases), which changes the fences when coverage differs (e.g. soil Ba 114 of 188 rows)."""
    for el in els:
        w.select([s1.column(el)])
        w.aat(prefix=f"AAT_{el}_", log=True, tails="both")


def _aat_summary(saved: pd.DataFrame, ds: str, els: list[str]) -> list[dict]:
    rows = []
    for el in els:
        c = s1.column(el)
        k = f"AAT_{el}_{c}-Tukey"
        lab = saved[k] if k in saved else pd.Series(dtype=str)
        a, p = s1.aat_counts(lab, c), s1.tukey_counts(saved[c], log=True)
        rows.append({"dataset": ds, "element": el, "kolom": c, "n": int(saved[c].notna().sum()),
                     **{f"iogas_{k}": v for k, v in a.items()}, **{f"python_{k}": v for k, v in p.items()},
                     "sama": a == p})
    return rows


def phase_qaqc():
    aat_rows = []
    # surface: AAT (Tukey on log10) + tiled Tukey box plots of log10 values
    for ds in ("tanah", "batuan"):
        els = s1.DATASETS[ds][3]
        df = load(ds)
        d, al, lcols = add_log10(df[id_cols(ds) + [s1.column(e) for e in els]], els)
        gas_in = ip.build_gas(d, WORK / f"{ds}_qaqc_masuk.gas", special=special(), aliases=al)
        w = ip.Workflow(f"s1 pencilan {ds}", export_dir=FIG, aliases=al)
        aat_each(w, els)
        w.select(lcols)
        fr = w.plot("Box Plots", ip.A_BOX_TILED, lcols)
        w.export_window(FIG / f"s1_box_tukey_{ds}_v1.png", fr)
        out = PROJ / f"RJ_{ds}_s1_qaqc_v1.gas"
        w.save_as(out)
        print(f"{ds} AAT + box plots")
        run(gas_in, w, f"qaqc_{ds}")
        aat_rows += _aat_summary(check_saved(out, len(d)), ds, els)

    # drillholes: precision (CN vs total), AAT, boxes by oxidation; then by lab year and by hole
    bor = load("bor")
    els = s1.DATASETS["bor"][3]
    base = bor[id_cols("bor") + ["Tahun_lab", "Status_Oksidasi"] + [s1.column(e) for e in els]
               + ["AuCN_ppm", "AgCN_ppm"]].copy()
    base["Tahun_lab"] = base.Tahun_lab.map(lambda v: "" if pd.isna(v) else str(int(v))).replace("", pd.NA)
    base["Status_Oksidasi"] = base.Status_Oksidasi.fillna("Tidak dicatat")
    d, al, lcols = add_log10(base, LOG_EL)
    al = {**al, "Status_Oksidasi": "Zona oksidasi", "Tahun_lab": "Tahun lab"}
    ox_order = [k for k in OX_COLOURS if k in set(d.Status_Oksidasi)]
    gas_in = ip.build_gas(d, WORK / "bor_qaqc_masuk.gas", special=special(), aliases=al,
                          colour_by="Status_Oksidasi", colours=OX_COLOURS, colour_order=ox_order)
    w = ip.Workflow("s1 presisi dan pencilan bor", export_dir=FIG, aliases=al)
    for el in ("Au", "Ag"):
        w.select([f"{el}_ppm", f"{el}CN_ppm"])
        fr = w.plot("XY Plot", ip.A_XY, [f"{el}_ppm", f"{el}CN_ppm"])
        w.action("Log X axis", ip.A_LOG_X, fr)
        w.action("Log Y axis", ip.A_LOG_Y, fr)
        w.export_window(FIG / f"s1_xy_{el}CN_{el}_bor_v1.png", fr)
    aat_each(w, els)
    w.select(lcols)
    fr = w.plot("Box Plots", ip.A_BOX_TILED, lcols)
    w.export_window(FIG / "s1_box_oksidasi_bor_v1.png", fr)
    out = PROJ / "RJ_bor_s1_qaqc_v1.gas"
    w.save_as(out)
    print("bor precision + AAT")
    run(gas_in, w, "qaqc_bor")
    aat_rows += _aat_summary(check_saved(out, len(d)), "bor", els)

    hole_pal = ["#1f77b4", "#aec7e8", "#ff7f0e", "#ffbb78", "#2ca02c", "#98df8a", "#d62728", "#ff9896", "#9467bd",
                "#c5b0d5", "#8c564b", "#c49c94", "#e377c2", "#f7b6d2", "#7f7f7f", "#bcbd22", "#dbdb8d", "#17becf",
                "#9edae5"]
    years = sorted(d.Tahun_lab.dropna().unique())
    yr_pal = ["#4d4d4d", "#b2182b", "#2166ac", "#1b7837", "#e08214", "#762a83"]
    holes = sorted(d.HoleID.unique())
    for tag, col, colours, title in (
            ("tahun", "Tahun_lab", dict(zip(years, yr_pal)), "Tahun lab"),
            ("lubang", "HoleID", dict(zip(holes, hole_pal)), "Lubang bor")):
        gas_in = ip.build_gas(d, WORK / f"bor_{tag}_masuk.gas", special=special(), aliases=al, colour_by=col,
                              colours=colours, colour_order=list(colours), colour_title=title)
        w = ip.Workflow(f"s1 kotak per {title.lower()}", export_dir=FIG, aliases=al)
        w.select(lcols)
        fr = w.plot("Box Plots", ip.A_BOX_TILED, lcols)
        w.export_window(FIG / f"s1_box_{tag}_bor_v1.png", fr)
        out = PROJ / f"RJ_bor_s1_{tag}_v1.gas"
        w.save_as(out)
        print(f"bor boxes by {col}")
        run(gas_in, w, f"{tag}_bor")
        check_saved(out, len(d))

    # rock field duplicates (samples sharing XY), all rows as in qaqc_precision.csv
    rock = pd.read_csv(IODIR / "RJ_batuan.csv", low_memory=False)
    pairs = s1.duplicate_pairs(rock, ["Au", "Cu", "As"])
    pairs["Jenis"] = pairs.Jenis.map(JENIS_DUP).fillna(pairs.Jenis)
    pairs["Z"] = np.nan
    al = {f"{e}_{i}": f"{e} sampel {i} (ppm)" for e in ("Au", "Cu", "As") for i in (1, 2)}
    al["Jenis"] = "Jenis duplikat"
    gas_in = ip.build_gas(pairs, WORK / "batuan_duplikat_masuk.gas", special=special("Pasangan"), aliases=al,
                          colour_by="Jenis", colours=DUP_COLOURS,
                          colour_order=[k for k in DUP_COLOURS if k in set(pairs.Jenis)])
    w = ip.Workflow("s1 duplikat lapangan batuan", export_dir=FIG, aliases=al)
    for el in ("Au", "Cu"):
        w.select([f"{el}_1", f"{el}_2"])
        fr = w.plot("XY Plot", ip.A_XY, [f"{el}_1", f"{el}_2"])
        w.action("Log X axis", ip.A_LOG_X, fr)
        w.action("Log Y axis", ip.A_LOG_Y, fr)
        w.export_window(FIG / f"s1_xy_duplikat_{el}_batuan_v1.png", fr)
    out = PROJ / "RJ_batuan_s1_duplikat_v1.gas"
    w.save_as(out)
    print(f"rock duplicates: {len(pairs)} pairs")
    run(gas_in, w, "duplikat_batuan")
    check_saved(out, len(pairs))

    aat = pd.DataFrame(aat_rows)
    aat.to_csv(PROCESSED / "s1_aat_ringkasan_v1.csv", index=False)
    print(aat.to_string(index=False))
    if not aat.sama.all():
        print("WARNING: ioGAS AAT and Python Tukey counts differ for:",
              aat.loc[~aat.sama, ["dataset", "element"]].values.tolist())


# ---------------------------------------------------------------- phase: ambang
def phase_ambang():
    if not PICKS.exists():
        sys.exit(f"{PICKS} missing: pick thresholds from the blind plots first")
    h = sha256(PICKS)
    if h not in (ROOT / "LOG.md").read_text(encoding="utf-8"):
        sys.exit(f"picks SHA-256 {h} not in LOG.md: log the frozen picks before comparing")
    h_thr = sha256(THR_V1)
    picks = pd.read_csv(PICKS)
    need = {(ds, e) for ds, v in s1.DATASETS.items() for e in v[3]}
    assert set(zip(picks.dataset, picks.element)) == need, "picks must cover exactly the 22 fitted elements"
    data = {ds: load(ds) for ds in s1.DATASETS}

    thr = pd.read_csv(THR_V1)
    comp = s1.compare_thresholds(thr, picks, data)
    comp.to_csv(PROCESSED / "s1_ambang_perbandingan_v1.csv", index=False)
    v2 = thr.copy()
    key = picks.set_index(["dataset", "element"])
    idx = list(zip(v2.dataset, v2.element))
    v2["thr_probplot_iogas"] = [key.pick1.get(k, np.nan) for k in idx]
    v2.insert(v2.columns.get_loc("thr_probplot_iogas") + 1, "thr_probplot_iogas_2",
              [key.pick2.get(k, np.nan) for k in idx])
    v2.insert(v2.columns.get_loc("pct_above_tukey") + 1, "pct_above_probplot",
              [s1.pct_above(data[ds][s1.column(e)], key.pick1.get((ds, e), np.nan)) if ds in data else np.nan
               for ds, e in idx])
    v2.to_csv(PROCESSED / "element_thresholds_v2.csv", index=False)
    print(comp[["dataset", "element", "pp_ambang_1", "pp_ambang_2", "gmm_utama", "pp1_T_terdekat",
                "pp1_kesesuaian_T", "pp1_kesesuaian_gmm_utama"]].to_string(index=False))

    for ds, (_s, _c, _v, els) in s1.DATASETS.items():
        df = data[ds]
        d = df[id_cols(ds) + [s1.column(e) for e in els]].copy()
        for el in els:
            p = key.loc[(ds, el)]
            d[f"Kelas_{el}_pp"] = s1.classify(d[s1.column(el)], p.pick1, p.pick2)
        for el in els:  # one .gas per colour scheme (colour attributes come from build_gas)
            kc = f"Kelas_{el}_pp"
            order = [k for k in s1.KELAS if k in set(d[kc].dropna())]
            final = el == "Au"
            gas_in = ip.build_gas(d, WORK / f"{ds}_kelas_{el}_masuk.gas", special=special(), colour_by=kc,
                                  colours=s1.KELAS_COLOURS, colour_order=order,
                                  colour_title=f"Kelas ambang {el} (plot probabilitas)")
            w = ip.Workflow(f"s1 ambang {ds} {el}", export_dir=FIG)
            c = s1.column(el)
            w.select([c])
            fr = w.plot("Probability Plot", ip.A_PROB_PLOT, [c])
            w.action("Log Y axis", ip.A_LOG_Y, fr)
            w.export_window(FIG / f"s1_pp_kelas_{ds}_{el}_v1.png", fr)
            out = PROJ / (f"RJ_{ds}_s1_v1.gas" if final else f"s1_kelas/RJ_{ds}_s1_kelas_{el}_v1.gas")
            out.parent.mkdir(parents=True, exist_ok=True)
            w.save_as(out)
            run(gas_in, w, f"kelas_{ds}_{el}")
            check_saved(out, len(d))
    assert sha256(THR_V1) == h_thr, "element_thresholds.csv (v1) changed"
    print("element_thresholds.csv unchanged; v2 + comparison written")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", required=True, choices=["blind", "qaqc", "ambang"])
    a = ap.parse_args()
    for p in (FIG, PROJ, WF, WORK):
        p.mkdir(parents=True, exist_ok=True)
    {"blind": phase_blind, "qaqc": phase_qaqc, "ambang": phase_ambang}[a.phase]()
