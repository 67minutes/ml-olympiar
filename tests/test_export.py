import numpy as np
import pandas as pd
import pytest

from src import export


def test_iogas_name():
    assert export.iogas_name("AuPPM_ml") == "Au_ppm"
    assert export.iogas_name("FePCT_ml") == "Fe_pct"
    assert export.iogas_name("AuCNPPM_ml") == "AuCN_ppm"
    assert export.iogas_name("SCIS_PCT_ml") == "S_sulfida_SCIS_pct"
    assert export.iogas_name("S2_SPCT_ml") == "S_sulfida_S2_pct"
    assert export.iogas_name("S_PCT_ml") == "S_total_pct"
    assert export.iogas_name("NAGpH_ml") == "NAG_pH"
    assert export.iogas_name("NAGpH4.5_kgH2SO4/ton_ml") == "NAG_pH45_kgH2SO4_t"
    assert export.iogas_name("NAGpH7.0_kgH2SO4/ton_ml") == "NAG_pH70_kgH2SO4_t"
    with pytest.raises(KeyError):
        export.iogas_name("Lith1Interp")


def test_to_yn():
    s = pd.Series([True, False, np.nan, "True", "False"], dtype=object)
    assert export.to_yn(s).tolist() == ["Y", "N", "", "Y", "N"]
    with pytest.raises(ValueError):
        export.to_yn(pd.Series(["maybe"]))


def test_long_flags_shape():
    df = pd.DataFrame({"SiteID": ["A", "A"], "SampleID": ["s1", "s2"], "DepthFrom": [0, 1], "DepthTo": [1, 2],
                       "dz": [5.0, 40.0]})
    out = export.long_flags(df, df.dz > 30, dataset="assay", check_id="X1", issue="big", severity="error",
                            action="flagged", agents_ref="§0", value=df.dz)
    assert list(out.columns) == export.FLAG_COLUMNS
    assert len(out) == 1 and out.record_id.iloc[0] == "s2" and out.site_id.iloc[0] == "A"
    assert out.depth_to.iloc[0] == 2 and out.value.iloc[0] == "40.0"


def test_interval_checks_detect_planted_errors():
    collar = pd.DataFrame({"SiteID": ["A"], "EndDepth": [10.0]})
    ok = pd.DataFrame({"SiteID": ["A"] * 3, "DepthFrom": [0, 2, 5], "DepthTo": [2, 5, 10]})
    assert export.interval_checks(ok, collar) == {"overlaps": 0, "gaps": 0, "nonpositive_length": 0,
                                                  "past_eoh": 0}
    bad = pd.DataFrame({"SiteID": ["A"] * 4, "DepthFrom": [0, 1.5, 5, 9], "DepthTo": [2, 5, 5, 11]})
    assert export.interval_checks(bad, collar) == {"overlaps": 1, "gaps": 1, "nonpositive_length": 1,
                                                   "past_eoh": 1}


def test_group_cv():
    df = pd.DataFrame({"g": [1, 1, 2, 2], "Au": [1.0, 3.0, 2.0, 2.0]})
    out = export.group_cv(df, "g", ["Au"])
    assert out.n.tolist() == [2, 2]
    assert np.isclose(out.cv_pct.iloc[0], 100 * np.std([1, 3], ddof=1) / 2) and out.cv_pct.iloc[1] == 0


def test_merge_ml(tmp_path):
    df = pd.DataFrame({"SampleID": ["a", "b", "c"], "Au_ppm": [1, 2, 3]})
    pd.DataFrame({"SampleID": ["a", "c"], "ML_zone": ["H", "L"]}).to_csv(tmp_path / "tanah__ml3.csv", index=False)
    out = export.merge_ml(df, ["SampleID"], tmp_path, "tanah")
    assert out.ML_zone.tolist()[0] == "H" and pd.isna(out.ML_zone.iloc[1]) and len(out) == 3
    # a file for another target is ignored even if it shares the key name
    assert "ML_zone" not in export.merge_ml(df, ["SampleID"], tmp_path, "batuan")
    pd.DataFrame({"SampleID": ["a"], "zone": ["H"]}).to_csv(tmp_path / "tanah__bad.csv", index=False)
    with pytest.raises(ValueError):
        export.merge_ml(df, ["SampleID"], tmp_path, "tanah")
