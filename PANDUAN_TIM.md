# Panduan Tim: Ramba Joring, OlympiAR 2026 Babak 2

Panduan ini untuk anggota tim yang menulis laporan, membuat peta akhir, menyusun slide, dan
presentasi. Isinya: istilah dan cara membaca nama file, file mana yang dipakai untuk setiap bab
laporan, isi kiriman ke panitia, pekerjaan yang masih terbuka, referensi yang harus diverifikasi,
dan cara memakai repo.

> **Repo ini PRIVAT, khusus tim.** Isinya data rahasia dari panitia dan file brief (yang memuat
> kunci lisensi ioGAS kita). Jangan jadikan publik, jangan unggah data ke layanan AI/ML daring,
> dan jangan menyalin kunci lisensi atau kontak panitia ke mana pun.

## Mulai dari sini

| Untuk | Buka |
|---|---|
| Mulai menulis sembilan bab: bukti geologi, ioGAS, ML, peta, hasil uji dan batas interpretasi | **[Buku temuan Ramba Joring](outputs/laporan_final/laporan_final_v1.html)**. Pilih Bahasa Indonesia atau English. Buka dari salinan repo untuk mengakses sumber asli. |
| Temuan ML, angka kunci, cara membaca gambar, ucapan presentasi, pertanyaan juri | **[Laporan ML v2](outputs/laporan_ml/laporan_ml_v2.html)** (satu file, buka dengan browser; bisa dicetak ke PDF) |
| Istilah dan singkatan di repo ini | Bagian 1 di bawah |
| File per bab laporan | Bagian 3 |
| Daftar semua gambar ioGAS (bab, isi, catatan keterangan gambar) | [`outputs/figures/iogas/indeks_gambar_iogas.csv`](outputs/figures/iogas/indeks_gambar_iogas.csv) (buka dengan Excel) |
| Proyek ioGAS akhir | [`outputs/iogas_project/BACA_SAYA.txt`](outputs/iogas_project/BACA_SAYA.txt) |
| Berkas kiriman ke panitia (7 November) | [`outputs/kirim/`](outputs/kirim/) (bagian 5) |
| Rincian teknis lengkap (bahasa Inggris) | `LOG.md`, ringkasan di `README.md` |

`Laporan ML v1` (`laporan_ml_v1.html`) dibekukan dan tidak diubah lagi; v2 menambah perbandingan
ambang dengan plot probabilitas ioGAS dan penunjuk gambar ioGAS per bab.

## 1. Istilah dan cara membaca nama file

Repo ini memakai beberapa singkatan internal. Di laporan dan slide, **pakai nama panjangnya**
(kolom kanan), bukan singkatannya.

### 1a. Tugas machine learning (ML-1 sampai ML-6)

| Singkatan | Nama untuk laporan | Metode | Bab |
|---|---|---|---|
| ML-1 | Ambang unsur (*threshold*) | model campuran Gauss (GMM) pada log10, BIC memilih jumlah populasi | 3 |
| ML-2 | Litologi, alterasi, oksidasi dari kimia (ML vs log) | Random Forest, validasi tinggalkan-satu-pad, SHAP | 3 |
| ML-3 | Zonasi kadar permukaan Tinggi / Sedang / Rendah | log → PCA → GMM, tanah lalu batuan | 4 |
| ML-4 | Geokimia-stratigrafi bawah permukaan | hidden Markov model (HMM) pada komposit 1 m | 5 |
| ML-5 | Klasifikasi dan pengelompokan PAF/NAF | GMM + klasifikasi dengan prediksi konformal Mondrian | 6 |
| ML-6 | Penargetan bor (bonus desain eksplorasi) | Gaussian process (= kriging) + peringkat UCB | 7 |
| §9 / "pembanding" | Pembanding literatur | Jansson dkk. (k-means) dan Fontana dkk. (RF + penghalus) | diskusi |

### 1b. Tahap ioGAS (0 sampai 5) dan satuan HMM (S1 sampai S5)

