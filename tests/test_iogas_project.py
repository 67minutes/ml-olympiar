import io
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pytest

from src import iogas_project as ip


def _df():
    return pd.DataFrame({
        "SampleID": ["S1", "S2", "S3", "S4"],
        "X": [506500.0, 506600.0, 506700.0, 506800.0],
        "Y": [168000.0, 168100.0, 168200.0, 168300.0],
        "Au_ppm": [0.01, np.nan, 0.5, 1.2],
        "Note": ["a,b", None, "x_y", "plain"],
        "ML_zona": ["Rendah", None, "Sedang", "Tinggi"],
    })


def test_escape_round_trip_and_underscore_first():
    s = 'Au_ppm, "a<b>&c"\t'
    assert ip.gas_escape("Au_ppm") == "Au_uppm"
    assert ip.gas_escape("a,b") == "a_cb"
    assert ip.gas_unescape(ip.gas_escape(s)) == s


def test_argb_matches_iogas_values():
    assert ip.argb("#000000") == -16777216  # ioGAS "Default Colour"
    assert ip.argb("#ffffff") == -1
    with pytest.raises(ValueError):
        ip.argb("#fff")


def test_colour_index_default_for_missing_and_rejects_unknown():
    legend, idx = ip.colour_index(pd.Series(["B", None, "A", "B"]), {"A": "#ff0000"}, order=["A", "B"])
    assert [n for n, _ in legend] == ["Default Colour", "A", "B"]
    assert idx.tolist() == [2, 0, 1, 2]
    assert legend[1][1] == ip.argb("#ff0000") and legend[2][1] == ip.argb("#808080")
    with pytest.raises(ValueError):
        ip.colour_index(pd.Series(["C"]), order=["A"])


def test_build_gas_contents(tmp_path):
    df = _df()
    out = ip.build_gas(df, tmp_path / "t.gas",
                       special=ip.SpecialColumns(east="X", north="Y", sample_id="SampleID", epsg=32647),
                       colour_by="ML_zona", colour_order=["Tinggi", "Sedang", "Rendah"],
                       colours={"Tinggi": "#d7191c"})
    z = zipfile.ZipFile(out)
    assert set(z.namelist()) == {"version.txt", "changelog.txt", "metadata.xml", "data.csv", "workspace.xml"}

    meta = ET.fromstring(z.read("metadata.xml"))
    cols = meta.find("columns").findall("column")
    assert [c.findtext("origonalName") for c in cols] == [ip.gas_escape(c) for c in df.columns]
    types = {c.findtext("origonalName"): c.findtext("type") for c in cols}
    assert types["Au_uppm"] == "Numeric" and types["SampleID"] == "Text"
    sp = meta.find("specialColumns")
    assert sp.findtext("map_epsg") == "32647" and sp.findtext("map_east") == "X" and sp.findtext("id") == "SampleID"
    names = [a.findtext("name") for a in meta.find("colourAttributes").findall("colourAttribute")]
    assert names == ["Default Colour", "Tinggi", "Sedang", "Rendah"]

    data = pd.read_csv(io.BytesIO(z.read("data.csv")), encoding="cp1252", keep_default_na=False)
    assert len(data) == len(df)  # row count preserved
    assert data.columns[-4:].str.strip().tolist() == ["__gas__extra__", "__gas__color__", "__gas__shape__", "__gas__size__"]
    assert data.iloc[:, -3].tolist() == [3, 0, 2, 1]  # Rendah, missing, Sedang, Tinggi
    assert data["Note"].tolist() == ["a_cb", "", "x_uy", "plain"]  # text escaped, missing stays empty
    assert data["Au_ppm"].tolist()[1] == ""  # NaN -> empty, not 0


def test_build_gas_rejects_missing_columns(tmp_path):
    with pytest.raises(KeyError):
        ip.build_gas(_df(), tmp_path / "t.gas", special=ip.SpecialColumns(east="nope"))
    with pytest.raises(KeyError):
        ip.build_gas(_df(), tmp_path / "t.gas", colour_by="nope")


def test_workflow_xml_links_frames_and_export(tmp_path):
    w = ip.Workflow("t", export_dir=tmp_path)
    w.select(["Au_ppm", "As_ppm"])
    fr = w.plot("Probability Plot", ip.A_PROB_PLOT, ["Au_ppm", "As_ppm"])
    w.action("Log Y axis", ip.A_LOG_Y, fr)
    w.export_window(tmp_path / "pp.png", fr, scale=2)
    w.save_as(tmp_path / "t.gas")
    root = ET.fromstring(w.xml().split("\n", 1)[1])

    ops = root.find("operations").findall("Operation.Action")
    assert [o.findtext("actionName") for o in ops] == [ip.A_SELECT, ip.A_PROB_PLOT, ip.A_LOG_Y, ip.A_EXPORT_WINDOW, ip.A_SAVE]
    pp_uuid = ops[1].get("uuid")
    assert ops[2].find("actionFrameID/opUUID").text == pp_uuid == ops[3].find("actionFrameID/opUUID").text
    assert ops[2].findtext("actionFrameID/title") == "Probability Plot [Au_ppm, As_ppm] "
    assert ops[3].findtext("actionState/m__exportedFilename").endswith("pp.png")
    assert ops[4].findtext("actionCreator/m__saveAs") == "true"
    assert root.findtext("exportConfig/exportOption") == "Overwrite"
    assert [s.text for s in root.find("columnsUsed/m__colNames")] == ["Au_ppm", "As_ppm"]
    assert w.write(tmp_path / "wf.xml").read_text(encoding="utf-8").startswith("<?xml")


