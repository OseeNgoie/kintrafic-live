"""Approximate commune polygons and instrumented road axes for Kinshasa (WGS84).

Geometries are simplified rectangles / polylines for assignment and demo display,
not cadastral boundaries.
"""

from __future__ import annotations

# name, slug, priority, west, south, east, north
COMMUNES: list[tuple[str, str, int, float, float, float, float]] = [
    ("Gombe", "gombe", 1, 15.300, -4.325, 15.335, -4.285),
    ("Lingwala", "lingwala", 1, 15.285, -4.340, 15.310, -4.310),
    ("Barumbu", "barumbu", 1, 15.320, -4.340, 15.350, -4.305),
    ("Kinshasa", "kinshasa", 1, 15.265, -4.350, 15.295, -4.315),
    ("Kintambo", "kintambo", 1, 15.250, -4.335, 15.280, -4.300),
    ("Ngaliema", "ngaliema", 1, 15.220, -4.380, 15.270, -4.300),
    ("Kasa-Vubu", "kasa-vubu", 1, 15.285, -4.365, 15.320, -4.335),
    ("Bandalungwa", "bandalungwa", 1, 15.255, -4.375, 15.290, -4.340),
    ("Limete", "limete", 1, 15.320, -4.410, 15.370, -4.350),
    ("Matete", "matete", 1, 15.335, -4.415, 15.370, -4.380),
    ("Lemba", "lemba", 1, 15.300, -4.425, 15.340, -4.385),
    ("Ngaba", "ngaba", 1, 15.305, -4.400, 15.335, -4.370),
    ("Makala", "makala", 1, 15.290, -4.395, 15.325, -4.360),
    ("Bumbu", "bumbu", 1, 15.270, -4.400, 15.305, -4.360),
    ("Selembao", "selembao", 1, 15.240, -4.410, 15.280, -4.360),
    ("Mont-Ngafula", "mont-ngafula", 1, 15.230, -4.470, 15.300, -4.400),
    ("Masina", "masina", 1, 15.360, -4.405, 15.420, -4.350),
    ("Ndjili", "ndjili", 1, 15.350, -4.430, 15.410, -4.385),
    ("Kisenso", "kisenso", 1, 15.320, -4.450, 15.370, -4.410),
]


def box_wkt(west: float, south: float, east: float, north: float) -> str:
    return (
        "MULTIPOLYGON((("
        f"{west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}"
        ")))"
    )


# name, WKT LINESTRING
ROAD_AXES: list[tuple[str, str]] = [
    (
        "Boulevard du 30 Juin",
        "LINESTRING(15.270 -4.312, 15.292 -4.310, 15.313 -4.305, 15.330 -4.302)",
    ),
    (
        "Boulevard Triomphal / Sendwe",
        "LINESTRING(15.305 -4.330, 15.318 -4.345, 15.330 -4.360)",
    ),
    (
        "Boulevard Lumumba",
        "LINESTRING(15.330 -4.320, 15.350 -4.350, 15.370 -4.385, 15.390 -4.405)",
    ),
    (
        "Route de Matadi",
        "LINESTRING(15.250 -4.320, 15.240 -4.350, 15.235 -4.390, 15.230 -4.440)",
    ),
    (
        "Avenue de la Libération",
        "LINESTRING(15.300 -4.320, 15.298 -4.345, 15.295 -4.370)",
    ),
    (
        "Avenue Kasa-Vubu",
        "LINESTRING(15.290 -4.330, 15.300 -4.350, 15.310 -4.370)",
    ),
    (
        "Pont Matete / échangeurs Limete",
        "LINESTRING(15.335 -4.365, 15.345 -4.380, 15.355 -4.395)",
    ),
    (
        "Avenue de l’Université",
        "LINESTRING(15.310 -4.385, 15.318 -4.400, 15.325 -4.415)",
    ),
    (
        "Route de Kingasani / Masina",
        "LINESTRING(15.350 -4.360, 15.375 -4.370, 15.400 -4.375)",
    ),
    (
        "Avenue By-Pass / aéroport Ndjili",
        "LINESTRING(15.360 -4.390, 15.380 -4.400, 15.405 -4.410)",
    ),
]
