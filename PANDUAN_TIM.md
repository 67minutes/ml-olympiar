# Panduan Tim: Ramba Joring, OlympiAR 2026 Babak 2

Panduan ini untuk anggota tim yang menulis laporan, membuat peta akhir, menyusun slide, dan
presentasi. Isinya: untuk setiap bab laporan, file mana yang dipakai, angka kunci, dan penjelasan
singkat yang bisa diucapkan saat presentasi. Rincian teknis lengkap ada di `LOG.md` (bahasa
Inggris). Ringkasan teknis ada di `README.md`.

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
- **Angka kunci:**
  - Tidak ada sampel QAQC (standar, blank, duplikat) di basis data. Kolom repeat/split kosong.
    Kita memakai pemeriksaan internal sebagai gantinya.
  - Nilai 0 di data permukaan berarti "tidak dianalisis": 20.275 nilai batuan dan 12.826 nilai
    tanah diubah menjadi kosong. Tanpa ini, ML akan mengelompokkan batch lab, bukan geologi.
  - Batas deteksi berbeda antar-era lab (1998–2017) diseragamkan ke batas tertinggi per unsur.
  - Elevasi sampel permukaan: 68 sampel menyimpang > 10 m dari lidar, 19 di antaranya > 30 m
    (satu sampel tanah tercatat 36.076 m). Semua di-drape ulang ke lidar, nilai asli disimpan.
  - Presisi emas: Au sianida > 1,1 × Au total pada 125 dari 979 pasangan (Ag 173 dari 1.267).
    Ini efek nugget, bukan kesalahan. Satu kelompok sampel ulang singkapan (4 sampel): CV Au 31%.
  - Ambang ML-1: Au bor terpisah alami pada ~0,16 dan ~1 g/t. Au batuan permukaan RJ satu
    populasi, jadi batas klasik rerata + 2 SD (~7 g/t) yang tepat. As, Pb, Zn tanah memiliki
    kelompok latar di bawah populasi termineralisasi.
  - ML-2 (kimia → log): alterasi dan oksidasi benar ~70% (akurasi seimbang 0,70 dan 0,71;
    peluang acak 25–33%), pirit 84%. Litologi hanya 0,30 (acak 0,20): alterasi telah menghapus
    jejak batuan asal. Ini **temuan geologi, bukan kegagalan**.
  - Validasi jujur: model tidak pernah melihat pad bor yang diujikan (leave-one-pad-out, 12 pad).
  - Daftar tinjauan ML vs log: misalnya RJDH009 10–57 m dilog Oksida, tetapi kimianya Sulfida.
- **Outlier:** dua jenis. *Outlier kesalahan* (elevasi mustahil, dsb.) diperbaiki atau ditandai.
  *Outlier geologi* (mis. 36,5 g/t Au di RJDH015) adalah bijih: tidak pernah dipotong. Untuk ML
  dipakai transformasi log dan penskalaan robust (median/MAD), bukan pemotongan.
- **Ucapan presentasi:**
  > Laporan lab lama tidak menulis "di bawah deteksi"; mereka mencetak angka di batas bawah, dan
  > batasnya berbeda tiap lab selama 20 tahun. Kami mendeteksi batas tiap pekerjaan lab lalu
  > menyeragamkannya. Tanpa ini, ML akan mengelompokkan sampel menurut tahun lab, bukan geologi.
  > Semua masalah data tercatat di satu tabel; tidak ada yang kami hapus.

  > Kami bertanya apakah kimia saja bisa menebak apa yang dilog ahli geologi. Agar jujur, model
  > tidak pernah melihat pad yang diujikan. Alterasi dan oksidasi benar sekitar 70%, pirit 84%,
  > dan model menjelaskan dirinya secara geologi: emas di atas ~1 g/t berarti silika vuggy,
  > sulfur di atas ~2% berarti batuan sulfida segar. Jenis batuan tidak bisa dibaca dari empat
  > logam ini karena alterasi telah menimpa batuan asal.

### Bab 4. Data Permukaan
Bobot rubrik: tanah 25, batuan 25, zonasi 50.

- **File:** `ml3_summary.csv`, `ml3_comparisons.csv`, `geochem_statistik_kelompok.csv`;
  `gis/ml3_zonasi.gpkg`, `gis/ml3_tanah_{zona,indeks,indeks_sd,p_tinggi,p_rendah}.tif`.
- **Gambar:** `10_pca_biplot_v1.png`, `10_bic_stabilitas_v1.png`, `10_zona_unsur_v1.png`,
  `10_variogram_arah_v1.png`, `10_gp_cv_v1.png`. Peta zonasi akhir dibuat di QGIS dari layer
  `gis/` (proyek pemeriksaan: `outputs/maps/qc/10_ml3_check.qgz`).
