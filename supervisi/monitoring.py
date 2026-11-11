"""Pembandingan lokal dengan salinan bertanggal daftar SLS pada dashboard Monev."""
import json
from pathlib import Path

SNAPSHOT = Path(__file__).with_name("monev_1308.json")


def outside_rule(rows, status, source, scope):
    affected = {row["detail"].split()[2].rstrip(".") for row in rows}
    count = f"{len(rows):,}".replace(",", ".")
    return dict(id="III.R", title="Titik berstatus luar batas",
                source="Modul III.1–2 · Juknis, hlm. PDF 330–335 · " + source,
                status="temuan" if rows else status,
                detail=scope if status == "tidak_dinilai" and not rows else
                scope + f" Sebanyak {count} titik pada {len(affected)} Sub-SLS target memiliki flag_repair = 1.",
                issues=rows)


def monitoring(layers, rules):
    if SNAPSHOT.is_file():
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    else:
        from storage import connect
        with connect() as db:
            row = db.execute("select contents from wilkerstat.shared_files where name=%s",
                             (SNAPSHOT.name,)).fetchone()
        if not row:
            raise ValueError("Daftar Sub-SLS target Monev belum tersedia untuk pemeriksaan ini.")
        snap = json.loads(row[0])
    ids = set(snap["ids"])
    code = snap["kabupaten"]
    source = f"Monev Wilkerstat · {snap['menu']} · salinan {snap['tanggal']} · {snap['sumber']}"
    area = {str(f["properties"].get("kdprov", "")) + str(f["properties"].get("kdkab", ""))
            for f in layers["polygon"]["features"]}
    review = dict(id="monev-daftar", title="Daftar batas murni di Monev dan hierarki",
                  source=source, status="tidak_dinilai", issues=[],
                  detail="Salinan Monev tersedia untuk Kabupaten Lima Puluh Kota (1308).")
    flags = dict(id="monev-titik", title="Titik target perubahan batas murni",
                 source=source, status="tidak_dinilai", issues=[],
                 detail="Cakupan target mengikuti level_6_full_code pada titik dan daftar ID terdaftar di Monev.")
    if code not in area:
        return [review, flags, outside_rule([], "tidak_dinilai", source, review["detail"])]
    local = next(r for r in rules if r["id"] == "I.2b")
    hierarchy = {r["object"] for r in local["issues"] if r["object"].startswith(code)}
    review["status"] = "konfirmasi"
    review["detail"] = (f"Untuk 1308, {len(ids)} ID terdaftar di Monev dan {len(hierarchy)} ID muncul pada daftar Kode 9 hasil pembacaan hierarki. "
                        "Samakan periode, definisi, dan bukti unggah dengan petugas. Tanggal salinan tercantum pada sumber.")
    for sid in sorted(ids | hierarchy):
        if sid not in ids:
            note = "Kode 9 di hierarki, belum ditemukan dalam salinan Monev."
        elif sid not in hierarchy:
            note = "Terdaftar di Monev, tidak muncul pada daftar Kode 9 hasil pembacaan hierarki."
        else:
            note = "Terdaftar pada kedua sumber."
        review["issues"].append(dict(object=sid, detail=note))
    outside = []
    target = valid = missing = 0
    for i, f in enumerate(layers["point"]["features"], 1):
        p = f["properties"]
        key = p.get("level_6_full_code")
        if not isinstance(key, str) or len(key) != 16 or not key.isdigit():
            missing += 1
            continue
        if key not in ids:
            continue
        target += 1
        flag = str(p.get("flag_repair"))
        if flag == "0":
            valid += 1
        else:
            flags["issues"].append(dict(object=str(p.get("assignment_id") or f"Fitur #{i}"),
                                        detail=f"Sub-SLS target {key}. flag_repair = {flag}, target Monev 0."))
            if flag == "1":
                outside.append(flags["issues"][-1])
    def n(v):
        return f"{v:,}".replace(",", ".")
    flags["detail"] += (f" Khusus 1308: {n(target)} titik unggahan masuk cakupan {len(ids)} ID dalam salinan Monev; "
                        f"{n(valid)} bernilai flag_repair = 0. {n(missing)} fitur tanpa kunci 16 digit yang dapat dibaca. "
                        "Angka dihitung dari berkas titik yang sedang diperiksa.")
    flags["status"] = ("temuan" if flags["issues"] else "tidak_dinilai" if not target
                       else "konfirmasi" if missing else "sesuai")
    scope = (f"Pemeriksaan mencakup {n(target)} titik yang kode Sub-SLS asalnya (level_6_full_code) "
             f"tercantum dalam daftar {len(ids)} Sub-SLS Monev.")
    outside_status = "tidak_dinilai" if not target else "konfirmasi" if missing or target != valid + len(outside) else "sesuai"
    return [review, flags, outside_rule(outside, outside_status, source, scope)]
