# Analisis kesiapan production

Ditulis 2026-09-07. Dasar: pembacaan seluruh kode (5 modul Python ~1.960 baris +
`static/index.html` 1.647 baris), reproduksi bug di Chrome, silang-periksa dengan
knowledge graph Graphify, dan pengukuran langsung terhadap server yang berjalan.

Diperbarui setelah sesi perbaikan: Bagian 1-6 menandai mana yang SELESAI dan mana
yang belum, Bagian 7 memuat tabel statusnya. Setiap temuan menyertakan bukti
`path:baris` supaya tidak perlu ditelusuri ulang dari nol.

---

## Bagian 1 — Sudah diperbaiki hari ini

### 1.1 Gulir hantu ~1.258 px di dashboard desktop — SELESAI

**Gejala.** Di layout desktop (>=900px) halaman bisa digulir jauh ke bawah, dan di
bawahnya tidak ada apa-apa selain ruang kosong.

**Pengukuran sebelum perbaikan** (jendela 2086x956):

| | nilai |
|---|---|
| `documentElement.clientHeight` | 956 px |
| `documentElement.scrollHeight` | **2214 px** |
| gulir kosong | **1258 px** |
| elemen terbawah yang terlihat berakhir di | 956,8 px |

**Sebab.** Dua `<caption class="tersembunyi">` (dibuat di `static/index.html:1266`
dan `:1297` untuk tabel wilayah dan bandara) memakai aturan pembaca layar:

```css
.tersembunyi{position:absolute!important;width:1px;height:1px;overflow:hidden;
  clip:rect(0 0 0 0);white-space:nowrap}
```

`position:absolute` mencari *containing block* ke atas sampai menemukan leluhur
yang **berposisi**. Dulu `aside` hanya punya `overflow-y:auto`. Itu menjadikannya
wadah gulir, **tapi tidak menjadikannya containing block**. Jadi pencarian melewati
`aside`, melewati `.kerangka`, dan berhenti di *initial containing block* (`<html>`).

Akibatnya `overflow-y:auto` pada `aside` **tidak memotong** caption itu — elemen
absolut hanya dipotong oleh leluhur yang menjadi containing block-nya. Caption tabel
bandara duduk di posisi statisnya, y ~ 2214 dokumen, dan menyeret area gulir `<html>`
ikut melar sepanjang itu.

Ini menjelaskan kenapa gejalanya membingungkan saat ditelusuri:

- `aside{overflow:hidden}` **tidak** menyembuhkan (diuji: tetap 2214) — masalahnya
  bukan pemotongan, melainkan containing block.
- `aside{contain:strict}` dan `aside{position:absolute}` menyembuhkan, karena
  keduanya membuat `aside` jadi containing block.
- Layout ponsel (<900px) tidak terkena, karena di sana `aside` bukan wadah gulir
  dan caption mengalir wajar di dalam halaman.

**Perbaikan** — `static/index.html:75`, satu properti:

```css
aside{position:relative;
      padding:0 calc(12px + env(safe-area-inset-right)) 4px
               calc(12px + env(safe-area-inset-left))}
```

Sengaja ditaruh di aturan dasar `aside`, bukan di dalam `@media (min-width:900px)`,
supaya tetap benar kalau breakpoint-nya diubah suatu saat.

**Aturan umum yang layak diingat:** setiap wadah gulir harus `position:relative`,
kalau tidak isi absolutnya bocor keluar dan melebarkan gulir halaman.

**Verifikasi sesudah perbaikan.** Semua skenario: `scrollHeight == clientHeight`,
gulir kosong **0**, dan `aside` tetap menggulir sendiri (2354 vs 623) seperti yang
dirancang:

| Skenario | scrollH | clientH | gulir kosong |
|---|---|---|---|
| 1600x1000, muat awal | 823 | 823 | 0 |
| 3x next halaman wilayah + bandara | 823 | 823 | 0 |
| setelah pilih lokasi (Sleman) | 823 | 823 | 0 |
| setelah klik kartu gunung | 823 | 823 | 0 |
| setelah buka + tutup dialog Tentang | 823 | 823 | 0 |
| 1440x723 | 723 | 723 | 0 |
| 400x860 (ponsel) | 2932 | 683 | gulir wajar, ruang kosong di bawah 0 |
| 1000x384 (jendela pendek) | 612 | 384 | gulir wajar dari `min-height:520px`, ruang kosong di bawah 0 |

