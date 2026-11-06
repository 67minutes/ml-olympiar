"""ioGAS link tests. Stub generation needs a local ioGAS install; the live round trip also needs
IOGAS_LIVE=1 (it starts a second ioGAS window for ~20 s)."""
import os
import zipfile

import pandas as pd
import pytest

from src import iogas_link as il
from src import iogas_project as ip

needs_iogas = pytest.mark.skipif(not (il.IOGAS_HOME / "libs" / "GAS.jar").exists(), reason="ioGAS not installed")


def test_server_port_reads_ini(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert il.server_port() == il.DEFAULT_PORT
    ini = tmp_path / "ioGAS" / "userConfig" / "gaslink2.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text("serverPort=25123\nremotePort=25100\n")
    assert il.server_port() == 25123


@needs_iogas
def test_ensure_stubs_generates_and_caches(tmp_path):
    out = il.ensure_stubs(out=tmp_path / "stubs")
    assert (out / "server_pb2_grpc.py").exists() and (out / "gaslink2_pb2.py").exists()
    stamp = (out / "STAMP").read_text()
    (out / "server_pb2.py").write_text("# sentinel")
    il.ensure_stubs(out=out)  # same jar -> cache kept
    assert (out / "server_pb2.py").read_text() == "# sentinel" and (out / "STAMP").read_text() == stamp


@needs_iogas
@pytest.mark.skipif(os.environ.get("IOGAS_LIVE") != "1", reason="set IOGAS_LIVE=1 to start ioGAS")
def test_live_open_plot_export_save(tmp_path):
    df = pd.DataFrame({"SampleID": [f"S{i}" for i in range(30)], "X": range(30), "Y": range(30),
                       "Au_ppm": [0.01 * (i + 1) for i in range(30)], "As_ppm": [float(i + 1) for i in range(30)],
                       "Zona": ["A", "B", "C"] * 10})
    gas = ip.build_gas(df, tmp_path / "in.gas", special=ip.SpecialColumns(east="X", north="Y", sample_id="SampleID",
                       epsg=32647), colour_by="Zona")
    w = ip.Workflow("pytest live", export_dir=tmp_path)
    w.select(["Au_ppm", "As_ppm"])
    fr = w.plot("XY Plot", ip.A_XY, ["Au_ppm", "As_ppm"])
    w.export_window(tmp_path / "xy.png", fr)
    w.save_as(tmp_path / "out.gas")
    with il.IoGAS() as g:
        g.open_gas(gas)
        res = g.run_workflow(w.write(tmp_path / "wf.xml"))
    assert (tmp_path / "xy.png").stat().st_size > 1000 and res["files"]
    meta = zipfile.ZipFile(tmp_path / "out.gas").read("metadata.xml").decode()
    assert "<map_epsg>32647</map_epsg>" in meta
