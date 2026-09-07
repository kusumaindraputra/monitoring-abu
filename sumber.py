"""Klien untuk sumber data upstream.

Hanya dua sumber yang dipakai, karena hanya dua ini yang bisa mengubah
keputusan orang yang membuka halaman ini:

  - VAAC Darwin / BOM Australia .. poligon sebaran abu + ketinggiannya
  - MAGMA ESDM / PVMBG ........... status resmi gunung api Indonesia

Open-Meteo (angin di kawah) dan GDACS sengaja dibuang; alasannya ada di README.

Semua fetch di-cache dengan TTL, dan waktu penarikannya disimpan supaya UI bisa
menampilkan "data ini terakhir diperbarui kapan".
"""

from __future__ import annotations

import html
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

# Dikirim ke BOM dan MAGMA; harus memperkenalkan aplikasi ini apa adanya.
UA = "abu-indonesia/1.0 (+pemantau abu vulkanik Indonesia)"

BOM_ADVISORY_URL = "https://www.bom.gov.au/aviation/php/process.php"
BOM_REFERER = "https://www.bom.gov.au/aviation/volcanic-ash/darwin-va-advisory.shtml"
BOM_GRAPHIC_BASE = "https://www.bom.gov.au/fwo/"
MAGMA_URL = "https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas"

# SIGMET abu vulkanik BMKG untuk FIR Indonesia, lewat sistem Ina-SIAM.
#
# CATATAN PENTING soal host ini. Host resminya `inasiam.bmkg.go.id` ADA tapi dijaga
# tantangan JavaScript Cloudflare, jadi tidak bisa dipanggil dari server. Alamat di
# bawah inilah yang dipakai halaman va-map.php milik BMKG sendiri - jadi ini memang
# sistem mereka - TAPI domainnya `.my.id` (TLD perorangan Indonesia) dengan sertifikat
# atas nama `rack.my.id`, bukan milik BMKG. Kendali domainnya ada di pihak ketiga.
#
# Konsekuensinya, data dari sini diperlakukan sebagai KONFIRMASI SEKUNDER saja:
# tidak pernah menimpa VAAC Darwin, dan kalau gagal panelnya hilang tanpa suara.
SIGMET_URL = "https://inasiam.rack.my.id/api/v1/opmet/sigmet/geojson"

KAKI_KE_METER = 0.3048


# --------------------------------------------------------------------------
# cache TTL + catatan waktu penarikan
# --------------------------------------------------------------------------
class _Cache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: str, ttl: int, producer: Callable[[], Any]) -> Any:
        now = time.time()
        with self._lock:
            hit = self._data.get(key)
            if hit and now - hit[0] < ttl:
                return hit[1]
        value = producer()
        with self._lock:
            self._data[key] = (time.time(), value)
        return value

    def ditarik_pada(self, key: str) -> str | None:
        """ISO UTC kapan entri cache ini terakhir benar-benar ditarik dari upstream."""
        with self._lock:
            hit = self._data.get(key)
        return iso_utc(datetime.fromtimestamp(hit[0], timezone.utc)) if hit else None


_cache = _Cache()


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sekarang_iso() -> str:
    return iso_utc(datetime.now(timezone.utc))


# --------------------------------------------------------------------------
# waktu di dalam teks VAA
# --------------------------------------------------------------------------
_DTG_RE = re.compile(r"(\d{4})(\d{2})(\d{2})/(\d{2})(\d{2})Z")
_DDHHMM_RE = re.compile(r"\b(\d{2})/(\d{2})(\d{2})Z")


def dtg_ke_waktu(dtg: str | None) -> datetime | None:
    """`20260907/0100Z` -> datetime UTC."""
    m = _DTG_RE.search(dtg or "")
    if not m:
        return None
    th, bl, hr, jam, mnt = (int(x) for x in m.groups())
    return datetime(th, bl, hr, jam, mnt, tzinfo=timezone.utc)


def ddhhmm_ke_waktu(teks: str | None, acuan: datetime | None) -> datetime | None:
    """`07/0640Z` -> datetime UTC, tahun/bulannya diambil dari DTG advisory.

    Advisory yang terbit di awal bulan bisa memuat waktu observasi dari bulan
    sebelumnya, jadi selisih lebih dari 15 hari dianggap pergantian bulan.
    """
    m = _DDHHMM_RE.search(teks or "")
    if not m or acuan is None:
        return None
    hr, jam, mnt = (int(x) for x in m.groups())
    try:
        calon = acuan.replace(day=hr, hour=jam, minute=mnt, second=0, microsecond=0)
    except ValueError:
        return None
    if calon - acuan > timedelta(days=15):
        calon = (calon.replace(day=1) - timedelta(days=1)).replace(
            day=hr, hour=jam, minute=mnt)
    elif acuan - calon > timedelta(days=15):
        awal_bulan_depan = (calon.replace(day=28) + timedelta(days=7)).replace(day=1)
        calon = awal_bulan_depan.replace(day=hr, hour=jam, minute=mnt)
    return calon


