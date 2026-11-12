# CCTV-Monitoring-Employee

Aplikasi lokal Python: detektor orang + detektor HP, tracking ByteTrack, polygon zona,
konfirmasi temporal, dashboard berlogin, SQLite, review manusia, ekspor CSV, retensi otomatis.
Dataset pilihan: https://www.kaggle.com/datasets/a165079/cellphoneobjectdetectionusingyolov7

## Batas penggunaan

Ini baseline **kedekatan spasial HP dengan orang**, BUKAN pengenal penggunaan HP yang
tervalidasi, maksud pribadi, status bekerja, absensi, atau produktivitas. HP yang hanya
berada di meja dalam bounding box orang bisa memicu kejadian. Tidak ada deteksi tangan,
pengenalan wajah, identitas karyawan, cross-camera identity, atau sanksi otomatis.
Track ID sementara dan bisa berubah/berulang setelah reconnect. Semua kejadian perlu
review manusia; `confirmed_visual` hanya mengonfirmasi pengamatan visual, bukan pelanggaran.
Durasi adalah rentang observasi dengan toleransi gap, bukan total detik penggunaan pasti.

## 1. Instalasi Windows (PowerShell)

Gunakan **Python 3.11 atau 3.12 64-bit** untuk kompatibilitas PyTorch. Python 3.14 belum
menjadi lingkungan yang diuji untuk dependensi AI proyek ini. Jalankan dari folder ini:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Isi `MONITOR_PASSWORD` di `.env` dengan password unik minimal 16 karakter.
Tidak ada default password. Jangan menimpa `.env` yang sudah Anda isi.
Paket ultralytics/PyTorch dapat jauh lebih besar dari dataset 210 MB. Unduhan model
pretrained juga membutuhkan internet pada penggunaan pertama. Gunakan instruksi resmi
PyTorch untuk memasang build CUDA yang cocok jika memakai NVIDIA GPU.

## 2. Unduh dataset Kaggle

Kaggle membutuhkan akun dan kredensial Anda sendiri. Buat API token di pengaturan akun,
simpan legacy `kaggle.json` di `%USERPROFILE%\.kaggle\kaggle.json`, atau atur kredensial
sesuai dokumentasi Kaggle CLI versi terpasang. Jangan masukkan token ke repo atau chat.

Periksa lisensi Kaggle **CC BY-SA 4.0**, sumber asli Roboflow, atribusi dan ketentuan
penggunaan sebelum dipakai operasional. Label lisensi unggahan ulang bukan jaminan
seluruh hak data sudah terpenuhi. Skrip tidak mengunduh sebelum diperintahkan:

```powershell
.\.venv\Scripts\python.exe scripts/download_dataset.py --accept-dataset-terms
.\.venv\Scripts\python.exe scripts/prepare_dataset.py
```

Penyiapan mencari `data.yaml`, membaca nama kelas, memeriksa anotasi YOLO detection,
menemukan folder train/valid/test dan menghasilkan `data/phone-data.yaml` berpath absolut.
Tidak menjalankan instruksi atau blok download dari YAML pihak ketiga. Jika struktur
arsip berbeda, skrip berhenti dengan pesan; gunakan `--input` untuk menunjuk root yang
memiliki satu konfigurasi dataset. Belum ada jaminan struktur unduhan terbaru identik.
Gambar negatif tanpa objek harus memiliki file label kosong yang telah diverifikasi.
Periksa contoh label, duplikasi antarsplit dan izin sumber; tidak ada audit dataset otomatis.

## 3. Latih detektor HP

```powershell
# GPU NVIDIA yang sudah memiliki PyTorch CUDA:
.\.venv\Scripts\python.exe scripts/train.py --device 0 --epochs 50 --batch 4
# Alternatif tanpa GPU (bisa sangat lambat):
.\.venv\Scripts\python.exe scripts/train.py --device cpu --epochs 10 --batch 2
```

Gunakan SALAH SATU perintah. Training membuat bobot di `runs/phone*/weights/best.pt`.
Path tepat dicetak saat selesai. Isi di `.env`, contoh:

```dotenv
PHONE_MODEL=runs/phone/weights/best.pt
```

Periksa `names` pada `data/phone-data.yaml`. Auto-deteksi kelas mencari nama yang
mengandung `phone` atau `mobile`. Jika nama tidak sesuai, atur `phone_class_ids` pada
`cameras.yaml` ke ID kelas HP yang benar; jangan menebak ID. Detektor orang tetap memakai
model COCO terpisah karena dataset HP mungkin tidak mengandung kelas orang.
`device: cpu` pada cameras.yaml bisa diubah menjadi `device: '0'` untuk GPU.

## 4. Input dan menjalankan dashboard

