# Panduan Tim: Ramba Joring, OlympiAR 2026 Babak 2

Panduan ini untuk anggota tim yang menulis laporan, membuat peta akhir, menyusun slide, dan
presentasi. Isinya: untuk setiap bab laporan, file mana yang dipakai, pekerjaan yang masih terbuka,
referensi yang harus diverifikasi, dan cara memakai repo.

**Temuan ML, angka kunci, cara membaca gambar, keterbatasan, ucapan presentasi dan pertanyaan juri
yang mungkin ada di Laporan ML:
[`outputs/laporan_ml/laporan_ml_v1.html`](outputs/laporan_ml/laporan_ml_v1.html)** (satu file, buka
dengan browser; bisa dicetak ke PDF). Rincian teknis lengkap ada di `LOG.md` (bahasa Inggris).
Ringkasan teknis ada di `README.md`.

> **Repo ini PRIVAT, khusus tim.** Isinya data rahasia dari panitia dan file brief (yang memuat
> kunci lisensi ioGAS kita). Jangan jadikan publik, jangan unggah data ke layanan AI/ML daring,
> dan jangan menyalin kunci lisensi atau kontak panitia ke mana pun.

## 1. Ringkasan proyek

- **Prospek:** Ramba Joring (RJ), distrik emas Martabe, Sumatra Utara. Sistem epitermal
  sulfidasi tinggi Au-Cu: silika vuggy, argilik lanjut kuarsa-alunit, Cu enargit/kovelit, emas
  dominan di zona oksida.
- **Tema babak 2:** "Orebody to Ecosystem: Integrating Mining Performance and Environmental
  Resilience". Tema utama penilaian adalah **Machine Learning**.
- **Tenggat:** pengiriman **7 November 2026, 23.59 WIB** lewat email ke panitia. Presentasi
  14–15 November 2026. Nilai: **presentasi 60%, laporan 40%**, jadi setiap hasil harus bisa
  dijelaskan secara lisan.
- **Deliverable:**
  1. Validasi data (CSV): `data/processed/validation_flags.csv`, `validation_summary.csv`,
     `qaqc_precision.csv`.
  2. Proyek ioGAS: dibuat oleh rekan ioGAS dari `data/processed/iogas/*.csv`.
  3. Analisis geokimia (CSV): `data/processed/geochem_analysis.csv` dan tiga tabel pendampingnya.
  4. Laporan (PDF).
  5. Presentasi (PowerPoint diekspor ke PDF).
- **Format laporan (dari brief):** Bahasa Indonesia (EYD), Times New Roman (judul 16, subjudul
  14, isi dan keterangan 12), teks hitam, potret, satu kolom, gambar HD. Peta/penampang boleh
  lanskap. Bonus hanya dihitung jika semua sub-parameter lengkap. Setiap referensi harus ditautkan
  dan dilampirkan.

Semua gambar di `outputs/figures/` dan peta di `outputs/maps/` sudah berlabel Bahasa Indonesia,
300 dpi. **Jangan menimpa gambar yang sudah masuk laporan**; buat versi `_v2`.

## 2. Peta file per bab laporan

### Bab 1. Pendahuluan
Latar belakang, tujuan, dan alur kerja. Sebutkan bahwa seluruh pengolahan dilakukan secara lokal
dengan perangkat lunak gratis (Python, QGIS) dan ioGAS berlisensi, tanpa layanan daring.

### Bab 2. Lokasi dan Geologi Regional
- Sumber geologi: `data/raw/Geological Resume_OlympiAR_2026.pdf`.
- Topografi prospek: `gis/lidar_dem.tif` dan `gis/hillshade.tif` (DEM lidar 5 m dari kontur
  panitia; interpolasi spline, diuji dengan menghapus kontur lalu membangunnya kembali).
- **Belum ada:** peta lokasi regional. Unduh DEMNAS dari BIG (Badan Informasi Geospasial) untuk
  konteks regional saja, dan cantumkan sumbernya.

### Bab 3. QAQC dan Validasi Data
Bobot rubrik: QAQC 30, perlakuan outlier 35, nilai ambang 35. Ditambah ML (klasifikasi dari
kimia).

