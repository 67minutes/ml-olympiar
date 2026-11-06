import pandas as pd
import pytest

from src import iogas_project as ip
from src import iogas_s3 as s3
from src import iogas_stage as st
from src.paths import PROCESSED

KOMP = PROCESSED / "iogas" / "RJ_DH_komposit_1m.csv"
SECT = PROCESSED / "ml4_sections.csv"


@pytest.fixture(scope="module")
def komp():
    if not KOMP.exists():
        pytest.skip("processed composites not built")
    return s3.load_composites(pd.read_csv(KOMP, low_memory=False))


def test_subset_matches_ml4(komp):
    assert len(komp) == 3057
    counts = {s.split()[0]: n for s, n in komp.ML_hmm_nama.value_counts().items()}
    assert counts == {"S1": 533, "S2": 776, "S3": 368, "S4": 643, "S5": 737}
    assert komp.Status_Oksidasi.notna().all()
    assert {f"{e}_log10" for e in s3.LOG_EL} <= set(komp.columns)


def test_state_order_and_palette(komp):
    order = s3.state_order(komp.ML_hmm_nama)
    assert [s.split()[0] for s in order] == ["S1", "S2", "S3", "S4", "S5"]
    cols = s3.state_colours(komp.ML_hmm_nama)
    assert list(cols) == order and len(set(cols.values())) == 5
    for s in order:
        s.encode("cp1252")


def test_sections_cover_all_holes_once(komp):
    holes = sorted(komp.HoleID.unique())
    sec = s3.section_holes(pd.read_csv(SECT), holes)
    flat = [h for hs in sec.values() for h in hs]
    assert sorted(flat) == holes and len(flat) == len(set(flat)) == 19
    assert sec[s3.OFF_SECTION] == ["RJDH004", "RJDH010", "RJDH011"]
    assert len(sec["A"]) == 6 and len(sec["B"]) == 6 and len(sec["C"]) == 4
    assert {h for pad in s3.TWIN_PADS for h in pad} <= set(holes)


def test_section_order_follows_kolar_x():
    sec = pd.DataFrame({"penampang": ["A", "A", "A"], "SiteID": ["H2", "H1", "H3"], "kolar_x": [20.0, 10.0, 30.0]})
    assert s3.section_holes(sec, ["H1", "H2", "H3", "H9"]) == {"A": ["H1", "H2", "H3"], s3.OFF_SECTION: ["H9"]}


def test_summaries():
    d = pd.DataFrame({"HoleID": ["H1", "H1", "H2", "H2"], "From": [0, 1, 0, 1], "To": [1, 2, 1, 2],
                      "ML_hmm_nama": ["S2 b", "S1 a", "S1 a", "S1 a"], "Au_ppm": [1.0, 2.0, 4.0, None]})
    r = s3.status_ringkasan(d, ["Au_ppm"])
    s1 = r[r.status_hmm.eq("S1 a")].iloc[0]
    assert s1.n_komposit == 3 and s1.n_lubang == 2 and s1.n_nilai == 2 and s1["median"] == 3.0
    m = s3.status_per_lubang(d).set_index("HoleID")
    assert list(m.columns) == ["S1 a", "S2 b", "total_m"]
    assert m.loc["H1", "S1 a"] == 1.0 and m.loc["H2", "total_m"] == 2.0


def test_log10_aliases_are_not_element_columns():
    al = s3.log10_aliases()
    assert al["Au_log10"] == "log10 Au (ppm)" and al["SCIS_log10"] == "log10 SCIS (%)"
    assert not any(ip.ELEMENT_COLUMN.match(c) for c in al)


def test_oxidation_palette_shared():
    assert s3.OX_MISSING in st.OX_COLOURS
