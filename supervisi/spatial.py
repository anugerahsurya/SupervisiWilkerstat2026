"""Pemeriksaan geometri Wilkerstat. Fitur dan koordinat sumber tidak diubah."""
from collections import defaultdict
from math import isfinite

import shapely
from pyproj import CRS, Geod
from shapely.geometry import Polygon, shape
from shapely.validation import explain_validity


GEOD = Geod(ellps="WGS84")
TOPO = "Modul II.2–3 · Juknis, hlm. PDF 229–236"
POINT = "Modul III.1–2 · Juknis, hlm. PDF 330–335"
# Mengabaikan selisih representasi desimal hingga sekitar 0,1 mm.
EPS = 1e-9


def rule(code, title, source, detail):
    return dict(id=code, title=title, source=source, detail=detail, status="sesuai", issues=[])


def issue(check, obj, detail):
    check["issues"].append({"object": obj, "detail": detail})
    check["status"] = "temuan"


def location(g):
    pt = g.representative_point()
    return f"{pt.y:.7f}, {pt.x:.7f} (lintang, bujur)"


def area_text(g):
    # Jumlah per bagian untuk menghindari pembatalan tanda antar-poligon.
    orient = shapely.geometry.polygon.orient
    def calc(part):
        if part.geom_type == "Polygon":
            return abs(GEOD.geometry_area_perimeter(orient(part))[0])
        return sum(calc(sub) for sub in getattr(part, "geoms", ()))
    square_metres = calc(g)
    if square_metres >= 1_000_000:
        return f"{square_metres / 1_000_000:.2f} km²".replace(".", ",")
    return f"{square_metres:.4g} m²".replace(".", ",")


def properties(feature):
    value = feature.get("properties") if isinstance(feature, dict) else None
    return value if isinstance(value, dict) else {}


def object_name(feature, index, kind):
    props = properties(feature)
    key = "idsubsls" if kind == "Poligon" else "assignment_id"
    value = props.get(key)
    return f"{value} (fitur {index + 1})" if value else f"{kind} #{index + 1}"


def crs_valid(fc):
    if fc.get("crs") is None:
        return True
    try:
        name = fc["crs"]["properties"]["name"]
        return CRS.from_user_input(name).equals(CRS.from_epsg(4326), ignore_axis_order=True)
    except (KeyError, TypeError, ValueError, RuntimeError):
        return False


def coord_pair(value, parse_text=False):
    if not isinstance(value, (tuple, list)) or len(value) < 2:
        return None
    try:
        if any(isinstance(n, bool) or (not parse_text and not isinstance(n, (float, int))) for n in value[:2]):
            return None
        x, y = map(float, value[:2])
        if isfinite(x) and isfinite(y) and abs(x) <= 180 and abs(y) <= 90:
            return x, y
    except (OverflowError, TypeError, ValueError):
        pass
    return None


def same(a, b):
    return abs(a[0] - b[0]) <= EPS and abs(a[1] - b[1]) <= EPS


def polygon_geometry(feature):
    geom = feature.get("geometry") if isinstance(feature, dict) else None
    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("Geometri kosong atau bertipe selain Polygon/MultiPolygon.")
    parts = geom.get("coordinates")
    if geom["type"] == "Polygon":
        parts = [parts]
    if not isinstance(parts, (list, tuple)) or not parts:
        raise ValueError("Susunan koordinat poligon kosong atau tidak sesuai.")
    dup = False
    for part in parts:
        if not isinstance(part, (list, tuple)) or not part:
            raise ValueError("Bagian poligon kosong.")
        for ring in part:
            if not isinstance(ring, (list, tuple)) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("Cincin harus tertutup dan berisi minimal empat posisi.")
            coords = [coord_pair(c) for c in ring[:-1]]
            if None in coords:
                raise ValueError("Koordinat bukan bilangan geografis yang valid.")
            dup |= len(set(coords)) != len(coords)
    poly = shape(geom)
    if poly.is_empty or not poly.is_valid:
        raise ValueError("Geometri kosong." if poly.is_empty else explain_validity(poly))
    return poly, dup


