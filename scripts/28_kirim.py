"""Submission folder for the 7 Nov 2026 email to the committee (deliverables 1-3; report and deck added by the team).

    uv run python scripts/28_kirim.py

Copies (never moves) finished files from data/processed/ and outputs/iogas_project/ into outputs/kirim/, with a
Bahasa README per deliverable, a zip of the ioGAS project (4 final projects at the top, supporting ones in
pendukung/) and MANIFEST.csv (file, bytes, sha256, source). Rebuilt from scratch on each run: outputs/kirim/ holds
copies only, nothing original. Checks: total < 25 MB (Gmail attachment limit), no raw data, no brief, no licence text.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.paths import PROCESSED, ROOT  # noqa: E402

OUT = ROOT / "outputs" / "kirim"
PROJ = ROOT / "outputs" / "iogas_project"
LIMIT = 25 * 1024 * 1024
FORBIDDEN = ("Technical Meeting", "data/raw", "data\\raw", ".claude", "LOG.md", "AGENTS.md")

# folder -> [(source relative to ROOT, name in the folder)]
FILES = {
    "1_validasi_data": [
        ("data/processed/validation_flags.csv", "validasi_flag.csv"),
        ("data/processed/validation_summary.csv", "validasi_ringkasan.csv"),
        ("data/processed/qaqc_precision.csv", "qaqc_presisi.csv"),
    ],
    "3_analisis_geokimia": [
        ("data/processed/geochem_analysis.csv", "analisis_geokimia.csv"),
        ("data/processed/geochem_analysis_kolom.csv", "analisis_geokimia_kamus_kolom.csv"),
        ("data/processed/geochem_statistik.csv", "statistik_unsur.csv"),
        ("data/processed/geochem_statistik_kelompok.csv", "statistik_per_kelompok.csv"),
        ("data/processed/element_thresholds_v2.csv", "ambang_unsur.csv"),
        ("data/processed/s1_ambang_perbandingan_v1.csv", "ambang_perbandingan_metode.csv"),
        ("data/processed/s1_aat_ringkasan_v1.csv", "pencilan_tukey.csv"),
        ("data/processed/s2_zona_ringkasan_v1.csv", "zona_permukaan_median.csv"),
        ("data/processed/s2_zona_vs_kelas_v1.csv", "zona_permukaan_vs_kelas_ambang.csv"),
        ("data/processed/s3_status_ringkasan_v1.csv", "satuan_hmm_median.csv"),
        ("data/processed/s3_status_per_lubang_v1.csv", "satuan_hmm_meter_per_lubang.csv"),
        ("data/processed/s4_kelas_nag_ringkasan_v1.csv", "kelas_nag_median_rjdh012.csv"),
        ("data/processed/s4_kelola_per_lubang_v1.csv", "pengelolaan_paf_naf_per_lubang.csv"),
    ],
}

README = {
    "1_validasi_data": """DELIVERABLE 1 - VALIDASI DATA (CSV)
Prospek Ramba Joring (RJ), OlympiAR 2026 Babak 2

validasi_flag.csv       Satu baris per masalah per data (sampel, interval atau lubang): kode pemeriksaan
                        (check_id), masalah, nilai, tingkat (severity), tindakan, catatan. Tidak ada data yang
                        dihapus; setiap masalah diberi tanda dan hanya dikeluarkan di dalam analisis tertentu.
validasi_ringkasan.csv  Satu baris per jenis pemeriksaan: jumlah data yang diperiksa dan yang ditandai.
qaqc_presisi.csv        Presisi dari pemeriksaan internal (Au/Ag terlarut sianida vs total, sampel ulang
                        batuan pada koordinat sama), karena data panitia tidak memuat standar, blank atau
                        duplikat lab.

Istilah: NS-SEL = interval tidak disampel; DL = batas deteksi; nilai di bawah DL diseragamkan ke DL
tertinggi per unsur dan diisi DL/2 dengan tanda "tersensor" (_cens). Nilai 0 pada data permukaan berarti
"tidak dianalisis" dan diubah menjadi kosong. Koordinat UTM WGS84 Zona 47N (EPSG:32647).
Kolom agents_ref merujuk ke dokumen aturan kerja internal tim; boleh diabaikan.
""",
    "2_proyek_iogas": """DELIVERABLE 2 - PROYEK ioGAS
Buka RJ_proyek_ioGAS.zip, lalu baca BACA_SAYA.txt di dalamnya. Empat proyek akhir (*_final_v1.gas)
ada di folder utama zip; proyek pendukung (satu per skema warna) ada di folder pendukung/.
Dibuka dengan ioGAS 8.3 (File > Open).
""",
    "3_analisis_geokimia": """DELIVERABLE 3 - ANALISIS GEOKIMIA (CSV)
Prospek Ramba Joring (RJ), OlympiAR 2026 Babak 2

analisis_geokimia.csv              Semua sampel (tanah, batuan, interval bor) dalam satu tabel: unsur yang
                                   sudah dibersihkan, kelas ambang, dan hasil model (kolom berawalan ML_).
analisis_geokimia_kamus_kolom.csv  Arti dan satuan setiap kolom tabel di atas.
statistik_unsur.csv                Statistik per unsur per jenis data (n, % tersensor, rerata geometrik,
                                   persentil P25-P98, ambang).