Dua hal berbeda yang kebetulan sama-sama bernomor. Agar tidak tertukar, **selalu tulis
"Tahap ioGAS 1"** atau **"satuan HMM S1"**, jangan hanya "S1".

- **Tahap ioGAS 0–5** = urutan kerja pembuatan proyek ioGAS. Awalan nama file `s1_`–`s4_`
  menunjuk tahapnya (bukan satuan HMM):

  | Awalan | Tahap ioGAS | Bab |
  |---|---|---|
  | (tanpa file) | 0 Fondasi: otomatisasi ioGAS | - |
  | `s1_` | 1 QAQC, pencilan, ambang | 3 |
  | `s2_` | 2 Data permukaan | 4 |
  | `s3_` | 3 Data pemboran | 5 |
  | `s4_` | 4 Lingkungan | 6 |
  | `*_final_v1.gas` | 5 Proyek akhir (deliverable 2) | semua |

- **Satuan HMM S1–S5** = lima satuan geokimia bawah permukaan dari ML-4. Namanya sudah deskriptif:
  S1 Au rendah, Cu rendah (sulfida); S2 Au rendah, Cu rendah (oksida); S3 Au sedang, Cu rendah
  (oksida); S4 Au sedang, Cu tinggi (sulfida); S5 Au tinggi, Cu rendah (oksida).

### 1c. Kelas PAF/NAF (Bab 6)

| Istilah | Arti |
|---|---|
| NAF | *Non-acid forming*: tidak membentuk asam |
| PAF-LC | *Potentially acid forming, low capacity*: berpotensi asam, kapasitas rendah (pH NAG < 4,5, kapasitas kecil) |
| PAF-HC | *Potentially acid forming, high capacity*: berpotensi asam, kapasitas tinggi |
| Kelas NAG | Hasil uji lab NAG. **Hanya lubang RJDH012** (106 sampel) |
| Kelas konformal (`ML_paf_kelas`) | Jawaban model: satu kelas jika yakin, `ambigu` jika himpunan konformal berisi lebih dari satu kelas |
| Kelas pengelolaan (`ML_paf_kelola`) | Kelas **terburuk yang masih mungkin** menurut model; dipakai untuk penanganan batuan (konservatif) |
| Prioritas uji NAG | Interval yang paling perlu diuji NAG: `1_HC_tidak_pasti` (mungkin PAF-HC tetapi tidak pasti), `2_NAF_atau_LC`, `3_luar_domain` (kimianya di luar data latih RJDH012) |

### 1d. Sulfur dan kode data

| Istilah | Arti |
|---|---|
| SCIS | Metode lab S sulfida yang dipakai di sebagian besar lubang (kolom `S_sulfida_SCIS_pct`) |
| S2 | Metode lab S sulfida lain (RJDH004, RJDH019, sebagian RJDH006/007/009). **Tidak dicampur** dengan SCIS |
| S total | Hanya ada di RJDH012. Kolom `S_pct` = S total, dibuat agar diagram Scott Halley di ioGAS mengenali sulfur |
| NS-SEL | Interval bor yang tidak disampel |
| DL | Batas deteksi lab. Nilai di bawahnya diisi DL/2 dan ditandai tersensor |
| CN | Terlarut sianida (mis. `AuCN_ppm`); rasio CuCN/Cu = penanda oksida vs sulfida |
| Pad, lubang kembar | Satu lokasi dengan dua lubang berdekatan: 005/014, 007/013, 010/011, 016/017, 008/019 |
| RJ | Ramba Joring. `prospek_RJ = Y` = sampel di dalam prospek |

### 1e. Nama kolom