def test_build_gas_drillhole_shapes_aliases(tmp_path):
    df = pd.DataFrame({"HoleID": ["H1", "H1", "H2"], "From": [0.0, 1.0, 0.0], "To": [1.0, 2.0, 1.0],
                       "Au_ppm": [0.1, 0.2, 0.3], "Status_Oksidasi": ["Oksida", None, "Sulfida"],
                       "ML_hmm_nama": ["S1", "S2", "S1"]})
    out = ip.build_gas(df, tmp_path / "dh.gas", special=ip.SpecialColumns(group="HoleID"),
                       drillhole=ip.Drillhole("HoleID", "From", "To"), colour_by="ML_hmm_nama",
                       shape_by="Status_Oksidasi", shape_order=["Oksida", "Sulfida"], shapes={"Sulfida": 10},
                       aliases={"Status_Oksidasi": "Zona oksidasi", "ML_hmm_nama": "Status HMM"})
    z = zipfile.ZipFile(out)
    meta = ET.fromstring(z.read("metadata.xml"))
    assert meta.findtext("specialColumns/group") == "HoleID"
    assert meta.findtext("DHOptions/fromField") == "From" and meta.findtext("DHOptions/toField") == "To"
    assert meta.findtext("DrillholeConfig/groupColumnName") == "HoleID"
    alias = {c.findtext("origonalName"): c.findtext("aliasName") for c in meta.find("columns")}
    assert alias["Status_uOksidasi"] == "Zona oksidasi" and alias["Au_uppm"] == "Au_uppm"
    assert meta.findtext("colourAttributes/title") == "Status HMM"  # legend title = alias
    sh = meta.find("shapeAttributes")
    assert sh.findtext("title") == "Zona oksidasi"
    entries = [(a.findtext("name"), a.findtext("shapeCode"), a.findtext("shape"), a.findtext("filled"))
               for a in sh.findall("shapeAttribute")]
    assert entries == [("Default Shape", "0", "0", "true"), ("Oksida", "1", "1", "true"),
                       ("Sulfida", "10", "1", "false")]  # code 10 = open symbol 1
    data = pd.read_csv(io.BytesIO(z.read("data.csv")), encoding="cp1252", keep_default_na=False)
    assert data.iloc[:, -2].tolist() == [1, 0, 2]  # shape index per row; missing -> default


def test_build_gas_refuses_element_alias_and_duplicate_names(tmp_path):
    df = pd.DataFrame({"Au_ppm": [1.0], "Fe_pct": [2.0], "Zona": ["A"]})
    with pytest.raises(ValueError, match="element"):
        ip.build_gas(df, tmp_path / "t.gas", aliases={"Au_ppm": "Au (ppm)"})
    with pytest.raises(ValueError, match="duplicate"):
        ip.build_gas(df, tmp_path / "t.gas", aliases={"Zona": "Fe_pct"})
    with pytest.raises(KeyError):
        ip.build_gas(df, tmp_path / "t.gas", drillhole=ip.Drillhole("HoleID", "From", "To"))


def test_title_list_truncates_like_iogas():
    assert ip.title_list(["a", "b"]) == "[a, b]"
    assert ip.title_list([str(i) for i in range(12)]) == "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, (+2)]"


def test_workflow_aliases_strip_log_diagram_and_responses(tmp_path):
    w = ip.Workflow("t", aliases={"ML_hmm_nama": "Status HMM", "HoleID": "Lubang"})
    w.select(["Au_ppm", "ML_hmm_nama"])
    w.configure_downhole("HoleID", "From", "To", ["RJDH005", "RJDH014"])
    sl = w.strip_log()
    w.trace_mode(sl, "Bar")
    st = w.strip_log(stacked=True)
    d = w.diagram("Exploration/Porphyry Cu Exploration/Scott Halley/Ca-Fe-S Ternary Plot.xml",
                  overwrite=["Ca_ppm", "Fe_ppm", "S_ppm"])
    w.export_window(tmp_path / "d.png", d)
    with pytest.raises(ValueError):
        w.trace_mode(sl, "Wiggly")
    root = ET.fromstring(w.xml().split("\n", 1)[1])
    ops = root.find("operations").findall("Operation.Action")
    assert [s.text for s in ops[0].find("actionCreator/columnList/m__colNames")] == ["Au_ppm", "Status HMM"]
    assert ops[1].findtext("actionState/groupName") == "Lubang"  # aliases used in the workflow
    assert [s.text for s in ops[1].find("actionState/selectedGroups")] == ["RJDH005", "RJDH014"]
    assert sl.title == "Strip Log [RJDH005, RJDH014] [Au_ppm, Status HMM] "
    assert ops[2].findtext("actionCreator/m__config/traceMode") == "WindowPerGroup"
    assert ops[3].findtext("actionState/m__mode") == "Bar" and ops[3].findtext("actionFrameID/opUUID") == sl.op_uuid
    assert ops[4].findtext("actionName") == ip.A_STRIP_LOG_STACKED and st.op_uuid == ops[4].get("uuid")
    assert ops[5].findtext("actionCreator/m__filename").startswith(ip.PROVIDED + "Exploration/")
    assert ops[6].findtext("actionFrameID/opUUID") == d.op_uuid
    assert ops[6].findtext("actionState/m__exportConfig/scaleX") == "3.0"  # HD default
    r = root.find("userResponses/UserResponse")
    assert r.findtext("message") == "OK to overwrite columns Ca_ppm, Fe_ppm, S_ppm to open diagram?."
    assert r.find("response").get("class") == "boolean" and r.findtext("response") == "true"