statistik_per_kelompok.csv         Median unsur per kelompok (zona kadar ML, alterasi, litologi, oksidasi,
                                   satuan HMM, kelas pengelolaan PAF/NAF).
ambang_unsur.csv                   Ambang per unsur per jenis data: model campuran Gauss (GMM, dengan selang
                                   bootstrap), median + 2 MAD, pagar Tukey, dan dua patahan dari plot
                                   probabilitas ioGAS (kolom thr_probplot_iogas, thr_probplot_iogas_2).
ambang_perbandingan_metode.csv     Kesesuaian patahan plot probabilitas dengan patahan GMM terdekat
                                   (dalam selang bootstrap / dalam faktor 2 / berbeda > 2x).
pencilan_tukey.csv                 Jumlah pencilan Tukey (log10) dari Anomaly Assessment Tool ioGAS, sama
                                   dengan hitungan ulang di Python (kolom sama).
zona_permukaan_median.csv          Median unsur per zona kadar ML (Tinggi/Sedang/Rendah), tanah dan batuan.
zona_permukaan_vs_kelas_ambang.csv Tabulasi silang zona kadar ML vs kelas ambang Au/As (Cramer's V).
satuan_hmm_median.csv              Median unsur per satuan geokimia bawah permukaan (HMM S1-S5).
satuan_hmm_meter_per_lubang.csv    Panjang (m) setiap satuan HMM per lubang bor.
kelas_nag_median_rjdh012.csv       Median pH NAG, kapasitas NAG, S dan unsur AMD per kelas NAG dan zona
                                   oksidasi (lubang RJDH012, satu-satunya dengan uji NAG).
pengelolaan_paf_naf_per_lubang.csv Panjang (m) per kelas pengelolaan NAF / PAF-LC / PAF-HC dan per prioritas
                                   uji NAG, per lubang bor.

Istilah: NAF = tidak membentuk asam; PAF-LC / PAF-HC = berpotensi membentuk asam dengan kapasitas
rendah / tinggi. Kelas pengelolaan = kelas terburuk yang masih mungkin menurut prediksi konformal (dipakai
untuk penanganan). Satuan HMM S1-S5 = satuan geokimia dari hidden Markov model pada komposit 1 m.
SCIS dan S2 = dua metode lab S sulfida (tidak dicampur). Nama kolom unsur: <unsur>_ppm atau _pct.
""",
    "4_laporan": "Letakkan laporan akhir (PDF) di sini sebelum dikirim.\n",
    "5_presentasi": "Letakkan presentasi (PowerPoint diekspor ke PDF) di sini sebelum dikirim.\n",
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def iogas_zip(dest: Path) -> list[str]:
    """Final projects at the top, supporting projects under pendukung/ (same sub-folders), README and index."""
    idx = pd.read_csv(PROJ / "indeks_proyek_iogas.csv", encoding="utf-8-sig")
    names = []
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(PROJ / "BACA_SAYA.txt", "BACA_SAYA.txt")
        for r in idx.itertuples():
            arc = r.file if r.jenis == "akhir" else f"pendukung/{r.file}"
            z.write(PROJ / r.file, arc)
            names.append(arc)
        idx = idx.assign(file=[f if j == "akhir" else f"pendukung/{f}" for f, j in zip(idx.file, idx.jenis)])
        z.writestr("indeks_proyek_iogas.csv", idx.to_csv(index=False).encode("utf-8-sig"))
    on_disk = {p.relative_to(PROJ).as_posix() for p in PROJ.rglob("*.gas")}
    assert on_disk == set(pd.read_csv(PROJ / "indeks_proyek_iogas.csv").file), "index out of date: run 27 --index"
    return names


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)   # copies only; rebuilt from the sources every run
    rows = []
    for folder, text in README.items():
        d = OUT / folder
        d.mkdir(parents=True)
        (d / "BACA_SAYA.txt").write_text(text, encoding="utf-8")
        for src, name in FILES.get(folder, []):
            s = ROOT / src
            shutil.copy2(s, d / name)
            rows.append({"file": f"{folder}/{name}", "sumber": src, "sha256_sumber": sha(s)})
    z = OUT / "2_proyek_iogas" / "RJ_proyek_ioGAS.zip"
    arcs = iogas_zip(z)
    rows.append({"file": "2_proyek_iogas/RJ_proyek_ioGAS.zip", "sumber": "outputs/iogas_project/ (semua .gas)",
                 "sha256_sumber": ""})
    man = pd.DataFrame(rows)
    man["bytes"] = [(OUT / f).stat().st_size for f in man.file]
    for r in man.itertuples():   # copies are byte-identical to their sources
        if r.sha256_sumber:
            assert sha(OUT / r.file) == r.sha256_sumber, r.file
    man.to_csv(OUT / "MANIFEST.csv", index=False, encoding="utf-8-sig")

    every = [p for p in OUT.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in every)
    inside = arcs + [p.relative_to(OUT).as_posix() for p in every]
    bad = [n for n in inside if any(f.lower() in n.lower() for f in FORBIDDEN)]
    assert not bad, f"forbidden files in the submission: {bad}"
    assert total < LIMIT, f"{total / 1e6:.1f} MB is over the 25 MB email limit"
    print(f"{len(every)} files, {total / 1e6:.2f} MB (< 25 MB); zip holds {len(arcs)} projects")
    print(man[["file", "bytes"]].to_string(index=False))


if __name__ == "__main__":
    main()