| Pola | Arti |
|---|---|
| `Au_ppm`, `Fe_pct` | Kadar unsur (ppm atau %). **Tidak diterjemahkan** di ioGAS: ioGAS membaca unsur dan satuan dari nama itu |
| `<unsur>_cens` | `Y` = nilai di bawah batas deteksi (tersensor) |
| `<unsur>_log10` | log10 kadar; dipakai di box plot dan strip log ioGAS (keduanya tidak bisa diberi sumbu log) |
| `Kelas_<unsur>_pp` | Kelas ambang dari plot probabilitas ioGAS: Latar / Anomali lemah / Anomali kuat |
| `ML_*` | Keluaran model: `ML_thr_*` ML-1, `ML_alt_*`/`ML_oks_*`/`ML_lit_*` ML-2, `ML_zona*` ML-3, `ML_hmm_*` ML-4, `ML_paf_*` ML-5, `ML_gp_*` ML-6, `ML_s9_*` pembanding |
| `*_p_maks`, `*_stabil`, `*_ambigu` | Ukuran keyakinan: peluang kelas terbesar, stabilitas bootstrap, tanda ragu |
| `flag_*` | Tanda validasi (lihat `validation_flags.csv`) |

Kamus kolom lengkap: `data/processed/geochem_analysis_kolom.csv` dan
`data/processed/iogas/kolom_iogas.csv`.

### 1f. Nama file dan folder

| Pola | Arti |
|---|---|
| `scripts/00_…` – `07_…` | Langkah pembersihan data, berurutan (nomor = urutan jalan) |
| `scripts/08_…` – `21_…` | ML-1 sampai ML-6, pembanding literatur, Laporan ML |
| `scripts/22_…` – `28_…` | ioGAS (22 proyek dasar, 23–26 Tahap ioGAS 1–4, 27 proyek akhir) dan folder kiriman (28) |
| `outputs/figures/08_…` – `14_…` | Gambar Python; nomor = nomor skrip pembuatnya (08 = ML-1, 09 = ML-2, 10 = ML-3, 11 = ML-4, 12 = ML-5, 13 = ML-6, 14 = pembanding) |
| `outputs/figures/iogas/s1_…` – `s4_…` | Gambar yang digambar ioGAS; awalan = Tahap ioGAS |
| `_v1`, `_v2` | Versi. **File yang sudah masuk laporan tidak pernah ditimpa**; perubahan jadi versi baru |
| `RJ_tanah`, `RJ_batuan`, `RJ_bor`/`RJ_DH` | Data tanah, batuan, bor (DH = *drillhole*) |
| `komposit_1m` | Interval bor digabung menjadi 1 m berbobot panjang (dipakai ML-4) |
| `penampang_A/B/C` | Tiga penampang geokimia-stratigrafi (ML-4, Bab 5); urutan lubang tenggara ke barat laut |
| `penampang D–D'` | Penampang desain bor usulan (ML-6, bonus) |
| `Lain` | Lubang di luar penampang A–C: RJDH004, RJDH010, RJDH011 |
| `kembar_005_014` | Pasangan lubang kembar RJDH005 dan RJDH014 |
| `data/interim/` | Hasil antara (termasuk file `*_masuk.gas` = masukan ioGAS dan log); tidak untuk laporan |

## 2. Ringkasan proyek

- **Prospek:** Ramba Joring (RJ), distrik emas Martabe, Sumatra Utara. Sistem epitermal
  sulfidasi tinggi Au-Cu: silika vuggy, argilik lanjut kuarsa-alunit, Cu enargit/kovelit, emas
  dominan di zona oksida.
- **Tema babak 2:** "Orebody to Ecosystem: Integrating Mining Performance and Environmental
  Resilience". Tema utama penilaian adalah **Machine Learning**.
- **Tenggat:** pengiriman **7 November 2026, 23.59 WIB** lewat email ke panitia. Presentasi
  14–15 November 2026. Nilai: **presentasi 60%, laporan 40%**, jadi setiap hasil harus bisa
  dijelaskan secara lisan.
- **Deliverable** (semua kecuali laporan dan slide sudah siap di `outputs/kirim/`, bagian 5):
  1. Validasi data (CSV).
  2. Proyek ioGAS.
  3. Analisis geokimia (CSV).
  4. Laporan (PDF).
  5. Presentasi (PowerPoint diekspor ke PDF).