def spatial_checks(polygons, points):
    geo = rule("II.G", "Validitas geometri poligon", TOPO, "Tipe, koordinat WGS 84, penutupan cincin, geometri kosong, dan validitas GEOS.")
    vertices = rule("II.V", "Simpul poligon berulang", TOPO, "Perulangan simpul dalam satu cincin diperiksa dengan mengecualikan simpul penutup.")
    overlap = rule("II.O", "Tumpang tindih antarpoligon", TOPO, "Setiap pasangan beririsan luas positif diperiksa, termasuk lintas desa. Sentuhan garis batas diperbolehkan.")
    duplicate = rule("II.D", "Geometri poligon duplikat", TOPO, "Membandingkan kesamaan spasial dua fitur, termasuk urutan simpul yang berbeda.")
    gaps = rule("II.C", "Celah tertutup antarpoligon", TOPO, "Memeriksa ruang kosong yang terkepung oleh gabungan seluruh poligon. Cakupan batas luar memerlukan peta pembanding.")
    crs = rule("II.S", "Sistem koordinat kedua layer", "Juknis, hlm. PDF 238", "GeoJSON tanpa deklarasi CRS dibaca sebagai WGS 84 dalam urutan bujur, lintang.")
    pt_geom = rule("III.G", "Validitas geometri titik", POINT, "Memeriksa tipe Point serta rentang dan kelengkapan koordinat.")
    move = rule("III.P", "Konsistensi pergeseran titik", POINT, "Membandingkan posisi awal dan akhir dengan flag_position, serta koordinat akhir dengan geometri. Toleransi numerik 0,000000001 derajat.")
    flag = rule("III.R", "Titik berstatus luar batas", POINT, "Menelusuri setiap titik yang masih memiliki flag_repair = 1.")
    inside = rule("III.B", "Posisi titik terhadap Sub-SLS", POINT, "Mencocokkan geometri titik dengan idsubsls_edited pada poligon yang diinput. Titik pada garis batas atau di beberapa poligon memerlukan konfirmasi.")
    checks = [crs, geo, vertices, overlap, duplicate, gaps, pt_geom, move, flag, inside]
    poly_ok, pt_ok = crs_valid(polygons), crs_valid(points)
    for ok, name in [(poly_ok, "Layer poligon"), (pt_ok, "Layer titik")]:
        if not ok:
            issue(crs, name, "Deklarasi CRS tidak terbaca sebagai WGS 84. Periksa atau reproyeksikan layer di QGIS.")

    polys, names, ids, periods = [], [], [], set()
    for i, feature in enumerate(polygons["features"]):
        label = object_name(feature, i, "Poligon")
        try:
            poly, dup = polygon_geometry(feature)
        except (TypeError, ValueError, IndexError, AttributeError, shapely.errors.GEOSException) as exc:
            issue(geo, label, f"Geometri tidak dapat digunakan. {exc}")
            continue
        if dup:
            issue(vertices, label, "Ada koordinat simpul berulang dalam satu cincin.")
        props = properties(feature)
        polys.append(poly)
        names.append(label)
        ids.append(str(props.get("idsubsls") or ""))
        periods.add(str(props.get("periode") or "tanpa periode"))
    tree = shapely.STRtree(polys)
    usable = bool(polys) and poly_ok
    if usable:
        left, right = tree.query(polys, predicate="intersects")
        for i, j in zip(left, right):
            if i >= j:
                continue
            a, b = polys[i], polys[j]
            if a.touches(b):
                continue
            shared = a.intersection(b)
            if shared.area:
                pair = f"{names[i]} / {names[j]}"
                issue(overlap, pair, f"Irisan {area_text(shared)} di sekitar {location(shared)}.")
                if a.equals(b):
                    issue(duplicate, pair, "Kedua fitur menutupi wilayah yang sama persis.")
        if not geo["issues"]:
            cover = shapely.union_all(polys)
            components = [cover] if cover.geom_type == "Polygon" else cover.geoms
            candidates = [Polygon(ring) for p in components for ring in p.interiors]
            if candidates:
                void = shapely.union_all(candidates).difference(cover)
                empty_parts = [void] if void.geom_type == "Polygon" else void.geoms
                for hole in empty_parts:
                    if hole.is_empty or hole.area == 0:
                        continue
                    adjacent = tree.query(hole, predicate="intersects")
                    nearby = ", ".join(names[k] for k in adjacent)
                    issue(gaps, nearby or "Area tertutup", f"Ruang kosong {area_text(hole)} di sekitar {location(hole)}. Cocokkan dengan batas resmi atau enklave.")
                if gaps["issues"]:
                    gaps["status"] = "konfirmasi"
    if not usable or geo["issues"]:
        for r in [vertices, overlap, duplicate, gaps]:
            r["detail"] += " Cakupan terbatas karena geometri atau CRS poligon."
            if not r["issues"]:
                r["status"] = "tidak_dinilai"

    features = points["features"]
    coords, indices = [], []
    spatial_checked = 0
    missing_pairs = 0
    inconsistent = 0
    def eval_points():
        nonlocal spatial_checked
        if not coords:
            return
        xs, ys = zip(*coords)
        pts = shapely.points(xs, ys)
        hits = defaultdict(list)
        for local, polyidx in zip(*tree.query(pts, predicate="intersects")):
            hits[local].append(polyidx)
        for local, row in enumerate(indices):
            feature = features[row]
            props = properties(feature)
            expected = str(props.get("idsubsls_edited") or "")
            label = object_name(feature, row, "Titik")
            matches = hits[local]
            spatial_checked += 1
            actual = ", ".join(ids[k] or names[k] for k in matches)
            if not expected:
                reason = "idsubsls_edited kosong."
            elif not matches:
                reason = "Titik berada di luar semua poligon yang dapat diuji."
            elif len(matches) > 1:
                reason = f"Titik mengenai beberapa poligon ({actual})."
            elif polys[matches[0]].touches(pts[local]):
                reason = f"Titik tepat pada garis batas {actual}."
            elif expected != actual:
                reason = f"Titik masuk Sub-SLS {actual}."
            else:
                continue
            x, y = coords[local]
            issue(inside, label, f"{reason} ID edited {expected or 'kosong'}. Posisi {y:.7f}, {x:.7f}.")
        coords.clear()
        indices.clear()

    for i, feature in enumerate(features):
        label = object_name(feature, i, "Titik")
        props = properties(feature)
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        point = coord_pair(geometry.get("coordinates")) if isinstance(geometry, dict) and geometry.get("type") == "Point" else None
        if point is None:
            issue(pt_geom, label, "Geometri titik kosong, salah tipe, atau koordinat berada di luar rentang WGS 84.")
        elif usable and pt_ok:
            coords.append(point)
            indices.append(i)
            if len(coords) == 8192:
                eval_points()
        old = coord_pair([props.get("longitude_origin"), props.get("latitude_origin")], True)
        new = coord_pair([props.get("longitude_edited"), props.get("latitude_edited")], True)
        position = str(props.get("flag_position"))
        messages = []
        mismatch = False
        if old is None or new is None:
            missing_pairs += 1
            messages.append("Pasangan koordinat asal/akhir tidak lengkap atau di luar rentang WGS 84.")
        elif position not in ("0", "1"):
            mismatch = True
            messages.append("flag_position tidak dapat dibandingkan (nilai wajib 0 atau 1).")
        elif (position == "1") == same(old, new):
            mismatch = True
            messages.append(f"flag_position {position} tetapi koordinat asal dan akhir " + ("sama." if position == "1" else "berbeda."))
        if pt_ok and point is not None and new is not None and not same(point, new):
            mismatch = True
            messages.append(f"Posisi geometri ({point[1]:.7f}, {point[0]:.7f}) berbeda dari atribut edited ({new[1]:.7f}, {new[0]:.7f}).")
        inconsistent += int(mismatch)
        if messages:
            issue(move, label, " ".join(messages))
        repair = str(props.get("flag_repair"))
        if repair == "1":
            issue(flag, label, "flag_repair masih 1. Cocokkan dengan peta lapangan dan bukti posisi sebelum menutup temuan.")
        elif repair != "0":
            issue(flag, label, "flag_repair kosong atau di luar kode 0/1.")
    eval_points()
    move["detail"] += f" {missing_pairs} fitur tanpa pasangan koordinat yang dapat dibandingkan; {inconsistent} fitur dengan ketidakcocokan terukur."
    if missing_pairs and not inconsistent:
        move["status"] = "konfirmasi"
    if not features:
        for check in (pt_geom, move, flag):
            check["status"] = "tidak_dinilai"
            check["detail"] += " Layer titik kosong."
    if not polygons["features"]:
        geo["status"] = "tidak_dinilai"
        geo["detail"] += " Layer poligon kosong."
    if not spatial_checked:
        inside["status"] = "tidak_dinilai"
    elif periods != {"2025_2"} or geo["issues"] or pt_geom["issues"] or inside["issues"]:
        inside["status"] = "konfirmasi"
    inside["detail"] += f" Sebanyak {spatial_checked} titik diuji. Periode poligon: {', '.join(sorted(periods)) or 'tidak diketahui'}. Verifikasi hasil dengan peta lapangan 2025_2 yang telah disesuaikan untuk perubahan batas murni."
    return checks
