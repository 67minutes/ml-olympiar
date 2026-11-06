"""ioGAS Stage 5: final projects, Bahasa indexes and the submission folder (no ioGAS needed)."""
import hashlib
import zipfile

import pandas as pd
import pytest

from src import iogas_s5 as s5
from src import iogas_stage as st
from src.paths import INTERIM, ROOT

PROJ = ROOT / "outputs" / "iogas_project"
FIG = ROOT / "outputs" / "figures" / "iogas"
KIRIM = ROOT / "outputs" / "kirim"
ROWS = {"RJ_tanah_final_v1.gas": 188, "RJ_batuan_final_v1.gas": 382, "RJ_bor_komposit_final_v1.gas": 3057,
        "RJ_lingkungan_final_v1.gas": 2466}


@pytest.fixture(scope="module")
def picks():
    p = INTERIM / "s1_probplot_picks.csv"
    if not p.exists():
        pytest.skip("Stage 1 picks not present")
    return pd.read_csv(p)


def test_describe_figure_names():
    d = s5.describe_figure("s3_strip_hmm_kembar_005_014_v1.png")
    assert d["bab_laporan"].startswith("Bab 5") and "RJDH005" in d["isi"] and "x" in d["catatan_keterangan"]
    d = s5.describe_figure("s4_halley_FeS_rjdh012_v1.png")
    assert "S_pct" in d["catatan_keterangan"] and d["data"].startswith("lubang RJDH012")
    d = s5.describe_figure("s1_pp_kelas_tanah_Au_v1.png")
    assert "kelas ambang Au" in d["warna"] and "Au_ppm" in d["catatan_keterangan"]
    with pytest.raises(ValueError):
        s5.describe_figure("08_ambang_bor_v1.png")


def test_every_iogas_figure_indexed():
    pngs = sorted(p.name for p in FIG.glob("s[1-4]_*_v*.png"))
    idx = pd.read_csv(FIG / "indeks_gambar_iogas.csv", encoding="utf-8-sig")
    assert sorted(idx.file) == pngs and len(pngs) >= 129
    for c in ("bab_laporan", "jenis_plot", "warna", "isi"):
        assert idx[c].notna().all() and (idx[c].astype(str).str.len() > 0).all(), c


def test_project_index_matches_disk():
    idx = pd.read_csv(PROJ / "indeks_proyek_iogas.csv", encoding="utf-8-sig")
    on_disk = {p.relative_to(PROJ).as_posix() for p in PROJ.rglob("*.gas")}
    assert set(idx.file) == on_disk
    fin = idx[idx.jenis.eq("akhir")].set_index("file")
    assert set(fin.index) == set(s5.FINALS) == set(ROWS)
    assert fin.baris.to_dict() == ROWS
    assert idx.epsg_32647.all() and (idx.jendela_plot > 0).all()
    assert idx.data.notna().all()


def test_final_projects_on_disk():
    for name, n in ROWS.items():
        d = st.check_saved(PROJ / name, n)
        assert d.shape[1] > 100, name     # every CSV column, not a stage subset
        assert s5.gas_summary(PROJ / name)["jendela"] >= 7


def test_final_loaders(picks):
    t, al = s5.load_surface_final("tanah", picks)
    assert len(t) == 188 and {f"Kelas_{e}_pp" for e in picks[picks.dataset.eq("tanah")].element} <= set(t.columns)
    b, _ = s5.load_surface_final("batuan", picks)
    assert len(b) == 382 and (b.ML_zona == s5.NO_ZONE).sum() == 30 and b.ML_zona.notna().all()
    k, _ = s5.load_komposit_final()
    assert len(k) == 3057
    e, eal = s5.load_lingkungan_final(picks)
    assert len(e) == 2466 and e.Kelas_NAG.ne("Tanpa uji NAG").sum() == 106
    assert e.S_pct.notna().sum() == 118 and not any("," in v for v in {**al, **eal}.values())


def test_kirim_folder():
    man = pd.read_csv(KIRIM / "MANIFEST.csv", encoding="utf-8-sig")
    for r in man.itertuples():
        f = KIRIM / r.file
        assert f.stat().st_size == r.bytes
        if isinstance(r.sha256_sumber, str):
            assert hashlib.sha256(f.read_bytes()).hexdigest() == r.sha256_sumber
            src = ROOT / r.sumber    # the copy still matches its source (re-run 28_kirim.py if not)
            assert hashlib.sha256(src.read_bytes()).hexdigest() == r.sha256_sumber, r.sumber
    files = [p for p in KIRIM.rglob("*") if p.is_file()]
    assert sum(p.stat().st_size for p in files) < 25 * 1024 * 1024
    names = [p.relative_to(KIRIM).as_posix() for p in files]
    arcs = zipfile.ZipFile(KIRIM / "2_proyek_iogas" / "RJ_proyek_ioGAS.zip").namelist()
    assert set(ROWS) <= set(arcs) and "BACA_SAYA.txt" in arcs
    for n in names + arcs:
        assert "Technical Meeting" not in n and "raw" not in n.lower().split("/"), n
