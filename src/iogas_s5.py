"""Pure helpers for ioGAS Stage 5 (final projects and hand-off indexes); no ioGAS needed.

Used by scripts/27_iogas_s5_final.py. No new ML and no new numbers: the final projects carry the same tables as the
stage projects (all columns of the ioGAS-ready CSVs, plus the derived columns the stages added), and the indexes
describe files that already exist. Index text is Bahasa Indonesia for teammates and the committee.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

from src import iogas_project as ip
from src import iogas_s1 as s1
from src import iogas_s2 as s2
from src import iogas_s3 as s3
from src import iogas_s4 as s4
from src import iogas_stage as st
from src.paths import PROCESSED

IODIR = PROCESSED / "iogas"
NO_ZONE = "Tanpa zona ML"

# Bahasa display names for non-element columns (never alias element columns: build_gas refuses them)
SURFACE_AL = {**s2.BASE_AL, "ML_zona_p_maks": "Peluang maks zona ML", "ML_zona_stabil": "Stabilitas zona ML"}
BOR_AL = {"ML_hmm_nama": "Status HMM", "ML_hmm_status": "Nomor status HMM", "ML_hmm_stabil": "Stabilitas status HMM",
          "ML_hmm_p_maks": "Peluang maks status HMM", "Status_Oksidasi": "Zona oksidasi (log)",
          "Fasies_Alterasi": "Fasies alterasi (log)", "Kelompok_Litologi": "Kelompok litologi (log)",
          "CuCN_Cu_rasio": "Rasio CuCN/Cu"}
ENV_AL = {"Kelas_NAG": "Kelas NAG (uji)", "ML_paf_kelola": "Kelas pengelolaan PAF/NAF",
          "ML_paf_kelas": "Kelas konformal", "ML_paf_set": "Himpunan konformal",
          "ML_paf_n_set": "Ukuran himpunan konformal", "Prioritas_uji_NAG": "Prioritas uji NAG",
          "Status_Oksidasi": "Zona oksidasi (log)", "Fasies_Alterasi": "Fasies alterasi (log)", "S_metode": "Metode S",
          "NAG_pH": "pH NAG", "NAG_pH45_kgH2SO4_t": "Kapasitas NAG pH 4.5 (kg H2SO4/t)",
          "NAG_pH70_kgH2SO4_t": "Kapasitas NAG pH 7.0 (kg H2SO4/t)", "S_total_pct": "S total (%)",
          "S_sulfida_SCIS_pct": "S sulfida SCIS (%)", "S_sulfida_S2_pct": "S sulfida S2 (%)"}

# final project file -> (data in Bahasa, colour scheme, report chapter)
FINALS = {
    "RJ_tanah_final_v1.gas": ("Sampel tanah prospek RJ", "Zona kadar ML (Tinggi/Sedang/Rendah)", "Bab 3, 4"),
    "RJ_batuan_final_v1.gas": ("Sampel batuan prospek RJ", "Zona kadar ML (Tinggi/Sedang/Rendah)", "Bab 3, 4"),
    "RJ_bor_komposit_final_v1.gas": ("Komposit bor 1 m, 19 lubang", "Satuan geokimia HMM S1-S5", "Bab 5"),
    "RJ_lingkungan_final_v1.gas": ("Interval assay bor (semua lubang; uji NAG hanya RJDH012)",
                                   "Kelas pengelolaan PAF/NAF; bentuk simbol = zona oksidasi", "Bab 3, 6"),
}


def _classes(df: pd.DataFrame, ds: str, picks: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Probability-plot threshold class (frozen Stage 1 picks) for every picked element of `ds`."""
    df = df.copy()
    al = {}
    for r in picks[picks.dataset.eq(ds)].itertuples():
        c = f"Kelas_{r.element}_pp"
        df[c] = s1.classify(df[st.element_column(r.element)], r.pick1, r.pick2)
        al[c] = s2.kelas_alias(r.element)
    return df, al