- **Format laporan (dari brief):** Bahasa Indonesia (EYD), Times New Roman (judul 16, subjudul
  14, isi dan keterangan 12), teks hitam, potret, satu kolom, gambar HD. Peta/penampang boleh
  lanskap. Bonus hanya dihitung jika semua sub-parameter lengkap. Setiap referensi harus ditautkan
  dan dilampirkan.

Semua gambar di `outputs/figures/` dan peta di `outputs/maps/` sudah berlabel Bahasa Indonesia.
Gambar Python 300 dpi; gambar ioGAS 1.500–4.800 piksel. **Jangan menimpa gambar yang sudah masuk
laporan**; buat versi `_v2`.

**Catatan untuk keterangan gambar ioGAS** (berlaku untuk semua gambar `outputs/figures/iogas/`):
sumbu unsur tertulis `Au_ppm` dan seterusnya (ioGAS butuh nama asli kolom unsur); legenda warna
tidak ikut terekspor, jadi tulis arti warna di keterangan gambar; di strip log, skala sumbu-x tiap
lubang berdiri sendiri, jadi bandingkan pola, bukan panjang batang. Catatan khusus per gambar ada di
kolom `catatan_keterangan` pada `indeks_gambar_iogas.csv`.

## 3. Peta file per bab laporan

Semua tabel ada di `data/processed/`, gambar Python di `outputs/figures/`, gambar ioGAS di
`outputs/figures/iogas/`.

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
Bobot rubrik: QAQC 30, perlakuan pencilan 35, nilai ambang 35. Ditambah ML (klasifikasi dari
kimia).

- **Tabel:** `validation_flags.csv` (satu baris per masalah per data), `validation_summary.csv`
  (satu baris per pemeriksaan), `qaqc_precision.csv`, `element_thresholds_v2.csv` (ambang GMM,
  MAD, Tukey **dan** plot probabilitas ioGAS), `s1_ambang_perbandingan_v1.csv` (kesesuaian plot
  probabilitas vs GMM), `s1_aat_ringkasan_v1.csv` (pencilan Tukey dari ioGAS), `ml2_scores.csv`,
  `ml2_review_list.csv`.
- **Gambar Python:** `07_au_lubang_tahun_v1.png` (Au per lubang dan tahun lab),
  `08_ambang_{bor,batuan,tanah}_v1.png`, `08_bic_v1.png`, `09_skor_v1.png`,
  `09_matriks_konfusi_v1.png`, `09_shap_v1.png`, `09_shap_dependensi_v1.png`,
  `09_reliabilitas_v1.png`, `09_skor_pad_v1.png`.
- **Gambar ioGAS (Tahap 1):** plot probabilitas per unsur tanpa warna (`s1_pp_<data>_<unsur>`) dan
  diwarnai kelas ambang (`s1_pp_kelas_…`); box plot Tukey (`s1_box_tukey_…`); box plot Au per tahun
  lab dan per lubang (`s1_box_tahun_bor`, `s1_box_lubang_bor`); presisi Au/Ag sianida vs total
  (`s1_xy_AuCN_Au_bor`, `s1_xy_AgCN_Ag_bor`) dan sampel ulang batuan (`s1_xy_duplikat_…`).
