"""ioGAS Stage 2 (AGENTS.md Â§10): surface soil and rock figures drawn by ioGAS itself.

    uv run python scripts/24_iogas_s2_surface.py

Inputs: data/processed/iogas/RJ_tanah.csv, RJ_batuan.csv (ML-3 zones `ML_zona*`), the frozen Stage 1 picks
(data/interim/s1_probplot_picks.csv, hash must be in LOG.md) for the threshold classes. No new ML.
One .gas per colour scheme (colour attributes come from build_gas); each runs in our own -gaslink2 instance.

Outputs: outputs/figures/iogas/s2_*_v1.png; outputs/iogas_project/RJ_tanah_s2_v1.gas, RJ_batuan_s2_v1.gas
(coloured by zone, class/confidence columns kept) and outputs/iogas_project/s2/*.gas (other schemes);
data/processed/s2_zona_vs_kelas_v1.csv, s2_zona_ringkasan_v1.csv. Workflow XML: iogas/workflows/s2_*.xml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import iogas_project as ip  # noqa: E402
from src import iogas_s1 as s1  # noqa: E402
from src import iogas_s2 as s2  # noqa: E402
from src import iogas_stage as st  # noqa: E402
from src.paths import FIGURES, INTERIM, PROCESSED, ROOT  # noqa: E402

IODIR = PROCESSED / "iogas"
FIG = FIGURES / "iogas"
PROJ = ROOT / "outputs" / "iogas_project"
WORK = INTERIM / "iogas_s2"
PICKS = INTERIM / "s1_probplot_picks.csv"
HALLEY_AKM = "Exploration/Porphyry Cu Exploration/Scott Halley/Al-K-Mg Ternary Plot.xml"
RJ_SHAPE = {"Di dalam RJ": 0, "Di luar RJ": 10}  # filled circle / open square

BOX_EL, XY_PAIRS, KELAS_EL, BASE_AL, kelas_alias = s2.BOX_EL, s2.XY_PAIRS, s2.KELAS_EL, s2.BASE_AL, s2.kelas_alias
EXPECTED = []  # every PNG this run must produce


def run(gas_in: Path, w: ip.Workflow, tag: str) -> dict:
    return st.run(gas_in, w, tag, WORK, "s2")


def export(w: ip.Workflow, fr: ip.Frame, name: str) -> None:
    p = FIG / f"s2_{name}_v1.png"
    if p.exists():
        sys.exit(f"{p} exists: frozen output, write _v2 instead")
    EXPECTED.append(p)
    w.export_window(p, fr)


def map_open(w: ip.Workflow, col: str = "Au_ppm") -> ip.Frame:
    """Open the attribute map now; export it at the end of the workflow. Exporting straight after opening
    raced ioGAS's map rendering (ConcurrentModificationException, 0-byte PNG; 6 Nov 2026)."""
    w.select([col])
    return w.plot("Attribute Map", ip.A_MAP, [col])


def xy_log(w: ip.Workflow, x: str, y: str, name: str) -> None:
    cx, cy = st.element_column(x), st.element_column(y)
    w.select([cx, cy])
    fr = w.plot("XY Plot", ip.A_XY, [cx, cy])
    w.action("Log X axis", ip.A_LOG_X, fr)
    w.action("Log Y axis", ip.A_LOG_Y, fr)
    export(w, fr, name)


def boxes(w: ip.Workflow, lcols: list[str], name: str) -> None:
    w.select(lcols)
    export(w, w.plot("Box Plots", ip.A_BOX_TILED, lcols), name)