Dua baris terakhir memang menggulir, tapi itu **sah**: yang tergulir adalah konten
asli, dan di posisi gulir maksimum sisa ruang kosong di bawah = 0 px.

### 1.2 Gulir sub-piksel dari pembulatan tinggi header — SELESAI

`ukurHeader()` memakai `offsetHeight` yang membulatkan ke bilangan bulat. Header
sebenarnya setinggi 64,103 px tercatat sebagai 64 px, sehingga
`height:calc(100dvh - var(--tinggi-header))` membuat `.kerangka` 0,1 px terlalu
tinggi — cukup untuk memunculkan bilah gulir yang tidak menggulir apa pun.

Diperbaiki di `static/index.html:1590` dengan `getBoundingClientRect().height`,
yang tidak membulatkan.

### 1.3 Legenda peta bertumpuk dengan kontrol linimasa — SELESAI

**Gejala.** Kotak legenda menimpa tombol "Sekarang / +6 jam / +12 jam / +18 jam".

**Dua cacat berbeda, terukur:**

| Kasus | Tumpang tindih |
|---|---|
| Muat di 1400px lalu jendela dikecilkan | **182 px** |
| Muat segar di 902px (tepat di atas breakpoint) | **28 px** |

**Sebab 1 — posisi legenda dibekukan saat peta dibuat.** Kode lama menghitung
`window.matchMedia("(min-width:900px)").matches` **satu kali** lalu tidak pernah
mengevaluasinya lagi. Halaman yang dimuat lebar lalu dikecilkan meninggalkan legenda
di `bottomright` dalam keadaan terbuka, sementara CSS memindahkan linimasa jadi
membentang selebar peta - keduanya lalu berebut pojok yang sama.

**Sebab 2 — ambang breakpoint tidak sama dengan ambang "muat".** Pada 902px layout
desktop sudah aktif, tapi kolom peta hanya 902 - 390 = 512px, sedangkan linimasa
(~340px) + legenda (~182px) butuh ~520px. Jadi bahkan muat segar pun bertumpuk.

**Perbaikan** (`static/index.html`): posisi legenda kini diputuskan oleh dua syarat
sekaligus, dan dievaluasi ulang setiap ukuran berubah.

```js
const diBawah = window.matchMedia("(min-width:900px)").matches &&
                peta.getContainer().clientWidth >= AMBANG_LEGENDA;   // 560
```

Syarat pertama perlu karena di bawah 900px linimasa selalu membentang penuh, berapa
pun lebar petanya. Syarat kedua perlu karena layout desktop yang sempit tetap tidak
menyisakan ruang. Kalau salah satu gagal, legenda pindah ke kanan ATAS dan ditutup.

Pemicunya tiga, sengaja tumpang tindih supaya tidak ada celah: `resize` jendela,
event `resize` milik Leaflet, dan `ResizeObserver` pada wadah peta. Pemanggilan
berulang gratis karena `tempatkanLegenda()` langsung keluar kalau posisinya tidak
berubah - penjagaan ini juga yang mencegah ResizeObserver memasang ulang tiap frame.

**Verifikasi 1 - muat segar.** Di 1398 / 1097 / 947 / 899 / 897 / 797 / 497 / 411 /
357 px: `BERTUMPUK: false` di semuanya. Peralihan 947px (peta 558px, di bawah ambang)
benar pindah ke kanan atas - kasus 28px yang dulu bocor.

**Verifikasi 2 - resize jendela sungguhan.** Ini yang paling meyakinkan, dan sempat
gagal dilakukan sampai ketahuan sebabnya (lihat catatan di bawah). Satu jendela,
diubah ukurannya berturut-turut, tanpa muat ulang:

| Lebar jendela | Lebar peta | Layout | Legenda | Tumpang tindih |
|---|---|---|---|---|
| 1033 px | 644 px | desktop | `bottom right`, terbuka | tidak |
| 760 px | 745 px | ponsel | `top right`, tertutup | tidak |
| 930 px | 540 px | desktop sempit | `top right`, tertutup | tidak |
| 1500 px | 1111 px | desktop | `bottom right`, terbuka | tidak |

Baris 930px adalah kasus yang dulu bertumpuk 28px, dan baris 760px kasus yang dulu
bertumpuk 182px. Keduanya bersih, dengan event `resize` asli (4x) dan callback
ResizeObserver asli (4x). Gulir kosong halaman tetap 0 sepanjang rangkaian.

