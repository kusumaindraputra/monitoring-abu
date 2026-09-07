"""Perhitungan dampak abu vulkanik terhadap seluruh Indonesia.

Modul ini menjawab dua pertanyaan yang berbeda bentuknya:

  1. NASIONAL  - dari semua advisory VAAC Darwin yang sedang aktif, kabupaten/kota
                 (508) dan bandara (244) mana saja yang berada di bawah poligon
                 abu, serta LANGKAH WAKTU PERTAMA yang menaunginya. Perhitungan
                 ini menyapu 752 titik x semua advisory x 4 langkah waktu, jadi
                 hasilnya di-cache.
  2. SATU TITIK - status satu koordinat sembarang (kabupaten/kota pilihan atau
                 lokasi GPS pengguna). Murah, tidak perlu cache.

Kenapa di-cache: advisory VAAC hanya terbit tiap ~6 jam, sedangkan halaman bisa
dibuka ribuan kali di antara dua advisory. Kunci cache-nya adalah sidik jari
daftar advisory - tuple (kode, dtg) semua advisory - sehingga cache otomatis
gugur begitu ada advisory baru, tanpa perlu TTL yang menebak-nebak.

Semua titik berformat (lat, lon), mengikuti geometri.py.
"""

from __future__ import annotations

import re
import threading

import geometri
import wilayah

# Urutan langkah waktu yang dipakai di seluruh aplikasi.
LANGKAH = [
    ("obs", "Sekarang"),
    ("f6", "+6 jam"),
    ("f12", "+12 jam"),
    ("f18", "+18 jam"),
]


# --------------------------------------------------------------------------
# identitas gunung
# --------------------------------------------------------------------------
def nama_rapi(nama_vaac: str | None) -> str:
    """`KRAKATAU 262000` -> `Krakatau`; `LEWOTOBI LAKI-LAKI 264180` -> `Lewotobi Laki-Laki`."""
    nama = (nama_vaac or "").strip()
    if not nama:
        return ""
    bagian = nama.split()
    if len(bagian) > 1 and bagian[-1].isdigit():
        bagian = bagian[:-1]
    return " ".join(bagian).title()


def kode_gunung(adv: dict) -> str:
    """Kode Smithsonian advisory; kalau VAAC tidak mencantumkannya, pakai slug nama.

    Tidak boleh mengembalikan string kosong: kode ini dipakai sebagai identitas
    di /api/gunung/{kode}, jadi advisory tanpa nomor pun harus tetap bisa dibuka.
    """
    kode = (adv.get("kode") or "").strip()
    if kode:
        return kode
    slug = re.sub(r"[^a-z0-9]+", "-", (adv.get("gunung") or "").lower()).strip("-")
    return slug or "tanpa-kode"


# --------------------------------------------------------------------------
# alat bantu geometri: kotak pembatas untuk menolak cepat
# --------------------------------------------------------------------------
def _kotak(poligon: list[list[float]]) -> tuple[float, float, float, float]:
    """(lat_min, lat_max, lon_min, lon_max) satu poligon."""
    lats = [t[0] for t in poligon]
    lons = [t[1] for t in poligon]
    return (min(lats), max(lats), min(lons), max(lons))


def _di_luar_kotak(titik: tuple[float, float], kotak) -> bool:
    lat, lon = titik
    lat_min, lat_max, lon_min, lon_max = kotak
    return lat < lat_min or lat > lat_max or lon < lon_min or lon > lon_max


def _siapkan(adv: dict) -> list[tuple]:
    """Advisory -> [(kunci, label, berlaku_iso, [(kotak, lapisan), ...]), ...].

    Kotak pembatas dihitung sekali saja di sini, bukan sekali per titik: dengan
    752 titik yang harus diuji, ini yang membuat sapuan nasional tetap murah.
    Struktur ini terpisah dari dict advisory supaya objek cache sumber.py tidak
    ikut ternodai field internal.
    """
    langkah = []
    for kunci, label in LANGKAH:
        lapisan = adv.get("lapisan", {}).get(kunci) or []
        siap = [(_kotak(lap["titik"]), lap) for lap in lapisan if len(lap.get("titik") or []) >= 3]
        langkah.append((kunci, label, (adv.get("berlaku_iso") or {}).get(kunci), siap))
    return langkah


def _lapisan_menaungi(titik: tuple[float, float], siap: list[tuple]) -> list[dict]:
    """Lapisan mana saja pada satu langkah waktu yang benar-benar menaungi titik."""
    return [lap for kotak, lap in siap
            if not _di_luar_kotak(titik, kotak) and geometri.titik_di_dalam(titik, lap["titik"])]


