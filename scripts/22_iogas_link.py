"""ioGAS projects from the hand-off CSVs, plus an optional live check through ioGAS's gRPC server.

    uv run python scripts/22_iogas_link.py                 # build the .gas projects only (no ioGAS needed)
    uv run python scripts/22_iogas_link.py --check DIR     # also open RJ_tanah.gas in ioGAS, draw probability
                                                           # plots, export a PNG and save a copy into DIR

Writes data/processed/iogas/RJ_tanah.gas, RJ_batuan.gas, RJ_DH_assay.gas, RJ_DH_komposit_1m.gas: same rows and
columns as the CSVs, EPSG:32647 and coordinates set, rows coloured by the ML class (zone colours from
scripts/10_ml3_zonation.py, PAF colours from scripts/14_ml5_paf.py). The ioGAS project deliverable is still made
in ioGAS; these files only save the import and attribute steps. See LOG.md 2026-11-05 ioGAS probes.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import iogas_project as ip  # noqa: E402
from src.iogas_stage import PAF_COLOURS, PAF_ORDER, ZONE_COLOURS, ZONE_ORDER  # noqa: E402
from src.paths import PROCESSED  # noqa: E402

IODIR = PROCESSED / "iogas"
EPSG = 32647

PROJECTS = {
    # name: (sample id column, colour column, colours, order)
    "RJ_tanah": ("SampleID", "ML_zona", ZONE_COLOURS, ZONE_ORDER),
    "RJ_batuan": ("SampleID", "ML_zona", ZONE_COLOURS, ZONE_ORDER),
    "RJ_DH_assay": ("SampleID", "ML_paf_kelas", PAF_COLOURS, PAF_ORDER),
    "RJ_DH_komposit_1m": (None, None, None, None),
}


def build_all() -> dict[str, Path]:
    out = {}
    for name, (sid, colour, colours, order) in PROJECTS.items():
        df = pd.read_csv(IODIR / f"{name}.csv", low_memory=False)
        order = [o for o in order if colour and o in set(df[colour].dropna())] if colour else None
        p = ip.build_gas(df, IODIR / f"{name}.gas",
                         special=ip.SpecialColumns(east="X", north="Y", elevation="Z", sample_id=sid, epsg=EPSG),
                         colour_by=colour, colours=colours, colour_order=order,
                         source_note=f"from data/processed/iogas/{name}.csv")
        # check: row count preserved, colour legend as intended
        n = sum(1 for _ in zipfile.ZipFile(p).open("data.csv")) - 1
        assert n == len(df), (name, n, len(df))
        counts = df[colour].value_counts(dropna=False).to_dict() if colour else {}
        print(f"{p.relative_to(PROCESSED.parent.parent)}: {len(df)} rows x {df.shape[1]} cols; "
              f"colour={colour or '-'} {counts}")
        out[name] = p
    return out


def live_check(gas: Path, outdir: Path):
    from src.iogas_link import IoGAS

    outdir = outdir.resolve()
    w = ip.Workflow("RJ check: soil probability plots", export_dir=outdir)
    cols = ["Au_ppm", "As_ppm", "Cu_ppm"]
    w.select(cols)
    fr = w.plot("Probability Plot", ip.A_PROB_PLOT, cols)
    w.action("Log Y axis", ip.A_LOG_Y, fr)
    w.export_window(outdir / "cek_pp_tanah_AuAsCu.png", fr, scale=2)
    w.save_as(outdir / "cek_RJ_tanah.gas")
    wf = w.write(outdir / "cek_workflow.xml")
    with IoGAS(log=outdir / "cek_iogas.log") as g:
        g.open_gas(gas)
        res = g.run_workflow(wf)
    print("exported:", res["files"])
    meta = zipfile.ZipFile(outdir / "cek_RJ_tanah.gas").read("metadata.xml").decode("utf-8", "replace")
    assert f"<map_epsg>{EPSG}</map_epsg>" in meta, "EPSG lost on save"
    print("saved:", outdir / "cek_RJ_tanah.gas", "(EPSG kept)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", type=Path, metavar="DIR", help="run the live ioGAS check, writing into DIR")
    a = ap.parse_args()
    projects = build_all()
    if a.check:
        a.check.mkdir(parents=True, exist_ok=True)
        live_check(projects["RJ_tanah"], a.check)
