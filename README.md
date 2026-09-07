# Pantau Abu Vulkanik Indonesia

Memantau sebaran abu vulkanik dari **VAAC Darwin** terhadap **seluruh Indonesia**:
38 provinsi, 508 kabupaten/kota, dan 244 bandara ber-kode IATA. Untuk setiap gunung
yang sedang punya advisory abu aktif, aplikasi menghitung wilayah mana saja yang
ternaungi poligon abu — sekarang, dan pada prakiraan +6, +12, dan +18 jam.

Versi ini adalah pengembangan nasional dari versi sebelumnya yang hanya melingkupi
Kabupaten Bogor. Yang berubah: cakupan wilayah dan kontrak API. Yang tetap: sumber
data, parser VA ADVISORY, dan sikap terhadap data yang tidak bisa diverifikasi.

## Jalankan

```bash
cd ~/Projects/abu-indonesia
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn app:app --reload --port 8931
# buka http://127.0.0.1:8931
```

Dokumentasi API otomatis: `http://127.0.0.1:8931/api/docs`

Tidak ada API key, tidak ada database, tidak ada build step di frontend. Dependensi
hanya `fastapi`, `uvicorn[standard]`, dan `httpx`.

## Sumber data

Semua upstream ditarik **di sisi server** (`sumber.py`), hasilnya di-cache dengan TTL,
dan waktu penarikannya dicatat supaya UI bisa menampilkan umur data.

| Data | Sumber | Endpoint | TTL |
|---|---|---|---|
| Poligon abu, flight level, prakiraan +6/+12/+18 jam, jam terbit & jam berlaku | **VAAC Darwin — Bureau of Meteorology, Australia** | `POST www.bom.gov.au/aviation/php/process.php` dengan body `page=volcanic-ash-darwin` | 5 menit |
| Konfirmasi SIGMET abu vulkanik FIR Indonesia | **BMKG / Ina-SIAM** | `inasiam.rack.my.id/api/v1/opmet/sigmet/geojson` | 10 menit |
| Status resmi gunung api (Normal…Awas) | **MAGMA Indonesia / PVMBG — ESDM** | `GET magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas` | 15 menit |
| 38 provinsi, 508 kabupaten/kota, 244 bandara IATA | **OpenStreetMap** (ODbL) | Overpass API + Nominatim, sudah dibekukan ke `wilayah.py` | statis |
| Peta dasar | OpenStreetMap tiles | digelapkan lewat CSS filter agar senada dengan tema | — |

Permintaan ke BOM dikirim dengan `Referer` halaman advisory Darwin dan header
`X-Requested-With`, karena endpoint itu memang dipakai oleh halaman web BOM sendiri.
Balasannya JSON berisi potongan HTML; teks advisory dibersihkan dari tag sebelum
diparse.

Data wilayah sengaja dibekukan menjadi kode Python, bukan ditarik saat runtime.
Batas administrasi tidak berubah tiap jam, dan Overpass tidak layak dijadikan
dependensi permintaan-per-permintaan. Koordinat kabupaten/kota adalah centroid batas
wilayah, dan relasi Malaysia, Timor-Leste, serta PNG yang ikut terjaring bbox sudah
disaring dengan point-in-polygon terhadap poligon provinsi.

### Catatan jujur soal MAGMA/PVMBG

WAF milik ESDM menolak sebagian IP — termasuk banyak IP datacenter — dengan
**HTTP 403 "Request Rejected"**, dan penolakan itu berlaku di **seluruh domain**:
`magma.esdm.go.id`, `vsi.esdm.go.id`, maupun `geologi.esdm.go.id`. Akibatnya:

- **Bentuk field respons MAGMA belum bisa diverifikasi** dari mesin pengembangan.
  Tidak ada satu pun respons 200 yang bisa dijadikan acuan skema.
- Karena itu `sumber.status_pvmbg()` mencocokkan secara **longgar**: nama gunung
  dinormalisasi (huruf kecil, non-alfabet dibuang) dan dicocokkan sebagai substring;
  level dibaca dari `status` / `level` / `tingkat_aktivitas`, mana pun yang ada.
  Kalau tidak ketemu, fungsinya mengembalikan `None` — **tidak menebak**.
