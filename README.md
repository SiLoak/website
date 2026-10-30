# SiLoak

<p align="center">
  <img src="static/images/mascot.png" alt="Maskot SiLoak" width="180">
</p>

## Daftar Isi

- [Tentang SiLoak](#deskripsi)
- [Menjalankan Proyek](#menjalankan-proyek)
- [Manfaat bagi Masyarakat](#manfaat-bagi-masyarakat)
- [Anggota Kelompok](#anggota-kelompok-5-pbp-e)
- [Modul Aplikasi](#modul-aplikasi)
- [Integrasi dan Data Eksternal](#integrasi-dan-data-eksternal)
- [Jenis Pengguna](#jenis-pengguna)
- [Penggunaan AI dan Sumber Eksternal](#penggunaan-ai-dan-sumber-eksternal)
- [Penerapan dan Desain](#penerapan-dan-desain)
- [Lisensi](#lisensi)

## Deskripsi

SiLoak adalah aplikasi web pengelolaan barang bekas yang menghubungkan masyarakat dengan titik pengumpulan dan layanan penjemputan. Pengguna dapat mengumpulkan barang bekas yang mereka miliki untuk mendapatkan insentif berdasarkan berat barang yang disetorkan, atau memilih untuk mendonasikan hasil pengumpulan mereka.

Aplikasi ini dirancang untuk membuat pengelolaan sampah menjadi lebih mudah, terukur, dan memberikan nilai tambah bagi masyarakat.

SiLoak membantu pengguna mengelola sampah dengan dua cara utama:

### 1. Setor Loak

- Pengguna mengumpulkan barang bekas dan membawanya ke gudang atau titik pengumpulan terdekat.
- Barang ditimbang oleh petugas.
- Pengguna memperoleh insentif berdasarkan berat sampah yang berhasil dikumpulkan.

### 2. Layanan Penjemputan

- Pengguna dapat meminta layanan penjemputan dari lokasinya.
- Kurir atau petugas akan datang ke lokasi pengguna untuk mengambil sampah.
- Pengguna dapat melihat status penjemputan hingga sampah berhasil diterima dan ditimbang.

Selain mendapatkan insentif, pengguna juga dapat memilih untuk mendonasikan hasil pengumpulan sampah daripada menerima insentif secara pribadi.

---

## Menjalankan Proyek

### Persyaratan

- Python 3.10 atau lebih baru.
- `pip` untuk memasang dependensi Python.
- SQLite (sudah tersedia bersama Python) atau PostgreSQL jika `DATABASE_URL` diatur.
- Kredensial Google OAuth hanya diperlukan untuk mengaktifkan masuk dengan Google.

### Instalasi lokal

1. Buat dan aktifkan lingkungan virtual Python:

   ```bash
   python -m venv .venv
   ```

   Di Linux atau macOS:

   ```bash
   source .venv/bin/activate
   ```

   Di Windows PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. Pasang dependensi proyek:

   ```bash
   pip install -r requirements.txt
   ```

3. Dari direktori utama proyek, buat berkas konfigurasi lokal dari contoh yang tersedia. Di Linux atau macOS:

   ```bash
   cp .env.example .env
   ```

   Di Windows PowerShell, jalankan `Copy-Item .env.example .env`.

   Buat kunci rahasia Django dengan perintah berikut, lalu masukkan hasilnya ke `SECRET_KEY` di `.env`:

   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

   `DATABASE_URL` dapat dibiarkan kosong untuk memakai SQLite. Jangan memasukkan berkas `.env` yang berisi rahasia ke Git.

4. Siapkan basis data dan jalankan server pengembangan:

   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

5. Buka <http://127.0.0.1:8000/> di peramban. Untuk membuat akun administrator Django, jalankan `python manage.py createsuperuser` di terminal lain.

### Mengaktifkan masuk dengan Google

Buat klien OAuth bertipe aplikasi web di Google Cloud Console. Tambahkan alamat penerima respons berikut ke daftar URI pengalihan yang diizinkan:

```text
http://localhost:8000/auth/google/callback/
```

Isi `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, dan `GOOGLE_OAUTH_REDIRECT_URI` di `.env`. Nilai `GOOGLE_OAUTH_REDIRECT_URI` harus sama persis dengan alamat penerima respons yang didaftarkan. Tanpa kredensial tersebut, fitur masuk Google tidak aktif; aplikasi tetap dapat dijalankan untuk pengembangan.

### Perintah berguna

```bash
python manage.py test
python manage.py seed_waste_catalog
```

Perintah pertama menjalankan pengujian Django. Perintah kedua menyinkronkan ulang katalog sampah dan titik pengumpulan dari `waste.json` dan `dropoff.json`.

### Struktur proyek

| Direktori atau berkas | Kegunaan |
| --- | --- |
| `auth/` | Autentikasi, profil pengguna, dan integrasi Google OAuth. |
| `waste/` | Pengajuan setoran, katalog sampah, dan penimbangan. |
| `wallet/` | Insentif, penarikan saldo, transaksi, dan donasi. |
| `pickup/` | Permintaan penjemputan dan alur kerja petugas. |
| `location/` | Titik pengumpulan, pencarian lokasi, dan pencarian alamat berdasarkan koordinat. |
| `main/` | Konfigurasi proyek Django dan halaman utama. |
| `templates/` | Templat halaman aplikasi. |
| `static/` | Gambar, lembar gaya, dan JavaScript. |
| `waste.json`, `dropoff.json` | Data awal jenis sampah dan titik pengumpulan. |

---

## Manfaat bagi Masyarakat

SiLoak bertujuan untuk:

- Mempermudah masyarakat dalam menemukan lokasi pengumpulan barang bekas.
- Memberikan insentif kepada masyarakat yang aktif mengelola dan mengumpulkan barang bekas.
- Menyediakan alternatif penjemputan bagi pengguna yang tidak dapat datang langsung ke titik pengumpulan.
- Mendorong pemilahan dan pengelolaan sampah secara lebih teratur.
- Membuka pilihan bagi masyarakat untuk menyalurkan nilai sampah mereka melalui donasi.

---

## Anggota Kelompok 5 PBP E

1. Bagas Aulia Rezki (2506656545)
2. Tiffany Ekklesia (2506546062)
3. Lee Devin Gerrard (2506548452)
4. Nadin Putri Cahyani (2506623332)
5. Samuel Kaevin Phasca (2506657333)

---

# Modul Aplikasi

SiLoak terdiri dari beberapa modul utama yang saling terintegrasi.

## 1. Modul Pengguna dan Autentikasi

Mengelola akun dan informasi pengguna.

### Fitur

- Pendaftaran akun
- Masuk dan keluar
- Profil pengguna
- Memperbarui profil
- Pengelolaan informasi kontak
- Melihat riwayat aktivitas pengguna
- Pengaturan akses berdasarkan autentikasi

**Paket:** `auth`  
**Penanggung jawab:** Bagas Aulia Rezki

---

## 2. Modul Pengajuan Setoran Sampah

Modul ini menangani proses pengguna dalam menyetorkan sampah hingga sampah tersebut berhasil ditimbang dan diverifikasi.

### Fitur

- Membuat pengajuan penyetoran sampah
- Memilih jenis sampah
- Memasukkan jumlah/berat sampah
- Memilih titik pengumpulan
- Melihat detail pengajuan
- Melihat status pengajuan
- Memperbarui pengajuan yang masih dapat diubah
- Membatalkan pengajuan
- Melihat riwayat penyetoran
- Mencatat hasil penimbangan sampah

**Paket:** `waste`  
**Penanggung jawab:** Tiffany Ekklesia dan Bagas Aulia Rezki

---

## 3. Modul Insentif dan Dompet

### Fitur

- Menghitung insentif berdasarkan berat sampah
- Menambahkan insentif ke saldo pengguna
- Menampilkan saldo pengguna
- Menampilkan riwayat transaksi insentif
- Mengajukan penarikan saldo
- Melihat status penarikan saldo
- Memilih untuk mendonasikan insentif
- Melihat riwayat donasi

**Paket:** `wallet`  
**Penanggung jawab:** Nadin Putri Cahyani

---

## 4. Modul Penjemputan

Modul ini mengelola layanan penjemputan sampah langsung dari lokasi pengguna.

### Fitur

- Membuat permintaan penjemputan
- Menentukan alamat penjemputan
- Memilih jadwal penjemputan
- Melihat detail dan status penjemputan
- Melihat petugas atau kurir yang ditugaskan
- Memperbarui status penjemputan
- Membatalkan permintaan yang masih dapat dibatalkan
- Melihat riwayat penjemputan

**Paket:** `pickup`  
**Penanggung jawab:** Lee Devin Gerrard

---

## 5. Modul Titik Pengumpulan dan Lokasi

### Fitur

- Menampilkan titik pengumpulan
- Mencari titik pengumpulan berdasarkan lokasi
- Menampilkan alamat titik pengumpulan
- Menampilkan koordinat/lokasi
- Menampilkan jam operasional
- Menampilkan jenis layanan yang tersedia
- Menyaring titik pengumpulan
- Mencari titik pengumpulan terdekat
- Integrasi dengan API publik berbasis lokasi

**Paket:** `location`  
**Penanggung jawab:** Samuel Kaevin Phasca

---

## Integrasi dan Data Eksternal

SiLoak memakai data peta dan pencarian lokasi dari OpenStreetMap serta Nominatim. Google OAuth digunakan untuk autentikasi pengguna, bukan untuk fitur lokasi.

Layanan eksternal membantu aplikasi untuk:

- Menentukan lokasi pengguna.
- Mencari lokasi berdasarkan alamat.
- Menampilkan dan/atau mencari titik pengumpulan berdasarkan lokasi.
- Mendukung pencarian lokasi terdekat.

### Dokumentasi API

- API OpenStreetMap:  
  https://api.openstreetmap.org/api/0.6

- API pencarian lokasi Nominatim:  
  https://nominatim.org/release-docs/latest/api/Overview/

### Konfigurasi Google OAuth di Sisi Server

Server Django menggunakan sesi untuk mempertahankan status masuk pengguna. Buat klien OAuth 2.0 bertipe aplikasi web di Google Cloud Console, lalu tambahkan alamat penerima respons berikut ke daftar URI pengalihan yang diizinkan. Salin `.env.example` menjadi `.env`, lalu isi ID klien dan rahasia klien:

```text
GOOGLE_OAUTH_CLIENT_ID=your-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/auth/google/callback/
```

Rute `GET /auth/google/login/` memulai proses masuk dan `GET /auth/google/callback/` memproses respons dari Google. Setelah respons berhasil diverifikasi, aplikasi menghubungkan identitas Google dengan akun pengguna, membuat sesi Django, lalu mengarahkan pengguna untuk melengkapi profil atau menuju dasbor. URI penerima respons harus sama persis dengan yang didaftarkan di Google Cloud. Jalankan migrasi basis data sebelum menggunakan OAuth.

Data utama seperti pengguna, transaksi sampah, titik pengumpulan, penjemputan, dan insentif dikelola di basis data aplikasi.

### Memuat Ulang Data Awal Sampah

Migrasi aplikasi `waste` mengisi katalog jenis sampah dari `waste.json` dan titik pengumpulan dari `dropoff.json` saat `python manage.py migrate` dijalankan. Untuk menyinkronkan ulang basis data setelah salah satu berkas JSON diperbarui, jalankan:

```bash
python manage.py seed_waste_catalog
```

Titik yang belum memiliki alamat akan menggunakan teks `Alamat belum tersedia`, sedangkan jam operasional yang belum tersedia dibiarkan kosong.

---

# Jenis Pengguna

SiLoak memiliki beberapa jenis pengguna:

## 1. Penyetor

Pengguna yang memakai SiLoak untuk menyetorkan barang bekas.

### Penyetor dapat:

- Mengelola profil.
- Menyetorkan sampah.
- Meminta penjemputan.
- Mencari titik pengumpulan.
- Melihat hasil penimbangan.
- Mendapatkan insentif.
- Melakukan donasi.
- Melihat riwayat transaksi.

---

## 2. Petugas Pengangkut

Petugas yang menangani pengambilan barang bekas melalui layanan penjemputan.

### Petugas dapat:

- Melihat permintaan penjemputan.
- Menerima atau mengambil tugas penjemputan.
- Melihat lokasi penjemputan.
- Memperbarui status penjemputan.
- Mengonfirmasi pengambilan sampah.

---

## 3. Admin

Pihak yang mengelola operasional SiLoak.

### Admin dapat:

- Mengelola data pengguna.
- Mengelola jenis sampah dan harga insentif.
- Mengelola titik pengumpulan.
- Memverifikasi berat sampah.
- Mengelola transaksi.
- Mengelola data penjemputan.
- Memantau aktivitas aplikasi.

---

# Penerapan dan Desain

## Tautan Penerapan PWS

https://bagas-aulia-siloak.pws.cs.ui.ac.id/

---

## Desain Figma

https://www.figma.com/files/team/1681860133051205638/folder/655408932?fuid=1546679538808144971
**Penanggung jawab desain:** Tiffany Ekklesia dan Nadin Putri Cahyani

## Lisensi

SiLoak menggunakan lisensi MIT. Lihat berkas [LICENSE](LICENSE) untuk ketentuan lengkap.

---

# Penggunaan AI dan Sumber Eksternal

## Modul Dompet (Nadin Putri Cahyani)

**Alat AI yang Digunakan:** ChatGPT (OpenAI)

ChatGPT digunakan sebagai alat bantu dalam pengembangan modul dompet, terutama untuk berdiskusi, memahami alur penerapan, menelusuri dan memperbaiki kesalahan, serta menguji kode. Beberapa bagian yang dibantu antara lain:

- Integrasi dompet dengan pengajuan setoran: Membantu membahas pencatatan insentif setelah pengajuan setoran diverifikasi admin, termasuk penggunaan layanan Django dan pencegahan pencatatan transaksi ganda.
- Sistem penarikan: Membantu memahami dan mengevaluasi perhitungan biaya administrasi serta biaya transfer untuk penarikan melalui bank dan dompet digital, termasuk pengelolaan saldo dan status transaksi.
- Sistem donasi: Membantu membedakan donasi yang berasal dari insentif setoran dengan donasi langsung dari saldo dompet.
- Pengelolaan transaksi: Membantu menelusuri masalah pada riwayat transaksi, memperbarui deskripsi transaksi, serta memeriksa mekanisme pengembalian saldo jika penarikan gagal.

Seluruh kode dan saran yang dihasilkan AI tetap ditinjau, disesuaikan dengan struktur proyek, serta diuji kembali secara mandiri.

**Sumber Eksternal:**

- https://docs.djangoproject.com/en/6.1/topics/db/transactions/
- https://docs.djangoproject.com/en/6.1/ref/models/querysets/

## Modul Penjemputan (Lee Devin Gerrard)

**Alat AI yang Digunakan:** ChatGPT (OpenAI)

ChatGPT digunakan sebagai asisten diskusi untuk membantu pengembangan modul penjemputan, terutama terkait alur penerapan, praktik terbaik, penelusuran kesalahan, dan pengujian kode. Penggunaannya antara lain:

- Membantu mengevaluasi struktur dan kerangka modul yang sudah saya siapkan.
- Membantu memberikan praktik terbaik untuk alur penerapan kode.
- Membantu menelusuri kesalahan kode yang belum saya ketahui cara memperbaikinya.
- Membantu menyusun formulir penjemputan berdasarkan kolom yang tersedia pada formulir pengajuan setoran, serta mengintegrasikannya dengan modul sampah.

**Sumber Eksternal:**

- https://docs.djangoproject.com/en/6.1/topics/testing/
- https://docs.djangoproject.com/en/6.1/topics/forms/
- https://v2.tailwindcss.com/docs

## Modul Lokasi (Samuel Kaevin Phasca)

**Alat AI yang Digunakan:** Claude (Anthropic), melalui Claude Code

Claude digunakan sebagai asisten pemrograman untuk berdiskusi, memecahkan masalah, serta membantu menyusun kode modul lokasi berdasarkan kebutuhan yang saya tentukan dari README. Saya memberi arahan, membuat keputusan desain, dan meminta perbaikan sesuai masukan tim. Penggunaannya antara lain:

- Membantu mengevaluasi struktur kode pada modul yang saya kerjakan.
- Membantu memeriksa kode, konflik, dan kesalahan.
- Membantu menulis bagian kode yang sulit saya kerjakan sendiri.
- Membantu menganalisis pembagian dan keterkaitan pengerjaan antaranggota.

**Sumber Eksternal:**

- https://docs.djangoproject.com/en/6.1/topics/testing/
- https://docs.djangoproject.com/en/6.1/topics/forms/
- https://docs.djangoproject.com/en/6.1/howto/custom-template-tags/
- https://leafletjs.com/reference.html
- https://nominatim.org/release-docs/latest/api/Overview/
- https://operations.osmfoundation.org/policies/nominatim/
- https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API
- https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API

## Modul Pengguna dan Autentikasi (Bagas Aulia Rezki)

**Alat AI yang Digunakan:** ChatGPT (OpenAI)

ChatGPT digunakan sebagai alat bantu diskusi dan pengembangan modul pengguna dan autentikasi, terutama untuk memahami alur masuk dan keluar, integrasi masuk dengan Google OAuth, pengelolaan profil pengguna, penelusuran kesalahan, dan pengujian kode. Penggunaannya antara lain:

- Membantu mengevaluasi alur autentikasi pengguna dan pengelolaan sesi.
- Membantu memahami integrasi Google OAuth, termasuk penggunaan `state`, `nonce`, PKCE, pertukaran kode otorisasi, dan verifikasi token.
- Membantu meninjau alur pelengkapan profil, termasuk validasi dan penyimpanan nomor telepon.
- Membantu memeriksa keamanan alamat tujuan setelah pengguna masuk agar pengalihan hanya menuju alamat yang diizinkan.
- Membantu menganalisis dan memperbaiki pengujian untuk alur masuk, pemrosesan respons Google, keluar, dan pelengkapan profil.

Seluruh saran dan kode yang dihasilkan AI ditinjau, disesuaikan dengan kebutuhan serta struktur proyek, dan diuji kembali secara mandiri.

**Sumber Eksternal:**

- https://docs.djangoproject.com/en/6.1/topics/auth/default/
- https://docs.djangoproject.com/en/6.1/ref/contrib/auth/
- https://developers.google.com/identity/protocols/oauth2/web-server

## Modul Pengajuan Setoran Sampah (Tiffany Ekklesia)

**Alat AI yang Digunakan:** ChatGPT (OpenAI)

ChatGPT digunakan sebagai alat bantu diskusi dan pengembangan modul pengajuan setoran sampah, terutama untuk memahami alur pengajuan, formulir, validasi data, dan pengujian. Penggunaannya antara lain:

- Membantu membahas alur pembuatan dan pembaruan pengajuan setoran sampah.
- Membantu meninjau formulir pemilihan jenis sampah dan titik pengumpulan, termasuk masukan jumlah atau berat sampah.
- Membantu memahami validasi data dan aturan perubahan pengajuan sebelum diverifikasi.
- Membantu menelusuri kesalahan pada integrasi katalog sampah, titik pengumpulan, dan proses penimbangan.
- Membantu menyusun dan meninjau pengujian untuk proses pengajuan dan perubahan status.

Saran dan kode dari AI ditinjau, disesuaikan dengan kebutuhan serta struktur proyek, dan diuji kembali secara mandiri.

**Sumber Eksternal:**

- https://docs.djangoproject.com/en/5.0/topics/forms/
- https://docs.djangoproject.com/en/5.0/topics/db/models/
- https://docs.djangoproject.com/en/5.0/topics/testing/

## Strategi Penyusunan Instruksi AI, Batasan, dan Pemeriksaan Manual

### Tujuan dan strategi penyusunan instruksi

AI digunakan sebagai alat bantu untuk memahami alur fitur, membahas pilihan penerapan, mencari kemungkinan penyebab kesalahan, dan menyusun langkah pengujian. Instruksi kepada AI mencakup konteks modul, tujuan perubahan, alur yang diharapkan, berkas atau potongan kode terkait, serta pesan kesalahan bila ada. Jawaban AI kemudian ditindaklanjuti dengan pertanyaan untuk meminta penjelasan atau alternatif yang lebih sesuai dengan proyek.

### Batasan AI

Saran AI dapat keliru, tidak lengkap, memakai antarmuka pustaka yang berbeda versinya, atau tidak sesuai dengan aturan bisnis dan struktur SiLoak. Kode yang dihasilkan juga belum tentu menangani keamanan, transaksi, dan kondisi gagal secara memadai.

### Peninjauan dan perbaikan manual

Setiap anggota bertanggung jawab atas modulnya sendiri. Saran AI dibandingkan dengan dokumentasi resmi dan kode proyek, lalu ditinjau, disesuaikan, dan diuji kembali. Anggota memperbaiki sendiri bagian yang tidak cocok dengan model data, alur aplikasi, validasi, atau hasil pengujian; keluaran AI tidak langsung dianggap benar atau diterapkan tanpa pemeriksaan.
