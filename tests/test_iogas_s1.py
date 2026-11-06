"""Offline checks for ioGAS Stage 1 helpers (src/iogas_s1.py) and the AAT workflow XML."""
import numpy as np
import pandas as pd
import pytest

from src import iogas_project as ip
from src import iogas_s1 as s1
from src.paths import PROCESSED

IODIR = PROCESSED / "iogas"


def test_subsets_match_ml1_counts():
    thr = pd.read_csv(PROCESSED / "element_thresholds.csv").set_index(["dataset", "element"])
    for ds, (stem, *_rest, els) in s1.DATASETS.items():
        d = s1.subset(pd.read_csv(IODIR / f"{stem}.csv", low_memory=False), ds)
        for el in els:
            assert d[s1.column(el)].notna().sum() == thr.loc[(ds, el), "n_analysed"], (ds, el)


def test_classify_two_and_one_pick():
    v = pd.Series([0.1, 1.0, 2.0, 5.0, np.nan])
    assert s1.classify(v, 1.0, 5.0).tolist()[:4] == ["Latar", "Anomali lemah", "Anomali lemah", "Anomali kuat"]
    assert pd.isna(s1.classify(v, 1.0, 5.0).iloc[4])
    assert s1.classify(v, 1.0).tolist()[:4] == ["Latar", "Anomali kuat", "Anomali kuat", "Anomali kuat"]
    with pytest.raises(ValueError):
        s1.classify(v, 5.0, 1.0)


def test_tukey_and_aat_label_counts():
    v = pd.Series([1, 2, 2, 3, 3, 3, 4, 4, 5, 1000.0])
    t = s1.tukey_counts(v, log=True)
    assert t["atas"] == 1 and t["bawah"] == 0
    labels = pd.Series(["+Au_uppm*", "-Au_uppm", None, "+Au_uppm"])  # as read from a saved .gas
    assert s1.aat_counts(labels, "Au_ppm") == {"atas": 2, "atas_jauh": 1, "bawah": 1, "bawah_jauh": 0}


def test_duplicate_pairs():
    df = pd.DataFrame({"SampleID": ["a", "b", "c", "d", "e"], "dupxy_group": [1, 1, 1, 2, np.nan],
                       "dupxy_type": ["x", "x", "y", "x", None], "X": [0, 0, 0, 1, 2], "Y": [0, 0, 0, 1, 2],
                       "Au_ppm": [1.0, 2.0, 3.0, 4.0, 5.0]})
    p = s1.duplicate_pairs(df, ["Au"])
    assert len(p) == 2 and p.Sampel_1.tolist() == ["a", "a"] and p.Au_2.tolist() == [2.0, 3.0]


def test_compare_thresholds_maths():
    thr = pd.DataFrame([{"dataset": "tanah", "element": "Au", "thr_gmm_main": 1.0, "K": 2, "thr_mad": 2.0,
                         "thr_tukey": 3.0, "T1": 1.0, "T1_ci05": 0.8, "T1_ci95": 1.2,
                         **{f"T{k}{s}": np.nan for k in (2, 3, 4) for s in ("", "_ci05", "_ci95")}}])
    picks = pd.DataFrame([{"dataset": "tanah", "element": "Au", "pick1": 1.1, "pick2": 4.0, "confidence": "m"}])
    data = {"tanah": pd.DataFrame({"Au_ppm": [0.5, 1.05, 1.5, 5.0]})}
    c = s1.compare_thresholds(thr, picks, data).iloc[0]
    assert c.pp1_kesesuaian_T == "dalam CI bootstrap"
    assert c.pp2_kesesuaian_T == "berbeda (> 2x)"
    assert c.pp1_log10_beda_gmm_utama == pytest.approx(np.log10(1.1), abs=1e-3)
    assert c.pct_di_atas_pp1 == 50.0


def test_aat_xml():
    w = ip.Workflow("t")
    w.select(["Au_ppm"])
    w.aat(prefix="AAT_Au_", tails="upper")
    x = w.xml()
    assert ip.A_AAT + "$AATCalculateActionCreator" in x and "UpperLowerEntry$2" in x
    assert "<m__logData>true</m__logData>" in x and "<m__columnPrefix>AAT_Au_</m__columnPrefix>" in x