- **File:** `validation_flags.csv` (satu baris per masalah per data), `validation_summary.csv`
  (satu baris per pemeriksaan), `qaqc_precision.csv`, `element_thresholds.csv`,
  `ml2_scores.csv`, `ml2_review_list.csv`.
- **Gambar:** `07_au_lubang_tahun_v1.png` (Au per lubang dan tahun lab),
  `08_ambang_{bor,batuan,tanah}_v1.png`, `08_bic_v1.png`, `09_skor_v1.png`,
  `09_matriks_konfusi_v1.png`, `09_shap_v1.png`, `09_shap_dependensi_v1.png`,
  `09_reliabilitas_v1.png`, `09_skor_pad_v1.png`.
- **Temuan, angka kunci dan ucapan presentasi:** [Laporan ML](outputs/laporan_ml/laporan_ml_v1.html#fondasi), [ML-1](outputs/laporan_ml/laporan_ml_v1.html#ml1) dan [ML-2](outputs/laporan_ml/laporan_ml_v1.html#ml2)

### Bab 4. Data Permukaan
Bobot rubrik: tanah 25, batuan 25, zonasi 50.

- **File:** `ml3_summary.csv`, `ml3_comparisons.csv`, `geochem_statistik_kelompok.csv`;
  `gis/ml3_zonasi.gpkg`, `gis/ml3_tanah_{zona,indeks,indeks_sd,p_tinggi,p_rendah}.tif`.
- **Gambar:** `10_pca_biplot_v1.png`, `10_bic_stabilitas_v1.png`, `10_zona_unsur_v1.png`,
  `10_variogram_arah_v1.png`, `10_gp_cv_v1.png`. Peta zonasi akhir dibuat di QGIS dari layer
  `gis/` (proyek pemeriksaan: `outputs/maps/qc/10_ml3_check.qgz`).
- **Temuan, angka kunci dan ucapan presentasi:** [Laporan ML](outputs/laporan_ml/laporan_ml_v1.html#ml3)

### Bab 5. Data Pemboran
Bobot rubrik: validasi 20, korelasi 40, geokimia-stratigrafi 40. Maksimal 3 penampang.

- **File:** `ml4_summary.csv`, `ml4_states.csv`, `ml4_comparisons.csv`, `ml4_sections.csv`;
  `gis/ml4_hmm.gpkg`, `gis/ml4_penampang.gpkg`, `gis/drillholes.gpkg`.
- **Gambar:** `11_pemilihan_K_v1.png`, `11_profil_status_v1.png`, `11_matriks_transisi_v1.png`,
  `11_strip_log_v1.png`, `11_kontinuitas_v1.png`.
- **Peta/penampang (siap pakai):** `outputs/maps/11_penampang_{A,B,C}_v1.png`,
  `11_peta_indeks_penampang_v1.png`; proyek QGIS `outputs/maps/11_ml4_penampang.qgz`.
- **Temuan, angka kunci dan ucapan presentasi:** [Laporan ML](outputs/laporan_ml/laporan_ml_v1.html#ml4)

### Bab 6. Analisis Lingkungan
Bobot rubrik: unsur AMD 40, klasifikasi PAF/NAF dan penanganan 60. **Diagram alir wajib.**

- **File:** `ml5_summary.csv`, `ml5_scores.csv`, `ml5_conformal.csv`, `ml5_per_hole.csv`,
  `ml5_uji_nag.csv` (daftar interval yang perlu uji NAG), `ml5_napp.csv`, `ml5_clusters.csv`,
  `drainase_ringkasan.csv`; `gis/ml5_paf.gpkg`, `gis/drainage.gpkg`.
- **Gambar:** `12_diagram_alir_paf_naf_v1.png` (**diagram alir wajib**),
  `12_nag_ph_kapasitas_v1.png`, `12_profil_rjdh012_v1.png`, `12_cakupan_konformal_v1.png`,
  `12_matriks_kebingungan_v1.png`, `12_shap_lengkap_v1.png`, `12_gmm_u1_u2_v1.png`,
  `12_ringkasan_lubang_v1.png`, `12_napp_proksi_v1.png`.
- **Temuan, angka kunci dan ucapan presentasi:** [Laporan ML](outputs/laporan_ml/laporan_ml_v1.html#ml5)

### Bab 7. Sintesis Eksplorasi (+ Bonus desain eksplorasi)
Bobot rubrik: prospeksi 50, eksplorasi lanjutan 50; bonus desain 100. Maksimal 4 penampang.

- **File:** `ml6_summary.csv`, `ml6_cv.csv`, `ml6_kandidat.csv`, `ml6_usulan_lubang.csv`
  (format kolar/survei, siap untuk ioGAS); `gis/ml6_target.gpkg`, `gis/ml6_penampang.gpkg`,
  `gis/ml6_{ucb_maks,meter_cutoff,sd_rerata}.tif`.
- **Gambar:** `13_profil_theta_v1.png`, `13_cv_lopo_v1.png`, `13_variogram_gp_v1.png`,
  `13_peringkat_kandidat_v1.png`.
- **Peta/penampang bonus (siap pakai):** `outputs/maps/13_peta_desain_v1.png`,
  `13_penampang_desain_v1.png` (D–D'); proyek QGIS `outputs/maps/13_ml6_desain.qgz`.
- **Temuan, angka kunci dan ucapan presentasi:** [Laporan ML](outputs/laporan_ml/laporan_ml_v1.html#ml6)

### Bab 8. Kesimpulan
Rangkum per bab di atas. Tekankan tema "ML yang tahu apa yang tidak diketahuinya": setiap peta
dan kelas punya ukuran ketidakpastian (probabilitas, stabilitas bootstrap, himpunan konformal,
deviasi standar kriging).

- **Temuan, angka kunci dan ucapan presentasi:** [Laporan ML](outputs/laporan_ml/laporan_ml_v1.html#sintesis)

### Bab 9. Daftar Pustaka
Lihat bagian 4 di bawah. **Semua referensi wajib diperiksa dari sumber aslinya.**

### Pembahasan tambahan: pembanding literatur (§9)
Dapat dimasukkan sebagai subbab diskusi (Bab 3/5) atau satu slide cadangan.

- **Gambar:** `14_jansson_vs_gmm_v1.png`, `14_rf_vs_hmm_v1.png`. File: `s9_*.csv`.
- Kedua makalah (Jansson dkk. 2022; Fontana dkk.) masih `[VERIFY]`. Jangan bandingkan akurasi kita
  dengan 82,5% Fontana.
- **Temuan, angka kunci dan ucapan presentasi:** [Laporan ML](outputs/laporan_ml/laporan_ml_v1.html#pembanding)

## 3. Pekerjaan terbuka untuk manusia

| Pekerjaan | Siapa | Catatan |
|---|---|---|
| Proyek ioGAS (plot probabilitas, plot bawah-lubang, diagram klasifikasi) | Rekan ioGAS | Input `data/processed/iogas/`. Baca `README_iogas.txt` dan `kolom_iogas.csv` |
| Ambang dari plot probabilitas ioGAS | Rekan ioGAS | Isi kolom `thr_probplot_iogas` di `element_thresholds.csv` / `geochem_statistik.csv` untuk dibandingkan dengan GMM |
| Peta lokasi regional (Bab 2) | Tim peta | DEMNAS dari BIG, cantumkan sumber |
| Cek jaringan sungai turunan dengan citra satelit | Tim peta | Buka `outputs/maps/qc/13_drainage_check.qgz`, tambah basemap satelit; 5 ruas bertanda `ragu`. Labeli "aliran turunan (lidar)" di setiap gambar |
| Tinjau nama satuan HMM S1–S5 | Tim geologi | Nama dibuat dari emisi dan tabulasi silang log; sesuaikan istilah bila perlu |
| Cek foto inti untuk daftar tinjauan ML-2 | Opsional | `ml2_review_list.csv` (mis. RJDH009 10–57 m) |
| Verifikasi semua referensi `[VERIFY]` | Semua | Lihat bagian 4 |
| Laporan dan slide | Tim | Ikuti format brief. Laporan ML adalah bahan, bukan teks laporan final: tulis ulang dalam gaya EYD formal |
| Ubah teks Laporan ML | Siapa saja | Sunting `reports/laporan_ml_src.html`, lalu jalankan `scripts/21_laporan_ml.py` (perlu Python). Jangan sunting file HTML hasil |

## 4. Referensi yang harus diverifikasi

Jangan mencantumkan referensi yang belum dibaca dari sumber aslinya. Semua di bawah ini masih
`[VERIFY]`. Perbaiki penulis, tahun, judul, jurnal, halaman, dan tautan sebelum masuk Daftar
Pustaka.

1. Sinclair (1974), *Journal of Geochemical Exploration* 3: 129–149: plot probabilitas (Bab 3).
2. Reimann, Filzmoser & Garrett (2005), *Science of the Total Environment* 346: 1–16: latar dan
   ambang geokimia (Bab 3).
3. Ashman, Bird & Zepf (1994), *Astronomical Journal* 108: 2348: statistik Ashman D untuk
   pemisahan populasi (Bab 3, 4).
4. Stanley & Lawie (2007): metode CV rata-rata untuk presisi duplikat (Bab 3).
5. AMIRA (2002), *ARD Test Handbook*: klasifikasi NAG, batas pH 4,5 dan kapasitas (Bab 6). Cek
   ambang yang tepat.
6. Faktor 30,6 (MPA dari %S) untuk proksi NAPP (Bab 6).
7. Permen PUPR No. 28/PRT/M/2015 tentang sempadan sungai: dasar buffer 50 m (Bab 6, 7).
8. Jansson, Allen, Skogsmo & Tavakoli (2022), *Journal of Geochemical Exploration* 233, 106909
   (pembanding §9.1). Juga makalah yang mengutip aturan seleksi unsurnya (belum diketahui).
9. Fontana, Hill, Huang, Stromberg & Sinclair, Golden Mile Dolerite (pembanding §9.2). Judul,
   jurnal dan tahun belum pasti; jangan diisi sebelum PDF-nya ada.
10. Geological Resume OlympiAR 2026 dan brief Technical Meeting (dari panitia).
11. Makalah rujukan di slide 20 brief, bila dipakai.

Metode yang sebaiknya juga dirujuk (cari dan verifikasi sumber primernya sendiri): Random Forest,
SHAP, Gaussian mixture dan BIC, hidden Markov model, prediksi konformal (Mondrian), Gaussian
process/kriging, transformasi log-rasio (clr/ilr), desurvey minimum curvature, orde sungai Strahler,
dan algoritma GRASS `r.watershed` / `r.stream.extract`.

## 5. Cara memakai repo ini

- **Clone sekali:** `git clone https://github.com/67minutes/ml-olympiar.git`. Repo ini sekitar
  90 MB. Pemilik repo yang mengundang anggota tim.
- **Sebelum bekerja:** `git pull`. **Setelah mengubah:** commit kecil dengan pesan jelas, lalu
  `git push`.
- Penulis laporan tidak perlu menjalankan Python. Semua hasil sudah ada di repo.
- Untuk membuka peta: buka `.qgz` di `outputs/maps/` dengan QGIS 3.44 atau lebih baru. Jika ada
  layer yang hilang, arahkan ke file bernama sama di `gis/`.
- CSV dibuka dengan Excel atau ioGAS. Kamus kolom: `geochem_analysis_kolom.csv` dan
  `iogas/kolom_iogas.csv`.
- **Jangan mengubah `data/raw/`**: uji otomatis akan gagal.
- **Cara membaca `LOG.md`:** entri berurutan waktu, tidak pernah ditulis ulang. Setiap langkah
  punya entri "plan" lalu "results". Di akhir tiap entri hasil ada "Plain-language explanation":
  itulah bahan ucapan presentasi (versi Bahasa ada di Laporan ML). Cari dengan judul `## <tanggal>
  · <langkah>`.
- Untuk agen AI (Claude Code, Codex): aturan ada di `AGENTS.md`; agen membaca ekor `LOG.md` lebih
  dulu dan mencatat setiap keputusan di sana. Jangan memakai layanan AI daring untuk mengolah data.
