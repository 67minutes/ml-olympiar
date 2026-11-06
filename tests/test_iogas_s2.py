import numpy as np
import pandas as pd
import pytest

from src import iogas_s2 as s2


def test_keyakinan_bins_edges_and_nan():
    p = pd.Series([0.95, 0.9, 0.89, 0.7, 0.69, 0.5, 0.49, np.nan])
    out = s2.keyakinan_zona(p)
    assert list(out[:7]) == ["Tinggi (>= 0.9)", "Tinggi (>= 0.9)", "Sedang (0.7-0.9)", "Sedang (0.7-0.9)",
                             "Rendah (0.5-0.7)", "Rendah (0.5-0.7)", "Ambigu (< 0.5)"]
    assert pd.isna(out.iloc[7])
    assert len(out) == len(p)
    assert set(s2.KEYAKINAN_COLOURS) == {k for k, _ in s2.KEYAKINAN}


def test_labels_are_cp1252_safe():
    for s in [*s2.KEYAKINAN_COLOURS, *s2.JENIS.values(), *s2.ALT_COLOURS]:
        s.encode("cp1252")


def test_jenis_sampel():
    out = s2.jenis_sampel(pd.Series(["Y", "N", np.nan, "x"]))
    assert out.iloc[0] == "Bongkah lepas (float)" and out.iloc[1] == "Singkapan"
    assert out.iloc[2:].isna().all()


def test_cramers_v_known_tables():
    perfect = pd.DataFrame([[10, 0], [0, 10]])
    assert s2.cramers_v(perfect) == pytest.approx(1.0)
    indep = pd.DataFrame([[10, 10], [10, 10]])
    assert s2.cramers_v(indep) == pytest.approx(0.0)
    assert np.isnan(s2.cramers_v(pd.DataFrame([[5, 5]])))


def test_zona_vs_kelas_counts():
    df = pd.DataFrame({"ML_zona": ["Tinggi", "Tinggi", "Sedang", "Rendah", np.nan],
                       "K": ["Anomali kuat", "Latar", "Latar", "Latar", "Latar"]})
    t = s2.zona_vs_kelas(df, "tanah", "Au", "K", ["Anomali kuat", "Anomali lemah", "Latar"])
    assert len(t) == 9 and t.n.sum() == 4 and (t.n_total == 4).all()
    r = t.set_index(["zona", "kelas_ambang"])
    assert r.loc[("Tinggi", "Anomali kuat"), "pct_zona"] == 50.0
    assert r.loc[("Rendah", "Latar"), "n"] == 1


def test_zona_ringkasan_skips_nan():
    df = pd.DataFrame({"ML_zona": ["Tinggi", "Tinggi", "Rendah"], "Au_ppm": [1.0, np.nan, 0.1]})
    r = s2.zona_ringkasan(df, "tanah", ["Au_ppm"]).set_index("zona")
    assert r.loc["Tinggi", "n"] == 1 and r.loc["Tinggi", "median"] == 1.0
    assert r.loc["Sedang", "n"] == 0 and np.isnan(r.loc["Sedang", "median"])
