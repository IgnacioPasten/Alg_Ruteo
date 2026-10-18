"""A3 · Zonas ENR 5.1 del AIP de Chile."""

import re
from collections import Counter
from math import atan2, isfinite

from pyproj import Geod, Transformer
from pypdf import PdfReader
from shapely.geometry import Point, Polygon, mapping
from shapely.ops import transform

_ENTRY_RE = re.compile(r"^\s*SC\s*-\s*([PRD])\s*(\d+)\s+FIR\b", re.I)
_POSITION_ENTRY_RE = re.compile(r"SC-([PRD])(\d+)FIR", re.I)
_SEPARATED_COORD_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s+(\d{1,2})\s+(\d{1,2}(?:[.,]\d+)?)\s*S"
    r"\s*(?:[/–—-]\s*)?(\d{1,3})\s+(\d{1,2})\s+(\d{1,2}(?:[.,]\d+)?)\s*W",
    re.I,
)
_COMPACT_COORD_RE = re.compile(
    r"(?<!\d)(\d{6}(?:[.,]\d+)?)\s*S\s*(?:[/–—-]\s*)?"
    r"(\d{6,7}(?:[.,]\d+)?)\s*W",
    re.I,
)
_ALTITUDE_RE = re.compile(
    r"\b(?:UNL|FL\s*\d{1,3}|"
    r"\d[\d ,.]*\s*FT(?:\s*(?:AGL|AMSL|ALT|MSL))?|"
    r"GND(?:\s*/\s*MSL)?|SFC|MSL)\b",
    re.I,
)
_UNSUPPORTED_FORMS = {
    "SC-P10": "arco de 40 NM y límites laterales mixtos",
    "SC-R32": "límite lateral que sigue el arco D92 de IQQ",
    "SC-R45": "sector definido por radiales y distancias desde NAS VOR/DME",
    "SC-R46": "sector definido por radiales y distancias desde NAS VOR/DME",
    "SC-R47": "sector definido por varios radiales y distancias desde NAS VOR/DME",
    "SC-R48": "sector definido por radiales y distancias desde NAS VOR/DME",
}
_NO_COORDINATE_EXCEPTIONS = {
    "SC-P51": (
        "Las cuatro latitudes se leen, pero las longitudes aparecen como "
        "'07 031 15 W', con minutos no válidos; requiere cotejo visual del AIP."
    ),
    "SC-R45": (
        "Sin coordenadas publicadas en ENR 5.1; radiales/distancias desde NAS "
        "VOR/DME en FIR Punta Arenas, fuera del AOI de Valparaíso."
    ),
    "SC-R46": (
        "Sin coordenadas publicadas en ENR 5.1; radiales/distancias desde NAS "
        "VOR/DME en FIR Punta Arenas, fuera del AOI de Valparaíso."
    ),
    "SC-R47": (
        "Sin coordenadas publicadas en ENR 5.1; radiales/distancias desde NAS "
        "VOR/DME en FIR Punta Arenas, fuera del AOI de Valparaíso."
    ),
    "SC-R48": (
        "Sin coordenadas publicadas en ENR 5.1; radiales/distancias desde NAS "
        "VOR/DME en FIR Punta Arenas, fuera del AOI de Valparaíso."
    ),
}
_TO_METRIC = Transformer.from_crs(4326, 32719, always_xy=True).transform
_GEOD = Geod(ellps="WGS84")
_UNSUPPORTED_DISTANCE_LIMIT_M = 50_000


def _coordinate(lat_deg, lat_min, lat_sec, lon_deg, lon_min, lon_sec):
    lat_sec = float(str(lat_sec).replace(",", "."))
    lon_sec = float(str(lon_sec).replace(",", "."))
    if (
        lat_deg > 90 or lon_deg > 180 or lat_min >= 60 or lon_min >= 60
        or lat_sec >= 60 or lon_sec >= 60
    ):
        return None
    return (
        -(lon_deg + lon_min / 60 + lon_sec / 3600),
        -(lat_deg + lat_min / 60 + lat_sec / 3600),
    )


def _coordinates(text):
    points = []
    for match in _SEPARATED_COORD_RE.finditer(text):
        lat_deg, lat_min, lat_sec, lon_deg, lon_min, lon_sec = match.groups()
        point = _coordinate(
            int(lat_deg), int(lat_min), lat_sec,
            int(lon_deg), int(lon_min), lon_sec,
        )
        if point is not None:
            points.append((match.start(), point))
    for match in _COMPACT_COORD_RE.finditer(text):
        latitude, longitude = match.groups()
        lat_whole, *lat_fraction = re.split(r"[.,]", latitude)
        lon_whole, *lon_fraction = re.split(r"[.,]", longitude)
        lat_sec_text = lat_whole[4:] + (("." + lat_fraction[0]) if lat_fraction else "")
        lon_degree_digits = len(lon_whole) - 4
        lon_sec_text = lon_whole[lon_degree_digits + 2:] + (
            ("." + lon_fraction[0]) if lon_fraction else ""
        )
        point = _coordinate(
            int(lat_whole[:2]), int(lat_whole[2:4]), lat_sec_text,
            int(lon_whole[:lon_degree_digits]), int(lon_whole[lon_degree_digits:lon_degree_digits + 2]),
            lon_sec_text,
        )
        if point is not None:
            points.append((match.start(), point))
    unique = []
    for _, point in sorted(points):
        if not any(abs(point[0] - prior[0]) < 1e-10 and abs(point[1] - prior[1]) < 1e-10 for prior in unique):
            unique.append(point)
    return unique