- **Angka kunci:**
  - Tanah RJ (188 sampel): satu indeks mineralisasi (PC1, 57,5% varians) dari Au, As, Pb, Hg, Sb,
    Cu yang naik bersama. Uji Horn: hanya satu gradien nyata.
  - Zona GMM K = 3: Rendah 30 / Sedang 92 / Tinggi 66. Median Au: 0,007 / 0,065 / 0,34 g/t.
    BIC sebenarnya memilih 2 kelompok (latar vs jejak mineralisasi); kami tampilkan stabilitas
    tiap sampel (zona Tinggi bertahan pada 96% pengulangan).
  - Batuan RJ (352 sampel): satu populasi (BIC K = 1), median Au zona R/S/T 0,12 / 0,53 / 5,0
    g/t. Zona batuan berubah jika unsur ditambah: **keyakinan rendah**.
  - Peta GP (kriging) indeks tanah: memanjang **E–ENE (75°)**, bukan NE seperti dugaan awal.
    Area Tinggi 27,4 ha. **Zona Tinggi terbesar (barat-tengah) sebagian besar belum dibor.**
  - Catatan jujur: lintasan tanah juga berarah E–W, jadi efek lintasan belum bisa dipisahkan dari
    geologi.
- **Ucapan presentasi:**
  > Tujuh unsur tanah kami gabungkan menjadi satu indeks mineralisasi. Emas, arsen, timbal,
  > antimon, merkuri dan tembaga naik bersama, dan uji statistik menunjukkan hanya ada satu
  > gradien ini. Model campuran membaginya menjadi zona rendah, sedang dan tinggi, dan kami
  > tunjukkan seberapa stabil zona tiap sampel. Kriging memberi peta beserta ketidakpastiannya.
  > Zona tinggi memanjang timur–barat sampai ENE, dan sebagian besar di barat pemboran belum diuji.

### Bab 5. Data Pemboran
Bobot rubrik: validasi 20, korelasi 40, geokimia-stratigrafi 40. Maksimal 3 penampang.

- **File:** `ml4_summary.csv`, `ml4_states.csv`, `ml4_comparisons.csv`, `ml4_sections.csv`;
  `gis/ml4_hmm.gpkg`, `gis/ml4_penampang.gpkg`, `gis/drillholes.gpkg`.
- **Gambar:** `11_pemilihan_K_v1.png`, `11_profil_status_v1.png`, `11_matriks_transisi_v1.png`,
  `11_strip_log_v1.png`, `11_kontinuitas_v1.png`.
- **Peta/penampang (siap pakai):** `outputs/maps/11_penampang_{A,B,C}_v1.png`,
  `11_peta_indeks_penampang_v1.png`; proyek QGIS `outputs/maps/11_ml4_penampang.qgz`.
- **Angka kunci:**
  - 19 lubang, 2.476 interval assay, dikomposit 1 m (3.057 komposit layak).
  - Variasi basis data: Au, Ag, As, Cu lengkap; unsur lain hanya di RJDH001 dan RJDH012; metode
    sulfur berbeda antar-lubang (SCIS vs S2); RJDH001 tanpa sulfur.
  - HMM (hidden Markov model) menemukan **5 satuan kimia**, dipilih dengan validasi silang per pad:
    - S1 Au rendah, Cu rendah (Sulfida): dasar argilik tandus, sangat stabil;
    - S2 Au rendah, Cu rendah (Oksida);
    - S3 Au sedang, Cu rendah (Oksida);
    - S4 Au sedang, Cu tinggi (Sulfida): zona Cu ~30 m, stabil;
    - S5 Au tinggi, Cu rendah (Oksida): nyata, tetapi batasnya paling tidak stabil.
  - Fragmentasi: HMM 6,3 pergantian per 100 m, mirip log litologi (5,2); GMM tanpa memori
    bawah-lubang 28,1 (empat kali lebih "berisik").
  - Korelasi antarlubang (pad kembar 005/014, 007/013, 010/011, 016/017, 008/019): satuan sama
    pada 71–72% pasangan < 20 m, tetap di atas peluang acak sampai ~40–50 m.
- **Ucapan presentasi:**
  > Model HMM membaca tiap lubang meter demi meter memakai emas, perak, tembaga dan arsen. Ia
  > menemukan lima satuan kimia dan belajar bahwa satuan cenderung berlanjut ke bawah, seperti
  > cara ahli geologi melog. Dua satuan jelas dan kokoh: dasar sulfida argilik yang tandus dan
  > zona sulfida kaya tembaga setebal ~30 m. Tiga lainnya satuan oksida dengan emas meningkat.
  > Satuan-satuan ini cocok antar-lubang kembar dan berkorelasi sampai 40–50 m ke samping.

