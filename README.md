# SiLoak

## Deskripsi

SiLoak adalah aplikasi web pengelolaan barang bekas yang menghubungkan masyarakat dengan titik pengumpulan dan layanan *pick up*. Pengguna dapat mengumpulkan barang bekas yang mereka miliki untuk mendapatkan insentif berdasarkan berat barang yang disetorkan, atau memilih untuk mendonasikan hasil pengumpulan mereka.

Aplikasi ini dirancang untuk membuat pengelolaan sampah menjadi lebih mudah, terukur, dan memberikan nilai tambah bagi masyarakat.

SiLoak membantu pengguna mengelola sampah dengan dua cara utama:

### 1. Setor Loak

- Pengguna mengumpulkan barang bekas dan membawanya ke *warehouse* atau titik pengumpulan terdekat.
- Barang ditimbang oleh petugas.
- Pengguna memperoleh insentif berdasarkan berat sampah yang berhasil dikumpulkan.

### 2. *Pick up* Loak

- Pengguna dapat meminta layanan *pick up* dari lokasi mereka.
- Kurir/petugas akan datang ke lokasi pengguna untuk mengambil sampah.
- Pengguna dapat melihat status pickup hingga sampah berhasil diterima dan ditimbang.

Selain mendapatkan insentif, pengguna juga dapat memilih untuk mendonasikan hasil pengumpulan sampah daripada menerima insentif secara pribadi.

---

## Manfaat bagi Masyarakat

SiLoak bertujuan untuk:

- Mempermudah masyarakat dalam menemukan lokasi pengumpulan barang bekas.
- Memberikan insentif kepada masyarakat yang aktif mengelola dan mengumpulkan barang bekas.
- Menyediakan alternatif *pick up* bagi pengguna yang tidak dapat datang langsung ke titik pengumpulan.
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

## 1. User & Authentication Module

Mengelola akun dan informasi pengguna.

### Fitur

- Register
- Login & logout
- User profile
- Update profile
- Pengelolaan informasi kontak
- Melihat riwayat aktivitas pengguna
- Authentication-based access control

**Package:** `auth`  
**PIC:** Bagas Aulia Rezki

---

## 2. Waste Submission Module

Modul ini menangani proses pengguna dalam menyetorkan sampah hingga sampah tersebut berhasil ditimbang dan diverifikasi.

### Fitur

- Membuat pengajuan penyetoran sampah
- Memilih jenis sampah
- Memasukkan jumlah/berat sampah
- Memilih collection point
- Melihat detail pengajuan
- Melihat status pengajuan
- Memperbarui pengajuan yang masih dapat diubah
- Membatalkan pengajuan
- Melihat riwayat penyetoran
- Mencatat hasil penimbangan sampah

**Package:** `waste`  
**PIC:** Samuel Kaevin Phasca

---

## 3. Incentive & Wallet Module

### Fitur

- Menghitung insentif berdasarkan berat sampah
- Menambahkan insentif ke saldo pengguna
- Menampilkan saldo pengguna
- Menampilkan riwayat transaksi insentif
- Mengajukan withdrawal
- Melihat status withdrawal
- Memilih untuk mendonasikan insentif
- Melihat riwayat donasi

**Package:** `incentive`  
**PIC:** Nadin Putri Cahyani

---

## 4. Pickup Module

Modul ini mengelola layanan pengambilan sampah langsung dari lokasi pengguna.

### Fitur

- Membuat pickup request
- Menentukan alamat pickup
- Memilih jadwal pickup
- Melihat detail pickup
- Melihat status pickup
- Melihat petugas/kurir yang ditugaskan
- Memperbarui status pickup
- Membatalkan pickup request yang masih dapat dibatalkan
- Melihat riwayat pickup

**Package:** `pickup`  
**PIC:** Lee Devin Gerrard

---

## 5. Collection Point & Location Module

### Fitur

- Menampilkan collection point
- Mencari collection point berdasarkan lokasi
- Menampilkan alamat collection point
- Menampilkan koordinat/lokasi
- Menampilkan jam operasional
- Menampilkan jenis layanan yang tersedia
- Filtering collection point
- Mencari collection point terdekat
- Integrasi dengan Public API berbasis lokasi

**Package:** `location`  
**PIC:** Tiffany Ekklesia

---

# Public API

SiLoak menggunakan OpenStreetMap dan Google OAuth sebagai Public API eksternal untuk mendukung fitur berbasis lokasi.

Public API digunakan untuk membantu aplikasi dalam:

- Menentukan lokasi pengguna.
- Mencari lokasi berdasarkan alamat.
- Menampilkan dan/atau mencari titik pengumpulan berdasarkan lokasi.
- Mendukung pencarian lokasi terdekat.

## API Documentation

- OpenStreetMap:  
  https://api.openstreetmap.org/api/0.6

- Google OAuth:  
  https://console.cloud.google.com

API akan digunakan sebagai sumber data eksternal untuk fitur lokasi, sementara data utama seperti pengguna, transaksi sampah, titik pengumpulan, pickup, dan insentif akan dikelola melalui database aplikasi.

---

# Jenis Pengguna

SiLoak memiliki beberapa jenis pengguna:

## 1. Giver

Masyarakat yang menggunakan SiLoak untuk memberikan barang bekasnya.

### Giver dapat:

- Mengelola profil.
- Menyetorkan sampah.
- Meminta pickup.
- Mencari titik pengumpulan.
- Melihat hasil penimbangan.
- Mendapatkan insentif.
- Melakukan donasi.
- Melihat riwayat transaksi.

---

## 2. Collector/Kurir

Petugas yang menangani pengambilan barang bekas melalui layanan *pickup*.

### Collector dapat:

- Melihat permintaan pickup.
- Menerima atau mengambil tugas pickup.
- Melihat lokasi pickup.
- Memperbarui status pickup.
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
- Mengelola data pickup.
- Memantau aktivitas aplikasi.

---

# Tautan Deployment PWS

https://bagas-aulia-siloak.pws.cs.ui.ac.id/

---

# Tautan Desain Figma

https://www.figma.com/files/team/1681860133051205638/folder/655408932?fuid=1546679538808144971