# --------------------------------------------------------------------------
# ketinggian abu (flight level)
# --------------------------------------------------------------------------
def _token_ke_kaki(token: str) -> int:
    return 0 if token == "SFC" else int(token[2:]) * 100


def parse_ketinggian(fl_label: str) -> dict:
    """`SFC/FL150` -> lapisan permukaan sampai 4.600 m.

    Ini angka yang paling menentukan buat warga: kalau dasar lapisan bukan SFC,
    abunya melintas di ketinggian dan tidak turun ke permukaan.
    """
    dasar_tok, puncak_tok = fl_label.split("/")
    dasar_ft, puncak_ft = _token_ke_kaki(dasar_tok), _token_ke_kaki(puncak_tok)
    bulat = lambda ft: int(round(ft * KAKI_KE_METER / 100.0) * 100)
    dasar_m, puncak_m = bulat(dasar_ft), bulat(puncak_ft)
    return {
        "label": fl_label,
        "dasar_m": dasar_m,
        "puncak_m": puncak_m,
        "sampai_permukaan": dasar_ft == 0,
        "ringkas": ("permukaan" if dasar_ft == 0 else f"{dasar_m:,} m".replace(",", "."))
                   + " – " + f"{puncak_m:,} m".replace(",", "."),
    }


# --------------------------------------------------------------------------
# parser VA ADVISORY
# --------------------------------------------------------------------------
_COORD_RE = re.compile(r"([NS])(\d{2})(\d{2})\s+([EW])(\d{3})(\d{2})")
_FL_RE = re.compile(r"\b(?:SFC|FL\d{3})/FL\d{3}\b")
_MOV_RE = re.compile(r"MOV\s+([NSEW]{1,3})(?:\s+(\d{1,3})KT)?")
_FIELD_RE = re.compile(r"^([A-Z][A-Z0-9 +/]*?):\s?", re.MULTILINE)


def _dm_to_deg(hemi: str, deg: str, minute: str) -> float:
    nilai = int(deg) + int(minute) / 60.0
    return -nilai if hemi in ("S", "W") else nilai


