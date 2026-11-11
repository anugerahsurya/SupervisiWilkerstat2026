"""Pembandingan lokal dengan salinan bertanggal daftar SLS pada dashboard Monev."""
import json
from pathlib import Path

SNAPSHOT = Path(__file__).with_name("monev_1308.json")


def monitoring(layers, rules):
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
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
        return [review, flags]
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
    def n(v):
        return f"{v:,}".replace(",", ".")
    flags["detail"] += (f" Khusus 1308: {n(target)} titik unggahan masuk cakupan 43 ID dalam salinan Monev; "
                        f"{n(valid)} bernilai flag_repair = 0. {n(missing)} fitur tanpa kunci 16 digit yang dapat dibaca. "
                        "Angka dihitung dari berkas titik yang sedang diperiksa.")
    flags["status"] = ("temuan" if flags["issues"] else "tidak_dinilai" if not target
                       else "konfirmasi" if missing else "sesuai")
    return [review, flags]
