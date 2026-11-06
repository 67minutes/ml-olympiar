"""ioGAS Stage 5 (AGENTS.md §10): the four final ioGAS projects (deliverable 2) and the Bahasa indexes.

    uv run python scripts/27_iogas_s5_final.py              # final projects + indexes
    uv run python scripts/27_iogas_s5_final.py --index      # indexes only (no ioGAS)

Each final project holds every column of its ioGAS-ready CSV (data/processed/iogas/) for the rows used by the
analysis, the columns the stage projects derived (threshold classes from the frozen Stage 1 picks, log10 columns,
zone confidence, NAG label, S_pct), Bahasa aliases, EPSG 32647, and the key report windows re-drawn in one project.
No new ML, no new report figures: window exports go to data/interim/iogas_s5/cek/ for review only.

Outputs: outputs/iogas_project/RJ_{tanah,batuan,bor_komposit,lingkungan}_final_v1.gas,
outputs/iogas_project/indeks_proyek_iogas.csv + BACA_SAYA.txt, outputs/figures/iogas/indeks_gambar_iogas.csv.
Workflow XML: iogas/workflows/s5_*.xml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import iogas_project as ip  # noqa: E402
from src import iogas_s2 as s2  # noqa: E402
from src import iogas_s3 as s3  # noqa: E402
from src import iogas_s4 as s4  # noqa: E402
from src import iogas_s5 as s5  # noqa: E402
from src import iogas_stage as st  # noqa: E402
from src.paths import FIGURES, INTERIM, PROCESSED, ROOT  # noqa: E402

FIG = FIGURES / "iogas"
PROJ = ROOT / "outputs" / "iogas_project"
WORK = INTERIM / "iogas_s5"
CEK = WORK / "cek"
PICKS = INTERIM / "s1_probplot_picks.csv"
HALLEY_FES = "Exploration/Porphyry Cu Exploration/Scott Halley/Fe vs S with Pyrite Line.xml"
ZONE_COLOURS = {**st.ZONE_COLOURS, s5.NO_ZONE: "#bdbdbd"}
ZONE_ORDER = st.ZONE_ORDER + [s5.NO_ZONE]
EXPECTED: list[Path] = []


def export(w: ip.Workflow, fr: ip.Frame, name: str) -> None:
    p = CEK / f"s5_{name}.png"
    EXPECTED.append(p)
    w.export_window(p, fr)


def pp(w: ip.Workflow, col: str, name: str) -> None:
    w.select([col])
    fr = w.plot("Probability Plot", ip.A_PROB_PLOT, [col])
    w.action("Log Y axis", ip.A_LOG_Y, fr)
    export(w, fr, name)


def xy(w: ip.Workflow, x: str, y: str, name: str, log_x: bool = True, log_y: bool = True) -> None:
    w.select([x, y])
    fr = w.plot("XY Plot", ip.A_XY, [x, y])
    if log_x:
        w.action("Log X axis", ip.A_LOG_X, fr)
    if log_y:
        w.action("Log Y axis", ip.A_LOG_Y, fr)
    export(w, fr, name)


def boxes(w: ip.Workflow, cols: list[str], name: str) -> None:
    w.select(cols)
    export(w, w.plot("Box Plots", ip.A_BOX_TILED, cols), name)


def strip(w: ip.Workflow, cols: list[str], holes: list[str], name: str) -> None:
    w.select(cols)
    w.configure_downhole("HoleID", "From", "To", holes)
    fr = w.strip_log(stacked=False)
    w.trace_mode(fr, "Bar")
    export(w, fr, name)


def stats(w: ip.Workflow, cols: list[str]) -> None:
    """Summary Statistics window: kept in the saved project (ioGAS cannot export it as an image)."""
    w.select(cols)
    w.plot("Summary Statistics", ip.A_STATS, cols)


def finish(w: ip.Workflow, gas_in: Path, out: Path, tag: str, n: int) -> dict:
    if out.exists():
        sys.exit(f"{out} exists: frozen output, write _v2 instead")
    w.save_as(out)
    st.run(gas_in, w, tag, WORK, "s5")
    st.check_saved(out, n)
    info = s5.gas_summary(out)
    print(f"  {out.name}: {info}")
    return info


def surface(ds: str, picks: pd.DataFrame) -> dict:
    d, al = s5.load_surface_final(ds, picks)
    shape = {"shape_by": "Jenis_sampel", "shape_order": list(s2.JENIS.values()),
             "shapes": {"Singkapan": 0, "Bongkah lepas (float)": 11}} if ds == "batuan" else {}
    gas_in = WORK / f"{ds}_final_masuk.gas"
    order = [k for k in ZONE_ORDER if k in set(d.ML_zona)]
    ip.build_gas(d, gas_in, special=st.special(), aliases=al, colour_by="ML_zona", colours=ZONE_COLOURS,
                 colour_order=order, source_note=f"s5 final, RJ subset of RJ_{ds}.csv", **shape)
    w = ip.Workflow(f"s5 proyek akhir {ds}", export_dir=CEK, aliases=al)
    w.select(["Au_ppm"])
    fmap = w.plot("Attribute Map", ip.A_MAP, ["Au_ppm"])          # exported last (map rendering race, Stage 2)
    for el in ("Au", "As"):
        pp(w, f"{el}_ppm", f"pp_{el}_{ds}")
    boxes(w, [f"{e}_log10" for e in s2.BOX_EL[ds]], f"box_zona_{ds}")
    for x, y in s2.XY_PAIRS[ds]:
        xy(w, f"{x}_ppm", f"{y}_ppm", f"xy_{y}_{x}_{ds}")
    stats(w, [st.element_column(e) for e in s2.BOX_EL[ds]])
    export(w, fmap, f"peta_zona_{ds}")
    print(f"{ds}: {len(d)} rows, {d.shape[1]} columns")
    return finish(w, gas_in, PROJ / f"RJ_{ds}_final_v1.gas", f"final_{ds}", len(d))


def dh_special() -> ip.SpecialColumns:
    return ip.SpecialColumns(east="X", north="Y", elevation="Z", epsg=st.EPSG, group="HoleID")


def komposit(sections: dict[str, list[str]]) -> dict:
    d, al = s5.load_komposit_final()
    colours = s3.state_colours(d.ML_hmm_nama)
    gas_in = WORK / "bor_komposit_final_masuk.gas"
    ip.build_gas(d, gas_in, special=dh_special(), drillhole=ip.Drillhole("HoleID", "From", "To"), aliases=al,
                 colour_by="ML_hmm_nama", colours=colours, colour_order=list(colours),
                 source_note="s5 final, comp_ok = Y of RJ_DH_komposit_1m.csv")
    w = ip.Workflow("s5 proyek akhir komposit bor", export_dir=CEK, aliases=al)
    w.select(["Au_ppm"])
    fmap = w.plot("Attribute Map 3D", ip.A_MAP_XYZ, ["Au_ppm"])
    for el in ("Au", "Cu"):
        pp(w, f"{el}_ppm", f"pp_{el}_komposit")
    tracks = [f"{e}_log10" for e in s3.STRIP_EL] + ["ML_hmm_stabil"]
    for sec in ("A", "B", "C"):
        strip(w, tracks, sections[sec], f"strip_penampang_{sec}")
    strip(w, tracks, list(s3.TWIN_PADS[0]), "strip_kembar_005_014")
    boxes(w, [f"{e}_log10" for e in s3.LOG_EL] + ["CuCN_Cu_rasio"], "box_status_hmm")
    xy(w, "Au_ppm", "Cu_ppm", "xy_Cu_Au_komposit")
    stats(w, ["Au_ppm", "Ag_ppm", "Cu_ppm", "As_ppm", "S_sulfida_SCIS_pct"])
    export(w, fmap, "peta3d_status_hmm")
    print(f"komposit: {len(d)} rows, {d.shape[1]} columns")
    return finish(w, gas_in, PROJ / "RJ_bor_komposit_final_v1.gas", "final_komposit", len(d))


def lingkungan(picks: pd.DataFrame, sections: dict[str, list[str]]) -> dict:
    d, al = s5.load_lingkungan_final(picks)
    order = [k for k in s4.KELOLA_COLOURS if k in set(d.ML_paf_kelola)]
    gas_in = WORK / "lingkungan_final_masuk.gas"
    ip.build_gas(d, gas_in, special=ip.SpecialColumns(east="X", north="Y", elevation="Z", sample_id="SampleID",
                                                      epsg=st.EPSG, group="HoleID"),
                 drillhole=ip.Drillhole("HoleID", "From", "To"), aliases=al,
                 colour_by="ML_paf_kelola", colours=s4.KELOLA_COLOURS, colour_order=order,
                 shape_by="Status_Oksidasi", shapes=s4.OX_SHAPES,
                 shape_order=[k for k in s4.OX_SHAPES if k in set(d.Status_Oksidasi)],
                 source_note="s5 final, sampled intervals of RJ_DH_assay.csv")
    w = ip.Workflow("s5 proyek akhir lingkungan", export_dir=CEK, aliases=al)
    w.select(["Cu_ppm"])
    fmap = w.plot("Attribute Map 3D", ip.A_MAP_XYZ, ["Cu_ppm"])
    xy(w, "S_total_pct", "NAG_pH", "xy_phNAG_Stotal", log_y=False)            # only RJDH012 has NAG and total S
    xy(w, "S_sulfida_SCIS_pct", "NAG_pH45_kgH2SO4_t", "xy_kapNAG_SCIS")
    w.select(["Fe_pct", "S_pct"])
    for msg in (["Fe_ppm", "S_ppm"], ["S_ppm", "Fe_ppm"]):
        w.respond(f"OK to overwrite columns {', '.join(msg)} to open diagram?.", True)
    export(w, w.diagram(HALLEY_FES), "halley_FeS")
    boxes(w, [f"{e}_log10" for e in s4.DH_LOG], "box_kelola")
    tracks = [f"{e}_log10" for e in s4.DH_STRIP] + ["ML_paf_n_set"]
    for sec in ("A", "B", "C"):
        strip(w, tracks, sections[sec], f"strip_kelola_penampang_{sec}")
    stats(w, ["NAG_pH", "S_total_pct", "S_sulfida_SCIS_pct", "S_sulfida_S2_pct", "Fe_pct", "Cu_ppm", "As_ppm"])
    export(w, fmap, "peta3d_kelola")
    print(f"lingkungan: {len(d)} rows, {d.shape[1]} columns")
    return finish(w, gas_in, PROJ / "RJ_lingkungan_final_v1.gas", "final_lingkungan", len(d))


def write_indexes() -> None:
    """Bahasa indexes of every ioGAS figure and every saved ioGAS project (regenerated, not frozen)."""
    fig = s5.figure_index(FIG)
    fig.to_csv(FIG / "indeks_gambar_iogas.csv", index=False, encoding="utf-8-sig")
    rows = []
    for g in sorted(PROJ.rglob("*.gas")):
        rel = g.relative_to(PROJ).as_posix()
        tahap, bab = s5.project_role(rel)
        info = s5.gas_summary(g)
        warna = s5.FINALS[g.name][1] if g.name in s5.FINALS else info["judul_warna"] or "tanpa warna"
        rows.append({"file": rel, "jenis": "akhir" if g.name in s5.FINALS else "pendukung", "tahap": tahap,
                     "bab_laporan": bab, "data": s5.project_data(g.name), "warna": warna,
                     "baris": info["baris"], "jendela_plot": info["jendela"], "epsg_32647": info["epsg_32647"]})
    t = pd.DataFrame(rows).sort_values(["jenis", "file"], key=lambda c: c.map({"akhir": 0, "pendukung": 1})
                                       if c.name == "jenis" else c)
    t.to_csv(PROJ / "indeks_proyek_iogas.csv", index=False, encoding="utf-8-sig")
    (PROJ / "BACA_SAYA.txt").write_text(s5.baca_saya(t), encoding="utf-8")
    print(f"indexes: {len(fig)} figures, {len(t)} projects ({int(t.jenis.eq('akhir').sum())} final)")


def main() -> None:
    if "--index" not in sys.argv:
        for p in (PROJ, WORK, CEK):
            p.mkdir(parents=True, exist_ok=True)
        assert st.sha256(PICKS) in (ROOT / "LOG.md").read_text(encoding="utf-8"), "Stage 1 picks changed"
        prev = sorted(FIG.glob("s[1-4]_*_v1.png")) + sorted(PROJ.rglob("*_s[1-4]*_v1.gas"))
        prev_hash = {p.as_posix(): st.sha256(p) for p in prev}
        picks = pd.read_csv(PICKS)
        sections = s3.section_holes(pd.read_csv(PROCESSED / "ml4_sections.csv"), [])
        for ds in ("tanah", "batuan"):
            surface(ds, picks)
        komposit(sections)
        lingkungan(picks, sections)
        missing = [p for p in EXPECTED if not p.exists() or p.stat().st_size == 0]
        assert not missing, missing
        assert {p.as_posix(): st.sha256(p) for p in prev} == prev_hash, "a Stage 1-4 output changed"
        print(f"{len(EXPECTED)} check exports; Stage 1-4 outputs unchanged ({len(prev)} files)")
    write_indexes()


if __name__ == "__main__":
    main()