**Catatan alat uji - kenapa pengujian resize sempat mustahil.** Percobaan awal
menyimpulkan window manager (Hyprland) menolak resize. Itu hanya sebagian benar:
sebab utamanya Chrome **men-throttle rendering** saat jendelanya tidak fokus,
sehingga event `resize` DAN callback ResizeObserver tidak pernah dikirim sama sekali -
callback pertama ResizeObserver yang seharusnya menyala begitu `observe()` dipanggil
pun tidak muncul (`ro: 0`). Ini juga yang membuat rig iframe tampak "tidak mengirim
event resize".

Menekan **F12** membuka DevTools, yang membangunkan rendering: seketika `rs: 1` dan
`ro: 1`, dan sesudah itu `resize_window` bekerja normal. Jadi kalau suatu saat
pengujian resize otomatis tampak mati lagi, buka DevTools dulu - bukan menyimpulkan
kodenya yang salah.

---

## Bagian 2 — Blocker

### 2.1 Aplikasi mati kalau CWD bukan root repo — SELESAI

`app.py:218` dan `app.py:223` memakai jalur relatif `"static"`. Diuji dari `/tmp`:

```
GAGAL saat impor: RuntimeError Directory 'static' does not exist
```

Gagalnya saat **impor**, bukan saat request — jadi systemd tanpa `WorkingDirectory=`,
Docker dengan `WORKDIR` berbeda, atau gunicorn yang dijalankan dari direktori lain
akan langsung mati sebelum melayani apa pun.

```python
from pathlib import Path
DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=DIR_STATIC), name="static")
# dan: FileResponse(DIR_STATIC / "index.html")
```

Diterapkan di `app.py`. Diverifikasi: `import app` dari `/tmp` berhasil, seluruh
delapan rute terdaftar.

### 2.2 VAAC gagal = seluruh halaman mati — SELESAI

`app.py:46-52` mengubah kegagalan upstream jadi HTTP 502, dan `sumber._Cache`
(`sumber.py:57-66`) tidak pernah menyimpan hasil lama ketika producer melempar
exception — entri hanya ditulis kalau fetch sukses.

Artinya: BOM tidak bisa dihubungi satu menit setelah TTL 300 detik habis -> halaman
kosong, padahal data 5 menit lalu masih sangat berguna. Advisory VAAC hanya terbit
tiap ~6 jam, jadi data "basi 20 menit" praktis sama validnya dengan data segar.

Untuk aplikasi kebencanaan ini temuan paling serius di berkas ini.

**Perbaikan.** `_Cache` tidak lagi membuang entri kedaluwarsa (`basi()`), dan
`ambil_vaac()` menyajikannya kalau BOM gagal, bukan melempar. `/api/nasional` kini
membawa `pembaruan.vaac_basi` + `vaac_basi_alasan` supaya UI bisa berterus terang.
Exception hanya tersisa untuk kasus yang memang tidak tertolong: proses baru hidup
dan belum pernah sekali pun berhasil menarik data.

Diverifikasi dengan mensimulasikan BOM mati:

```
1. cache terisi: 5 advisory, basi=False
2. BOM mati, TTL habis -> 5 advisory tetap kembali (tidak exception)
   vaac_basi(): basi=True alasan='Connection refused (simulasi BOM down)'
3. cache kosong + BOM mati -> tetap melempar (benar, tidak ada yang bisa disajikan)
4. BOM pulih -> basi=False (alasan dibersihkan)
```

### 2.3 Tile OpenStreetMap publik melanggar Tile Usage Policy

`static/index.html:710` memakai `{s}.tile.openstreetmap.org`. OSMF melarang pemakaian
tile publik untuk aplikasi yang disebar ke publik, dan memblokir per-Referer/UA tanpa
peringatan lebih dulu. Risikonya peta mendadak jadi kotak kosong di production.

Harus pindah ke penyedia berbayar (MapTiler, Stadia) atau self-host sebelum rilis.
Ini keputusan biaya/hosting, bukan keputusan teknis murni.

---

## Bagian 3 — Ketahanan dan performa

### 3.1 Tidak ada gzip sama sekali — SELESAI

Diukur langsung terhadap server yang berjalan:

