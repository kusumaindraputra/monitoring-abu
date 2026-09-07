# Catatan serah-terima sesi

Ditulis 2026-09-07 13:39 WIB. Tujuannya supaya sesi di terminal lain bisa
melanjutkan tanpa mengulang penelusuran yang sudah selesai.

## Keadaan sekarang

Aplikasi berjalan dan sudah diverifikasi. Commit terakhir sudah ter-push ke
`main`. Tidak ada pekerjaan yang menggantung.

```bash
cd ~/Projects/abu-indonesia
./.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8931
# lalu buka http://127.0.0.1:8931
```

Server dari sesi sebelumnya mungkin masih hidup di port 8931 (PID 2554957).
Matikan lewat PID dari `ss -ltnpH 'sport = :8931'` — **jangan** `pkill -f uvicorn`,
polanya cocok dengan baris perintah shell-nya sendiri dan akan membunuh shell Anda.

## Angka acuan saat sesi ditutup

Advisory VAAC 7 Sep 2026: **5 gunung** (Krakatau, Dukono, Semeru, Ibu, Lewotolok),
**63 kab/kota**, **9 provinsi**, **16 bandara** terdampak. Angka ini berubah tiap
advisory baru (~6 jam), jadi pakai sebagai gambaran, bukan patokan tetap.

## Cara memverifikasi ulang

Silang-periksa independen — hitung dampak nasional tanpa lewat `dampak.py`, lalu
bandingkan dengan `/api/nasional`. Kalau keempat angka cocok, jalur perhitungannya sehat:

```bash
./.venv/bin/python - <<'PY'
import json, urllib.request
import geometri, sumber
from wilayah import KABKOTA, BANDARA
adv = sumber.ambil_vaac(); L = ["obs","f6","f12","f18"]
kena = lambda t: any(geometri.titik_di_dalam(t, l["titik"])
                     for a in adv for k in L for l in a["lapisan"][k])
kab = {(w["nama"], w["provinsi"]) for w in KABKOTA if kena((w["lat"], w["lon"]))}
ban = {b["iata"] for b in BANDARA if kena((b["lat"], b["lon"]))}
r = json.load(urllib.request.urlopen("http://127.0.0.1:8931/api/nasional"))["ringkasan"]
print("kab/kota", len(kab), r["kabkota_terdampak"])
print("provinsi", len({p for _, p in kab}), r["provinsi_terdampak"])
print("bandara ", len(ban), r["bandara_terdampak"])
PY
```

Untuk frontend: ekstrak blok `<script>` dari `static/index.html` ke berkas
sementara lalu `node --check`. Tidak ada build step, jadi itu satu-satunya
pemeriksaan sintaks otomatis yang ada.

## Yang sudah diuji dan hasilnya

Jangan diulang dari nol — rinciannya ada di README bagian sumber data, ringkasnya:

| Sumber | Hasil |
|---|---|
| VAAC Darwin / BOM | bekerja, jadi satu-satunya penentu poligon dan status |
| MAGMA / PVMBG | **403 di seluruh domain esdm.go.id** dari IP ini, blokir tingkat IP |
| BMKG Ina-SIAM SIGMET | bekerja, dipakai sebagai konfirmasi sekunder saja |
| Lini masa Twitter/X | ditolak setelah dianalisis: API berbayar, widget kena 429, nitter mati |
| Overpass | `overpass-api.de` sering menolak; pakai mirror kumi.systems / private.coffee |

## Keputusan desain yang jangan diubah tanpa membaca alasannya

Semuanya sudah ditulis lengkap di `README.md`. Ringkasnya: satu warna untuk semua
poligon abu (batas 3 slot palet kategorikal pada kasus all-pairs), setiap status
wajib ikon + teks (hijau vs merah hanya berjarak deutan ΔE 4.1), linimasa adalah
filter bukan warna, waktu mengikuti zona provinsi wilayahnya, panel kiri hanya
punya satu gulir.

## Kesiapan production

Analisis lengkap + status tiap butir ada di `ANALISIS-PRODUCTION.md`. Dua belas butir
sudah dikerjakan dan diverifikasi, di antaranya:

- **Gulir hantu 1.258 px** di dashboard desktop. `aside` kekurangan `position:relative`,
  sehingga `<caption class="tersembunyi">` yang absolut menembus wadah gulir sampai ke
  `<html>`. Aturan yang layak diingat: setiap wadah gulir wajib `position:relative`.
- **Legenda peta bertumpuk dengan linimasa** (182 px saat jendela dikecilkan, 28 px
  pada muat segar di 902 px). Posisinya dulu dibekukan saat peta dibuat; kini
  dievaluasi ulang dan syaratnya dua: layout desktop DAN lebar peta >= 560 px.
- **Stale fallback VAAC.** BOM mati tidak lagi mematikan halaman; data terakhir tetap
  disajikan dengan penanda `pembaruan.vaac_basi`.
- **Gzip + Cache-Control.** `/api/wilayah` 71 KB -> 14,5 KB; `/api/nasional` 38 KB -> 5 KB.
- **Cache stampede.** 20 permintaan bersamaan kini memanggil upstream 1x, bukan 20x.
- **Koordinat GPS lewat POST**, tidak lagi masuk access log.
- Jalur `static/` jadi absolut, `/api/docs` ditutup, `/api/sehat` ditambahkan,
  cabang mati MAGMA/PVMBG dibuang.

Yang masih tersisa: berkas uji, pin dependensi + berkas deploy, logging, host Leaflet
sendiri, dan keputusan penyedia tile peta (tile OSM publik melanggar Tile Usage Policy).

## Kemungkinan langkah berikutnya

Belum dikerjakan, belum tentu diinginkan:

- Poligon SIGMET BMKG belum digambar di peta (sengaja — akan memaksa warna kedua).
- `gunung[].dampak.provinsi` hanya diturunkan dari kab/kota, jadi gunung yang cuma
  menaungi bandara tampil dengan daftar provinsi kosong.
- Label marker "Ibu" dan "Dukono" saling tindih pada zoom nasional (~40 km).
- Belum ada berkas uji di dalam repo; uji keadaan tepi masih ad-hoc.
