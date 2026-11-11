"""Server lokal pemeriksaan Wilkerstat. Jalankan dari direktori mana saja."""
import base64
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from waitress import serve
import storage
from narration import TOKEN, marked, narrative, plain

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
REFERENCES = WORKSPACE / "Referensi"
RESULTS = HERE / "hasil"
FILES = {"polygon": WORKSPACE / "Prod_SLS_202611308.geojson",
         "point": WORKSPACE / "1308_landmark_bangunan_se.geojson"}
LIMIT = 512 * 1024 * 1024
app = Flask(__name__, static_folder=str(HERE / "static"), static_url_path="/static")
app.config.update(MAX_CONTENT_LENGTH=LIMIT, TRUSTED_HOSTS=["localhost", "127.0.0.1"])
app.jinja_env.filters["columns"] = marked
worker = threading.Lock()
LABELS = {"sesuai": "Sesuai", "temuan": "Temuan", "konfirmasi": "Perlu konfirmasi",
          "tidak_dinilai": "Belum dinilai"}


def read_layer(stream, role):
    label = "Poligon" if role == "polygon" else "Titik"
    try:
        data = json.load(TextIOWrapper(stream, encoding="utf-8-sig"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{label}: berkas bukan JSON yang valid.") from exc
    if (not isinstance(data, dict) or data.get("type") != "FeatureCollection"
            or not isinstance(data.get("features"), list) or not data["features"]):
        raise ValueError(f"{label}: diperlukan GeoJSON FeatureCollection berisi fitur.")
    types = {"Polygon", "MultiPolygon"} if role == "polygon" else {"Point"}
    seen = set()
    for i, f in enumerate(data["features"], 1):
        if not isinstance(f, dict) or f.get("type") != "Feature":
            raise ValueError(f"{label}: objek ke-{i} bukan Feature.")
        if f.get("properties") is None:
            f["properties"] = {}
        if not isinstance(f["properties"], dict):
            raise ValueError(f"{label}: properties pada objek ke-{i} harus berupa objek JSON.")
        geom = f.get("geometry")
        if geom is not None:
            if not isinstance(geom, dict) or not isinstance(geom.get("type"), str):
                raise ValueError(f"{label}: geometri objek ke-{i} tidak dapat dibaca.")
            seen.add(geom["type"])
    if seen and not seen.intersection(types):
        raise ValueError(f"{label}: jenis geometri tidak sesuai ({', '.join(sorted(seen))}).")
    return data


def db_file(key):
    if not re.fullmatch('[0-9a-f]{32}', key):
        abort(404)
    path = RESULTS / (key + ".sqlite")
    if not path.is_file() and not storage.restore_run(key, path):
        abort(404)
    return path


def summary(key):
    with closing(sqlite3.connect(db_file(key))) as db:
        return present(json.loads(db.execute("SELECT data FROM summary").fetchone()[0]))


def present(result):
    result["column_pattern"] = TOKEN.pattern
    result["notes"] = storage.notes(result["run_id"])
    for rule in result["rules"]:
        rule["title"] = narrative(rule["title"])
        rule["detail"] = narrative(rule["detail"])
        for item in rule["issues"]:
            item["detail"] = narrative(item["detail"])
    return result


def export_names(layers, names):
    rows = []
    for role, pattern in (("polygon", "final_sls_{}_2026-1.geojson"),
                          ("point", "final_landmark_{}_se_2026.geojson")):
        codes = {str(f["properties"].get("kdprov", "")) + str(f["properties"].get("kdkab", ""))
                 for f in layers[role]["features"]}
        if len(codes) == 1 and re.fullmatch(r"[0-9]{4}", next(iter(codes))):
            expected = pattern.format(next(iter(codes)))
            if names[role] != expected:
                rows.append(dict(object=names[role], detail=f"Nama berkas akhir untuk GS sesuai materi: {expected}."))
        else:
            rows.append(dict(object=names[role], detail="Kode provinsi/kabupaten tidak lengkap atau tidak tunggal. Pastikan ekspor akhir dibuat per kabupaten/kota."))
    return dict(id="ekspor-nama", title="Penamaan berkas akhir untuk GS",
                source="Juknis · hlm. PDF 118, 238 dan 310",
                status="temuan" if rows else "sesuai",
                detail="Penamaan diperiksa untuk penyerahan berkas akhir. Berkas kerja dapat memiliki nama lain.",
                issues=rows)


def evaluate(key, layers, names):
    from audit import audit
    rules = audit(layers["polygon"], layers["point"], REFERENCES)
    from monitoring import monitoring
    rules.extend(monitoring(layers, rules))
    rules.append(export_names(layers, names))
    result = {"run_id": key, "files": names,
              "counts": {k: len(v["features"]) for k, v in layers.items()},
              "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
              "rules": rules}
    RESULTS.mkdir(exist_ok=True)
    tmp = RESULTS / (uuid.uuid4().hex + ".tmp")
    try:
        with closing(sqlite3.connect(tmp)) as db:
            db.executescript("""
                CREATE TABLE summary(data TEXT);
                CREATE TABLE findings(rule TEXT, seq INTEGER, object TEXT, detail TEXT,
                                      PRIMARY KEY(rule,seq)) WITHOUT ROWID;
            """)
            for rule in rules:
                rows = rule["issues"]
                db.executemany("INSERT INTO findings VALUES(?,?,?,?)",
                               ((rule["id"], i, str(r["object"]), str(r["detail"]))
                                for i, r in enumerate(rows)))
                rule["issue_count"] = len(rows)
                rule["issues"] = rows[:40]
            db.execute("INSERT INTO summary VALUES(?)", (json.dumps(result, ensure_ascii=False),))
            db.commit()
        storage.store_run(key, tmp)
        os.replace(tmp, RESULTS / (key + ".sqlite"))
    finally:
        tmp.unlink(missing_ok=True)
    return present(result)


def current_key():
    inputs = [*FILES.values(), *sorted(REFERENCES.glob("*.xlsx")), *[HERE / name for name in ("audit.py","spatial.py","monitoring.py")], HERE / "monev_1308.json"]
    signature = [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in inputs]
    return hashlib.sha256(repr(signature).encode()).hexdigest()[:32]


def current():
    if not all(path.exists() for path in FILES.values()):
        key = storage.default_run()
        if not key:
            abort(404, "Pilih berkas poligon dan titik untuk memulai pemeriksaan.")
        return summary(key)
    key = current_key()
    path = RESULTS / (key + ".sqlite")
    if not path.exists():
        with worker:
            if not path.exists():
                layers = {}
                for role, path_in in FILES.items():
                    with path_in.open("rb") as f:
                        layers[role] = read_layer(f, role)
                result = evaluate(key, layers, {k: v.name for k, v in FILES.items()})
                storage.default_run(key)
                return result
    return summary(key)


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/current")
def baseline():
    return jsonify(current())


@app.post("/api/audit")
def upload():
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        abort(403)
    if not worker.acquire(blocking=False):
        return jsonify(error="Pemeriksaan lain sedang berjalan. Coba lagi sesaat lagi."), 409
    try:
        layers, names = {}, {}
        for role in FILES:
            file = request.files.get(role)
            if not file or not file.filename:
                raise ValueError("Pilih satu berkas poligon dan satu berkas titik.")
            layers[role] = read_layer(file.stream, role)
            names[role] = file.filename.replace(chr(92), "/").split("/")[-1]
        return jsonify(evaluate(uuid.uuid4().hex, layers, names))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    finally:
        worker.release()


@app.get("/api/runs/<key>")
def previous_run(key):
    return jsonify(summary(key))


@app.put("/api/runs/<key>/notes/<field>")
def update_note(key, field):
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        abort(403)
    db_file(key)
    body = request.get_json()
    if (not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}",field) or not isinstance(body,dict)
            or not isinstance(body.get("value"),str) or len(body["value"]) > 60000):
        abort(400, "Catatan tidak valid atau lebih dari 60.000 karakter.")
    storage.save_note(key, field, body["value"])
    return jsonify(saved=True)


@app.get("/api/runs/<key>/issues/<rule>")
def issues(key, rule):
    offset = max(0, request.args.get("offset", 0, type=int))
    limit = min(250, max(1, request.args.get("limit", 50, type=int)))
    q = request.args.get("q", "").strip().lower()
    with closing(sqlite3.connect(db_file(key))) as db:
        where, args = "rule=?", [rule]
        if q:
            where += " AND (instr(lower(object),?) OR instr(lower(detail),?))"
            args.extend([q, q])
        total = db.execute("SELECT count(*) FROM findings WHERE " + where, args).fetchone()[0]
        rows = db.execute("SELECT object,detail FROM findings WHERE " + where
                          + " ORDER BY seq LIMIT ? OFFSET ?", [*args, limit, offset])
        return jsonify(total=total, issues=[{"object": obj, "detail": narrative(d)} for obj, d in rows])


def csv_text(values):
    buf = io.StringIO(newline="")
    csv.writer(buf).writerow("'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@"))
                             else v for v in values)
    return buf.getvalue()