- Kegagalan ditangani **sebagai data, bukan exception**: `ambil_pvmbg()` selalu
  mengembalikan `{"tersedia": False, "alasan": "...", "data": []}` sehingga seluruh
  panel abu tetap berjalan normal tanpa panel status gunung.

Kalau suatu hari MAGMA bisa diakses dari mesin penyaji, verifikasi skemanya dulu
sebelum memperketat pencocokan.

## Yang sengaja tidak dipakai

| Data | Alasan |
|---|---|
| **Angin di kawah** (Open-Meteo) | Angin permukaan di puncak gunung yang jaraknya ratusan sampai ribuan kilometer tidak bisa dipakai publik untuk apa pun. Abu berada di ribuan meter dan disetir angin atas, bukan angin permukaan di kawah. Lagipula arah sebarannya **sudah terkandung di poligon prakiraan VAAC**, yang justru dihitung dari model angin lengkap semua ketinggian. Panel ini terlihat teknis tapi menyesatkan. |
| **GDACS** | Dulu ditarik setiap request tapi **tidak pernah ditampilkan** sama sekali. Level Orange/Red-nya berskala global dan tidak mengubah keputusan apa pun di tingkat kabupaten/kota. |
| **Panel SO₂** | Isinya artikel edukasi umum + iframe pihak ketiga. Tidak menghasilkan satu angka pun yang berlaku untuk lokasi tertentu. |

## Keputusan desain visual

Tema gelap. Permukaan `#1a1a19`, panel sedikit lebih terang, teks utama `#ffffff`,
teks sekunder `#c3c2b7`, teks redup sekitar `#8a8a80`.

### Warna abu: satu warna untuk semua gunung

Semua poligon abu memakai **satu** warna, yaitu `#d03b3b`. Ini bukan kemalasan
melainkan konsekuensi bentuk datanya.

Peta ini adalah kasus **all-pairs**: poligon gunung mana pun bisa bersebelahan atau
tumpang tindih dengan poligon gunung mana pun yang lain, jadi setiap pasang warna
harus tetap bisa dibedakan. Palet kategorikal yang aman untuk syarat all-pairs
(termasuk untuk buta warna) hanya sanggup sampai **3 slot**, sedangkan gunung aktif
di wilayah VAAC Darwin bisa 5 atau lebih sekaligus. Memaksakan satu warna per gunung
berarti menyajikan pembeda yang tidak benar-benar bisa dibedakan.

Identitas gunung karena itu dibawa oleh **label dan marker**, bukan warna.

### Status: tiga keadaan, selalu ikon + teks

| Status | Warna | Arti |
|---|---|---|
| Aman | `#0ca30c` | tidak ada lapisan yang menaungi di langkah waktu mana pun |
| Akan terdampak | `#fab219` | tidak kena sekarang, tapi kena di +6/+12/+18 jam |
| Ada abu | `#d03b3b` | ada lapisan yang menaungi pada langkah `obs` |

**Syarat keras:** setiap status wajib tampil sebagai **ikon (SVG inline) + teks
label**, tidak pernah warna saja. Validator kontras membuktikan `#0ca30c` dan
`#d03b3b` hanya berjarak **deutan Delta-E 4.1** — mata dengan buta warna merah-hijau
tidak bisa membedakan keduanya. Jadi kata "Aman" / "Akan terdampak" / "Ada abu" dan
ikonnya selalu ada di samping setiap indikator berwarna. Angka dan label memakai token
teks, bukan warna status.

Tiga warna itu dipakai untuk **keadaan**, bukan untuk seri data.

### Linimasa adalah filter, bukan warna

Langkah waktu (`Sekarang` / `+6` / `+12` / `+18`) disajikan sebagai *segmented
control* empat langkah plus tombol play yang menyiklus otomatis. **Hanya satu langkah
tergambar di peta pada satu waktu, untuk semua gunung sekaligus.** Ini menggantikan
pendekatan lama yang mewarnai poligon per langkah waktu — pendekatan itu memakai
warna untuk dua hal berbeda sekaligus (identitas dan waktu) dan langsung ambruk begitu
gunungnya lebih dari satu.

