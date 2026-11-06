import numpy as np
import pandas as pd
import pytest

from src import iogas_project as ip
from src import iogas_s4 as s4
from src import iogas_stage as st
from src.paths import PROCESSED

ASSAY = PROCESSED / "iogas" / "RJ_DH_assay.csv"


@pytest.fixture(scope="module")
def assay():
    if not ASSAY.exists():
        pytest.skip("processed assays not built")
    return pd.read_csv(ASSAY, low_memory=False)


def test_rjdh012_nag_counts(assay):
    d = s4.load_rjdh012(assay)
    assert len(d) == 118
    assert d.Kelas_NAG.value_counts().to_dict() == {"PAF-LC": 48, "NAF": 37, "PAF-HC": 21, s4.NO_NAG: 12}
    assert d.NAG_pH.notna().sum() == 106
    assert np.array_equal(d.S_pct.values, d.S_total_pct.values, equal_nan=True)
    assert set(d.Kelas_NAG) <= set(s4.NAG_COLOURS)
    assert set(d.Status_Oksidasi) <= set(s4.OX_SHAPES)
    ox = pd.crosstab(d.Status_Oksidasi, d.Kelas_NAG)
    assert ox.loc["Sulfida", "PAF-HC"] == 14 and ox.loc["Oksida", "NAF"] == 37


def test_assay_subset_and_metres(assay):
    d = s4.load_assays(assay)
    assert len(d) == 2466
    m = (d.To - d.From).groupby(d.ML_paf_kelola).sum().round(1).to_dict()
    assert m == {"NAF": 42.8, "PAF-HC": 2215.6, "PAF-LC": 796.6}
    assert set(d.ML_paf_kelola) <= set(s4.KELOLA_COLOURS)
    assert set(d.ML_paf_kelas) <= set(s4.KELAS_COLOURS)
    assert set(d.Prioritas_uji_NAG) <= set(s4.PRIORITY_COLOURS)
    t = s4.kelola_per_lubang(d)
    assert np.isclose(t.total_m.sum(), (d.To - d.From).sum())
    assert np.isclose(t[[c for c in t if c.startswith("m_uji_")]].sum().sum(), t.total_m.sum())


def test_sulfur_methods_never_merged(assay):
    d = s4.load_assays(assay)
    both = d.SCIS_log10.notna() & d.S2_log10.notna()
    assert not both.any()
    assert d.S2_log10.notna().sum() == d.S_sulfida_S2_pct.gt(0).sum()


def test_aliases_and_units():
    al = s4.log10_aliases(s4.RJ12_LOG + s4.DH_LOG)
    assert al["SCIS_log10"] == "log10 SCIS (%)"           # unchanged from Stages 1-3
    assert al["Au_log10" if "Au_log10" in al else "Cu_log10"].endswith("(ppm)")
    assert al["NAGkap_log10"] == "log10 Kapasitas NAG pH 4.5 (kg H2SO4/t)"
    assert al["Fe_log10"] == "log10 Fe (%)"
    for k, v in al.items():
        assert not ip.ELEMENT_COLUMN.match(k)
        v.encode("cp1252")


def test_summary(assay):
    d = s4.load_rjdh012(assay)
    t = s4.ringkasan_nag(d)
    allz = t[t.zona_oksidasi.eq("Semua")].set_index("kelas_nag")
    assert allz.n.to_dict() == {"NAF": 37, "PAF-HC": 21, "PAF-LC": 48, s4.NO_NAG: 12}
    assert allz.loc["PAF-HC", "median_S_sulfida_SCIS_pct"] > allz.loc["NAF", "median_S_sulfida_SCIS_pct"]


def test_halley_workflow_xml(tmp_path):
    w = ip.Workflow("t")
    w.select(["Fe_pct", "S_pct"])
    w.diagram("Exploration/Porphyry Cu Exploration/Scott Halley/Fe vs S with Pyrite Line.xml")
    w.diagram("Exploration/Porphyry Cu Exploration/Scott Halley/Ca-Fe-S Ternary Plot.xml",
              overwrite=["Fe_ppm", "S_ppm"])
    x = w.write(tmp_path / "w.xml").read_text()
    assert "Fe vs S with Pyrite Line.xml" in x and "OK to overwrite columns Fe_ppm, S_ppm" in x


def test_paf_palette_shared():
    assert st.PAF_COLOURS["PAF-HC"] == "#b2182b" and st.PAF_ORDER[0] == "PAF-HC"