| Endpoint | Ukuran | Frekuensi |
|---|---|---|
| `/api/wilayah` | **70.896 B** | tiap muat halaman |
| `/api/nasional` | 37.564 B | tiap 5 menit per klien |
| `/` (index.html) | 76.624 B | tiap muat halaman |

**Perbaikan.** `GZipMiddleware(minimum_size=1024)` dipasang, dan `/api/wilayah`
diberi `Cache-Control: public, max-age=86400` karena isinya beku selama proses hidup.
Hasil terukur sesudahnya:

| Endpoint | Sebelum | Sesudah | Rasio |
|---|---|---|---|
| `/api/wilayah` | 70.896 B | **14.495 B** | 4,9x |
| `/api/nasional` | 38.190 B | **4.978 B** | 7,7x |

### 3.2 Cache stampede — SELESAI

`sumber.py` dulu melepas gembok **sebelum** menjalankan `producer()`. Saat TTL habis,
semua permintaan yang datang bersamaan menembak BOM serentak, masing-masing dengan
timeout 30 detik.

**Perbaikan.** `_Cache` kini memegang satu gembok per kunci selama pengambilan, dengan
pemeriksaan ulang di dalam gembok. Diverifikasi: 20 permintaan bersamaan pada cache
kosong -> upstream dipanggil **1x** (sebelumnya 20x).

### 3.3 `fetch()` frontend tanpa timeout — SELESAI

`ambil()` dulu tidak memakai `AbortController`. Koneksi yang menggantung meninggalkan
tulisan "Memuat..." selamanya tanpa jalan keluar bagi pengguna.

**Perbaikan.** `ambil()` kini memasang `AbortController` dengan batas 15 detik dan
menerjemahkan kegagalan jaringan jadi pesan berbahasa Indonesia.

### 3.4 Leaflet dari unpkg tanpa SRI

`static/index.html:8` dan `:505` menarik CSS dan JS Leaflet dari unpkg tanpa
`integrity` dan tanpa fallback. CDN pihak ketiga jadi titik gagal tunggal sekaligus
permukaan serangan supply chain. Untuk aplikasi kebencanaan, host sendiri.

---

## Bagian 4 — Privasi

### 4.1 Koordinat GPS masuk query string — SELESAI

`static/index.html:1479` mengirim `lat.toFixed(5)` dan `lon.toFixed(5)` — presisi
sekitar 1 meter — sebagai parameter URL ke `/api/lokasi`. Query string tercatat
permanen di access log uvicorn dan di setiap reverse proxy di depannya.

**Perbaikan.** Ditambahkan `POST /api/lokasi` yang menerima `{lat, lon, nama}` di
badan permintaan, dan tombol GPS di frontend memakainya. Badan POST tidak masuk
access log. Bentuk `GET` dipertahankan untuk pencarian kabupaten/kota dan pemanggilan
manual (curl, skrip verifikasi) - keduanya bukan data pribadi.

Penyegaran berkala ikut menyimpan badan permintaan (`permintaanLokasiTerakhir`),
supaya lokasi GPS tetap ikut disegarkan tanpa kembali ke query string.

---

## Bagian 5 — Operasional

### 5.1 Nol berkas uji di repo

Tidak ada `test*.py` maupun direktori `tests/`. Padahal `CATATAN-SESI.md` sudah memuat
skrip silang-periksa yang bagus (menghitung dampak nasional tanpa lewat `dampak.py`
lalu membandingkannya dengan `/api/nasional`).

Angkat skrip itu jadi `test_dampak.py` dengan advisory yang dibekukan sebagai fixture,
supaya ujinya tidak bergantung pada jaringan dan tidak berubah hasil tiap advisory baru.

### 5.2 Tidak ada berkas deploy

Tidak ada `Dockerfile`, unit systemd, maupun `pyproject.toml`. `requirements.txt`
memakai `>=` tanpa pin:

```
fastapi>=0.115
uvicorn[standard]>=0.30
httpx>=0.27
```

Build hari ini dan build bulan depan bisa menghasilkan lingkungan yang berbeda.

### 5.3 Lain-lain — SEBAGIAN SELESAI

- ~~`/api/docs` terbuka untuk publik~~ — **SELESAI.** Kini mati secara bawaan;
  nyalakan dengan `ABU_DOCS=1`. Diverifikasi: `GET /api/docs` -> HTTP 404.
