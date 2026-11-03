import numpy as np
import pandas as pd

from src import geochem


def test_describe_counts_censoring_and_quantiles():
    v = pd.Series([1.0, 10.0, np.nan, 100.0, 0.5])
    c = pd.Series(["N", "N", "", "N", "Y"])
    d = geochem.describe(v, c)
    assert d["n_total"] == 5 and d["n_analisis"] == 4
    assert np.isclose(d["pct_tersensor"], 25.0)
    assert np.isclose(d["rerata_geometrik"], np.exp(np.log([1, 10, 100, 0.5]).mean()))
    assert d["P50"] == 5.5 and d["max"] == 100.0


def test_describe_empty_column():
    d = geochem.describe(pd.Series([np.nan, np.nan]))
    assert d["n_analisis"] == 0 and "P50" not in d


def test_containing_interval_by_hole():
    c_hole = np.array(["A", "A", "B", "A"])
    c_from = np.array([1.0, 0.0, 0.0, 2.0])
    c_to = np.array([2.0, 1.0, 1.0, 3.0])
    hole = np.array(["A", "A", "B", "B", "C", "A"])
    depth = np.array([0.5, 2.5, 0.2, 1.5, 0.5, 1.0])
    assert geochem.containing_interval(hole, depth, c_hole, c_from, c_to).tolist() == [1, 3, 2, -1, -1, 0]


def test_group_medians_drops_missing_groups():
    df = pd.DataFrame({"g": ["a", "a", "b", None, ""], "x": [1.0, 3.0, 5.0, 7.0, 9.0]})
    out = geochem.group_medians(df, "tanah", "g", ["x"])
    assert out.nilai_kelompok.tolist() == ["a", "b"]
    assert out.x_median.tolist() == [2.0, 5.0] and out.n.tolist() == [2, 1]