def _ketinggian_unik(lapisan: list[dict]) -> list[dict]:
    """Dedup ketinggian berdasarkan fl_label, diurutkan dari yang paling tinggi.

    Satu langkah waktu bisa punya beberapa lapisan (contoh Krakatau: SFC/FL150
    dan SFC/FL500 sekaligus) dan lapisan yang sama bisa muncul lagi di langkah
    berikutnya, jadi tanpa dedup daftarnya penuh pengulangan.
    """
    unik: dict[str, dict] = {}
    for lap in lapisan:
        tinggi = lap.get("ketinggian") or {}
        label = tinggi.get("label") or lap.get("fl_label")
        if label and label not in unik:
            unik[label] = tinggi
    return sorted(unik.values(), key=lambda k: -(k.get("puncak_m") or 0))


def _ringkas_ketinggian(lapisan: list[dict]) -> str:
    """Teks pendek untuk kolom tabel, mis. `permukaan – 4.600 m · 900 m – 15.200 m`."""
    return " · ".join(k["ringkas"] for k in _ketinggian_unik(lapisan) if k.get("ringkas"))


# --------------------------------------------------------------------------
# satu titik terhadap satu advisory
# --------------------------------------------------------------------------
def _telaah_titik(titik: tuple[float, float], siap_langkah: list[tuple]) -> dict | None:
    """Langkah waktu pertama yang menaungi titik, plus semua lapisan yang menaunginya.

    Mengembalikan None kalau titik ini tidak pernah kena sama sekali. Lapisan
    dikumpulkan dari SELURUH langkah waktu, bukan hanya langkah pertama, supaya
    ketinggian yang dilaporkan lengkap sepanjang 18 jam ke depan.
    """
    pertama = None
    semua_lapisan: list[dict] = []
    lapisan_pertama: list[dict] = []

    for kunci, label, berlaku, siap in siap_langkah:
        menaungi = _lapisan_menaungi(titik, siap)
        if not menaungi:
            continue
        semua_lapisan.extend(menaungi)
        if pertama is None:
            pertama = (kunci, label, berlaku)
            lapisan_pertama = menaungi

    if pertama is None:
        return None
    return {
        "kunci_pertama": pertama[0],
        "label_pertama": pertama[1],
        "berlaku_pertama": pertama[2],
        "lapisan_pertama": lapisan_pertama,
        "lapisan_semua": semua_lapisan,
    }


def _jarak_terdekat(titik: tuple[float, float], siap_langkah: list[tuple]) -> float | None:
    """Jarak ke tepi poligon abu terdekat milik satu advisory (0.0 kalau di dalam).

    Jarak diukur ke poligon abu, bukan ke puncak gunung - itu angka yang berarti
    buat warga: "abu terdekat sekian km dari sini".
    """
    jarak = None
    for _, _, _, siap in siap_langkah:
        for _, lap in siap:
            j = geometri.jarak_ke_poligon_km(titik, lap["titik"])
            if jarak is None or j < jarak:
                jarak = j
            if jarak == 0.0:
                return 0.0
    return jarak


# --------------------------------------------------------------------------
# sapuan nasional (di-cache)
# --------------------------------------------------------------------------
_kunci_cache: tuple | None = None
_isi_cache: dict | None = None
_gembok = threading.Lock()


def sidik_jari(advisories: list[dict]) -> tuple:
    """Identitas satu kumpulan advisory: tuple (kode, dtg) semua advisory.

    dtg berubah setiap advisory baru terbit, jadi sidik jari ini cukup untuk
    tahu kapan hasil perhitungan harus dibuang.
    """
    return tuple(sorted((kode_gunung(a), a.get("dtg") or "") for a in advisories))


def hitung_nasional(advisories: list[dict]) -> dict:
    """Dampak seluruh advisory terhadap 508 kabupaten/kota dan 244 bandara.

    Hasilnya di-cache dengan kunci sidik jari daftar advisory. Cache dipegang
    satu gembok: dua permintaan bersamaan pada advisory baru akan menghitung
    berurutan, bukan mengembalikan hasil setengah jadi.
    """
    global _kunci_cache, _isi_cache

    kunci = sidik_jari(advisories)
    with _gembok:
        if _kunci_cache == kunci and _isi_cache is not None:
            return _isi_cache

    hasil = _hitung_nasional(advisories)

    with _gembok:
        _kunci_cache, _isi_cache = kunci, hasil
    return hasil


def bersihkan_cache() -> None:
    """Buang cache perhitungan (dipakai saat uji)."""
    global _kunci_cache, _isi_cache
    with _gembok:
        _kunci_cache, _isi_cache = None, None