Wajib ada juga: **legenda** (area abu / gunung / lokasi Anda), **tooltip hover** pada
poligon dan marker, serta **tampilan tabel** daftar wilayah dan bandara terdampak
sebagai jalur non-visual.

## Endpoint

| Endpoint | Isi |
|---|---|
| `GET /api/wilayah` | `{provinsi, kabkota, bandara}` — isi persis dari `wilayah.py` |
| `GET /api/nasional` | payload utama: seluruh gunung aktif, linimasa 4 langkah, ringkasan dampak, dan daftar kabupaten/kota, bandara, serta provinsi terdampak |
| `GET /api/lokasi?kabkota=<nama>[&provinsi=<nama>]` | status satu kabupaten/kota; `provinsi` opsional, hanya sebagai pembeda kalau namanya dipakai dua daerah (Banjar di Jawa Barat dan di Kalimantan Selatan) |
| `GET /api/lokasi?lat=<f>&lon=<f>[&nama=<teks>]` | status satu koordinat bebas + kabupaten/kota terdekat |
| `GET /api/gunung/{kode}` | advisory lengkap satu gunung, termasuk `teks_mentah` |
| `GET /` | `static/index.html`; `/static` dimount sebagai StaticFiles |

Kode gunung adalah nomor Smithsonian, mis. `262000` (Krakatau), `263300` (Semeru).

**Kode galat:** nama kabupaten/kota tidak dikenal → **404**. Koordinat di luar
`-90..90` / `-180..180` → **422**. Kode gunung tidak dikenal → **404**.

### `/api/nasional`

```json
{
  "pembaruan": {"sekarang": "...", "vaac_ditarik": "...",
                "terbit_terbaru": "...", "berikutnya_terdekat": "..."},
  "ringkasan": {"gunung_aktif": 3, "kabkota_terdampak": 41, "provinsi_terdampak": 6,
                "bandara_terdampak": 9, "ada_lapisan_permukaan": true},
  "gunung": [{
    "kode": "262000", "nama": "Krakatau",
    "lat": -6.102, "lon": 105.423, "elevasi": "155M AMSL",
    "advisory_nr": "2026/193", "terbit": "...", "berikutnya": "...",
    "obs_teramati": true,
    "detail_erupsi": "...", "catatan": "...", "info_source": "...", "grafik_url": "...",
    "linimasa": [{"kunci": "obs", "label": "Sekarang", "berlaku": "...", "lapisan": [ ... ]}],
    "dampak": {"kabkota": 12, "bandara": 3, "provinsi": ["Banten", "Lampung"]}
  }],
  "terdampak": {
    "kabkota": [{"nama": "...", "provinsi": "...", "iso": "...", "lat": 0, "lon": 0,
                 "gunung": "Krakatau", "kunci_pertama": "obs", "label_pertama": "Sekarang",
                 "berlaku_pertama": "...", "ketinggian_ringkas": "permukaan – 4.600 m",
                 "sampai_permukaan": true}],
    "bandara": [{"iata": "CGK", "nama": "...", "provinsi": "...", "lat": 0, "lon": 0,
                 "gunung": "Krakatau", "kunci_pertama": "f6", "label_pertama": "+6 jam",
                 "berlaku_pertama": "...", "ketinggian_ringkas": "..."}],
    "provinsi": [{"nama": "Banten", "iso": "ID-BT", "jumlah_kabkota": 6}]
  }
}
```

`kunci_pertama` / `label_pertama` / `berlaku_pertama` adalah **langkah waktu pertama**
yang menaungi titik itu. `obs` berarti wilayahnya sudah kena sekarang. Daftar
kabupaten/kota diurutkan per provinsi lalu per nama; provinsi diurutkan per jumlah
kabupaten/kota terdampak menurun.

`linimasa` selalu berisi **4 entri berurutan** (`obs`, `f6`, `f12`, `f18`) meski ada
langkah yang lapisannya kosong, supaya frontend tidak perlu menangani panjang array
yang berubah-ubah.

