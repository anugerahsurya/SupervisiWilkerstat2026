# SupervisiWilkerstat2026

Aplikasi Python untuk supervisi batas SLS dan titik bangunan SE2026. Pilih dua berkas GeoJSON untuk membandingkan data dengan master FRS, hierarki perubahan batas, dan indikator pada lembar supervisi. Setiap temuan menyertakan objek, alasan pemeriksaan, dan acuannya.

## Menjalankan aplikasi

1. Siapkan Python 3.10 atau lebih baru dan jalankan `python -m pip install -r supervisi/requirements.txt`.
2. Buat `supervisi/.env` dengan variabel `WILKERSTAT_DATABASE_URL` berisi connection string PostgreSQL dari menu **Connect** pada proyek Supabase. Gunakan koneksi langsung atau session pooler dengan TLS. Akun server perlu akses ke skema privat `wilkerstat` dan izin membuat skema pada penyiapan pertama.
3. Jalankan `python supervisi/server.py` atau buka **supervisi/Buka Supervisi.cmd** di Windows. Akses aplikasi di http://127.0.0.1:8765/.

Aplikasi menyimpan ringkasan dan seluruh baris temuan sebagai satu arsip terkompresi per pemeriksaan di PostgreSQL Supabase. Catatan per indikator, identitas supervisi, dan tindak lanjut tersimpan terpisah sehingga dapat diedit tanpa mengunggah ulang hasil. Salinan SQLite di komputer mempercepat pencarian dan ekspor. Browser menyimpan sementara teks yang masih menunggu konfirmasi penyimpanan.

Proyek Supabase yang sudah diisi dapat memulihkan hasil awal, dua workbook pembanding, dan salinan daftar Monev dari database. Untuk proyek kosong, tempatkan workbook `msubsls_26_1_1300.xlsx` dan `hirarki_sls_26_1_1300.xlsx` di folder `Referensi`, serta salinan resmi `monev_1308.json` di folder `supervisi`. Sumber internal dan kredensial disediakan terpisah dari repositori.

## Membaca dan membagikan hasil

Klik indikator untuk melihat aturan, mencari objek, dan menulis catatan konsultasi. Nama kolom seperti `unique_bang` diberi penanda khusus pada layar dan laporan. Simpan alamat hasil untuk membukanya kembali. Melalui **Buat laporan**, unduh HTML yang dapat dicetak menjadi PDF serta CSV untuk menelusuri semua objek. Impor kolom ID sebagai teks agar angka panjang tetap utuh.

Pemeriksaan kelengkapan FRS mengasumsikan kiriman satu kabupaten/kota utuh di Sumatera Barat. Pemeriksaan posisi titik pada poligon 2026 Semester I memerlukan konfirmasi dengan peta lapangan 2025 Semester II yang sudah disesuaikan.
