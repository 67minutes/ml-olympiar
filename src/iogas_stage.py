"""Shared plumbing for the ioGAS stage scripts (AGENTS.md §10): run a workflow in our own -gaslink2 instance,
check what ioGAS saved, add log10 columns, shared palettes. Used by scripts/23_… to 26_….
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from src import iogas_project as ip
from src.paths import ROOT

EPSG = 32647
WF = ROOT / "iogas" / "workflows"
ZONE_COLOURS = {"Rendah": "#2a78d6", "Sedang": "#e8a33d", "Tinggi": "#c8321e"}
ZONE_ORDER = ["Tinggi", "Sedang", "Rendah"]
OX_COLOURS = {"Oksida": "#e08214", "Transisi": "#fdb863", "Sulfida": "#5e3c99", "Tidak dicatat": "#bdbdbd"}
PAF_COLOURS = {"NAF": "#4575b4", "PAF-LC": "#f4a582", "PAF-HC": "#b2182b", "ambigu": "#999999"}  # ML-5 (script 14)
PAF_ORDER = ["PAF-HC", "PAF-LC", "NAF", "ambigu"]
# non-<El>_ppm columns used by add_log10: short name -> (column, alias label)
_SPECIAL_EL = {"SCIS": ("S_sulfida_SCIS_pct", "SCIS"), "S2": ("S_sulfida_S2_pct", "S sulfida S2"),
               "Stot": ("S_total_pct", "S total"), "Fe": ("Fe_pct", "Fe"), "Ca": ("Ca_pct", "Ca"),
               "NAGkap": ("NAG_pH45_kgH2SO4_t", "Kapasitas NAG pH 4.5")}


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def special(sid: str | None = "SampleID") -> ip.SpecialColumns:
    return ip.SpecialColumns(east="X", north="Y", elevation="Z", sample_id=sid, epsg=EPSG)


def element_column(el: str) -> str:
    return _SPECIAL_EL[el][0] if el in _SPECIAL_EL else f"{el}_ppm"


def _unit(col: str) -> str:
    return "%" if col.endswith("_pct") else "kg H2SO4/t" if col.endswith("kgH2SO4_t") else "ppm"


def add_log10(d: pd.DataFrame, elements: list[str]) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    """`<el>_log10` columns (box plots ignore log toggles in workflows) with Bahasa aliases."""
    d = d.copy()
    aliases, cols = {}, []
    for el in elements:
        c, lc = element_column(el), f"{el}_log10"
        d[lc] = np.log10(d[c].where(d[c] > 0))
        label = _SPECIAL_EL[el][1] if el in _SPECIAL_EL else el
        aliases[lc] = f"log10 {label} ({_unit(c)})"
        cols.append(lc)
    return d, aliases, cols


def run(gas_in: Path, w: ip.Workflow, tag: str, work: Path, prefix: str) -> dict:
    """Open `gas_in` in our own -gaslink2 ioGAS instance, run the workflow, close the instance.

    Asserts no operation failed and every exported image exists; prints image sizes.
    """
    from PIL import Image

    from src.iogas_link import IoGAS

    WF.mkdir(parents=True, exist_ok=True)
    wf = w.write(WF / f"{prefix}_{tag}.xml")
    logf = work / f"iogas_{tag}.log"
    with IoGAS(log=logf) as g:
        g.open_gas(gas_in)
        res = g.run_workflow(wf)
    log = logf.read_text(errors="replace")
    bad = [ln for ln in log.splitlines()
           if " failed" in ln.lower() and ("operation" in ln.lower() or " Action " in ln)]
    assert not bad, (tag, bad[:3])
    for f in res["files"]:
        assert Path(f).exists(), f
        with Image.open(f) as im:
            print(f"  {Path(f).name}: {im.size[0]} x {im.size[1]} px")
    return res


def check_saved(gas: Path, n_rows: int) -> pd.DataFrame:
    """The project ioGAS saved has our rows and kept EPSG 32647 (read back from ioGAS's own file)."""
    z = zipfile.ZipFile(gas)
    meta = z.read("metadata.xml").decode("utf-8", "replace")
    assert f"<map_epsg>{EPSG}</map_epsg>" in meta, f"EPSG lost: {gas}"
    d = pd.read_csv(z.open("data.csv"), encoding="cp1252", low_memory=False)
    d.columns = [ip.gas_unescape(c).strip() for c in d.columns]
    assert len(d) == n_rows, (gas.name, len(d), n_rows)
    print(f"  saved {gas.relative_to(ROOT)}: {len(d)} rows, EPSG {EPSG} kept")
    return d