def _urutan_langkah(kunci: str) -> int:
    for i, (k, _) in enumerate(LANGKAH):
        if k == kunci:
            return i
    return len(LANGKAH)


def _hitung_nasional(advisories: list[dict]) -> dict:
    """Sapuan sebenarnya. Jangan dipanggil langsung; pakai hitung_nasional()."""
    siap_per_gunung = [(adv, _siapkan(adv)) for adv in advisories]

    # Satu wilayah bisa dinaungi lebih dari satu gunung. Barisnya tetap satu per
    # wilayah - supaya jumlah di ringkasan sama persis dengan jumlah baris tabel -
    # dan gunung yang tercatat adalah yang menaungi PALING AWAL.
    #
    # Kunci kabupaten/kota adalah (nama, provinsi), BUKAN nama saja: ada nama yang
    # dipakai dua daerah berbeda (Kota Banjar di Jawa Barat dan Kabupaten Banjar di
    # Kalimantan Selatan). Kalau dikunci nama saja, salah satunya hilang dari
    # hitungan nasional dan provinsinya jadi salah.
    baris_kabkota: dict[tuple[str, str], dict] = {}
    baris_bandara: dict[str, dict] = {}
    dampak_gunung: dict[str, dict] = {}

    for adv, siap_langkah in siap_per_gunung:
        kode = kode_gunung(adv)
        nama = nama_rapi(adv.get("gunung"))
        dampak_gunung[kode] = {"kabkota": 0, "bandara": 0, "provinsi": []}

        for kab in wilayah.KABKOTA:
            telaah = _telaah_titik((kab["lat"], kab["lon"]), siap_langkah)
            if telaah is None:
                continue
            calon = {
                "nama": kab["nama"],
                "provinsi": kab["provinsi"],
                "iso": kab["iso"],
                "lat": kab["lat"],
                "lon": kab["lon"],
                "gunung": nama,
                "kunci_pertama": telaah["kunci_pertama"],
                "label_pertama": telaah["label_pertama"],
                "berlaku_pertama": telaah["berlaku_pertama"],
                "ketinggian_ringkas": _ringkas_ketinggian(telaah["lapisan_semua"]),
                "sampai_permukaan": any(
                    (lap.get("ketinggian") or {}).get("sampai_permukaan")
                    for lap in telaah["lapisan_semua"]),
                "_kode_gunung": kode,
            }
            kunci_kab = (kab["nama"], kab["provinsi"])
            lama = baris_kabkota.get(kunci_kab)
            if lama is None or _urutan_langkah(calon["kunci_pertama"]) < _urutan_langkah(
                    lama["kunci_pertama"]):
                baris_kabkota[kunci_kab] = calon

        for bdr in wilayah.BANDARA:
            telaah = _telaah_titik((bdr["lat"], bdr["lon"]), siap_langkah)
            if telaah is None:
                continue
            calon = {
                "iata": bdr["iata"],
                "nama": bdr["nama"],
                "provinsi": bdr["provinsi"],
                "lat": bdr["lat"],
                "lon": bdr["lon"],
                "gunung": nama,
                "kunci_pertama": telaah["kunci_pertama"],
                "label_pertama": telaah["label_pertama"],
                "berlaku_pertama": telaah["berlaku_pertama"],
                "ketinggian_ringkas": _ringkas_ketinggian(telaah["lapisan_semua"]),
                "_kode_gunung": kode,
            }
            lama = baris_bandara.get(bdr["iata"])
            if lama is None or _urutan_langkah(calon["kunci_pertama"]) < _urutan_langkah(
                    lama["kunci_pertama"]):
                baris_bandara[bdr["iata"]] = calon

    # Hitungan per gunung diambil dari baris yang akhirnya diatribusikan ke gunung
    # itu, sehingga jumlah per gunung selalu menjumlah pas ke total nasional.
    for baris in baris_kabkota.values():
        d = dampak_gunung.get(baris["_kode_gunung"])
        if d is not None:
            d["kabkota"] += 1
            if baris["provinsi"] not in d["provinsi"]:
                d["provinsi"].append(baris["provinsi"])
    for baris in baris_bandara.values():
        d = dampak_gunung.get(baris["_kode_gunung"])
        if d is not None:
            d["bandara"] += 1
    for d in dampak_gunung.values():
        d["provinsi"].sort()

    kabkota = sorted(baris_kabkota.values(), key=lambda b: (b["provinsi"], b["nama"]))
    bandara = sorted(baris_bandara.values(), key=lambda b: (b["provinsi"], b["nama"]))

    hitung_provinsi: dict[str, int] = {}
    iso_provinsi = {p["nama"]: p["iso"] for p in wilayah.PROVINSI}
    for baris in kabkota:
        hitung_provinsi[baris["provinsi"]] = hitung_provinsi.get(baris["provinsi"], 0) + 1
    provinsi = sorted(
        ({"nama": n, "iso": iso_provinsi.get(n), "jumlah_kabkota": j}
         for n, j in hitung_provinsi.items()),
        key=lambda p: (-p["jumlah_kabkota"], p["nama"]))

    for baris in kabkota:
        baris.pop("_kode_gunung", None)
    for baris in bandara:
        baris.pop("_kode_gunung", None)

    return {
        "kabkota": kabkota,
        "bandara": bandara,
        "provinsi": provinsi,
        "dampak_gunung": dampak_gunung,
        "ada_lapisan_permukaan": any(b["sampai_permukaan"] for b in kabkota),
    }


