import numpy as np
import pandas as pd

from src import joins


def _assay():
    return pd.DataFrame({"SiteID": ["A", "A", "A", "B"],
                         "DepthFrom": [0.0, 0.5, 2.5, 0.0],
                         "DepthTo": [1.0, 1.5, 4.5, 1.0]})


def _log():
    return pd.DataFrame({"SiteID": ["A", "A", "A", "B"],
                         "DepthFrom": [0.0, 1.0, 2.0, 0.5],
                         "DepthTo": [1.0, 2.0, 5.0, 2.0],
                         "lab": ["x", "y", "y", "z"],
                         "pct": [0.0, 100.0, 50.0, 10.0]})


def test_midpoint_pick_and_tie_goes_deeper():
    out = joins.midpoint_join(_assay(), _log(), ["lab"], "t_")
    # row 1 midpoint 1.0 sits on the 0-1 / 1-2 boundary: the deeper interval wins
    assert out.lab.tolist()[:3] == ["x", "y", "y"]
    assert out.t_from.tolist()[:3] == [0.0, 1.0, 2.0]
    assert out.t_frac.tolist()[:3] == [1.0, 0.5, 1.0]


def test_missing_interval_and_holes_do_not_cross_match():
    out = joins.midpoint_join(_assay(), _log(), ["lab"], "t_")
    # hole B midpoint 0.5 is the top of B's only interval; hole A's 0-1 must not leak in
    assert out.lab.iloc[3] == "z" and not out.t_missing.iloc[3]
    a = pd.DataFrame({"SiteID": ["B"], "DepthFrom": [0.0], "DepthTo": [0.8]})
    miss = joins.midpoint_join(a, _log(), ["lab"], "t_")
    assert miss.t_missing.iloc[0] and pd.isna(miss.lab.iloc[0]) and pd.isna(miss.t_frac.iloc[0])


def test_mixed_labels():
    ov = joins.overlap_table(_assay(), _log())
    mixed = joins.mixed_labels(_assay(), _log(), "lab", ov)
    assert mixed.tolist() == [False, True, False, False]


def test_length_weighted_mean():
    ov = joins.overlap_table(_assay(), _log())
    lw = joins.length_weighted(_assay(), _log(), "pct", ov)
    assert np.allclose(lw.iloc[:3], [0.0, 50.0, 50.0])
    assert lw.iloc[3] == 10.0  # only the 0.5-1.0 part of B is logged


def test_unlogged_mineral_flags_are_na():
    m = pd.DataFrame({"DomMin1_h": ["py", "um", np.nan], "min_py": [True, False, np.nan],
                      "min_cu": [False, False, np.nan]})
    missing = pd.Series([False, False, True])
    out = joins.mask_unlogged(m, missing, ["min_py", "min_cu"])
    assert out.min_logged.tolist() == [True, False, False]
    assert out.min_py.iloc[0] and out.min_py.iloc[1:].isna().all()
    assert str(out.min_py.dtype) == "boolean"