def _parse_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    matches = list(_FIELD_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        fields[m.group(1).strip()] = " ".join(text[m.end():end].strip().rstrip("=").split())
    return fields


def _parse_layers(value: str) -> list[dict]:
    """Ambil poligon dari satu field `... VA CLD ...`.

    Satu field bisa memuat lebih dari satu lapisan ketinggian, contoh Krakatau:
        SFC/FL150 S0218 E10434 - ... MOV W 15KT SFC/FL500 S1205 E09653 - ...
    jadi teksnya dipotong di setiap label flight level.
    """
    if not value or "NOT AVBL" in value or "NO VA EXP" in value or "NOT PROVIDED" in value:
        return []

    marks = list(_FL_RE.finditer(value))
    layers = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(value)
        chunk = value[m.end():end]
        titik = [[_dm_to_deg(c[0], c[1], c[2]), _dm_to_deg(c[3], c[4], c[5])]
                 for c in _COORD_RE.findall(chunk)]
        if len(titik) < 3:
            continue
        mov = _MOV_RE.search(chunk)
        layers.append({
            "fl_label": m.group(0),
            "ketinggian": parse_ketinggian(m.group(0)),
            "arah": mov.group(1) if mov else None,
            "kecepatan_kt": int(mov.group(2)) if mov and mov.group(2) else None,
            "titik": titik,  # [[lat, lon], ...]
        })
    return layers


def parse_vaa(text: str) -> dict:
    """Teks Volcanic Ash Advisory mentah -> struktur terpakai."""
    f = _parse_fields(text)
    nama_gunung = f.get("VOLCANO", "")
    kode = nama_gunung.split()[-1] if nama_gunung and nama_gunung.split()[-1].isdigit() else None

    psn = _COORD_RE.search(f.get("PSN", ""))
    posisi = [_dm_to_deg(*psn.groups()[:3]), _dm_to_deg(*psn.groups()[3:])] if psn else None

    terbit = dtg_ke_waktu(f.get("DTG"))
    # VAAC pakai "OBS" kalau abu terlihat di satelit, "EST" kalau diperkirakan
    obs_key = "OBS VA CLD" if "OBS VA CLD" in f else "EST VA CLD"

    lapisan, berlaku = {}, {}
    for kunci, field in (("obs", obs_key), ("f6", "FCST VA CLD +6 HR"),
                         ("f12", "FCST VA CLD +12 HR"), ("f18", "FCST VA CLD +18 HR")):
        nilai = f.get(field, "")
        lapisan[kunci] = _parse_layers(nilai)
        # field prakiraan diawali waktu berlakunya, mis. "07/0640Z SFC/FL070 ..."
        acuan = f.get("OBS VA DTG") or f.get("EST VA DTG") if kunci == "obs" else nilai
        waktu = ddhhmm_ke_waktu(acuan, terbit)
        berlaku[kunci] = iso_utc(waktu) if waktu else None

    berikutnya = dtg_ke_waktu(f.get("NXT ADVISORY"))
    return {
        "sumber": "VAAC Darwin (Bureau of Meteorology, Australia)",
        "dtg": f.get("DTG"),
        "terbit_iso": iso_utc(terbit) if terbit else None,
        "gunung": nama_gunung,
        "kode": kode,
        "posisi": posisi,
        "elevasi": f.get("SOURCE ELEV"),
        "advisory_nr": f.get("ADVISORY NR"),
        "info_source": f.get("INFO SOURCE"),
        "detail_erupsi": f.get("ERUPTION DETAILS"),
        "obs_teramati": obs_key.startswith("OBS"),
        "lapisan": lapisan,
        "berlaku_iso": berlaku,
        "catatan": f.get("RMK"),
        "advisory_berikutnya_iso": iso_utc(berikutnya) if berikutnya else None,
        "teks_mentah": text,
    }


def _bersihkan_html(fragment: str) -> str:
    teks = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", teks)).strip()


def _ambil_vaac() -> list[dict]:
    with httpx.Client(timeout=30, headers={"User-Agent": UA}, follow_redirects=True) as c:
        r = c.post(BOM_ADVISORY_URL,
                   data={"page": "volcanic-ash-darwin", "javascript": "1"},
                   headers={"Referer": BOM_REFERER, "X-Requested-With": "XMLHttpRequest"})
        r.raise_for_status()
        payload = r.json()

    advisories = payload.get("advisories") or {}
    items = advisories.values() if isinstance(advisories, dict) else advisories

    hasil = []
    for a in items:
        teks = _bersihkan_html(a.get("text", ""))
        if not teks:
            continue
        parsed = parse_vaa(teks)
        grafik = a.get("graphic")
        parsed["grafik_url"] = BOM_GRAPHIC_BASE + grafik if grafik else None
        hasil.append(parsed)
    hasil.sort(key=lambda x: x.get("gunung") or "")
    return hasil


def ambil_vaac(ttl: int = 300) -> list[dict]:
    """Semua advisory abu aktif dari VAAC Darwin."""
    return _cache.get_or_set("vaac", ttl, _ambil_vaac)


def vaac_ditarik_pada() -> str | None:
    return _cache.ditarik_pada("vaac")


# --------------------------------------------------------------------------
# MAGMA ESDM / PVMBG
# --------------------------------------------------------------------------
def ambil_pvmbg(ttl: int = 900) -> dict:
    """Status resmi gunung api Indonesia.

    MAGMA memasang WAF yang menolak sebagian IP (termasuk banyak IP datacenter)
    dengan HTTP 403 "Request Rejected". Kegagalan dikembalikan sebagai data,
    bukan exception, supaya panel abu tetap jalan tanpa panel ini.
    """
    def _fetch() -> dict:
        try:
            with httpx.Client(timeout=25, follow_redirects=True, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
                "Referer": "https://magma.esdm.go.id/v1",
            }) as c:
                r = c.get(MAGMA_URL)
            if r.status_code != 200 or "application/json" not in r.headers.get("content-type", ""):
                return {"tersedia": False,
                        "alasan": f"MAGMA menolak permintaan (HTTP {r.status_code})", "data": []}
            return {"tersedia": True, "alasan": None, "data": r.json()}
        except Exception as e:
            return {"tersedia": False, "alasan": f"MAGMA tidak bisa dihubungi: {e}", "data": []}

    return _cache.get_or_set("pvmbg", ttl, _fetch)


