import numpy as np
import pandas as pd
import pytest

from src import codes


def test_harmonise_case_keeps_nan():
    s = pd.Series(["Hm", "hm", np.nan, "PY"])
    out = codes.harmonise_case(s, "lower")
    assert out.iloc[[0, 1, 3]].tolist() == ["hm", "hm", "py"] and np.isnan(out.iloc[2])
    assert codes.harmonise_case(pd.Series(["prv", "PRV"]), "upper").tolist() == ["PRV", "PRV"]


def test_lith_group_and_unmapped_raises():
    df = pd.DataFrame({"Lith1Interp": ["VANh", "XUS-l", "SCR", "XUlo"]})
    out = codes.lith_group(df, "Lith1Interp")
    assert out.Lith_group.tolist() == ["Coherent dacite-andesite porphyry", "Phreatomagmatic breccia",
                                       "Surface cover", "Hydrothermal breccia"]
    assert out.Lith_group_id.notna().all()
    with pytest.raises(KeyError):
        codes.lith_group(pd.DataFrame({"Lith1Interp": ["ZZZ"]}), "Lith1Interp")


def test_alt_facies_ua_not_an_ml_class():
    out = codes.alt_facies(pd.DataFrame({"AltFacies": ["AA", "UA", "SI"]}), "AltFacies")
    assert out.Alt_facies_name.tolist()[0] == "Advanced argillic"
    assert out.alt_ml_label.isna().tolist() == [False, True, False]


def test_ox_state_and_sentinel():
    df = pd.DataFrame({"Comments": ["Oxide", "Sulphide", "Transition", np.nan, "Sulphide"],
                       "WRAltOxidPcnt": [0, 0, 50, 100, 95],
                       "WRAltSulphIntensity": [1, -999, 0, 2, 3]})
    out = codes.ox_state(df)
    assert out.ox_rank.tolist()[:3] == [0, 2, 1] and pd.isna(out.ox_rank.iloc[3])
    assert out.flag_ox_conflict.tolist() == [True, False, False, False, True]
    assert pd.isna(out.WRAltSulphIntensity_h.iloc[1]) and out.WRAltSulphIntensity.iloc[1] == -999


def test_ox_cutoffs_recover_rule():
    pct = np.array([0, 5, 10, 30, 40, 60, 80, 100] * 3)
    lab = np.where(pct <= 10, "Sulphide", np.where(pct <= 40, "Transition", "Oxide"))
    a, b = codes.fit_ox_cutoffs(pct, lab)
    assert (a, b) == (10, 40)
    assert codes.apply_ox_cutoffs(np.array([0, 20, 90]), a, b).tolist() == ["Sulphide", "Transition", "Oxide"]


def test_mineral_flags_across_columns():
    df = pd.DataFrame({"DomMin1_h": ["hm", "py", "um"], "DomMin2_h": [np.nan, "en", np.nan],
                       "SecMin1_h": ["ja", np.nan, np.nan]})
    out = codes.mineral_flags(df, ["DomMin1_h", "DomMin2_h", "SecMin1_h"])
    assert out.min_fe_ox.tolist() == [True, False, False]
    assert out.min_cu.tolist() == [False, True, False]
    assert out.min_ja.tolist() == [True, False, False]
    assert out.min_py.tolist() == [False, True, False]


def test_vocab_lookup_rejects_unknown():
    assert codes.lookup("mineral", "hm")["meaning_en"] == "hematite"
    with pytest.raises(KeyError):
        codes.lookup("mineral", "zz")