### `/api/lokasi`

```json
{
  "lokasi": {"nama": "...", "provinsi": "...", "lat": 0, "lon": 0,
             "sumber": "kabkota"},
  "kabkota_terdekat": null,
  "status": "aman",
  "kena": [{"gunung": "Krakatau", "kode": "262000",
            "kunci_pertama": "f6", "label_pertama": "+6 jam", "berlaku_pertama": "...",
            "ketinggian": [{ ... }], "sampai_permukaan": false}],
  "terdekat": {"gunung": "Krakatau", "kode": "262000", "jarak_km": 143.2},
  "bandara_terdekat": {"iata": "CGK", "nama": "...", "jarak_km": 21.5, "terdampak": false},
  "pembaruan": { ... }
}
```

Aturan status:

- `terdampak` — ada lapisan yang menaungi pada langkah `obs`.
- `akan_terdampak` — tidak pada `obs`, tapi ada pada `f6`, `f12`, atau `f18`.
- `aman` — selain itu.

`kabkota_terdekat` hanya terisi kalau `lokasi.sumber == "koordinat"`.

`terdekat` hanya terisi kalau `status == "aman"`. Untuk titik yang kena abu —
sekarang maupun di prakiraan — jaraknya selalu 0 km karena titiknya memang ada di
dalam poligon, sehingga angka itu tidak menambah informasi apa pun dan justru
membingungkan kalau dibaca bersama status `akan_terdampak`. Kapan abu tiba sudah
dijawab oleh `kena[].label_pertama` dan `kena[].berlaku_pertama`.

Semua waktu dikirim server dalam **UTC**. Frontend yang mengubahnya ke waktu setempat,
menampilkan umur data ("25 menit lalu"), dan menyegarkan tampilan berkala. Data upstream
sendiri ditarik ulang paling cepat tiap 5 menit sesuai TTL cache.

## Cara kerjanya

### 1. Parser VA ADVISORY (`sumber.py`)

Teks advisory mentah dipecah jadi field bernama (`DTG:`, `VOLCANO:`, `OBS VA CLD:`,
`FCST VA CLD +6 HR:`, …), lalu:

- **Koordinat derajat-menit.** `S0806 E11255` → desimal `(-8.10, 112.92)`. Semua titik
  di seluruh proyek berformat `(lat, lon)`, bukan `(lon, lat)`.
- **Waktu DTG.** `20260907/0100Z` → datetime UTC.
- **Waktu DD/HHMMZ.** `07/0640Z` hanya membawa tanggal, jadi tahun dan bulannya diambil
  dari DTG advisory. **Pergantian bulan ditangani**: selisih lebih dari 15 hari ke arah
  mana pun dianggap lompatan bulan, dan tanggalnya digeser ke bulan sebelumnya atau
  berikutnya. Advisory yang terbit di awal bulan bisa memuat waktu observasi dari bulan
  lalu.
- **Label flight level ke meter.** `SFC/FL150` → permukaan sampai 4.600 m;
  `FL070/FL150` → 2.100–4.600 m. Ini angka yang paling menentukan: kalau dasar lapisan
  bukan `SFC`, abunya melintas di ketinggian dan tidak turun ke tanah. Flag
  `sampai_permukaan` inilah yang membedakan "ada abu di ruang udara" dari "mungkin hujan
  abu".
- **Beberapa lapisan dalam satu field.** Satu langkah waktu bisa memuat lebih dari satu
  lapisan ketinggian — contohnya Krakatau dengan `SFC/FL150` dan `SFC/FL500` sekaligus.
  Teks field karena itu dipotong di **setiap** label flight level, dan tiap potongan
  menghasilkan poligon, arah gerak (`MOV W`), dan kecepatan (`15KT`) sendiri.
- **OBS vs EST.** VAAC memakai `OBS VA CLD` kalau abu terlihat di satelit dan
  `EST VA CLD` kalau hanya diperkirakan. Keduanya dibaca ke kunci `obs`, tapi bedanya
  dibawa apa adanya lewat flag `obs_teramati` — jangan disamarkan di UI.