def pvmbg_ditarik_pada() -> str | None:
    return _cache.ditarik_pada("pvmbg")


# --------------------------------------------------------------------------
# SIGMET abu vulkanik BMKG (konfirmasi sekunder)
# --------------------------------------------------------------------------
def _label_fl(dasar_ft, puncak_ft) -> str | None:
    """`0, 15000` -> `SFC/FL150`, supaya bisa dibaca parse_ketinggian()."""
    try:
        dasar, puncak = int(dasar_ft or 0), int(puncak_ft or 0)
    except (TypeError, ValueError):
        return None
    if puncak <= 0:
        return None
    awal = "SFC" if dasar <= 0 else f"FL{dasar // 100:03d}"
    return f"{awal}/FL{puncak // 100:03d}"


def ambil_sigmet(ttl: int = 600) -> dict:
    """VA SIGMET yang sedang berlaku untuk FIR Indonesia (WI* dan WA*).

    Feed-nya global (ratusan SIGMET sedunia), jadi disaring dua kali: hanya FIR
    Indonesia dan hanya bahaya abu vulkanik. Kegagalan dikembalikan sebagai data,
    bukan exception - panel ini sekunder dan tidak boleh menjatuhkan halaman.
    """
    def _fetch() -> dict:
        try:
            with httpx.Client(timeout=25, headers={"User-Agent": UA},
                              follow_redirects=True) as c:
                r = c.get(SIGMET_URL)
            if r.status_code != 200:
                return {"tersedia": False,
                        "alasan": f"Ina-SIAM menolak permintaan (HTTP {r.status_code})",
                        "data": []}
            fitur = r.json().get("features", [])
        except Exception as e:
            return {"tersedia": False, "alasan": f"Ina-SIAM tidak bisa dihubungi: {e}",
                    "data": []}

        hasil = []
        for f in fitur:
            p = f.get("properties") or {}
            fir = str(p.get("firId") or "")
            if not fir.startswith(("WI", "WA")) or p.get("hazard") != "VA":
                continue
            label = _label_fl(p.get("base"), p.get("top"))
            hasil.append({
                "gunung": (p.get("qualifier") or "").strip(),
                "fir": fir,
                "fir_nama": p.get("firName"),
                "seri": p.get("seriesId"),
                "berlaku_dari": p.get("validTimeFrom"),
                "berlaku_sampai": p.get("validTimeTo"),
                "ketinggian": parse_ketinggian(label) if label else None,
                "arah": p.get("dir") if p.get("dir") not in ("-", None) else None,
                "kecepatan_kt": p.get("spd"),
                "teks_mentah": p.get("rawSigmet"),
            })
        return {"tersedia": True, "alasan": None, "data": hasil}

    return _cache.get_or_set("sigmet", ttl, _fetch)


def sigmet_ditarik_pada() -> str | None:
    return _cache.ditarik_pada("sigmet")


def sigmet_untuk(nama_gunung: str) -> dict | None:
    """Cari SIGMET yang cocok dengan satu gunung VAAC.

    VAAC menulis "KRAKATAU 262000", SIGMET menulis "KRAKATAU", jadi dicocokkan
    pada kata pertama yang sudah dinormalkan.
    """
    hasil = ambil_sigmet()
    if not hasil["tersedia"] or not nama_gunung:
        return None
    target = _kunci(nama_gunung.split()[0])
    for s in hasil["data"]:
        if target and target == _kunci(s["gunung"]):
            return s
    return None


def _baris_pvmbg() -> list[dict]:
    rows = ambil_pvmbg()["data"]
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("gunung_api") or []
    return rows if isinstance(rows, list) else []


def _kunci(nama: str) -> str:
    return re.sub(r"[^a-z]", "", (nama or "").lower())


def status_pvmbg(nama_gunung: str) -> dict | None:
    """Cari satu gunung di daftar MAGMA berdasarkan nama.

    Bentuk field MAGMA bisa berbeda-beda antar versi, jadi pencocokannya longgar
    dan mengembalikan None kalau tidak ketemu, bukan menebak.
    """
    target = _kunci(nama_gunung)
    for row in _baris_pvmbg():
        nama = str(row.get("nama") or row.get("name") or row.get("gunung_api") or "")
        if target and target in _kunci(nama):
            return {
                "nama": nama,
                "level": row.get("status") or row.get("level") or row.get("tingkat_aktivitas"),
                "laporan_url": row.get("laporan") or row.get("url"),
                "diperbarui": row.get("updated_at") or row.get("tanggal") or row.get("waktu"),
            }
    return None
