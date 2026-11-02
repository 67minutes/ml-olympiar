import numpy as np
import pandas as pd

from src import composite


def _src():
    # hole A, EOH 4.4: 0-0.5 (2), 0.5-1.5 (4), 1.5-3.5 long (10), 3.5-4.4 NS-SEL
    return pd.DataFrame({"SiteID": ["A"] * 4,
                         "DepthFrom": [0.0, 0.5, 1.5, 3.5], "DepthTo": [0.5, 1.5, 3.5, 4.4],
                         "Au": [2.0, 4.0, 10.0, 99.0], "Cu": [np.nan, 4.0, 10.0, 99.0],
                         "no_sample": [False, False, False, True],
                         "S_method": ["SCIS", "SCIS", "S2", "none"],
                         "Au_cens_h": [True, False, False, pd.NA]})


def _grid():
    return composite.grid(pd.DataFrame({"SiteID": ["A"], "EndDepth": [4.4]}))


def test_grid_fractional_eoh():
    g = _grid()
    assert g.DepthFrom.tolist() == [0, 1, 2, 3, 4] and np.allclose(g.DepthTo, [1, 2, 3, 4, 4.4])
    assert np.isclose(g.comp_len.sum(), 4.4)


def test_length_weighted_offset_long_and_ns_sel():
    v = composite.composite(_src(), _grid(), ["Au", "Cu"])
    assert np.allclose(v.Au.iloc[:3], [3.0, 7.0, 10.0])
    assert np.isclose(v.Au.iloc[3], 10.0)  # 3-3.5 sampled (0.5 m), NS-SEL ignored
    assert np.isnan(v.Au.iloc[4])          # only NS-SEL: no weight
    assert np.isclose(v.Cu.iloc[0], 4.0)   # Cu covers exactly 0.5 m: enough
    v2 = composite.composite(_src(), _grid(), ["Cu"], min_cov=0.6)
    assert np.isnan(v2.Cu.iloc[0])


def test_quality_columns():
    q = composite.quality(_src(), _grid())
    assert np.allclose(q.comp_cov_m, [1.0, 1.0, 1.0, 0.5, 0.0])
    assert q.comp_nsrc.tolist() == [2, 2, 1, 1, 0]
    assert q.comp_shared_src.tolist() == [False, False, True, True, False]
    assert q.comp_ok.tolist() == [True, True, True, True, False]
    assert q.S_method_c.tolist() == ["SCIS", "mixed", "S2", "S2", "none"]


def test_ratio_of_sums():
    s = pd.DataFrame({"SiteID": ["A", "A"], "DepthFrom": [0.0, 0.5], "DepthTo": [0.5, 1.0],
                      "CN": [1.0, 9.0], "TOT": [10.0, 10.0], "ok": [True, True], "no_sample": [False, False]})
    g = composite.grid(pd.DataFrame({"SiteID": ["A"], "EndDepth": [1.0]}))
    r = composite.ratio(s, g, "CN", "TOT", s.ok)
    assert np.isclose(r.iloc[0], 0.5)  # (0.5*1 + 0.5*9) / (0.5*10 + 0.5*10), not mean(0.1, 0.9)


def test_cens_frac():
    c = composite.cens_frac(_src(), _grid(), "Au", "Au_cens_h")
    assert np.allclose(c.iloc[:4], [0.5, 0.0, 0.0, 0.0]) and np.isnan(c.iloc[4])


def test_metal_balance():
    src, g = _src(), _grid()
    v, cov = composite.composite(src, g, ["Au"], min_cov=0.0, return_cov=True)
    sampled = src[~src.no_sample]
    assert np.isclose((v.Au * cov.Au).sum(), (sampled.Au * (sampled.DepthTo - sampled.DepthFrom)).sum())