### 2. Geometri (`geometri.py`)

- **Ray casting** untuk menentukan apakah satu titik ada di dalam poligon.
- **Haversine ke ruas garis** untuk jarak kalau titik ada di luar: poligon diproyeksikan
  ke bidang lokal (cukup akurat untuk skala ratusan km di lintang rendah), titik
  diproyeksikan ke ruas terdekat, lalu jaraknya dihitung dengan haversine.
- Angkanya karena itu berarti **"abu terdekat sekian kilometer"**, bukan jarak ke puncak
  gunung dan bukan estimasi radius.
- `evaluasi_lapisan()` mengevaluasi satu titik terhadap **semua** sub-lapisan ketinggian
  di satu langkah waktu sekaligus, dan melaporkan yang terdekat.

### 3. Dampak nasional (`app.py`)

Menghitung 508 kabupaten/kota × 244 bandara × 4 langkah waktu × jumlah lapisan untuk
setiap advisory pada setiap request akan boros. Karena itu hasil perhitungan dampak
**di-cache dan diturunkan dari cache VAAC**: selama advisory yang mendasarinya belum
berganti, dampak nasional tidak dihitung ulang. Cache dampak batal begitu VAAC ditarik
ulang (TTL 5 menit) atau isi advisory-nya berubah.

Untuk setiap titik, aplikasi mencatat **langkah waktu pertama** yang menaunginya, bukan
sekadar "kena atau tidak". Itulah yang membedakan wilayah yang sudah tertutup abu
sekarang dari yang baru akan tertutup 18 jam lagi.

## Struktur file

```
app.py             endpoint FastAPI
dampak.py          sapuan dampak nasional (508 kab/kota + 244 bandara) + cache
sumber.py          klien upstream (BOM, MAGMA) + parser VA ADVISORY + cache TTL
geometri.py        ray casting, haversine, jarak titik ke poligon
wilayah.py         38 provinsi, 508 kabupaten/kota, 244 bandara (dibekukan dari OSM)
requirements.txt   fastapi, uvicorn[standard], httpx
static/index.html  frontend satu file, Leaflet, tanpa build step
```

`sumber.py`, `geometri.py`, `wilayah.py`, dan `requirements.txt` sudah selesai dan
teruji — jangan diubah tanpa alasan kuat.

Seluruh teks yang dilihat pengguna dan seluruh komentar kode ditulis dalam **Bahasa
Indonesia**.

### SIGMET BMKG sebagai konfirmasi sekunder

Selain VAAC Darwin, halaman ini menampilkan satu baris di tiap kartu gunung:
*"BMKG juga menerbitkan SIGMET WIIF · berlaku 12:30–15:30 WIB"*. Sumbernya sistem
**Ina-SIAM BMKG**, disaring dua kali dari feed global: hanya FIR Indonesia (`WI*`,
`WA*`) dan hanya bahaya `VA`.

**Statusnya penguat, bukan penentu.** Tidak satu pun poligon, jarak, ketinggian, atau
status di halaman ini berasal dari SIGMET — semuanya tetap murni dari VAAC Darwin.
Ini diuji, bukan sekadar dijanjikan: dengan feed dimatikan (host tak bisa dihubungi)
maupun mengembalikan HTML alih-alih GeoJSON, ringkasan nasional tetap **byte-identik**
dan halaman tetap HTTP 200 — hanya barisnya yang hilang tanpa suara. Barisnya juga
sengaja tanpa ikon dan tanpa warna status, supaya tidak terbaca sebagai peringatan
yang berdiri sendiri.

**Peringatan soal host.** Host resminya `inasiam.bmkg.go.id` memang ada, tapi dijaga
tantangan JavaScript Cloudflare sehingga tidak bisa dipanggil dari server. Alamat yang
dipakai adalah yang ditautkan halaman `va-map.php` milik BMKG sendiri — jadi ini memang
sistem mereka — **tetapi domainnya `.my.id`** (TLD perorangan Indonesia) dengan
sertifikat atas nama `rack.my.id`, bukan milik BMKG. Kendali domain itu ada di pihak
ketiga. Karena itulah perlakuannya dibatasi sebagai konfirmasi, dan catatan ini juga
ditampilkan kepada pengguna di panel Sumber data.

