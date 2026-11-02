import numpy as np
import pandas as pd
import pytest

from src import semantics as sem


@pytest.fixture
def jobs():
    # Job A: Ag floor 0.5 repeats 4/6 -> DL. Job B: Ag floor 0.25 repeats 3/5 -> DL.
    # Job C: single minimum 0.8 -> not a DL.
    return pd.DataFrame({
        "LabJobNo": list("AAAAAA") + list("BBBBB") + list("CC"),
        "AgPPM": [0.5, 0.5, 0.5, 0.5, 2.0, 3.0, 0.25, 0.25, 0.25, 0.4, 5.0, 0.8, 1.2],
    })


def test_analyte_columns_skips_ids_and_duplicates():
    df = pd.DataFrame(columns=["SampleID", "AuPPM", "AuPPB", "S2_SPCT", "NAGpH",
                               "NAGpH4.5_kgH2SO4/ton", "SizingPCT", "Easting"])
    assert sem.analyte_columns(df) == ["AuPPM", "S2_SPCT", "NAGpH", "NAGpH4.5_kgH2SO4/ton"]


def test_zeros_to_nan_counts_and_keeps_rows():
    df = pd.DataFrame({"CaPCT": [0, 1.2, np.nan, 0], "ID": [0, 1, 2, 3]})
    out, zeros = sem.zeros_to_nan(df, ["CaPCT"])
    assert zeros["CaPCT"] == 2 and out.CaPCT.isna().sum() == 3
    assert out.ID.tolist() == [0, 1, 2, 3]


def test_detect_floors(jobs):
    f = sem.detect_floors(jobs, ["AgPPM"]).set_index("job")
    assert f.loc["A", "is_censoring_floor"] and f.loc["A", "floor"] == 0.5
    assert f.loc["B", "is_censoring_floor"] and f.loc["B", "floor"] == 0.25
    assert not f.loc["C", "is_censoring_floor"]


def test_non_standard_floor_is_not_a_dl():
    df = pd.DataFrame({"LabJobNo": ["A"] * 6, "AsPPM": [36, 36, 36, 40, 55, 70]})
    f = sem.detect_floors(df, ["AsPPM"])
    assert f.repeats[0] and not f.is_censoring_floor[0]


def test_dl_or_half_gap_test():
    # floor 0.5 with values between 0.5 and 1.0 -> the floor is the DL
    assert sem.dl_or_half(pd.Series([0.5, 0.5, 0.5, 0.6, 0.8, 2.0]), 0.5) == ("DL", "gap")
    # floor 0.25, band (0.25, 0.5) empty, values sit at 0.5-1.0 -> already DL/2
    v = pd.Series([0.25] * 4 + [0.5, 0.6, 0.9, 3.0])
    assert sem.dl_or_half(v, 0.25) == ("DL/2", "gap")
    # integer data: band (1, 2) cannot hold a value -> pattern fallback, 1 -> DL
    assert sem.dl_or_half(pd.Series([1, 1, 1, 2, 3, 4]), 1.0) == ("DL", "pattern")
    # flat job at 2.5 -> pattern fallback -> DL/2
    assert sem.dl_or_half(pd.Series([2.5] * 5), 2.5) == ("DL/2", "pattern")


def test_harmonise_never_halves_twice():
    # Job A: DL 0.5 stored as 0.5. Job B: DL 0.5 stored as DL/2 = 0.25.
    df = pd.DataFrame({"LabJobNo": ["A"] * 6 + ["B"] * 6,
                       "AgPPM": [0.5, 0.5, 0.5, 0.6, 0.8, 2.0, 0.25, 0.25, 0.25, 0.5, 0.7, 0.9]})
    f = sem.detect_floors(df, ["AgPPM"])
    assert f.set_index("job").true_dl.tolist() == [0.5, 0.5]
    dl = sem.harmonised_dl(f, df.notna().sum())
    out = sem.harmonise(sem.flag_censored(df, f), f, dl)
    assert dl["AgPPM"] == 0.5
    # every censored value becomes 0.25 in both jobs; job B's 0.25 is not halved again
    assert (out.AgPPM_ml[out.AgPPM_cens_h.astype(bool)] == 0.25).all()
    assert out.AgPPM_cens_h.sum() == 7       # 0.5 x3, 0.25 x3, and job B's 0.5 (= DL)
    assert not out.AgPPM_dl_coarse.any()


def test_coarse_job_keeps_own_dl():
    # Big job DL 0.1 (gap test: DL); small job (< 10% of values) with DL 1.0.
    big = [0.1] * 5 + [0.15, 0.2, 0.3, 0.5, 0.8] * 8   # 45 values; job B = 3/48
    df = pd.DataFrame({"LabJobNo": ["A"] * len(big) + ["B"] * 3, "AgPPM": big + [1.0, 1.0, 1.0]})
    f = sem.detect_floors(df, ["AgPPM"])
    dl = sem.harmonised_dl(f, df.notna().sum())
    assert dl["AgPPM"] == 0.1                 # the 3-sample job does not set the DL
    out = sem.harmonise(sem.flag_censored(df, f), f, dl)
    b = out.LabJobNo == "B"
    assert out.AgPPM_dl_coarse[b].all() and (out.AgPPM_ml[b] == 0.5).all()
    assert (out.AgPPM_ml[~b & (out.AgPPM == 0.1)] == 0.05).all()


def test_harmonise_no_dl_keeps_values():
    df = pd.DataFrame({"LabJobNo": ["A"] * 3, "CuPPM": [np.nan, 3.0, 7.0]})
    f = sem.detect_floors(df, ["CuPPM"])
    out = sem.harmonise(df, f, pd.Series({"CuPPM": np.nan}))
    assert out.CuPPM_ml.isna().tolist() == [True, False, False]
    assert out.CuPPM_cens_h.isna().tolist() == [True, False, False]
    assert (out.CuPPM_ml[1:] == out.CuPPM[1:]).all()


def test_s_method():
    df = pd.DataFrame({"SCIS_PCT": [0.1, np.nan, np.nan], "S2_SPCT": [np.nan, 0.3, np.nan]})
    assert sem.add_s_method(df).S_method.tolist() == ["SCIS", "S2", "none"]
    with pytest.raises(AssertionError):
        sem.add_s_method(pd.DataFrame({"SCIS_PCT": [0.1], "S2_SPCT": [0.2]}))


def test_cn_ratios():
    df = pd.DataFrame({"AuPPM": [1.0, 1.0, 0.005, np.nan], "AuCNPPM": [0.5, 2.0, 0.05, 1.0],
                       "AuPPM_cens": pd.array([False, False, True, pd.NA], "boolean")})
    out = sem.add_cn_ratios(df)
    assert out.AuCN_ratio.tolist()[:2] == [0.5, 2.0]
    assert out.AuCN_ratio[2:].isna().all()          # censored and missing pairs
    assert out.flag_AuCN_gt_total.tolist()[:3] == [False, True, True]
    assert pd.isna(out.flag_AuCN_gt_total[3])


def test_parse_dates():
    assert sem.parse_dates(pd.Series([19980112]), fmt="%Y%m%d").dt.year[0] == 1998
    assert sem.parse_dates(pd.Series(["2/12/1998"]), dayfirst=True).dt.month[0] == 12
