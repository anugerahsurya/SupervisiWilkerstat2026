"""Penyimpanan hasil, catatan, dan referensi pada PostgreSQL Supabase."""
import gzip
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import psycopg
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env", encoding="utf-8-sig")
REFERENCES = {
    "msubsls_26_1_1300.xlsx": HERE.parent / "Referensi" / "msubsls_26_1_1300.xlsx",
    "hirarki_sls_26_1_1300.xlsx": HERE.parent / "Referensi" / "hirarki_sls_26_1_1300.xlsx",
    "monev_1308.json": HERE / "monev_1308.json",
}


def connect():
    url = os.environ.get("WILKERSTAT_DATABASE_URL")
    if not url:
        raise RuntimeError("Isi WILKERSTAT_DATABASE_URL di supervisi/.env untuk menghubungkan aplikasi.")
    return psycopg.connect(url, sslmode="require", connect_timeout=12)


def initialize():
    with connect() as db:
        sql = HERE.parent / "supabase/migrations/202611110001_supervisi.sql"
        db.execute(sql.read_text(encoding="utf-8-sig"))
        for name, path in REFERENCES.items():
            if path.is_file():
                db.execute("""insert into wilkerstat.shared_files values (%s,%s)
                              on conflict(name) do nothing
""", (name, path.read_bytes()))
            else:
                row = db.execute("select contents from wilkerstat.shared_files where name=%s", (name,)).fetchone()
                if row:
                    path.parent.mkdir(exist_ok=True, parents=True)
                    path.write_bytes(row[0])


def store_run(key, path):
    compressed = gzip.compress(path.read_bytes(), compresslevel=3)
    with connect() as db:
        db.execute("insert into wilkerstat.runs(id,snapshot) values (%s,%s) on conflict(id) do nothing",
                   (key, compressed))


def restore_run(key, path):
    with connect() as db:
        row = db.execute("select snapshot from wilkerstat.runs where id=%s", (key,)).fetchone()
    if row is None:
        return False
    path.parent.mkdir(exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(gzip.decompress(row[0]))
    try:
        os.replace(tmp.name, path)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    return True


def default_run(key=None):
    with connect() as db:
        if key:
            db.execute("""insert into wilkerstat.settings values ('baseline',%s)
                          on conflict(name) do update set value=excluded.value""",(key,))
            return key
        row = db.execute("select value from wilkerstat.settings where name='baseline'").fetchone()
        return row[0] if row else None


def notes(key):
    with connect() as db:
        return dict(db.execute("select field,value from wilkerstat.notes where run_id=%s",(key,)))


def save_note(key, field, value):
    with connect() as db:
        db.execute("""insert into wilkerstat.notes values (%s,%s,%s)
                      on conflict(run_id,field) do update set value=excluded.value""",
                   (key, field, value))