def zone_project(ds: str, d: pd.DataFrame, al: dict, lcols: dict) -> pd.DataFrame:
    """Main stage project: coloured by ML zone; map, scatters, boxes per zone (and soil Au probability plot)."""
    dz = d[d.ML_zona.notna()].reset_index(drop=True)
    shape = {"shape_by": "Jenis_sampel", "shape_order": list(s2.JENIS.values()),
             "shapes": {"Singkapan": 0, "Bongkah lepas (float)": 11}} if ds == "batuan" else {}
    gas_in = WORK / f"{ds}_zona_masuk.gas"
    ip.build_gas(dz, gas_in, special=st.special(), aliases=al, colour_by="ML_zona", colours=st.ZONE_COLOURS,
                 colour_order=st.ZONE_ORDER, source_note=f"s2 zones, RJ subset of {s1.DATASETS[ds][0]}.csv", **shape)
    w = ip.Workflow(f"s2 zona {ds}", export_dir=FIG, aliases=al)
    fmap = map_open(w)
    for x, y in XY_PAIRS[ds]:
        xy_log(w, x, y, f"xy_{y}_{x}_zona_{ds}")
    boxes(w, lcols["box"], f"box_zona_{ds}")
    if ds == "tanah":
        w.select(["Au_ppm"])
        fr = w.plot("Probability Plot", ip.A_PROB_PLOT, ["Au_ppm"])
        w.action("Log Y axis", ip.A_LOG_Y, fr)
        export(w, fr, "pp_Au_zona_tanah")
    export(w, fmap, f"peta_zona_{ds}")
    out = PROJ / f"RJ_{ds}_s2_v1.gas"
    w.save_as(out)
    print(f"{ds} zone project: {len(dz)} rows")
    run(gas_in, w, f"zona_{ds}")
    return st.check_saved(out, len(dz))


def scheme_project(ds: str, d: pd.DataFrame, al: dict, tag: str, colour_by: str, colours: dict,
                   title: str | None = None, box_cols: list[str] | None = None) -> None:
    """Extra colour scheme: attribute map (and optional boxes) in its own .gas under outputs/iogas_project/s2/."""
    order = [k for k in colours if k in set(d[colour_by].dropna())]
    gas_in = WORK / f"{ds}_{tag}_masuk.gas"
    ip.build_gas(d, gas_in, special=st.special(), aliases=al, colour_by=colour_by, colours=colours,
                 colour_order=order, colour_title=title)
    w = ip.Workflow(f"s2 {tag} {ds}", export_dir=FIG, aliases=al)
    fmap = map_open(w)
    # the map is exported last: the zone workflow (4 exports before the map) never raced, one histogram did
    boxes(w, box_cols or [f"{e}_log10" for e in BOX_EL[ds]], f"box_{tag}_{ds}")
    for x, y in XY_PAIRS[ds]:
        xy_log(w, x, y, f"xy_{y}_{x}_{tag}_{ds}")
    export(w, fmap, f"peta_{tag}_{ds}")
    out = PROJ / "s2" / f"RJ_{ds}_s2_{tag}_v1.gas"
    out.parent.mkdir(parents=True, exist_ok=True)
    w.save_as(out)
    print(f"{ds} {tag}: {len(d)} rows")
    run(gas_in, w, f"{tag}_{ds}")
    st.check_saved(out, len(d))


def halley_project() -> int:
    """Halley Al-K-Mg ternary on every rock with full ICP (Al, K, Mg), coloured by logged alteration."""
    rock = pd.read_csv(IODIR / "RJ_batuan.csv", low_memory=False)
    d = rock[rock[["Al_pct", "K_pct", "Mg_pct"]].notna().all(axis=1)].reset_index(drop=True)
    d["Posisi_RJ"] = d.prospek_RJ.map({"Y": "Di dalam RJ", "N": "Di luar RJ"})
    d = d[["SampleID", "X", "Y", "Z", "Posisi_RJ", "Fasies_Alterasi", "Kelompok_Litologi", "Al_pct", "K_pct",
           "Mg_pct", "Au_ppm", "Cu_ppm", "As_ppm"]]
    al = {k: v for k, v in BASE_AL.items() if k in d.columns}
    order = [k for k in s2.ALT_COLOURS if k in set(d.Fasies_Alterasi.dropna())]
    gas_in = WORK / "batuan_halley_masuk.gas"
    ip.build_gas(d, gas_in, special=st.special(), aliases=al, colour_by="Fasies_Alterasi", colours=s2.ALT_COLOURS,
                 colour_order=order, shape_by="Posisi_RJ", shapes=RJ_SHAPE, shape_order=list(RJ_SHAPE))
    w = ip.Workflow("s2 Halley Al-K-Mg batuan", export_dir=FIG, aliases=al)
    w.select(["Al_pct", "K_pct", "Mg_pct"])
    export(w, w.diagram(HALLEY_AKM), "halley_AlKMg_batuan")
    out = PROJ / "s2" / "RJ_batuan_s2_halley_v1.gas"
    w.save_as(out)
    print(f"Halley Al-K-Mg: {len(d)} rocks ({int((d.Posisi_RJ == 'Di dalam RJ').sum())} inside RJ)")
    run(gas_in, w, "halley_batuan")
    st.check_saved(out, len(d))
    return len(d)


