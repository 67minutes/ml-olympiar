"""ioGAS Stage 4 (AGENTS.md §10): environmental figures (NAG, PAF/NAF, AMD elements) drawn by ioGAS itself.

    uv run python scripts/26_iogas_s4_environmental.py            # full stage (frozen _v1 outputs)
    uv run python scripts/26_iogas_s4_environmental.py --probe    # one figure per plot type, data/interim/iogas_s4/probe

Inputs: data/processed/iogas/RJ_DH_assay.csv (ML-5 `ML_paf_*`, RJDH012 NAG, logged oxidation),
data/processed/ml4_sections.csv (holes per section, as Stage 3). No new ML.
One .gas per colour scheme (colour attributes come from build_gas); each runs in our own -gaslink2 instance.

Outputs: outputs/figures/iogas/s4_*_v1.png; outputs/iogas_project/RJ_RJDH012_s4_v1.gas (NAG class),
RJ_DH_s4_kelola_v1.gas (management class) and outputs/iogas_project/s4/*.gas (oxidation, conformal class, NAG
priority); data/processed/s4_kelas_nag_ringkasan_v1.csv, s4_kelola_per_lubang_v1.csv. Workflow XML:
iogas/workflows/s4_*.xml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import iogas_project as ip  # noqa: E402
from src import iogas_s3 as s3  # noqa: E402
from src import iogas_s4 as s4  # noqa: E402
from src import iogas_stage as st  # noqa: E402
from src.paths import FIGURES, INTERIM, PROCESSED, ROOT  # noqa: E402

PROBE = "--probe" in sys.argv
IODIR = PROCESSED / "iogas"
WORK = INTERIM / "iogas_s4"
FIG = WORK / "probe" if PROBE else FIGURES / "iogas"
PROJ = WORK / "probe" if PROBE else ROOT / "outputs" / "iogas_project"
HALLEY = "Exploration/Porphyry Cu Exploration/Scott Halley/"
HALLEY_FES = HALLEY + "Fe vs S with Pyrite Line.xml"
HALLEY_CAFES = HALLEY + "Ca-Fe-S Ternary Plot.xml"

RJ12_KEEP = (["SampleID", "HoleID", "From", "To", "X", "Y", "Z", "Kelas_NAG", "Status_Oksidasi", "Fasies_Alterasi",
              "ML_paf_kelola", "S_pct"] + s4.SUMMARY_COLS)
DH_KEEP = ["SampleID", "HoleID", "From", "To", "X", "Y", "Z", "ML_paf_kelola", "ML_paf_kelas", "ML_paf_set",
           "ML_paf_n_set", "ML_paf_tier", "Prioritas_uji_NAG", "Status_Oksidasi", "Fasies_Alterasi", "S_metode",
           "S_sulfida_SCIS_pct", "S_sulfida_S2_pct", "Cu_ppm", "As_ppm", "Zn_ppm", "Pb_ppm"]
ALIASES = {"Kelas_NAG": "Kelas NAG (uji)", "ML_paf_kelola": "Kelas pengelolaan PAF/NAF",
           "ML_paf_kelas": "Kelas konformal", "ML_paf_set": "Himpunan konformal",
           "ML_paf_n_set": "Ukuran himpunan konformal", "ML_paf_tier": "Tingkat domain ML-5",
           "Prioritas_uji_NAG": "Prioritas uji NAG", "Status_Oksidasi": "Zona oksidasi (log)",
           "Fasies_Alterasi": "Fasies alterasi (log)", "S_metode": "Metode S",
           "NAG_pH": "pH NAG", "NAG_pH45_kgH2SO4_t": "Kapasitas NAG pH 4.5 (kg H2SO4/t)",
           "NAG_pH70_kgH2SO4_t": "Kapasitas NAG pH 7.0 (kg H2SO4/t)", "S_total_pct": "S total (%)",
           "S_sulfida_SCIS_pct": "S sulfida SCIS (%)", "S_sulfida_S2_pct": "S sulfida S2 (%)",
           **s4.log10_aliases(sorted(set(s4.RJ12_LOG + s4.DH_LOG)))}
EXPECTED: list[Path] = []


def export(w: ip.Workflow, fr: ip.Frame, name: str) -> None:
    p = FIG / f"s4_{name}_v1.png"
    if p.exists() and not PROBE:
        sys.exit(f"{p} exists: frozen output, write _v2 instead")
    EXPECTED.append(p)
    w.export_window(p, fr)


def panel(w: ip.Workflow, cols: list[str], holes: list[str], name: str) -> None:
    """Strip log (one window, a track per variable, holes in the given order), bar traces, colour track."""
    w.select(cols)
    w.configure_downhole("HoleID", "From", "To", holes)
    fr = w.strip_log(stacked=False)
    w.trace_mode(fr, "Bar")
    export(w, fr, name)


def xy(w: ip.Workflow, x: str, y: str, name: str, log_x: bool = True, log_y: bool = False) -> None:
    w.select([x, y])
    fr = w.plot("XY Plot", ip.A_XY, [x, y])
    if log_x:
        w.action("Log X axis", ip.A_LOG_X, fr)
    if log_y:
        w.action("Log Y axis", ip.A_LOG_Y, fr)
    export(w, fr, name)


def build(d: pd.DataFrame, tag: str, colour_by: str, colours: dict[str, str], shape: bool = False) -> Path:
    order = [k for k in colours if k in set(d[colour_by])]
    assert set(d[colour_by]) <= set(order), set(d[colour_by]) - set(order)
    gas_in = WORK / f"{tag}_masuk.gas"
    kw = {}
    if shape:
        kw = dict(shape_by="Status_Oksidasi", shapes=s4.OX_SHAPES,
                  shape_order=[k for k in s4.OX_SHAPES if k in set(d.Status_Oksidasi)])
    al = {k: v for k, v in ALIASES.items() if k in d.columns}
    ip.build_gas(d, gas_in, special=ip.SpecialColumns(east="X", north="Y", elevation="Z", sample_id="SampleID",
                                                      epsg=st.EPSG, group="HoleID"),
                 drillhole=ip.Drillhole("HoleID", "From", "To"), aliases=al, colour_by=colour_by, colours=colours,
                 colour_order=order, source_note=f"s4 {tag}, from RJ_DH_assay.csv", **kw)
    return gas_in


def workflow(name: str, d: pd.DataFrame) -> ip.Workflow:
    return ip.Workflow(name, export_dir=FIG, aliases={k: v for k, v in ALIASES.items() if k in d.columns})


def save(w: ip.Workflow, gas_in: Path, d: pd.DataFrame, tag: str, out: Path) -> pd.DataFrame:
    out = WORK / "probe" / f"{tag}_probe.gas" if PROBE else out
    if out.exists() and not PROBE:
        sys.exit(f"{out} exists: frozen output, write _v2 instead")
    out.parent.mkdir(parents=True, exist_ok=True)
    w.save_as(out)
    st.run(gas_in, w, tag, WORK, "s4_probe" if PROBE else "s4")
    saved = st.check_saved(out, len(d))
    return saved.rename(columns={v: k for k, v in ALIASES.items()})


def rj12_tracks() -> list[str]:
    return ["NAG_pH", "NAGkap_log10", "SCIS_log10", "Stot_log10"]


def rjdh012_nag(d: pd.DataFrame) -> pd.DataFrame:
    """P1: RJDH012 by NAG class (shape = oxidation): NAG pH vs S, capacity vs SCIS, Halley, AMD box plots, strip."""
    gas_in = build(d, "rjdh012_nag", "Kelas_NAG", s4.NAG_COLOURS, shape=True)
    w = workflow("s4 RJDH012 kelas NAG", d)
    xy(w, "S_total_pct", "NAG_pH", "xy_phNAG_Stotal_kelas_nag")
    if not PROBE:
        xy(w, "S_sulfida_SCIS_pct", "NAG_pH", "xy_phNAG_SCIS_kelas_nag")
        xy(w, "S_sulfida_SCIS_pct", "NAG_pH45_kgH2SO4_t", "xy_kapNAG_SCIS_kelas_nag", log_y=True)
    w.select(["Fe_pct", "S_pct"])
    export(w, w.diagram(HALLEY_FES), "halley_FeS_rjdh012")
    w.select(["Ca_pct", "Fe_pct", "S_pct"])
    for msg in (["Fe_ppm", "S_ppm"], ["Ca_ppm", "Fe_ppm", "S_ppm"], ["S_ppm", "Fe_ppm"]):
        w.respond(f"OK to overwrite columns {', '.join(msg)} to open diagram?.", True)
    export(w, w.diagram(HALLEY_CAFES), "halley_CaFeS_rjdh012")
    box = [f"{e}_log10" for e in s4.RJ12_BOX]
    w.select(box)
    export(w, w.plot("Box Plots", ip.A_BOX_TILED, box), "box_amd_kelas_nag")
    panel(w, rj12_tracks(), [s4.NAG_HOLE], "strip_rjdh012_kelas_nag")
    saved = save(w, gas_in, d, "rjdh012_nag", PROJ / "RJ_RJDH012_s4_v1.gas")
    print(f"RJDH012 NAG project: {len(d)} rows")
    return saved


def rjdh012_ox(d: pd.DataFrame) -> None:
    """P2: RJDH012 by logged oxidation: strip log and NAG pH vs S total."""
    gas_in = build(d, "rjdh012_oks", "Status_Oksidasi", st.OX_COLOURS)
    w = workflow("s4 RJDH012 oksidasi", d)
    xy(w, "S_total_pct", "NAG_pH", "xy_phNAG_Stotal_oksidasi")
    panel(w, rj12_tracks(), [s4.NAG_HOLE], "strip_rjdh012_oksidasi")
    save(w, gas_in, d, "rjdh012_oks", PROJ / "s4" / "RJ_RJDH012_s4_oksidasi_v1.gas")


def dh_tracks() -> list[str]:
    return [f"{e}_log10" for e in s4.DH_STRIP] + ["ML_paf_n_set"]


def dh_kelola(d: pd.DataFrame, sections: dict[str, list[str]]) -> pd.DataFrame:
    """P3: all holes by management class: section strip logs, box plots, XYZ map (exported last)."""
    gas_in = build(d, "dh_kelola", "ML_paf_kelola", s4.KELOLA_COLOURS)
    w = workflow("s4 kelas pengelolaan PAF/NAF", d)
    w.select(["Cu_ppm"])
    fmap = w.plot("Attribute Map 3D", ip.A_MAP_XYZ, ["Cu_ppm"])
    for sec, holes in (sections.items() if not PROBE else [("B", sections["B"])]):
        panel(w, dh_tracks(), holes, f"strip_kelola_penampang_{sec}")
    box = [f"{e}_log10" for e in s4.DH_LOG]
    w.select(box)
    export(w, w.plot("Box Plots", ip.A_BOX_TILED, box), "box_kelola")
    if not PROBE:
        xy(w, "S_sulfida_SCIS_pct", "Cu_ppm", "xy_Cu_SCIS_kelola", log_y=True)
    export(w, fmap, "peta3d_kelola")
    saved = save(w, gas_in, d, "dh_kelola", PROJ / "RJ_DH_s4_kelola_v1.gas")
    print(f"management-class project: {len(d)} intervals")
    return saved


def dh_scheme(d: pd.DataFrame, sections: dict[str, list[str]], tag: str, colour_by: str,
              colours: dict[str, str]) -> None:
    """P4/P5: same section strip logs coloured by conformal class or NAG-testing priority."""
    gas_in = build(d, f"dh_{tag}", colour_by, colours)
    w = workflow(f"s4 {tag}", d)
    for sec, holes in sections.items():
        panel(w, dh_tracks(), holes, f"strip_{tag}_penampang_{sec}")
    save(w, gas_in, d, f"dh_{tag}", PROJ / "s4" / f"RJ_DH_s4_{tag}_v1.gas")


def unescape(d: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        d[c] = d[c].map(lambda v: v if pd.isna(v) else ip.gas_unescape(str(v)).strip())
    return d


def main() -> None:
    for p in (FIG, PROJ, WORK):
        p.mkdir(parents=True, exist_ok=True)
    if PROBE:
        for f in FIG.glob("*"):
            f.unlink()
    prev = sorted((FIGURES / "iogas").glob("s[123]_*_v1.png"))
    prev_hash = {p.name: st.sha256(p) for p in prev}

    assay = pd.read_csv(IODIR / "RJ_DH_assay.csv", low_memory=False)
    r12 = s4.load_rjdh012(assay)
    r12 = r12[RJ12_KEEP + [f"{e}_log10" for e in s4.RJ12_LOG]]
    dh = s4.load_assays(assay)
    dh = dh[DH_KEEP + [f"{e}_log10" for e in s4.DH_LOG]]
    sections = s3.section_holes(pd.read_csv(PROCESSED / "ml4_sections.csv"), sorted(dh.HoleID.unique()))
    print("sections:", sections)

    saved = unescape(rjdh012_nag(r12), ["Kelas_NAG", "Status_Oksidasi"])
    assert saved.Kelas_NAG.value_counts().to_dict() == r12.Kelas_NAG.value_counts().to_dict(), "NAG classes changed"
    summ, ref = s4.ringkasan_nag(saved), s4.ringkasan_nag(r12)
    num = [c for c in summ if c.startswith("median_")]
    assert np.allclose(summ[num].astype(float), ref[num].astype(float), rtol=1e-6, equal_nan=True), "medians differ"

    saved = unescape(dh_kelola(dh, sections), ["ML_paf_kelola", "Prioritas_uji_NAG", "HoleID"])
    per_hole = s4.kelola_per_lubang(saved)
    ref_hole = s4.kelola_per_lubang(dh)
    assert np.allclose(per_hole.drop(columns="HoleID"), ref_hole.drop(columns="HoleID")), "metres differ"

    if not PROBE:
        rjdh012_ox(r12)
        dh_scheme(dh, sections, "kelas", "ML_paf_kelas", s4.KELAS_COLOURS)
        dh_scheme(dh, sections, "uji_nag", "Prioritas_uji_NAG", s4.PRIORITY_COLOURS)
        for name, t in (("s4_kelas_nag_ringkasan_v1.csv", summ), ("s4_kelola_per_lubang_v1.csv", per_hole)):
            p = PROCESSED / name
            if p.exists():
                sys.exit(f"{p} exists: frozen output, write _v2 instead")
            t.to_csv(p, index=False)

    missing = [p for p in EXPECTED if not p.exists() or p.stat().st_size == 0]
    assert not missing, missing
    assert {p.name: st.sha256(p) for p in prev} == prev_hash, "a Stage 1-3 figure changed"
    print(f"{len(EXPECTED)} figures; Stage 1-3 figures unchanged ({len(prev)})")
    show = summ[summ.zona_oksidasi.eq("Semua")].set_index("kelas_nag")
    print(show[["n"] + num[:6]].round(3).to_string())
    print(per_hole.to_string(index=False))


if __name__ == "__main__":
    main()