Kualitasnya sendiri bagus: 5 dari 5 permintaan sukses dalam 0,2–0,3 detik tanpa rate
limit, dan kelima VA SIGMET-nya cocok persis dengan kelima gunung yang sedang
beradvisory di VAAC.

### Panel kiri: paging, bukan gulir dalam gulir

Panel kiri hanya punya **satu** wadah gulir, yaitu dirinya sendiri. Daftar wilayah dan
bandara terdampak dipenggal jadi halaman 8 baris dengan kendali `‹ 9–16 dari 63 ›`,
bukan diberi `max-height` + `overflow-y:auto` sendiri. Gulir di dalam gulir membuat
orang tidak sengaja menggulir kotak dalam padahal maksudnya menggulir halaman — dan di
layar sentuh itu nyaris tidak bisa dihindari.

Pengelompokan per provinsi yang dulu memakai seksi buka-tutup diganti satu baris
ringkas di atas tabel (*"Jawa Barat 26 · Lampung 15 · Banten 8 · +6 provinsi lagi"*),
sehingga angkanya tetap terbaca tanpa memaksa wadah gulir kedua.

Nomor halaman dijepit otomatis kalau daftarnya menyusut setelah advisory baru terbit,
jadi tidak pernah tersangkut di halaman kosong.

### Tentang: dialog, bukan seksi dan footer

Footer dihapus. Panel "Tentang" dikeluarkan dari daftar panel kiri dan dipindah ke
dialog yang dipanggil tombol **?** di pojok kanan atas navbar. Isinya: deskripsi
singkat, alamat repositori, nama pembuat, seluruh keterangan sumber data, dan teks VA
ADVISORY asli per gunung.

Memakai elemen `<dialog>` asli, bukan tiruan dari `div` + `tabindex`: Escape, penguncian
fokus, latar modal, dan pengembalian fokus ke tombol pemanggil ditangani peramban.
Yang ditulis sendiri hanya pembuka, penutup, dan klik-latar-untuk-menutup. Keempatnya
diverifikasi dengan interaksi sungguhan, bukan event sintetis.

### Zona waktu

Indonesia punya tiga zona dan aplikasi ini nasional, jadi menampilkan semuanya sebagai
WIB keliru untuk separuh negeri — Dukono dan Ibu, dua gunung yang paling sering
beradvisory, ada di Maluku Utara yang **WIT**, selisih dua jam.

Pemetaannya mengikuti batas provinsi resmi, bukan garis bujur:

| Zona | UTC | Provinsi |
|---|---|---|
| WIB (`Asia/Jakarta`) | +7 | Sumatera, Jawa, Kalimantan Barat & Tengah |
| WITA (`Asia/Makassar`) | +8 | Kalimantan Selatan/Timur/Utara, Bali, NTB, NTT, seluruh Sulawesi |
| WIT (`Asia/Jayapura`) | +9 | Maluku, Maluku Utara, seluruh Papua |

Aturan pemakaiannya: **baris tabel wilayah dan bandara memakai zona daerahnya
sendiri** (satu tabel bisa memuat daerah dari tiga zona sekaligus, jadi tiap baris
membawa labelnya sendiri), sedangkan header, kartu jawaban, dan tombol linimasa
mengikuti **zona lokasi yang dipilih pengguna** — jatuh ke WIB kalau belum memilih.
Zona perangkat sengaja tidak dipakai supaya orang di luar negeri tetap melihat
waktu Indonesia.

## Mobile-first

CSS dasarnya menyasar ponsel; tata letak dua kolom baru muncul pada `@media (min-width:900px)`.
Urutan DOM juga urutan ponsel dan sekaligus urutan prioritas pertanyaan pengguna:

```
header -> .panel-atas (pilih lokasi + jawaban) -> main (peta) -> aside (rincian)
```

Di layar >=900px, `.panel-atas` dipatok di atas kolom kiri dan `aside` menggulir di bawahnya,
sementara peta mengisi kolom kanan setinggi layar. Jadi jawabannya tidak pernah tergulir hilang.

