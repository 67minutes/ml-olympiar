"""ioGAS Stage 3 (AGENTS.md §10): drillhole correlation panels and geochem-stratigraphy drawn by ioGAS itself.

    uv run python scripts/25_iogas_s3_drillhole.py            # full stage (frozen _v1 outputs)
    uv run python scripts/25_iogas_s3_drillhole.py --probe    # one panel per plot type into data/interim/iogas_s3/probe

Inputs: data/processed/iogas/RJ_DH_komposit_1m.csv (ML-4 HMM states `ML_hmm_*`, logged alteration/oxidation),
data/processed/ml4_sections.csv (holes per section A-C, along-section order). No new ML.
One .gas per colour scheme (colour attributes come from build_gas); each runs in our own -gaslink2 instance.

Outputs: outputs/figures/iogas/s3_*_v1.png; outputs/iogas_project/RJ_bor_s3_v1.gas (HMM colours) and
outputs/iogas_project/s3/RJ_bor_s3_{alterasi,oksidasi}_v1.gas; data/processed/s3_status_ringkasan_v1.csv,
s3_status_per_lubang_v1.csv. Workflow XML: iogas/workflows/s3_*.xml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import iogas_project as ip  # noqa: E402
from src import iogas_s2 as s2  # noqa: E402
from src import iogas_s3 as s3  # noqa: E402
from src import iogas_stage as st  # noqa: E402
from src.paths import FIGURES, INTERIM, PROCESSED, ROOT  # noqa: E402

PROBE = "--probe" in sys.argv
IODIR = PROCESSED / "iogas"
WORK = INTERIM / "iogas_s3"
FIG = WORK / "probe" if PROBE else FIGURES / "iogas"
PROJ = WORK / "probe" if PROBE else ROOT / "outputs" / "iogas_project"
ALT_COLOURS = {**s2.ALT_COLOURS, "Alterasi tidak dicatat (penutup/rongga)": "#bdbdbd"}
STAB = "ML_hmm_stabil"
SUMMARY_COLS = ["Au_ppm", "Ag_ppm", "Cu_ppm", "As_ppm", "S_sulfida_SCIS_pct", "CuCN_Cu_rasio"]
KEEP = (["HoleID", "From", "To", "X", "Y", "Z", "ML_hmm_nama", "ML_hmm_status", STAB, "ML_hmm_p_maks",
         "Status_Oksidasi", "Fasies_Alterasi", "Kelompok_Litologi"] + SUMMARY_COLS)
ALIASES = {"ML_hmm_nama": "Status HMM", "ML_hmm_status": "Nomor status HMM", STAB: "Stabilitas status HMM",
           "ML_hmm_p_maks": "Peluang maks status HMM", "Status_Oksidasi": "Zona oksidasi (log)",
           "Fasies_Alterasi": "Fasies alterasi (log)", "Kelompok_Litologi": "Kelompok litologi (log)",
           "CuCN_Cu_rasio": "Rasio CuCN/Cu", **s3.log10_aliases()}
EXPECTED: list[Path] = []


def export(w: ip.Workflow, fr: ip.Frame, name: str) -> None:
    p = FIG / f"s3_{name}_v1.png"
    if p.exists() and not PROBE:
        sys.exit(f"{p} exists: frozen output, write _v2 instead")
    EXPECTED.append(p)
    w.export_window(p, fr)


def panel(w: ip.Workflow, cols: list[str], holes: list[str], name: str) -> None:
    """Strip log of `cols` for `holes` (in this order, one window, a track per variable), bar traces, with the
    .gas colour attribute as a category track. Not the 'stacked' mode: that sums all variables into one bar."""
    w.select(cols)
    w.configure_downhole("HoleID", "From", "To", holes)
    fr = w.strip_log(stacked=False)
    w.trace_mode(fr, "Bar")
    export(w, fr, name)


def run(gas_in: Path, w: ip.Workflow, tag: str) -> dict:
    return st.run(gas_in, w, tag, WORK, "s3_probe" if PROBE else "s3")


def build(d: pd.DataFrame, tag: str, colour_by: str, colours: dict[str, str]) -> Path:
    order = [k for k in colours if k in set(d[colour_by])]
    assert set(d[colour_by]) <= set(order), set(d[colour_by]) - set(order)
    gas_in = WORK / f"bor_{tag}_masuk.gas"
    ip.build_gas(d, gas_in, special=ip.SpecialColumns(east="X", north="Y", elevation="Z", epsg=st.EPSG,
                                                      group="HoleID"),
                 drillhole=ip.Drillhole("HoleID", "From", "To"), aliases=ALIASES, colour_by=colour_by,
                 colours=colours, colour_order=order, source_note=f"s3 {tag}, comp_ok = Y of RJ_DH_komposit_1m.csv")
    return gas_in


def hmm_project(d: pd.DataFrame, sections: dict[str, list[str]]) -> pd.DataFrame:
    """Main stage project, coloured by HMM state: section panels, twin pads, state boxes/scatters, XYZ map."""
    gas_in = build(d, "hmm", "ML_hmm_nama", s3.state_colours(d.ML_hmm_nama))
    w = ip.Workflow("s3 status HMM bor", export_dir=FIG, aliases=ALIASES)
    w.select(["Au_ppm"])
    fmap = w.plot("Attribute Map 3D", ip.A_MAP_XYZ, ["Au_ppm"])   # exported last (map rendering race, Stage 2)
    tracks = [f"{e}_log10" for e in s3.STRIP_EL] + [STAB]
    for sec, holes in (sections.items() if not PROBE else [("B", sections["B"])]):
        panel(w, tracks, holes, f"strip_hmm_penampang_{sec}")
    for a, b in (s3.TWIN_PADS if not PROBE else s3.TWIN_PADS[:1]):
        panel(w, tracks, [a, b], f"strip_hmm_kembar_{a[-3:]}_{b[-3:]}")
    box = [f"{e}_log10" for e in s3.LOG_EL] + ["CuCN_Cu_rasio"]
    w.select(box)
    export(w, w.plot("Box Plots", ip.A_BOX_TILED, box), "box_status_hmm")
    for x, y in [("Au_ppm", "Cu_ppm"), ("Au_ppm", "As_ppm")]:
        w.select([x, y])
        fr = w.plot("XY Plot", ip.A_XY, [x, y])
        w.action("Log X axis", ip.A_LOG_X, fr)
        w.action("Log Y axis", ip.A_LOG_Y, fr)
        export(w, fr, f"xy_{y[:2]}_{x[:2]}_status_hmm")
    export(w, fmap, "peta3d_status_hmm")
    out = PROJ / ("RJ_bor_s3_probe.gas" if PROBE else "RJ_bor_s3_v1.gas")
    if out.exists() and not PROBE:
        sys.exit(f"{out} exists: frozen output, write _v2 instead")
    w.save_as(out)
    print(f"HMM project: {len(d)} composites")
    run(gas_in, w, "hmm")
    return st.check_saved(out, len(d))


def log_project(d: pd.DataFrame, sections: dict[str, list[str]], tag: str, colour_by: str,
                colours: dict[str, str], twins: bool) -> None:
    """Same section stacks coloured by a logged attribute (alteration or oxidation), for state-vs-log comparison."""
    gas_in = build(d, tag, colour_by, colours)
    w = ip.Workflow(f"s3 {tag} bor", export_dir=FIG, aliases=ALIASES)
    tracks = [f"{e}_log10" for e in s3.STRIP_EL_LOG]
    for sec, holes in sections.items():
        panel(w, tracks, holes, f"strip_{tag}_penampang_{sec}")
    for a, b in (s3.TWIN_PADS if twins else []):
        panel(w, tracks, [a, b], f"strip_{tag}_kembar_{a[-3:]}_{b[-3:]}")
    out = PROJ / "s3" / f"RJ_bor_s3_{tag}_v1.gas"
    if out.exists():
        sys.exit(f"{out} exists: frozen output, write _v2 instead")
    out.parent.mkdir(parents=True, exist_ok=True)
    w.save_as(out)
    print(f"{tag} project: {len(d)} composites")
    run(gas_in, w, tag)
    st.check_saved(out, len(d))


def main() -> None:
    for p in (FIG, PROJ, WORK):
        p.mkdir(parents=True, exist_ok=True)
    if PROBE:  # scratch only: clear the last probe so ioGAS never meets an existing file
        for f in FIG.glob("*"):
            f.unlink()
    prev = sorted((FIGURES / "iogas").glob("s[12]_*_v1.png"))
    prev_hash = {p.name: st.sha256(p) for p in prev}

    d = s3.load_composites(pd.read_csv(IODIR / "RJ_DH_komposit_1m.csv", low_memory=False))
    d = d[KEEP + [f"{e}_log10" for e in s3.LOG_EL]]
    sections = s3.section_holes(pd.read_csv(PROCESSED / "ml4_sections.csv"), sorted(d.HoleID.unique()))
    print("sections:", sections)

    saved = hmm_project(d, sections).rename(columns={v: k for k, v in ALIASES.items()})
    for c in ["ML_hmm_nama", "HoleID"]:
        saved[c] = saved[c].map(lambda v: v if pd.isna(v) else ip.gas_unescape(str(v)).strip())
    assert saved.ML_hmm_nama.value_counts().to_dict() == d.ML_hmm_nama.value_counts().to_dict(), "states changed"
    summ = s3.status_ringkasan(saved, SUMMARY_COLS)
    ref = s3.status_ringkasan(d, SUMMARY_COLS)
    assert np.allclose(summ["median"], ref["median"], rtol=1e-6, equal_nan=True), "read-back medians differ"
    per_hole = s3.status_per_lubang(saved)
    assert np.isclose(per_hole.total_m.sum(), (d.To - d.From).sum())

    if not PROBE:
        log_project(d, sections, "alterasi", "Fasies_Alterasi", ALT_COLOURS, twins=True)
        log_project(d, sections, "oksidasi", "Status_Oksidasi", st.OX_COLOURS, twins=False)
        for name, t in (("s3_status_ringkasan_v1.csv", summ), ("s3_status_per_lubang_v1.csv", per_hole)):
            p = PROCESSED / name
            if p.exists():
                sys.exit(f"{p} exists: frozen output, write _v2 instead")
            t.to_csv(p, index=False)

    missing = [p for p in EXPECTED if not p.exists() or p.stat().st_size == 0]
    assert not missing, missing
    assert {p.name: st.sha256(p) for p in prev} == prev_hash, "a Stage 1-2 figure changed"
    print(f"{len(EXPECTED)} figures; Stage 1-2 figures unchanged ({len(prev)})")
    print(summ.pivot_table(index="status_hmm", columns="kolom", values="median").round(3).to_string())
    print(per_hole.to_string(index=False))


if __name__ == "__main__":
    main()