def main() -> None:
    for p in (FIG, PROJ, WORK):
        p.mkdir(parents=True, exist_ok=True)
    h = st.sha256(PICKS)
    assert h in (ROOT / "LOG.md").read_text(encoding="utf-8"), "Stage 1 picks changed since they were frozen"
    s1_files = sorted(FIG.glob("s1_*_v1.png"))
    s1_hash = {p.name: st.sha256(p) for p in s1_files}
    picks = pd.read_csv(PICKS)

    cross, summ = [], []
    for ds in ("tanah", "batuan"):
        d, al, lcols = s2.load_surface(ds, picks)
        saved = zone_project(ds, d, al, lcols).rename(columns={v: k for k, v in al.items()})  # saved under aliases
        for c in ["ML_zona"] + [f"Kelas_{el}_pp" for el in KELAS_EL[ds]]:
            saved[c] = saved[c].map(lambda v: v if pd.isna(v) else ip.gas_unescape(str(v)).strip())
        assert saved.ML_zona.value_counts().to_dict() == d.ML_zona.value_counts().to_dict(), "zones changed in ioGAS"
        num = [st.element_column(e) for e in BOX_EL[ds]]
        summ.append(s2.zona_ringkasan(saved, ds, num))
        for el in KELAS_EL[ds]:
            cross.append(s2.zona_vs_kelas(saved, ds, el, f"Kelas_{el}_pp", s1.KELAS))
        for el in KELAS_EL[ds] if ds == "tanah" else ["Au"]:
            scheme_project(ds, d, al, f"kelas_{el}", f"Kelas_{el}_pp", s1.KELAS_COLOURS,
                           title=f"{kelas_alias(el)} (plot probabilitas)")
        if ds == "tanah":
            scheme_project(ds, d, al, "keyakinan", "Keyakinan_zona", s2.KEYAKINAN_COLOURS)
        else:
            scheme_project(ds, d, al, "alterasi", "Fasies_Alterasi", s2.ALT_COLOURS,
                           box_cols=["Au_log10", "Cu_log10", "As_log10"])
    halley_project()

    cross = pd.concat(cross, ignore_index=True)
    summ = pd.concat(summ, ignore_index=True)
    for name, t in (("s2_zona_vs_kelas_v1.csv", cross), ("s2_zona_ringkasan_v1.csv", summ)):
        p = PROCESSED / name
        if p.exists():
            sys.exit(f"{p} exists: frozen output, write _v2 instead")
        t.to_csv(p, index=False)
    missing = [p for p in EXPECTED if not p.exists()]
    assert not missing, missing
    assert {p.name: st.sha256(p) for p in s1_files} == s1_hash, "a Stage 1 figure changed"
    print(f"{len(EXPECTED)} figures; Stage 1 figures unchanged")
    print(cross.drop_duplicates(["dataset", "element"])[["dataset", "element", "n_total", "cramers_v"]].to_string(
        index=False))
    print(summ.pivot_table(index=["dataset", "kolom"], columns="zona", values="median").to_string())


if __name__ == "__main__":
    main()