def _positioned_lines(page):
    runs = []

    def collect(text, _cm, tm, _font, font_size):
        for index, line in enumerate(text.splitlines()):
            if line.strip():
                runs.append((tm[5] - index * font_size * 1.15, tm[4], line.strip()))

    page.extract_text(visitor_text=collect)
    rows = []
    for y, x, text in sorted(runs, key=lambda run: -run[0]):
        if not rows or abs(rows[-1]["y"] - y) > 1.0:
            rows.append({"y": y, "_y_total": y, "_y_count": 1, "segments": []})
        else:
            row = rows[-1]
            row["_y_total"] += y
            row["_y_count"] += 1
            row["y"] = row["_y_total"] / row["_y_count"]
        rows[-1]["segments"].append((x, text))
    for row in rows:
        row["segments"].sort(key=lambda segment: segment[0])
        row["text"] = " ".join(text for _, text in row["segments"])
        del row["_y_total"], row["_y_count"]
    return rows


def _vertical_limits(positioned_lines, code):
    headers = []
    for index, row in enumerate(positioned_lines):
        normalized = re.sub(r"\s+", "", row["text"]).upper()
        match = _POSITION_ENTRY_RE.search(normalized)
        if match:
            headers.append((index, f"SC-{match.group(1).upper()}{match.group(2)}"))
    header_indices = [index for index, found_code in headers if found_code == code]
    if len(header_indices) != 1:
        raise ValueError(f"No se pudo ubicar la columna vertical de {code}")
    start = header_indices[0]
    end = next((index for index, _ in headers if index > start), len(positioned_lines))
    tokens = []
    for row in positioned_lines[start + 1:end]:
        column_text = " ".join(
            text for x, text in row["segments"] if 250 <= x <= 370
        )
        tokens.extend(match.group(0).strip() for match in _ALTITUDE_RE.finditer(column_text))
    if len(tokens) < 2:
        raise ValueError(f"Límites verticales incompletos para {code}")
    upper = "; ".join(tokens[::2])
    lower = "; ".join(tokens[1::2])
    if not upper or not lower:
        raise ValueError(f"Límites verticales incompletos para {code}")
    return lower, upper


def _circle_radius(block, code):
    candidates = list(re.finditer(r"círculo|circulo|circle|radio", block, re.I))
    for candidate in candidates:
        clause = block[candidate.start():candidate.start() + 160]
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(NM|KM|M)\b", clause, re.I)
        if match:
            value = float(match.group(1).replace(",", "."))
            unit = match.group(2).upper()
            return value * {"NM": 1852, "KM": 1000, "M": 1}[unit]
    raise ValueError(f"No se pudo interpretar el radio de {code}")


def _entry_blocks(reader):
    for page_number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        printed_page = re.search(r"ENR\s*5\.1\s*-\s*(\d+)", text, re.I)
        if not printed_page or int(printed_page.group(1)) < 5:
            continue
        lines = text.splitlines()
        headers = [
            (index, f"SC-{match.group(1).upper()}{match.group(2)}")
            for index, line in enumerate(lines)
            if (match := _ENTRY_RE.match(line))
        ]
        positions = _positioned_lines(page)
        for index, (start, code) in enumerate(headers):
            end = headers[index + 1][0] if index + 1 < len(headers) else len(lines)
            yield code, page_number, "\n".join(lines[start:end]), positions


def _reported_entry(code, page, form, status, lower, upper, **details):
    return dict(
        code=code,
        document_page=str(page),
        geometry_type=form,
        status=status,
        lower_limit=lower,
        upper_limit=upper,
        **details,
    )


