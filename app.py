"""Pantau Abu Vulkanik Indonesia.

Backend FastAPI: menarik VA ADVISORY dari VAAC Darwin (Bureau of Meteorology,
Australia) di sisi server, lalu menghitungnya terhadap seluruh Indonesia -
38 provinsi, 508 kabupaten/kota, 244 bandara ber-kode IATA.

Pembagian tugas antar modul:
  sumber.py   - ambil & parse advisory VAAC (dan status PVMBG)
  geometri.py - titik di dalam poligon, jarak ke poligon
  wilayah.py  - daftar wilayah Indonesia (beku, dari OpenStreetMap)
  dampak.py   - sapuan nasional yang di-cache + status satu titik
  app.py      - hanya menyusun respons; tidak ada logika perhitungan di sini

Frontend adalah satu berkas static/index.html yang memprogram terhadap kontrak
JSON di bawah ini.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import dampak
import sumber
import wilayah

app = FastAPI(
    title="Pantau Abu Vulkanik Indonesia",
    description="Sebaran abu vulkanik VAAC Darwin terhadap seluruh wilayah Indonesia.",
    docs_url="/api/docs",
)

# /api/wilayah tidak pernah berubah selama proses hidup, jadi payload-nya disusun
# sekali saat impor - bukan dirakit ulang tiap permintaan.
PAYLOAD_WILAYAH = {
    "provinsi": wilayah.PROVINSI,
    "kabkota": wilayah.KABKOTA,
    "bandara": wilayah.BANDARA,
}


# --------------------------------------------------------------------------
# alat bantu bersama
# --------------------------------------------------------------------------
def _advisories() -> list[dict]:
    """Advisory aktif VAAC Darwin; kegagalan upstream jadi HTTP 502 berbahasa Indonesia."""
    try:
        return sumber.ambil_vaac()
    except Exception as e:
        raise HTTPException(
            502, f"Gagal menghubungi VAAC Darwin (Bureau of Meteorology): {e}")


def _pembaruan(advisories: list[dict]) -> dict:
    """Blok waktu yang bentuknya sama persis di semua endpoint.

    `terbit_terbaru` = advisory paling baru yang sedang dipakai.
    `berikutnya_terdekat` = advisory berikutnya yang paling cepat dijadwalkan,
    yaitu kapan halaman ini paling cepat punya data baru.
    """
    terbit = [a["terbit_iso"] for a in advisories if a.get("terbit_iso")]
    berikutnya = [a["advisory_berikutnya_iso"] for a in advisories
                  if a.get("advisory_berikutnya_iso")]
    return {
        "sekarang": sumber.sekarang_iso(),
        "vaac_ditarik": sumber.vaac_ditarik_pada(),
        "sigmet_ditarik": sumber.sigmet_ditarik_pada(),
        "terbit_terbaru": max(terbit) if terbit else None,
        "berikutnya_terdekat": min(berikutnya) if berikutnya else None,
    }


def _linimasa(adv: dict) -> list[dict]:
    """Empat langkah waktu satu advisory, berurutan, lapisan apa adanya untuk peta."""
    return [{
        "kunci": kunci,
        "label": label,
        "berlaku": (adv.get("berlaku_iso") or {}).get(kunci),
        "lapisan": (adv.get("lapisan") or {}).get(kunci) or [],
    } for kunci, label in dampak.LANGKAH]


# --------------------------------------------------------------------------
# endpoint
# --------------------------------------------------------------------------
@app.get("/api/wilayah")
def daftar_wilayah():
    """Daftar wilayah Indonesia untuk pencarian dan penanda peta di frontend."""
    return PAYLOAD_WILAYAH


@app.get("/api/nasional")
def nasional():
    """Payload utama: semua gunung yang beradvisory + siapa saja yang terdampak."""
    advisories = _advisories()
    hasil = dampak.hitung_nasional(advisories)

    gunung = []
    for adv in advisories:
        kode = dampak.kode_gunung(adv)
        posisi = adv.get("posisi") or [None, None]
        d = hasil["dampak_gunung"].get(kode, {"kabkota": 0, "bandara": 0, "provinsi": []})
        gunung.append({
            "kode": kode,
            "nama": dampak.nama_rapi(adv.get("gunung")),
            "lat": posisi[0],
            "lon": posisi[1],
            "elevasi": adv.get("elevasi"),
            "advisory_nr": adv.get("advisory_nr"),
            "terbit": adv.get("terbit_iso"),
            "berikutnya": adv.get("advisory_berikutnya_iso"),
            "obs_teramati": adv.get("obs_teramati"),
            "detail_erupsi": adv.get("detail_erupsi"),
            "catatan": adv.get("catatan"),
            "info_source": adv.get("info_source"),
            "grafik_url": adv.get("grafik_url"),
            "linimasa": _linimasa(adv),
            "dampak": d,
            # Konfirmasi sekunder dari BMKG. Sengaja TIDAK ikut menentukan poligon,
            # jarak, atau status apa pun - itu semua tetap murni dari VAAC Darwin.
            "sigmet": sumber.sigmet_untuk(adv.get("gunung") or ""),
        })
    gunung.sort(key=lambda g: (-g["dampak"]["kabkota"], g["nama"]))

    return {
        "pembaruan": _pembaruan(advisories),
        "ringkasan": {
            "gunung_aktif": len(gunung),
            "kabkota_terdampak": len(hasil["kabkota"]),
            "provinsi_terdampak": len(hasil["provinsi"]),
            "bandara_terdampak": len(hasil["bandara"]),
            "ada_lapisan_permukaan": hasil["ada_lapisan_permukaan"],
        },
        "gunung": gunung,
        "terdampak": {
            "kabkota": hasil["kabkota"],
            "bandara": hasil["bandara"],
            "provinsi": hasil["provinsi"],
        },
    }


@app.get("/api/lokasi")
def lokasi(
    kabkota: str | None = Query(None, description="Nama kabupaten/kota, mis. Bogor"),
    provinsi: str | None = Query(
        None, description="Provinsi pembeda, dipakai kalau nama kab/kota dipakai dua daerah"),
    lat: float | None = Query(None, description="Lintang, -90..90"),
    lon: float | None = Query(None, description="Bujur, -180..180"),
    nama: str | None = Query(None, description="Label bebas untuk koordinat"),
):
    """Status satu lokasi: kabupaten/kota bernama, atau koordinat GPS sembarang."""
    if kabkota:
        target = kabkota.strip().lower()
        # `provinsi` opsional: ada nama yang dipakai dua daerah sekaligus (Banjar di
        # Jawa Barat dan di Kalimantan Selatan). Tanpa pembeda, yang pertama dipakai.
        pembeda = (provinsi or "").strip().lower()
        senama = [k for k in wilayah.KABKOTA if k["nama"].lower() == target]
        cocok = next((k for k in senama if k["provinsi"].lower() == pembeda), None) \
            if pembeda else None
        if cocok is None:
            cocok = senama[0] if senama else None
        if cocok is None:
            raise HTTPException(
                404, f"Kabupaten/kota '{kabkota}' tidak ada dalam daftar wilayah Indonesia.")
        titik = (cocok["lat"], cocok["lon"])
        info_lokasi = {
            "nama": cocok["nama"],
            "provinsi": cocok["provinsi"],
            "lat": cocok["lat"],
            "lon": cocok["lon"],
            "sumber": "kabkota",
        }
        terdekat_kabkota = None
    elif lat is not None and lon is not None:
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            raise HTTPException(
                422, "Koordinat di luar jangkauan: lintang harus -90..90 dan bujur -180..180.")
        titik = (lat, lon)
        terdekat_kabkota = dampak.kabkota_terdekat(titik)
        info_lokasi = {
            "nama": (nama or "").strip() or "Lokasi Anda",
            "provinsi": terdekat_kabkota["provinsi"],
            "lat": lat,
            "lon": lon,
            "sumber": "koordinat",
        }
    else:
        raise HTTPException(
            422, "Sertakan parameter 'kabkota', atau pasangan 'lat' dan 'lon'.")

    advisories = _advisories()
    hasil_titik = dampak.status_titik(titik, advisories)
    terdampak_iata = {b["iata"] for b in dampak.hitung_nasional(advisories)["bandara"]}

    return {
        "lokasi": info_lokasi,
        "kabkota_terdekat": terdekat_kabkota,
        "status": hasil_titik["status"],
        "kena": hasil_titik["kena"],
        "terdekat": hasil_titik["terdekat"],
        "bandara_terdekat": dampak.bandara_terdekat(titik, terdampak_iata),
        "pembaruan": _pembaruan(advisories),
    }


@app.get("/api/gunung/{kode}")
def detail_gunung(kode: str):
    """Advisory lengkap satu gunung, termasuk teks VAA mentah untuk yang mau memverifikasi."""
    advisories = _advisories()
    for adv in advisories:
        if dampak.kode_gunung(adv) == kode:
            return {**adv, "nama_rapi": dampak.nama_rapi(adv.get("gunung"))}
    raise HTTPException(404, f"Tidak ada advisory abu aktif untuk kode gunung '{kode}'.")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def beranda():
    return FileResponse("static/index.html")