def csv_rows(key, rules):
    yield "\ufeff" + csv_text(["Uji", "Indikator", "Status", "Acuan", "Objek", "Keterangan"])
    with closing(sqlite3.connect(db_file(key))) as db:
        for r in rules:
            chunk = []
            for obj, detail in db.execute("SELECT object,detail FROM findings WHERE rule=? ORDER BY seq", (r["id"],)):
                chunk.append(csv_text([r["id"], r["title"], LABELS[r["status"]], r["source"], obj, plain(detail)]))
                if len(chunk) == 256:
                    yield "".join(chunk)
                    chunk.clear()
            if chunk:
                yield "".join(chunk)


@app.get("/api/runs/<key>/findings.csv")
def findings(key):
    return Response(csv_rows(key, summary(key)["rules"]), mimetype="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="rincian-supervisi.csv"'})


@app.get("/api/runs/<key>/report.html")
def report(key):
    from flask import render_template
    font = base64.b64encode((HERE / "static" / "jakarta.ttf").read_bytes()).decode("ascii")
    return render_template("report.html", result=summary(key), labels=LABELS, font=font)


@app.errorhandler(HTTPException)
def http_error(exc):
    msg = "Jumlah ukuran unggahan melebihi 512 MiB." if exc.code == 413 else exc.description
    return jsonify(error=msg), exc.code


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser()
    cli.add_argument("--prepare", action="store_true", help="Periksa kedua GeoJSON dalam folder Pengecekan")
    cli.add_argument("--port", type=int, default=8765)
    args = cli.parse_args()
    storage.initialize()
    if args.prepare:
        result = current()
        print(json.dumps({k: result[k] for k in ("run_id", "counts")}))
    else:
        print(f"Supervisi Wilkerstat: http://127.0.0.1:{args.port}", flush=True)
        serve(app, host="127.0.0.1", port=args.port, threads=5, max_request_body_size=LIMIT+1,
              channel_timeout=600)