def load_surface_final(ds: str, picks: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """All columns of RJ_tanah/RJ_batuan.csv for the Ramba Joring subset (as ML-1 and Stage 2), plus threshold
    classes for every picked element, zone confidence, sample type (rock) and log10 columns."""
    df = s1.subset(pd.read_csv(IODIR / f"{s1.DATASETS[ds][0]}.csv", low_memory=False), ds)
    df, kal = _classes(df, ds, picks)
    df["Keyakinan_zona"] = s2.keyakinan_zona(df.ML_zona_p_maks)
    if ds == "batuan":
        df["Jenis_sampel"] = s2.jenis_sampel(df.ML_zona_float)
    df["ML_zona"] = df.ML_zona.fillna(NO_ZONE)
    els = sorted(set(s1.DATASETS[ds][3]) | set(s2.BOX_EL[ds]))
    df, lal, _ = st.add_log10(df, els)
    al = {k: v for k, v in {**SURFACE_AL, **lal, **kal}.items() if k in df.columns}
    return df, al


def load_komposit_final() -> tuple[pd.DataFrame, dict[str, str]]:
    """All columns of RJ_DH_komposit_1m.csv for usable composites (as ML-4 and Stage 3), log10 columns."""
    d = s3.load_composites(pd.read_csv(IODIR / "RJ_DH_komposit_1m.csv", low_memory=False))
    al = {k: v for k, v in {**BOR_AL, **s3.log10_aliases()}.items() if k in d.columns}
    return d, al


def load_lingkungan_final(picks: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """All columns of RJ_DH_assay.csv for sampled intervals (as ML-5 and Stage 4): NAG label ('Tanpa uji NAG'
    outside the tested RJDH012 samples), `S_pct` = `S_total_pct` for the Halley diagram (only RJDH012 has total S),
    drillhole threshold classes from the Stage 1 picks, log10 columns."""
    d = s4.load_assays(pd.read_csv(IODIR / "RJ_DH_assay.csv", low_memory=False))
    d["Kelas_NAG"] = d.ML_paf_label.fillna(s4.NO_NAG)
    d["S_pct"] = d.S_total_pct
    d, kal = _classes(d, "bor", picks)
    els = sorted(set(s4.DH_LOG) | set(s4.RJ12_LOG) | {"Au", "Ag"})
    d, lal, _ = st.add_log10(d, els)
    al = {k: v for k, v in {**ENV_AL, **lal, **kal}.items() if k in d.columns}
    return d, al


# ------------------------------------------------------------------ indexes (Bahasa)
BAB = {"s1": "Bab 3 (QAQC, pencilan, ambang)", "s2": "Bab 4 (data permukaan)", "s3": "Bab 5 (data pemboran)",
       "s4": "Bab 6 (lingkungan)"}
TAHAP = {"s1": "Tahap ioGAS 1: QAQC dan ambang", "s2": "Tahap ioGAS 2: permukaan", "s3": "Tahap ioGAS 3: pemboran",
         "s4": "Tahap ioGAS 4: lingkungan", "final": "Tahap ioGAS 5: proyek akhir"}
DATA = {"tanah": "tanah (prospek RJ)", "batuan": "batuan (prospek RJ)", "bor": "assay/komposit bor",
        "rjdh012": "lubang RJDH012 (satu-satunya dengan uji NAG)", "DH": "interval assay bor, semua lubang"}
WARNA = {"zona": "zona kadar ML (Tinggi/Sedang/Rendah)", "keyakinan": "keyakinan zona ML (peluang maks)",
         "alterasi": "fasies alterasi hasil log", "oksidasi": "zona oksidasi hasil log",
         "hmm": "satuan geokimia HMM S1-S5", "status_hmm": "satuan geokimia HMM S1-S5",
         "kelola": "kelas pengelolaan PAF/NAF (NAF, PAF-LC, PAF-HC)",
         "kelas": "kelas konformal PAF/NAF (satu kelas pasti atau 'ambigu')",
         "uji_nag": "prioritas uji NAG", "kelas_nag": "kelas NAG hasil uji lab; bentuk = zona oksidasi",
         "lubang": "lubang bor", "tahun": "tahun lab", "tukey": "tanpa warna (kotak Tukey)",
         "duplikat": "jenis pasangan duplikat", "pp": "tanpa warna (dipilih buta)"}
PLOT = {"pp": "plot probabilitas (log)", "box": "box plot log10 bertingkat (Tukey)", "xy": "scatter log-log",
        "peta": "peta atribut (tampak atas)", "peta3d": "peta 3D XYZ (tampak atas)", "strip": "strip log bawah-lubang",
        "halley": "diagram klasifikasi Scott Halley (bawaan ioGAS)"}
UNSUR = {"SCIS": "S sulfida (SCIS)", "Stotal": "S total", "phNAG": "pH NAG", "kapNAG": "kapasitas NAG pH 4,5"}
CAT_EL = "Sumbu unsur tertulis seperti Au_ppm: nama kolom unsur tidak diterjemahkan agar ioGAS mengenali satuannya."
CAT_STRIP = "Skala sumbu-x tiap lubang dan tiap jalur berdiri sendiri: bandingkan pola, bukan panjang batang."
CAT_LEG = "Legenda warna tidak bisa diekspor ioGAS: tulis arti warna di keterangan gambar."


def _el(t: str) -> str:
    return UNSUR.get(t, t)


def describe_figure(name: str) -> dict:
    """Bahasa description of one ioGAS export (`s<N>_<…>_v<k>.png`) from its file name."""
    m = re.fullmatch(r"(s[1-4])_(.+)_v(\d+)\.png", name)
    if not m:
        raise ValueError(f"not an ioGAS stage figure name: {name}")
    stg, body = m.group(1), m.group(2)
    t = body.split("_")
    kind = t[0]
    ds = next((x for x in ("tanah", "batuan", "bor", "rjdh012") if x in t), "DH")
    notes = [CAT_LEG]
    warna, isi = "", ""
    if kind == "pp":
        if t[1] == "kelas":
            warna, isi = f"kelas ambang {t[3]} (Latar / Anomali lemah / Anomali kuat)", \
                f"Plot probabilitas {t[3]} dengan dua ambang hasil pembacaan plot sebagai kelas warna"
        elif t[1] == "Au" and "zona" in t:
            warna, isi = WARNA["zona"], "Plot probabilitas Au tanah per zona kadar ML"
        else:
            warna, isi = WARNA["pp"], f"Plot probabilitas {_el(t[2])} untuk membaca patahan populasi (ambang)"
    elif kind == "box":
        scheme = "_".join(x for x in t[1:] if x not in ("tanah", "batuan", "bor"))
        key = "kelas" if scheme.startswith("kelas_") and scheme != "kelas_nag" else scheme
        if scheme in ("amd_kelas_nag",):
            warna, isi = WARNA["kelas_nag"], "Unsur pembentuk air asam tambang (AMD) per kelas NAG, RJDH012"
        elif key == "kelas":
            el = scheme.split("_")[1]
            warna, isi = f"kelas ambang {el}", f"Sebaran log10 unsur per kelas ambang {el}"
        else:
            warna = WARNA.get(key, key)
            isi = {"tukey": "Pencilan Tukey per unsur (pagar 1,5 dan 3 IQR)",
                   "oksidasi": "Sebaran unsur bor per zona oksidasi", "lubang": "Au per lubang bor (cek bias lokasi)",
                   "tahun": "Au per tahun lab (cek bias era lab)"}.get(key, f"Sebaran log10 unsur per {warna}")
    elif kind == "xy":
        y, x = t[1], t[2]
        rest = "_".join(t[3:])
        scheme = re.sub(r"_?(tanah|batuan|bor|rjdh012)$", "", rest)
        if scheme.startswith("kelas_") and scheme != "kelas_nag":
            warna = f"kelas ambang {scheme.split('_')[1]}"
        else:
            warna = WARNA.get(scheme, scheme or "-")
        if x.endswith("CN") or y.endswith("CN"):
            isi = f"{y} terlarut sianida vs {x} total: presisi emas/perak (efek nugget)"
        elif y == "duplikat":
            isi, warna = f"Pasangan sampel ulang batuan, {x}: presisi lapangan", WARNA["duplikat"]
        else:
            isi = f"{_el(y)} vs {_el(x)}"
    elif kind in ("peta", "peta3d"):
        scheme = re.sub(r"_?(tanah|batuan|bor|rjdh012)$", "", "_".join(t[1:]))
        warna = f"kelas ambang {scheme.split('_')[1]}" if scheme.startswith("kelas_") else WARNA.get(scheme, scheme)
        isi = f"Sebaran sampel diwarnai {warna}"
    elif kind == "strip":
        if t[1] == "rjdh012":
            scheme = "_".join(t[2:])
            warna, isi = WARNA.get(scheme, scheme), "Strip log RJDH012: pH NAG, kapasitas NAG, S sulfida, S total"
        else:
            scheme = t[1] if t[1] not in ("uji",) else "uji_nag"
            where = t[-2:] if "kembar" in t else t[-1]
            warna = WARNA.get(scheme, scheme)
            if "kembar" in t:
                isi = f"Pasangan lubang kembar RJDH{where[0]} dan RJDH{where[1]}"
            elif where == "Lain":
                isi = "Lubang di luar penampang A-C (RJDH004, 010, 011)"
            else:
                isi = f"Lubang bor sepanjang penampang {where} (urut tenggara ke barat laut)"
            isi += ", jalur log10 unsur"
        notes.append(CAT_STRIP)
    elif kind == "halley":
        warna = WARNA["alterasi"] if ds == "batuan" else WARNA["kelas_nag"]
        isi = {"AlKMg": "Ternary Al-K-Mg (Scott Halley): mineral alterasi dari kimia, 26 batuan ICP lengkap",
               "FeS": "Fe vs S dengan garis pirit (Scott Halley); S_pct = S total",
               "CaFeS": "Ternary Ca-Fe-S (Scott Halley); Ca tersensor pada 106 dari 118 sampel"}[t[1]]
        if t[1] in ("FeS", "CaFeS"):
            notes.append("Kolom S_pct = S total (%), dibuat agar diagram bawaan ioGAS mengenali S.")
    else:
        raise ValueError(f"unknown plot type in {name}")
    if kind in ("pp", "box", "xy", "halley"):
        notes.insert(0, CAT_EL)
    if kind == "peta3d":
        notes.append("Tampak atas; rotasi ke penampang belum bisa diotomatisasi.")
    return {"file": name, "tahap": TAHAP[stg], "bab_laporan": BAB[stg], "data": DATA[ds],
            "jenis_plot": PLOT[kind], "warna": warna, "isi": isi, "catatan_keterangan": " ".join(notes)}


def figure_index(fig_dir: Path) -> pd.DataFrame:
    return pd.DataFrame([describe_figure(p.name) for p in sorted(fig_dir.glob("s[1-4]_*_v*.png"))])


def gas_summary(gas: Path) -> dict:
    """Rows, windows and colour legend title read from a saved .gas (ioGAS's own files)."""
    z = zipfile.ZipFile(gas)
    names = z.namelist()
    n = sum(1 for _ in z.open("data.csv")) - 1
    meta = z.read("metadata.xml").decode("utf-8", "replace")
    ws = z.read("workspace.xml").decode("utf-8", "replace") if "workspace.xml" in names else ""
    windows = ws.count("<m__plotFrameState>")
    title = re.search(r"<colourAttributes>\s*<title>\s*(.*?)\s*</title>", meta, flags=re.S)
    return {"baris": n, "jendela": windows, "epsg_32647": f"<map_epsg>{st.EPSG}</map_epsg>" in meta,
            "judul_warna": ip.gas_unescape(title.group(1)).strip() if title else ""}


def project_role(rel: str) -> tuple[str, str]:
    """(tahap, bab) for a saved project path relative to outputs/iogas_project/."""
    name = Path(rel).name
    if "_final_" in name:
        return TAHAP["final"], FINALS[name][2]
    m = re.search(r"_(s[1-4])(_|$)", name.replace(".gas", ""))
    stg = m.group(1) if m else "s1"
    return TAHAP[stg], BAB[stg]


def project_data(name: str) -> str:
    """Bahasa description of the rows in a saved project, from its file name."""
    if name in FINALS:
        return FINALS[name][0]
    if "RJDH012" in name:
        return "Lubang RJDH012 (satu-satunya dengan uji NAG), interval assay"
    if "_DH_" in name:
        return "Interval assay bor, semua lubang"
    if "_bor_s3" in name:
        return "Komposit bor 1 m, 19 lubang"
    if "_bor_" in name:
        return "Interval assay bor (tanpa interval tidak disampel)"
    if "duplikat" in name:
        return "Pasangan sampel ulang batuan (koordinat sama)"
    if "halley" in name:
        return "Batuan dengan analisis ICP lengkap (Al, K, Mg)"
    return "Sampel tanah prospek RJ" if "_tanah_" in name else "Sampel batuan prospek RJ"


BACA_SAYA = """PROYEK ioGAS - PROSPEK RAMBA JORING (RJ), DISTRIK MARTABE
OlympiAR 2026 Babak 2 - Deliverable 2 (Proyek ioGAS)

Semua plot di proyek ini digambar oleh ioGAS 8.3 (IMDEX) dari tabel data yang sudah divalidasi.
Koordinat: UTM WGS84 Zona 47N (EPSG:32647). Buka file .gas dengan File > Open di ioGAS.

1. PROYEK AKHIR (mulai dari sini)
{finals}

   Setiap proyek akhir memuat semua kolom data untuk sampel yang dianalisis: unsur (ppm atau %),
   kolom log10, kelas ambang dari plot probabilitas, dan keluaran model machine learning (kolom
   berawalan ML_). Jendela plot tersimpan di dalam proyek (plot probabilitas, box plot, scatter,
   strip log bawah-lubang, peta, diagram Scott Halley, Summary Statistics).

2. PROYEK PENDUKUNG (di file zip kiriman: folder pendukung/)
   Satu proyek per skema warna (ioGAS menyimpan satu skema warna per proyek), misalnya kelas
   ambang tiap unsur, keyakinan zona, alterasi hasil log, zona oksidasi, kelas konformal PAF/NAF.
   Nama file: _s1_ sampai _s4_ = tahap kerja ioGAS (1 QAQC, pencilan dan ambang; 2 data permukaan;
   3 data pemboran; 4 lingkungan); tanah / batuan / bor / DH (drillhole) = jenis data; _v1 = versi.
   Daftar lengkap: indeks_proyek_iogas.csv (kolom: file, tahap, bab laporan, data, warna, jumlah
   baris, jumlah jendela plot).

3. ISTILAH
   Zona kadar ML    : zona Tinggi / Sedang / Rendah dari pengelompokan tanpa label (PCA + model
                      campuran Gauss) pada log unsur; "Tanpa zona ML" = sampel tanpa data cukup.
   Kelas ambang     : Latar / Anomali lemah / Anomali kuat, dari dua patahan pada plot
                      probabilitas ioGAS (kolom Kelas_<unsur>_pp).
   Satuan HMM S1-S5 : satuan geokimia bawah permukaan dari hidden Markov model pada komposit 1 m
                      (Au, Ag, Cu, As); nama satuan menyebut kadar Au, Cu dan zona oksidasi dominan.
   NAF / PAF-LC / PAF-HC : batuan tidak membentuk asam / berpotensi asam dengan kapasitas rendah /
                      kapasitas tinggi. Kelas NAG = hasil uji lab (hanya lubang RJDH012).
                      Kelas pengelolaan = kelas terburuk yang masih mungkin menurut model
                      (prediksi konformal), dipakai untuk penanganan batuan.
   SCIS, S2         : dua metode lab untuk S sulfida, tidak dicampur. S total hanya ada di RJDH012.
                      Kolom S_pct = S total, dibuat agar diagram Scott Halley mengenali sulfur.
   Nama kolom unsur (mis. Au_ppm) sengaja tidak diterjemahkan: ioGAS membaca unsur dan satuan
   dari nama kolom.

Batasan: satu lubang dengan uji NAG (RJDH012); tidak ada ANC terukur; tidak ada sampel QAQC
(standar, blank, duplikat) di data panitia.
"""


def baca_saya(index: pd.DataFrame) -> str:
    fin = index[index.jenis.eq("akhir")]
    lines = [f"   {r.file}\n      {r.data}; {r.baris} baris; warna: {r.warna};\n"
             f"      {r.jendela_plot} jendela plot; {r.bab_laporan}" for r in fin.itertuples()]
    return BACA_SAYA.format(finals="\n".join(lines))