- ~~Tidak ada endpoint health~~ — **SELESAI.** `GET /api/sehat` menjawab status
  proses + umur data VAAC. Sengaja TIDAK menghubungi BOM: kesehatan proses tidak
  boleh ditentukan pihak ketiga, kalau tidak load balancer akan menurunkan instans
  sehat yang sebenarnya masih sanggup menyajikan data dari cache.
- Tidak ada logging terstruktur sama sekali — **belum**.

---

## Bagian 6 — Kebersihan kode

### 6.1 Seluruh cabang MAGMA/PVMBG adalah kode mati (~60 baris) — SELESAI

Diverifikasi dua arah — lewat grep dan lewat graph:

```
graphify explain "status_pvmbg"  ->  Degree: 4
  <-- sumber.py [contains]        (bukan pemanggil)
  --> _kunci() [calls]            (keluar)
  --> _baris_pvmbg() [calls]      (keluar)
  <-- docstring [rationale_for]   (bukan pemanggil)
```

Nol edge masuk. Yang tidak terjangkau dari endpoint mana pun:

| Fungsi | Lokasi |
|---|---|
| `status_pvmbg` | `sumber.py:412` |
| `pvmbg_ditarik_pada` | `sumber.py:317` |
| `ambil_pvmbg` | `sumber.py:290` (hanya dipakai `_baris_pvmbg`) |
| `_baris_pvmbg` | `sumber.py:401` (hanya dipakai `status_pvmbg`) |
| `geometri.evaluasi_lapisan` | `geometri.py:66` |
| `dampak.bersihkan_cache` | `dampak.py:213` |

Yang lebih mengganggu daripada baris matinya sendiri: docstring `app.py:8` dan
`sumber.py:6-7` masih mengiklankan MAGMA/PVMBG sebagai sumber data aktif. Itu
menyesatkan pembaca berikutnya. Kalau MAGMA memang ditinggalkan karena 403 tingkat IP
(sebagaimana dicatat di `CATATAN-SESI.md`), buang kodenya dan betulkan docstring-nya.

**Perbaikan.** `status_pvmbg`, `pvmbg_ditarik_pada`, `ambil_pvmbg`, `_baris_pvmbg`
dan konstanta `MAGMA_URL` dibuang dari `sumber.py`; `geometri.evaluasi_lapisan`
dibuang dari `geometri.py`. Docstring modul `sumber.py` dan `app.py` dibetulkan
sehingga tidak lagi mengiklankan MAGMA sebagai sumber aktif.

`dampak.bersihkan_cache` sengaja DIPERTAHANKAN: docstring-nya menyatakan itu untuk
keperluan uji, dan berkas uji memang akan ditulis (lihat 5.1).

### 6.2 Docstring `dampak.py` menjanjikan hal yang tidak terjadi — SELESAI

Ia menulis *"Cache dipegang satu gembok: dua permintaan bersamaan pada advisory baru
akan menghitung berurutan, bukan mengembalikan hasil setengah jadi"*. Padahal
`_hitung_nasional()` dipanggil di **luar** blok `with _gembok` (`dampak.py:206`),
jadi dua permintaan bersamaan menghitung paralel.

Dampak praktisnya nihil: sapuan diukur hanya **6 ms** untuk 15.040 uji titik
(508 kab/kota + 244 bandara, 5 advisory, 4 langkah waktu). Justru itu temuannya —
seluruh mesin cache (gembok + sidik jari) menjaga komputasi 6 ms.

**Perbaikan.** Docstring dibetulkan supaya menyatakan apa yang benar-benar terjadi:
gembok hanya melindungi baca/tulis variabel cache, dan perhitungan paralel memang
disengaja karena menahan permintaan lain di belakang gembok lebih mahal daripada
menghitung ulang 6 ms. Mesin cache-nya sendiri tidak dibongkar.

### 6.3 `var(--teks1)` tidak pernah didefinisikan — SELESAI

`static/index.html:166` memakai `color:var(--teks1)` untuk `tbody th`, padahal `:root`
hanya mendefinisikan `--teks`, `--teks2`, dan `--teks3`. Warnanya diam-diam jatuh ke
inherit. **Perbaikan.** Diganti jadi `var(--teks)`.

---

## Bagian 7 — Status