- **Temuan dan ucapan:** [Laporan ML: fondasi data](outputs/laporan_ml/laporan_ml_v2.html#fondasi),
  [ambang](outputs/laporan_ml/laporan_ml_v2.html#ml1), [ML vs log](outputs/laporan_ml/laporan_ml_v2.html#ml2).

### Bab 4. Data Permukaan
Bobot rubrik: tanah 25, batuan 25, zonasi 50.

- **Tabel:** `ml3_summary.csv`, `ml3_comparisons.csv`, `geochem_statistik_kelompok.csv`,
  `s2_zona_ringkasan_v1.csv` (median per zona), `s2_zona_vs_kelas_v1.csv` (zona vs kelas ambang);
  layer `gis/ml3_zonasi.gpkg`, `gis/ml3_tanah_{zona,indeks,indeks_sd,p_tinggi,p_rendah}.tif`.
- **Gambar Python:** `10_pca_biplot_v1.png`, `10_bic_stabilitas_v1.png`, `10_zona_unsur_v1.png`,
  `10_variogram_arah_v1.png`, `10_gp_cv_v1.png`. Peta zonasi akhir dibuat di QGIS dari layer
  `gis/` (proyek pemeriksaan: `outputs/maps/qc/10_ml3_check.qgz`).
- **Gambar ioGAS (Tahap 2):** peta sampel per zona kadar, per kelas ambang Au/As, per keyakinan
  zona dan per alterasi (`s2_peta_…`); scatter As-Au, Pb-Au, Cu-Au (`s2_xy_…`); box plot per zona
  (`s2_box_zona_…`); plot probabilitas Au tanah per zona (`s2_pp_Au_zona_tanah`); ternary Al-K-Mg
  Scott Halley pada 26 batuan ICP lengkap (`s2_halley_AlKMg_batuan`).
- **Temuan dan ucapan:** [Laporan ML: zonasi permukaan](outputs/laporan_ml/laporan_ml_v2.html#ml3)

### Bab 5. Data Pemboran
Bobot rubrik: validasi 20, korelasi 40, geokimia-stratigrafi 40. Maksimal 3 penampang.

- **Tabel:** `ml4_summary.csv`, `ml4_states.csv`, `ml4_comparisons.csv`, `ml4_sections.csv`,
  `s3_status_ringkasan_v1.csv` (median per satuan HMM), `s3_status_per_lubang_v1.csv` (meter per
  satuan per lubang); layer `gis/ml4_hmm.gpkg`, `gis/ml4_penampang.gpkg`, `gis/drillholes.gpkg`.
- **Gambar Python:** `11_pemilihan_K_v1.png`, `11_profil_status_v1.png`, `11_matriks_transisi_v1.png`,
  `11_strip_log_v1.png`, `11_kontinuitas_v1.png`.
- **Peta/penampang (siap pakai):** `outputs/maps/11_penampang_{A,B,C}_v1.png`,
  `11_peta_indeks_penampang_v1.png`; proyek QGIS `outputs/maps/11_ml4_penampang.qgz`.
- **Gambar ioGAS (Tahap 3):** strip log per penampang A, B, C dan lubang di luar penampang
  (`s3_strip_<warna>_penampang_…`), diwarnai satuan HMM, alterasi log, atau oksidasi log; lubang
  kembar (`s3_strip_<warna>_kembar_…`); box plot dan scatter per satuan HMM; peta 3D tampak atas.
- **Temuan dan ucapan:** [Laporan ML: geokimia-stratigrafi](outputs/laporan_ml/laporan_ml_v2.html#ml4)

### Bab 6. Analisis Lingkungan
Bobot rubrik: unsur AMD 40, klasifikasi PAF/NAF dan penanganan 60. **Diagram alir wajib.**

- **Tabel:** `ml5_summary.csv`, `ml5_scores.csv`, `ml5_conformal.csv`, `ml5_per_hole.csv`,
  `ml5_uji_nag.csv` (daftar interval yang perlu uji NAG), `ml5_napp.csv`, `ml5_clusters.csv`,
  `drainase_ringkasan.csv`, `s4_kelas_nag_ringkasan_v1.csv` (median per kelas NAG dan oksidasi),
  `s4_kelola_per_lubang_v1.csv` (meter per kelas pengelolaan per lubang); layer `gis/ml5_paf.gpkg`,
  `gis/drainage.gpkg`.
- **Gambar Python:** `12_diagram_alir_paf_naf_v1.png` (**diagram alir wajib**),
  `12_nag_ph_kapasitas_v1.png`, `12_profil_rjdh012_v1.png`, `12_cakupan_konformal_v1.png`,
  `12_matriks_kebingungan_v1.png`, `12_shap_lengkap_v1.png`, `12_gmm_u1_u2_v1.png`,
  `12_ringkasan_lubang_v1.png`, `12_napp_proksi_v1.png`.
- **Gambar ioGAS (Tahap 4):** RJDH012 diwarnai kelas NAG (bentuk simbol = zona oksidasi): pH NAG vs S
  total dan vs SCIS, kapasitas NAG vs SCIS, Scott Halley Fe vs S (garis pirit) dan ternary Ca-Fe-S,
  box plot unsur AMD, strip log; semua lubang: strip log per penampang diwarnai kelas pengelolaan,
  kelas konformal dan prioritas uji NAG, box plot, scatter Cu-SCIS dan peta 3D.
- **Temuan dan ucapan:** [Laporan ML: PAF/NAF](outputs/laporan_ml/laporan_ml_v2.html#ml5)

### Bab 7. Sintesis Eksplorasi (+ Bonus desain eksplorasi)
Bobot rubrik: prospeksi 50, eksplorasi lanjutan 50; bonus desain 100. Maksimal 4 penampang.

- **Tabel:** `ml6_summary.csv`, `ml6_cv.csv`, `ml6_kandidat.csv`, `ml6_usulan_lubang.csv`
  (format kolar/survei, siap untuk ioGAS); layer `gis/ml6_target.gpkg`, `gis/ml6_penampang.gpkg`,
  `gis/ml6_{ucb_maks,meter_cutoff,sd_rerata}.tif`.
- **Gambar Python:** `13_profil_theta_v1.png`, `13_cv_lopo_v1.png`, `13_variogram_gp_v1.png`,
  `13_peringkat_kandidat_v1.png`.
- **Peta/penampang bonus (siap pakai):** `outputs/maps/13_peta_desain_v1.png`,
  `13_penampang_desain_v1.png` (D–D'); proyek QGIS `outputs/maps/13_ml6_desain.qgz`.
- **Temuan dan ucapan:** [Laporan ML: penargetan bor](outputs/laporan_ml/laporan_ml_v2.html#ml6)

### Bab 8. Kesimpulan
Rangkum per bab di atas. Tekankan tema "ML yang tahu apa yang tidak diketahuinya": setiap peta
dan kelas punya ukuran ketidakpastian (probabilitas, stabilitas bootstrap, himpunan konformal,
deviasi standar kriging).

- **Temuan dan ucapan:** [Laporan ML: sintesis](outputs/laporan_ml/laporan_ml_v2.html#sintesis)

### Bab 9. Daftar Pustaka
Lihat bagian 7 di bawah. **Semua referensi wajib diperiksa dari sumber aslinya.**

### Pembahasan tambahan: pembanding literatur
Dapat dimasukkan sebagai subbab diskusi (Bab 3/5) atau satu slide cadangan.

- **Gambar:** `14_jansson_vs_gmm_v1.png`, `14_rf_vs_hmm_v1.png`. Tabel: `s9_*.csv`.
- Kedua makalah (Jansson dkk. 2022; Fontana dkk.) masih `[VERIFY]`. Jangan bandingkan akurasi kita
  dengan 82,5% Fontana.
- **Temuan dan ucapan:** [Laporan ML: pembanding](outputs/laporan_ml/laporan_ml_v2.html#pembanding)

## 4. Proyek ioGAS (deliverable 2)

- **Siapa dan bagaimana:** pemilik repo, di PC-nya sendiri dengan lisensi uji coba 14 hari dari
  IMDEX (berlaku sampai 19 November 2026; brief panitia tidak melarangnya). Grafik dibuat oleh
  ioGAS sendiri, bukan oleh Python: Python hanya menyusun proyek `.gas` (data sama persis dengan
  CSV, koordinat UTM 47N/EPSG 32647, warna kelas ML, nama Bahasa untuk kolom non-unsur dan judul
  legenda) dan *workflow* ioGAS, yang dijalankan agen AI lewat server bawaan ioGAS yang hanya
  mendengarkan di komputer ini (127.0.0.1). Data tidak keluar dari PC.
- **Proyek akhir** (`outputs/iogas_project/`, mulai dari `BACA_SAYA.txt`):

  | File | Isi | Warna | Bab |
  |---|---|---|---|
  | `RJ_tanah_final_v1.gas` | 188 sampel tanah prospek RJ, 7 jendela plot | zona kadar ML | 3, 4 |
  | `RJ_batuan_final_v1.gas` | 382 sampel batuan prospek RJ, 7 jendela | zona kadar ML | 3, 4 |
  | `RJ_bor_komposit_final_v1.gas` | 3.057 komposit 1 m, 10 jendela (strip log A–C, lubang kembar) | satuan HMM S1–S5 | 5 |
  | `RJ_lingkungan_final_v1.gas` | 2.466 interval assay, 9 jendela (NAG, Halley Fe-S, strip log) | kelas pengelolaan PAF/NAF | 3, 6 |

  Setiap proyek akhir memuat semua kolom data dan hasil ML untuk sampel itu. 47 proyek pendukung
  (satu per skema warna, karena ioGAS menyimpan satu skema warna per proyek) tercantum di
  `indeks_proyek_iogas.csv`.
- **Tangkapan layar GUI ioGAS tidak dibuat** (keputusan tim): gambar ekspor dan proyek tersimpan
  sudah membuktikan pemakaian ioGAS. Jika tetap ingin, tangkapan layar memuat tanda air
  "DEMONSTRATION COPY"; gambar ekspor tidak.
- **Menjalankan ulang** (perlu Python dan ioGAS di PC pemilik repo): `uv run python
  scripts/27_iogas_s5_final.py` (proyek akhir; menolak menimpa file yang sudah ada) atau
  `--index` (hanya memperbarui daftar). Skrip Tahap 1–4: `scripts/23_…` sampai `26_…`; rinciannya
  di `LOG.md`.
- **Aturan:** jangan mengutip kata sandi lisensi atau nomor kontak panitia dari brief (slide 17 dan
  21). Jangan menutup jendela ioGAS yang sedang Anda pakai saat agen bekerja; agen hanya memakai
  ioGAS kedua miliknya sendiri.

## 5. Berkas kiriman ke panitia (`outputs/kirim/`)

Dibuat oleh `uv run python scripts/28_kirim.py` (berisi salinan saja; dibuat ulang setiap kali
dijalankan). Total sekitar 4,6 MB, jauh di bawah batas lampiran Gmail 25 MB.

| Folder | Isi |
|---|---|
| `1_validasi_data/` | `validasi_flag.csv`, `validasi_ringkasan.csv`, `qaqc_presisi.csv` + `BACA_SAYA.txt` |
| `2_proyek_iogas/` | `RJ_proyek_ioGAS.zip`: 4 proyek akhir, 47 proyek pendukung di `pendukung/`, `BACA_SAYA.txt`, indeks |
| `3_analisis_geokimia/` | `analisis_geokimia.csv` + kamus kolom, statistik, ambang, ringkasan zona/satuan/kelas NAG + `BACA_SAYA.txt` |
| `4_laporan/`, `5_presentasi/` | Kosong: letakkan PDF laporan dan PDF presentasi di sini sebelum mengirim |
| `MANIFEST.csv` | Daftar file, ukuran, sumber dan sidik sha256 |

Nama file di folder kiriman memakai nama Bahasa yang jelas; sumbernya tercantum di `MANIFEST.csv`.
Email dikirim ke alamat panitia di brief (slide 12) paling lambat 7 November 2026, 23.59 WIB.

## 6. Pekerjaan terbuka untuk manusia

| Pekerjaan | Siapa | Catatan |
|---|---|---|
| Laporan dan slide | Tim | Ikuti format brief. Laporan ML adalah bahan, bukan teks laporan final: tulis ulang dalam gaya EYD formal |
| Peta lokasi regional (Bab 2) | Tim peta | DEMNAS dari BIG, cantumkan sumber |
| Cek jaringan sungai turunan dengan citra satelit | Tim peta | Buka `outputs/maps/qc/13_drainage_check.qgz`, tambah basemap satelit; 5 ruas bertanda `ragu`. Labeli "aliran turunan (lidar)" di setiap gambar |
| Tinjau nama satuan HMM S1–S5 | Tim geologi | Nama dibuat dari emisi dan tabulasi silang log; sesuaikan istilah bila perlu |
| Cek foto inti untuk daftar tinjauan ML-2 | Opsional | `ml2_review_list.csv` (mis. RJDH009 10–57 m) |
| Verifikasi semua referensi `[VERIFY]` | Semua | Lihat bagian 7 |
| Kirim email ke panitia | Ketua tim | Lampirkan isi `outputs/kirim/` setelah PDF laporan dan slide masuk |
| Ubah teks Laporan ML | Siapa saja | Sunting `reports/laporan_ml_src.html`, lalu jalankan `scripts/21_laporan_ml.py` (perlu Python). Jangan sunting file HTML hasil |

Sudah selesai: proyek ioGAS Tahap 1–5 (diperiksa pemilik repo di GUI ioGAS setiap tahap), ambang
plot probabilitas ioGAS (`thr_probplot_iogas`), folder kiriman.

## 7. Referensi yang harus diverifikasi

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
   (pembanding literatur 1). Juga makalah yang mengutip aturan seleksi unsurnya (belum diketahui).
9. Fontana, Hill, Huang, Stromberg & Sinclair, Golden Mile Dolerite (pembanding literatur 2). Judul,
   jurnal dan tahun belum pasti; jangan diisi sebelum PDF-nya ada.
10. Halley, S. (diagram Scott Halley di ioGAS: Al-K-Mg, Fe vs S, Ca-Fe-S): cari publikasi atau
    catatan teknis aslinya sebelum dikutip.
11. Geological Resume OlympiAR 2026 dan brief Technical Meeting (dari panitia).
12. Makalah rujukan di slide 20 brief, bila dipakai.

Metode yang sebaiknya juga dirujuk (cari dan verifikasi sumber primernya sendiri): Random Forest,
SHAP, Gaussian mixture dan BIC, hidden Markov model, prediksi konformal (Mondrian), Gaussian
process/kriging, transformasi log-rasio (clr/ilr), desurvey minimum curvature, orde sungai Strahler,
dan algoritma GRASS `r.watershed` / `r.stream.extract`.

## 8. Cara memakai repo ini

- **Clone sekali:** `git clone https://github.com/67minutes/ml-olympiar.git`. Repo ini sekitar
  170 MB setelah di-clone. Pemilik repo yang mengundang anggota tim.
- **Sebelum bekerja:** `git pull`. **Setelah mengubah:** commit kecil dengan pesan jelas, lalu
  `git push`.
- Penulis laporan tidak perlu menjalankan Python. Semua hasil sudah ada di repo.
- Untuk membuka peta: buka `.qgz` di `outputs/maps/` dengan QGIS 3.44 atau lebih baru. Jika ada
  layer yang hilang, arahkan ke file bernama sama di `gis/`.
- CSV dibuka dengan Excel atau ioGAS. Proyek `.gas` dibuka dengan ioGAS (hanya di PC pemilik repo
  selama lisensi uji coba).
- **Jangan mengubah `data/raw/`**: uji otomatis akan gagal.
- **Cara membaca `LOG.md`:** entri berurutan waktu, tidak pernah ditulis ulang. Setiap langkah
  punya entri "plan" lalu "results". Di akhir tiap entri hasil ada "Spoken/Plain-language
  explanation": itulah bahan ucapan presentasi (versi Bahasa ada di Laporan ML). Cari dengan judul
  `## <tanggal> · <langkah>`.
- Untuk agen AI (Claude Code, Codex): aturan ada di `AGENTS.md`; agen membaca ekor `LOG.md` lebih
  dulu dan mencatat setiap keputusan di sana. Jangan memakai layanan AI daring untuk mengolah data.
  Untuk ioGAS, agen memakai *skill* `.claude/skills/iogas/SKILL.md`.