### Bab 6. Analisis Lingkungan
Bobot rubrik: unsur AMD 40, klasifikasi PAF/NAF dan penanganan 60. **Diagram alir wajib.**

- **File:** `ml5_summary.csv`, `ml5_scores.csv`, `ml5_conformal.csv`, `ml5_per_hole.csv`,
  `ml5_uji_nag.csv` (daftar interval yang perlu uji NAG), `ml5_napp.csv`, `ml5_clusters.csv`,
  `drainase_ringkasan.csv`; `gis/ml5_paf.gpkg`, `gis/drainage.gpkg`.
- **Gambar:** `12_diagram_alir_paf_naf_v1.png` (**diagram alir wajib**),
  `12_nag_ph_kapasitas_v1.png`, `12_profil_rjdh012_v1.png`, `12_cakupan_konformal_v1.png`,
  `12_matriks_kebingungan_v1.png`, `12_shap_lengkap_v1.png`, `12_gmm_u1_u2_v1.png`,
  `12_ringkasan_lubang_v1.png`, `12_napp_proksi_v1.png`.
- **Angka kunci:**
  - Hanya RJDH012 punya data NAG (106 sampel). Tiga kelas: **NAF 37 / PAF-LC 48 / PAF-HC 21**
    (PAF-LC = kapasitas rendah, PAF-HC = kapasitas tinggi ≥ 10 kg H₂SO₄/t pada pH 4,5).
  - Zona sulfida: 16 sampel, 100% NAG pH < 4,5, kapasitas tinggi (~50–90 kg/t). Zona oksida:
    59% NAG pH < 4,5 tetapi kapasitas sangat rendah (~1–2 kg/t), kemungkinan keasaman tersimpan
    (jarosit/alunit), bukan sulfida.
  - Sulfur tidak membedakan NAF dan PAF-LC di zona oksida (AUC ≈ 0,51). PAF-HC mudah dikenali
    (AUC SCIS 0,97).
  - Prediksi konformal (Mondrian, α 0,10): tiap sampel mendapat himpunan kelas yang memuat kelas
    benar 90% kali. PAF-HC sering tunggal (71%); batuan oksida biasanya "NAF atau PAF-LC".
  - Kelas pengelolaan konservatif seluruh basis data: NAF 43 m (hanya yang terukur), PAF-LC
    797 m, PAF-HC 2.216 m, di antaranya PAF-HC yakin 866 m. **Tidak ada interval yang diberi NAF
    tanpa uji NAG.**
  - Daftar uji NAG: 736 run, 2.412 m; prioritas 1: 375 run / 1.350 m.
  - Pengelompokan tanpa label (GMM): U1 (RJDH012) memisahkan PAF-HC dari sisanya; di zona oksida
    tidak ada struktur kimia (BIC K = 1).
  - Aliran dan reseptor: jaringan sungai **turunan dari DEM lidar** (bukan data resmi), sempadan
    50 m (Permen PUPR 28/PRT/M/2015 `[VERIFY]`).
- **Keterbatasan yang wajib ditulis:** satu lubang, 16 sampel sulfida, tidak ada ANC terukur
  (NAPP tidak bisa dihitung langsung), hasil berlaku untuk material mirip RJDH012.
- **Ucapan presentasi:**
  > Hanya satu lubang, RJDH012, yang punya uji asam (NAG). Dari situ kami bentuk tiga kelas:
  > bukan pembentuk asam, pembentuk asam kapasitas rendah, dan kapasitas tinggi. Model mengenali
  > batuan kapasitas tinggi yang kaya sulfida dengan andal, tetapi tidak ada unsur yang bisa
  > membedakan batuan oksida non-asam dari yang kapasitas rendah. Prediksi konformal membuat ini
  > eksplisit, jadi batuan yang belum diuji kami kelola menurut kelas terburuk dalam himpunannya,
  > dan kami daftar interval yang perlu uji NAG.

### Bab 7. Sintesis Eksplorasi (+ Bonus desain eksplorasi)
Bobot rubrik: prospeksi 50, eksplorasi lanjutan 50; bonus desain 100. Maksimal 4 penampang.

- **File:** `ml6_summary.csv`, `ml6_cv.csv`, `ml6_kandidat.csv`, `ml6_usulan_lubang.csv`
  (format kolar/survei, siap untuk ioGAS); `gis/ml6_target.gpkg`, `gis/ml6_penampang.gpkg`,
  `gis/ml6_{ucb_maks,meter_cutoff,sd_rerata}.tif`.