# --------------------------------------------------------------------------
# status satu titik sembarang (untuk /api/lokasi)
# --------------------------------------------------------------------------
def status_titik(titik: tuple[float, float], advisories: list[dict]) -> dict:
    """Status satu koordinat terhadap semua advisory aktif.

    "terdampak"      -> ada lapisan yang menaungi pada langkah `obs` (sudah kena sekarang)
    "akan_terdampak" -> belum kena sekarang, tapi kena di f6/f12/f18
    "aman"           -> tidak kena sama sekali dalam 18 jam ke depan
    """
    kena: list[dict] = []
    terdekat: dict | None = None

    for adv in advisories:
        siap_langkah = _siapkan(adv)
        nama = nama_rapi(adv.get("gunung"))
        kode = kode_gunung(adv)

        telaah = _telaah_titik(titik, siap_langkah)
        if telaah is not None:
            ketinggian = _ketinggian_unik(telaah["lapisan_semua"])
            kena.append({
                "gunung": nama,
                "kode": kode,
                "kunci_pertama": telaah["kunci_pertama"],
                "label_pertama": telaah["label_pertama"],
                "berlaku_pertama": telaah["berlaku_pertama"],
                "ketinggian": ketinggian,
                "sampai_permukaan": any(k.get("sampai_permukaan") for k in ketinggian),
            })

        jarak = _jarak_terdekat(titik, siap_langkah)
        if jarak is not None and (terdekat is None or jarak < terdekat["jarak_km"]):
            terdekat = {"gunung": nama, "kode": kode, "jarak_km": round(jarak, 1)}

    kena.sort(key=lambda k: (_urutan_langkah(k["kunci_pertama"]), k["gunung"]))

    if any(k["kunci_pertama"] == "obs" for k in kena):
        status = "terdampak"
    elif kena:
        status = "akan_terdampak"
    else:
        status = "aman"

    # "abu terdekat" cuma punya arti kalau titiknya memang tidak kena sama sekali.
    # Untuk titik yang kena (sekarang atau di prakiraan), _jarak_terdekat() menyapu
    # semua langkah waktu sehingga menghasilkan 0.0 - angka yang benar secara
    # perhitungan tapi membingungkan kalau dibaca bersama status "akan_terdampak".
    # Jadi jaraknya hanya dilaporkan untuk status "aman"; kapan abu tiba sudah
    # dijawab oleh `kena[].label_pertama`.
    if status != "aman":
        terdekat = None

    return {"status": status, "kena": kena, "terdekat": terdekat}


def kabkota_terdekat(titik: tuple[float, float]) -> dict:
    """Kabupaten/kota dengan centroid terdekat dari sebuah koordinat bebas."""
    terdekat = min(wilayah.KABKOTA,
                   key=lambda k: geometri.haversine_km(titik, (k["lat"], k["lon"])))
    return {
        "nama": terdekat["nama"],
        "provinsi": terdekat["provinsi"],
        "jarak_km": round(geometri.haversine_km(titik, (terdekat["lat"], terdekat["lon"])), 1),
    }


def bandara_terdekat(titik: tuple[float, float], terdampak_iata: set[str]) -> dict | None:
    """Bandara terdekat, sekalian menandai apakah bandara itu sedang kena abu.

    Abu vulkanik adalah persoalan keselamatan penerbangan, jadi bandara terdekat
    adalah konsekuensi paling konkret dari sebuah advisory bagi orang awam.
    """
    if not wilayah.BANDARA:
        return None
    terdekat = min(wilayah.BANDARA,
                   key=lambda b: geometri.haversine_km(titik, (b["lat"], b["lon"])))
    return {
        "iata": terdekat["iata"],
        "nama": terdekat["nama"],
        "jarak_km": round(geometri.haversine_km(titik, (terdekat["lat"], terdekat["lon"])), 1),
        "terdampak": terdekat["iata"] in terdampak_iata,
    }