def transformar(path, area, aip_margin_m):
    """Interpreta ENR 5.1 y selecciona zonas que alcanzan el AOI ampliado."""
    if (
        isinstance(aip_margin_m, bool)
        or not isinstance(aip_margin_m, (int, float))
        or not isfinite(aip_margin_m)
        or aip_margin_m < 0
    ):
        raise ValueError("aip_margin_m debe ser un número no negativo")
    reader = PdfReader(path)
    area_m = transform(_TO_METRIC, area)
    selection_area = area_m.buffer(aip_margin_m)
    records = []
    report_entries = []
    explicit_exceptions = []
    counts = Counter()
    seen_codes = set()

    for code, page, block, positioned in _entry_blocks(reader):
        if code in seen_codes:
            raise ValueError(f"Registro AIP duplicado: {code}")
        seen_codes.add(code)
        counts[code[3]] += 1
        lower, upper = _vertical_limits(positioned, code)
        coords = _coordinates(block)

        if code == "SC-P51" and not coords:
            reason = _NO_COORDINATE_EXCEPTIONS[code]
            explicit_exceptions.append(dict(code=code, reason=reason))
            report_entries.append(_reported_entry(
                code, page, "polígono_no_reconstruible", "excepcion_sin_geometria",
                lower, upper, reason=reason,
            ))
            continue

        if code in _UNSUPPORTED_FORMS:
            if not coords:
                reason = _NO_COORDINATE_EXCEPTIONS.get(code)
                if reason is None:
                    raise ValueError(f"Forma no soportada sin coordenadas ni excepción: {code}")
                explicit_exceptions.append(dict(code=code, reason=reason))
                report_entries.append(_reported_entry(
                    code, page, _UNSUPPORTED_FORMS[code], "no_soportada_lejana",
                    lower, upper, reason=reason,
                ))
                continue
            distances = [
                transform(_TO_METRIC, Point(point)).distance(area_m)
                for point in coords
            ]
            nearest = min(distances)
            if nearest < _UNSUPPORTED_DISTANCE_LIMIT_M:
                raise ValueError(
                    f"Forma no soportada {code}: coordenada legible a {nearest:.1f} m del AOI"
                )
            report_entries.append(_reported_entry(
                code, page, _UNSUPPORTED_FORMS[code], "no_soportada_lejana",
                lower, upper, nearest_coordinate_distance_m=round(nearest, 1),
            ))
            continue

        is_circle = re.search(r"círculo|circulo|circle|radio", block, re.I)
        geometry_reordered = False
        if is_circle:
            if not coords:
                raise ValueError(f"Círculo sin centro legible: {code}")
            center = coords[0]
            radius_m = _circle_radius(block, code)
            ring = [
                _GEOD.fwd(center[0], center[1], bearing, radius_m)[:2]
                for bearing in range(360)
            ]
            ring.append(ring[0])
            geometry = Polygon(ring)
            geometry_type = "circle"
        elif len(coords) >= 3:
            geometry = Polygon(coords)
            geometry_reordered = False
            if not geometry.is_valid:
                centroid_x = sum(point[0] for point in coords) / len(coords)
                centroid_y = sum(point[1] for point in coords) / len(coords)
                ordered = sorted(
                    coords,
                    key=lambda point: atan2(point[1] - centroid_y, point[0] - centroid_x),
                )
                candidate = Polygon(ordered)
                if not candidate.is_valid or len(set(candidate.exterior.coords[:-1])) != len(set(coords)):
                    raise ValueError(f"Polígono AIP inválido: {code}")
                geometry = candidate
                geometry_reordered = True
            center = None
            radius_m = None
            geometry_type = "polygon"
        else:
            raise ValueError(f"No se pudo interpretar la geometría de {code}")

        geometry_m = transform(_TO_METRIC, geometry)
        if selection_area.intersects(geometry_m):
            status = "incluida"
            record = dict(
                provider_id=code,
                code=code,
                geometry=mapping(geometry),
                lower_limit=lower,
                upper_limit=upper,
                conditions=block.strip(),
                document_page=str(page),
                original_record=block.strip(),
                geometry_type=geometry_type,
            )
            if geometry_type == "circle":
                record.update(center=list(center), radius_m=radius_m)
            else:
                record["vertices"] = len(coords)
            records.append(record)
        else:
            status = "fuera_del_margen"
        report_entries.append(_reported_entry(
            code, page, geometry_type, status, lower, upper,
            center=list(center) if center is not None else None,
            radius_m=radius_m,
            vertices=len(coords) if geometry_type == "polygon" else None,
            geometry_reordered=geometry_reordered if geometry_type == "polygon" else False,
        ))

    if not counts or any(counts[kind] == 0 for kind in "PRD"):
        raise ValueError(f"Inventario ENR 5.1 incompleto: {dict(counts)}")
    selected_codes = sorted(record["code"] for record in records)
    report = dict(
        section="ENR 5.1",
        document_pages=sorted({entry["document_page"] for entry in report_entries}, key=int),
        aip_margin_m=aip_margin_m,
        selection_crs="EPSG:32719",
        unsupported_near_limit_m=_UNSUPPORTED_DISTANCE_LIMIT_M,
        counts={"SC-P": counts["P"], "SC-R": counts["R"], "SC-D": counts["D"]},
        total_records=sum(counts.values()),
        selected_codes=selected_codes,
        records=report_entries,
        explicit_exceptions=explicit_exceptions,
    )
    return records, report


if __name__ == "__main__":
    from core.aerial_etl import main  # import local para evitar import circular
    main("A3")