Letakkan video uji di `data/videos/demo.mp4` (buat foldernya), atau ubah `source`
di `cameras.yaml` ke path video lain. Angka `0` berarti webcam lokal, bukan string `'0'`.
Video lokal diproses sebagai analisis offline **secepat kemampuan mesin**, tidak selalu
real time; preview bisa cepat selesai. Kejadian tetap memakai detik media berdasarkan
FPS nominal video (video variable-frame-rate sebaiknya dikonversi ke constant-frame-rate).
Restart server untuk menganalisis ulang; pengulangan membuat kejadian sesi baru.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Buka http://127.0.0.1:8000 dan login dengan `.env`. Tanpa bobot hasil training,
kosongkan PHONE_MODEL untuk baseline COCO bawaan yang memiliki kelas `cell phone`.
Baseline ini **belum menggunakan hasil pelatihan dataset Kaggle**.
Gunakan satu process/worker, tanpa `--reload` untuk operasional (mencegah proses kamera
duplikat). SQLite dibuat di `data/events.sqlite3`. Hentikan dengan Ctrl+C.

## 5. EZVIZ RTSP

Model/firmware harus benar-benar mendukung stream lokal. Uji URL yang diberikan manual
perangkat di VLC terlebih dahulu. Tidak semua EZVIZ mendukung RTSP/ONVIF. Jangan menebak
atau membuka port kamera ke internet. Simpan URL beserta kredensial di `.env`:

```dotenv
OFFICE_RTSP=rtsp://USERNAME:PASSWORD@IP_KAMERA:554/PATH_SESUAI_MODEL
```

Lalu pada kamera yang relevan di `cameras.yaml`:

```yaml
source: env:OFFICE_RTSP
```

URL-encode karakter khusus pada user/password. Jangan mengirim `.env` atau label
verification code kepada orang lain. OpenCV/FFmpeg dapat menulis diagnostik sendiri
ke stderr; batasi akses log karena pustaka eksternal mungkin mencetak URL.
Kamera putus akan dicoba kembali. Kandidat temporal direset saat reconnect, status
kejadian aktif menjadi interrupted, dan preview lama tidak ditampilkan sebagai live.
Kamera error konfigurasi/model membutuhkan perbaikan lalu restart server.

## 6. Zona dan aturan

Titik polygon `points` memakai koordinat 0..1 relatif lebar/tinggi frame asli. Contoh
meja kiri: `[[0.05,0.2],[0.45,0.2],[0.45,0.95],[0.05,0.95]]`. Zona memakai **pusat
bounding box orang**, bukan titik kaki. Hindari zona tumpang tindih; yang pertama
dipakai jika pusat berada di beberapa zona. Tanpa zona berarti seluruh gambar.

`minimum_seconds: 10` = rentang kandidat minimal 10 detik sebelum dicatat.
`gap_seconds: 2` = toleransi hilangnya deteksi sementara. Pastikan interval sampling
lebih kecil daripada toleransi ini. Orang hadir tanpa HP tidak diberi label WORKING.
HP tidak diasosiasikan jika pusatnya di luar bounding box orang. Ini dapat melewatkan
HP yang dipegang jauh dari tubuh; sebaliknya HP di meja bisa salah diasosiasikan.
Perbaiki sudut kamera, latih dengan data kantor berizin, dan ukur precision/recall
kejadian, alarm salah per hari serta kesalahan asosiasi sebelum penggunaan nyata.

## 7. Privasi, keamanan, dan penyimpanan

- Default bind localhost. HTTP Basic tidak mengenkripsi password: untuk akses LAN,
  gunakan reverse proxy HTTPS dan firewall/VPN. Jangan expose langsung ke internet.
- Semua endpoint termasuk gambar dan ekspor membutuhkan login; satu akun admin,
  belum memiliki multiuser/RBAC, rate limiting, atau audit log review lengkap.
- Snapshot mati secara default. `store_snapshots: true` menyimpan satu frame anotasi
  saat kejadian terkonfirmasi; frame dapat memuat orang lain. Tidak ada perekaman klip/audio.
- `retention_days: 7` menghapus metadata/gambar lama saat startup dan setiap jam.
  Ini penghapusan logis, bukan secure erase. Terapkan enkripsi disk, backup dan retensi
  backup terpisah. Preview browser tidak disimpan aplikasi.
- Rekaman harus sesuai kebijakan kantor, dasar pemrosesan yang sah dan pemberitahuan
  kepada karyawan. Siapkan review HR/legal dan penilaian dampak bila diperlukan.
- Lisensi kode/bobot Ultralytics terpisah dari lisensi dataset; periksa AGPL/Enterprise
  sebelum distribusi/deployment. Proyek ini tidak memberikan lisensi ulang data/bobot.

## 8. Pengujian

Tes logika murni (tanpa download dataset, GPU, kamera atau kredensial):

```powershell
python -m unittest discover -s tests -v
python -m compileall app scripts tests
```

Tes HTTP tambahan memerlukan `httpx` (`pip install -r requirements-dev.txt`). Tanpa
httpx tes API dilewati. Tes API menggunakan worker palsu, bukan koneksi kamera nyata.

Uji lapangan terpisah: video tanpa HP, HP di meja, memegang HP, beberapa orang
berdekatan, orang terhalang, disconnect/reconnect, jam istirahat dan video sulit.
Keberhasilan tes unit tidak membuktikan akurasi detektor. Source ini tidak menyertakan
bobot hasil latih, dataset, atau klaim akurasi di CCTV kantor.