Hal-hal yang khusus diperbaiki untuk layar sentuh:

| Masalah | Penanganan |
|---|---|
| iOS Safari memperbesar halaman saat kotak isian difokus, dan tidak pernah kembali | `.cari input` dipaksa `font-size:16px` di ponsel (di bawah 16px memicu zoom otomatis) |
| Gulir bersarang di dalam gulir halaman | `.gulir` tidak menggulir sendiri di ponsel; batas tingginya baru dipasang pada >=900px |
| `100vh` lebih tinggi dari layar sebenarnya karena bilah alamat | seluruh tinggi memakai `dvh` |
| Sasaran sentuh terlalu kecil | tombol, kotak isian, saran pencarian, ringkasan provinsi, dan tombol zoom Leaflet semuanya >=40px |
| Poni dan bilah gestur ponsel menutupi isi | `viewport-fit=cover` + `env(safe-area-inset-*)` pada header, panel dan footer |
| Kontrol linimasa menyusut ke lebar isi | `float` dan margin bawaan `.leaflet-control` dibatalkan; di ponsel linimasa membentang selebar peta |
| Legenda menutupi peta yang sudah sempit | di ponsel legenda pindah ke pojok kanan atas dan tertutup secara bawaan |

Tinggi kerangka di desktop dikunci dengan `calc(100dvh - var(--tinggi-header))`, dan
`--tinggi-header` diisi JavaScript dari tinggi header yang sebenarnya (diukur, bukan
ditebak) sehingga tetap benar kalau judulnya membungkus ke baris kedua.

## Batasan

**Poligon VAAC menandai ruang udara, bukan permukaan tanah.** Sebuah kabupaten/kota
yang berada di dalam poligon berarti ada abu **di atasnya** pada ketinggian yang
tertera — belum tentu sedang terjadi hujan abu. Kalau dasar lapisannya bukan permukaan
(`SFC`), abu itu melintas di ketinggian dan tidak turun ke tanah. Untuk hujan abu di
permukaan, rujuk pengumuman PVMBG/BPBD setempat.

**Cakupan VAAC Darwin tidak sama dengan cakupan seluruh gunung Indonesia.** VAAC
menerbitkan advisory hanya kalau ada abu yang relevan bagi penerbangan. Gunung yang
statusnya Siaga tapi belum melontarkan abu tidak akan muncul di daftar ini. Layar yang
menampilkan "aman" berarti tidak ada advisory abu aktif yang menaungi wilayah, bukan
berarti tidak ada gunung yang sedang bermasalah.

**Koordinat kabupaten/kota adalah satu titik centroid**, bukan poligon batas wilayah.
Untuk kabupaten yang sangat luas atau bentuknya memanjang, status "terdampak" dihitung
terhadap titik pusatnya saja. Ini pilihan sadar demi biaya perhitungan; untuk keputusan
yang presisi, gunakan pencarian koordinat (`/api/lokasi?lat=&lon=`).

**Status MAGMA/PVMBG bisa kosong** karena WAF ESDM — lihat catatan di atas. Kolom yang
kosong disertai alasannya, dan tidak pernah diisi tebakan.

**Advisory VAAC terbit sekitar tiap 6 jam**, bukan realtime. Setiap respons membawa jam
terbit, jam berlaku, jam penarikan server, dan jadwal advisory berikutnya justru supaya
layar ini tidak dibaca seolah-olah detik-per-detik.

## Penyangkalan

**Ini bukan produk resmi BMKG, PVMBG/MAGMA, maupun Bureau of Meteorology Australia.**
Aplikasi ini menampilkan ulang data publik dari sumber-sumber tersebut dan tidak
berafiliasi dengan satu pun di antaranya. Untuk keputusan penerbangan, gunakan VA
SIGMET dan VA Advisory resmi. Untuk keputusan evakuasi dan tindakan kebencanaan,
gunakan pengumuman resmi PVMBG, BMKG, dan BPBD setempat.

Data wilayah bersumber dari OpenStreetMap dan tunduk pada lisensi **ODbL**.