| # | Perbaikan | Status |
|---|---|---|
| 1 | `aside{position:relative}` — gulir hantu 1.258 px (1.1) | **selesai** |
| 2 | `getBoundingClientRect` untuk tinggi header (1.2) | **selesai** |
| 3 | Legenda peta bertumpuk dengan linimasa (1.3) | **selesai** |
| 4 | Jalur absolut untuk `static/` (2.1) | **selesai** |
| 5 | Stale fallback saat VAAC gagal (2.2) | **selesai** |
| 6 | Gzip + `Cache-Control` (3.1) | **selesai** |
| 7 | Cache stampede: satu gembok per kunci (3.2) | **selesai** |
| 8 | Timeout `fetch()` frontend (3.3) | **selesai** |
| 9 | GPS keluar dari query string, lewat POST (4.1) | **selesai** |
| 10 | `/api/docs` ditutup + endpoint `/api/sehat` (5.3) | **selesai** |
| 11 | Buang kode mati MAGMA + betulkan docstring (6.1, 6.2) | **selesai** |
| 12 | `var(--teks1)` -> `var(--teks)` (6.3) | **selesai** |
| 13 | Berkas uji (5.1) | belum |
| 14 | Pin dependensi + Dockerfile/systemd (5.2) | belum |
| 15 | Logging terstruktur (5.3) | belum |
| 16 | Host Leaflet sendiri, tanpa unpkg (3.4) | belum |
| 17 | Pindah penyedia tile peta (2.3) | belum, perlu keputusan |

### Yang tersisa, dan kenapa

**Nomor 13-15** murni pekerjaan operasional: tulis `test_dampak.py` dari skrip
silang-periksa di `CATATAN-SESI.md`, pin `requirements.txt`, tambahkan unit systemd
atau Dockerfile, pasang logging. Tidak ada keputusan yang perlu diambil, hanya waktu.

**Nomor 16-17** menyangkut pihak ketiga dan biaya:

- Leaflet dari unpkg bisa langsung di-host sendiri (salin dua berkas ke `static/`),
  hanya perlu kesepakatan bahwa repo ikut menyimpan berkas vendor.
- Penyedia tile peta perlu keputusan Anda: MapTiler/Stadia (berbayar, cepat dipasang)
  atau self-host raster (butuh penyimpanan besar). Sampai itu diputuskan, peta masih
  memakai tile OSM publik yang bisa diblokir sewaktu-waktu.

---

## Bagian 8 — Pertanyaan terbuka

- **Penyedia tile peta.** Keputusan biaya dan hosting, bukan keputusan teknis. Kalau
  ada anggaran, MapTiler atau Stadia paling cepat dipasang; kalau tidak, self-host
  raster tile butuh penyimpanan yang tidak sedikit.
- **Feed SIGMET di `inasiam.rack.my.id`.** Risikonya sudah didokumentasikan dengan
  jujur di `sumber.py:36-43` dan pemakaiannya sudah dibatasi jadi konfirmasi sekunder.
  Untuk production perlu keputusan sadar apakah domain pihak ketiga itu tetap dipakai.
- **Batas cakupan graph.** Graphify di repo ini ikut mem-parse blok `<script>` inline
  (`gambarPeta()` dan kawan-kawan muncul sebagai god node), jadi cakupannya lebih baik
  dari biasanya. Tapi banyak edge antar-modul Python berlabel `INFERRED`, dan
  `graphify affected "ambil_vaac"` mengembalikan kosong — arah edge terbaliknya tidak
  lengkap. Semua klaim kode mati di Bagian 6 dikonfirmasi ulang lewat grep, bukan hanya
  lewat graph.

---

## Lampiran — cara memverifikasi ulang gulir hantu

Kalau gejalanya muncul lagi, jalankan ini di konsol peramban pada lebar >=900px:

```js
const de = document.documentElement;
console.log({
  clientH: de.clientHeight,
  scrollH: de.scrollHeight,
  gulirKosong: de.scrollHeight - de.clientHeight
});

// kalau gulirKosong > 0, cari elemen absolut yang lolos dari wadah gulir:
[...document.querySelectorAll('aside *')]
  .filter(e => getComputedStyle(e).position === 'absolute')
  .map(e => ({ el: e, bottom: Math.round(e.getBoundingClientRect().bottom) }));
```

Kalau ada elemen yang `bottom`-nya sama dengan `scrollH`, itu pelakunya, dan wadah
gulir terdekatnya kekurangan `position:relative`.