- **Gambar:** `13_profil_theta_v1.png`, `13_cv_lopo_v1.png`, `13_variogram_gp_v1.png`,
  `13_peringkat_kandidat_v1.png`.
- **Peta/penampang bonus (siap pakai):** `outputs/maps/13_peta_desain_v1.png`,
  `13_penampang_desain_v1.png` (D–D'); proyek QGIS `outputs/maps/13_ml6_desain.qgz`.
- **Angka kunci:**
  - Gaussian process = kriging (secara matematis setara). Kontinuitas emas pendek, **~10–25 m**.
    Di antara pad, model tidak lebih baik dari rata-rata; arah tren tidak dapat ditentukan dari
    data bor.
  - **5 usulan lubang** (semua 200 m, dip −60°, azimut 315°):
    - RJ-U01, RJ-U02: perluasan di dekat intersep terbaik (RJDH012/016/017);
    - RJ-U03: penutup celah antar-pad, untuk mengukur kontinuitas yang belum diketahui;
    - RJ-U04, RJ-U05 (tier B): uji anomali tanah ML-3, tanpa menjanjikan kadar.
  - Semua kolar di lereng landai, di luar sempadan sungai 50 m, dengan penanganan PAF
    (sump berlapis, cutting PAF-HC dikantongi, uji NAG pada inti baru).
- **Ucapan presentasi:**
  > Kami memakai Gaussian process, yang secara matematis sama dengan kriging, untuk menaksir emas
  > di antara lubang beserta tingkat keyakinannya. Temuan jujurnya: kontinuitas emas pendek,
  > sekitar 10–25 m. Karena itu kami usulkan lubang dengan tugas berbeda: dua perluasan di dekat
  > intersep terbaik, satu pengisi celah untuk mengukur kontinuitas, dan dua untuk menguji anomali
  > tanah. Semua kolar berada di luar sempadan sungai 50 m dengan penanganan PAF.

### Bab 8. Kesimpulan
Rangkum per bab di atas. Tekankan tema "ML yang tahu apa yang tidak diketahuinya": setiap peta
dan kelas punya ukuran ketidakpastian (probabilitas, stabilitas bootstrap, himpunan konformal,
deviasi standar kriging).

### Bab 9. Daftar Pustaka
Lihat bagian 4 di bawah. **Semua referensi wajib diperiksa dari sumber aslinya.**

### Pembahasan tambahan: pembanding literatur (§9)
Dapat dimasukkan sebagai subbab diskusi (Bab 3/5) atau satu slide cadangan.

- **Gambar:** `14_jansson_vs_gmm_v1.png`, `14_rf_vs_hmm_v1.png`. File: `s9_*.csv`.
- **Jansson dkk. (2022) `[VERIFY]`** (k-means pada data log-rasio): rasio log menghapus besaran
  kadar, jadi kelompoknya mengikuti "tanda tangan" kimia, bukan kadar; tidak cocok dengan zona
  H/M/L kita. Di RJDH012, GMM kita memisahkan oksida dan sulfida jauh lebih baik pada jumlah
  kelompok yang sama (ARI 0,56 vs 0,02).
- **Fontana dkk. `[VERIFY]`** (Random Forest + penghalusan bawah-lubang; analog sederhana, bukan
  replikasi Data Mosaic): RF lebih cocok dengan log (V 0,54 vs 0,45) karena dilatih dengan log;
  setelah dihaluskan fragmentasinya setara HMM (6,9 vs 6,3 per 100 m). HMM jauh lebih konsisten
  antar-lubang kembar < 10 m (0,93 vs 0,40). Jangan bandingkan akurasi kita dengan 82,5% mereka.
- **Ucapan presentasi:**
  > Kami mengulang dua alur kerja dari literatur pada sampel yang sama. Yang pertama mengelompokkan
  > menurut rasio unsur, bukan kadar, jadi tidak menggantikan zonasi kadar kami. Yang kedua, random
  > forest yang dihaluskan, cocok dengan log ahli geologi, tetapi HMM kami memberi jawaban yang
  > sama pada lubang kembar yang berjarak beberapa meter. Karena itu HMM kami pakai untuk penampang
  > korelasi.

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
| Laporan dan slide | Tim | Ikuti format brief |

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
  itulah bahan ucapan presentasi (versi Bahasa ada di panduan ini). Cari dengan judul `## <tanggal>
  · <langkah>`.
- Untuk agen AI (Claude Code, Codex): aturan ada di `AGENTS.md`; agen membaca ekor `LOG.md` lebih
  dulu dan mencatat setiap keputusan di sana. Jangan memakai layanan AI daring untuk mengolah data.
