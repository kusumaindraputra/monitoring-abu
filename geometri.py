"""Perhitungan geometri: apakah satu titik kena poligon abu, dan jaraknya.

Jarak dihitung ke poligon abu resmi VAAC (sisi terdekat), bukan ke puncak
gunung, supaya angkanya berarti: "abu terdekat X km dari wilayah ini".
"""

from __future__ import annotations

import math

RADIUS_BUMI_KM = 6371.0088


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * RADIUS_BUMI_KM * math.asin(math.sqrt(h))


def titik_di_dalam(titik: tuple[float, float], poligon: list[list[float]]) -> bool:
    """Ray casting. `titik` dan `poligon` sama-sama (lat, lon)."""
    lat, lon = titik
    di_dalam = False
    n = len(poligon)
    for i in range(n):
        lat_i, lon_i = poligon[i]
        lat_j, lon_j = poligon[(i - 1) % n]
        if (lat_i > lat) != (lat_j > lat):
            potong = (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i
            if lon < potong:
                di_dalam = not di_dalam
    return di_dalam


def _jarak_ke_ruas(p: tuple[float, float], a: list[float], b: list[float]) -> float:
    """Jarak titik ke ruas garis, diproyeksikan ke bidang lokal (cukup akurat
    untuk skala ratusan km di lintang rendah)."""
    lat0 = math.radians(p[0])
    skala_lon = math.cos(lat0)

    def xy(q):
        return (q[1] * skala_lon, q[0])

    px, py = xy(p)
    ax, ay = xy(a)
    bx, by = xy(b)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return haversine_km(p, (a[0], a[1]))
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    proyeksi_lat = ay + t * dy
    proyeksi_lon = (ax + t * dx) / skala_lon if skala_lon else a[1]
    return haversine_km(p, (proyeksi_lat, proyeksi_lon))


def jarak_ke_poligon_km(titik: tuple[float, float], poligon: list[list[float]]) -> float:
    """0.0 kalau titik ada di dalam poligon, selain itu jarak ke tepi terdekat."""
    if titik_di_dalam(titik, poligon):
        return 0.0
    n = len(poligon)
    return min(_jarak_ke_ruas(titik, poligon[i], poligon[(i + 1) % n]) for i in range(n))


def evaluasi_lapisan(titik: tuple[float, float], lapisan: list[dict]) -> dict:
    """Status satu titik terhadap semua sub-lapisan ketinggian di satu waktu."""
    if not lapisan:
        return {"kena": False, "jarak_km": None, "fl_terdekat": None}

    terbaik = None
    for lap in lapisan:
        jarak = jarak_ke_poligon_km(titik, lap["titik"])
        if terbaik is None or jarak < terbaik[0]:
            terbaik = (jarak, lap["fl_label"])
    jarak, fl = terbaik
    return {"kena": jarak == 0.0, "jarak_km": round(jarak, 1), "fl_terdekat": fl}
