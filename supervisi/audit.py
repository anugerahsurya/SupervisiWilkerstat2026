"""Pemeriksaan FRS, atribut dan bukti supervisi Wilkerstat SE2026."""
from collections import Counter, defaultdict
from functools import lru_cache

from openpyxl import load_workbook

CODES = dict(kdprov=2, kdkab=2, kdkec=3, kddesa=3, kdsls=4, kdsubsls=2, idsls=14, idsubsls=16)
NAMES = ('nmprov', 'nmkab', 'nmkec', 'nmdesa', 'nmsls')
POINT_FIELDS = {
    'assignment_id': 'teks', 'flag_repair': 'integer', 'flag_position': 'integer',
    'idsubsls_origin': 'teks', 'idsubsls_edited': 'teks',
    'latitude_origin': 'desimal', 'longitude_origin': 'desimal',
    'latitude_edited': 'desimal', 'longitude_edited': 'desimal',
    'no_bang': 'integer', 'kode_bang_value': 'integer', 'kdprov': 'teks',
    'nmprov': 'teks', 'kdkab': 'teks', 'nmkab': 'teks', 'kdkec': 'teks',
    'nmkec': 'teks', 'kddesa': 'teks', 'nmdesa': 'teks', 'idsls': 'teks',
    'nmsls': 'teks', 'sls': 'teks'
}
POLY_LENGTHS = dict(nmprov=50, nmkab=50, nmkec=50, nmdesa=50, nmsls=100,
                    rw_dki=3, nm_gedung=50, posisi=50)
FORM = 'Form supervisi, Modul '
MASTER = 'Master Sub-SLS 2026_1'
HIER = 'Hirarki SLS 2025_2–2026_1'


def number(n):
    return f'{n:,}'.replace(',', '.')


def rule(code, title, source, detail, issues=None, status=None):
    issues = issues or []
    return dict(id=code, title=title, source=source, detail=detail, issues=issues,
                status=status or ('temuan' if issues else 'sesuai'))


def issue(obj, detail):
    return dict(object=str(obj), detail=detail)


def props(feature):
    p = feature.get('properties') if isinstance(feature, dict) else None
    return p if isinstance(p, dict) else {}


def txt(value):
    return value if isinstance(value, str) else ''


def label(p, field, index):
    return txt(p.get(field)).strip() or f'Fitur #{index + 1}'


def is_code(value, width):
    return isinstance(value, str) and len(value) == width and value.isascii() and value.isdigit()


def read_rows(path):
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book.active
        # Some exports declare A1 as their used range despite having thousands of records.
        sheet.reset_dimensions()
        rows = iter(sheet.values)
        headers = next(rows)
        for row in rows:
            yield dict(zip(headers, row))
    finally:
        book.close()


@lru_cache(maxsize=2)
def references(master_path, hierarchy_path, master_mtime, hierarchy_mtime):
    master = {}
    changes = defaultdict(set)
    old_ids = set()
    for row in read_rows(master_path):
        if row['semester'] == '2026_1':
            master[row['idsubsls']] = {k: row.get(k) for k in (*CODES, *NAMES, 'berubah_batas')}
    for row in read_rows(hierarchy_path):
        if row['semester'] == '2026_1':
            if row.get('idsubsls_25_2'):
                old_ids.add(row['idsubsls_25_2'])
            if row.get('idsubsls_26_1'):
                changes[row['idsubsls_26_1']].add((str(row.get('id_perub')), str(row.get('ket_perub'))))
    if not master or not old_ids:
        raise ValueError('Referensi tidak memuat master 2026_1 atau relasi 2025_2.')
    return master, changes, old_ids


def polygon_checks(features, master, changes):
    ids = Counter()
    schema, mismatch, duplicates, absent, targets, code9 = [], [], [], [], [], []
    codes = set()
    coverage = {sid[:4] for sid in (master or {})}
    uncovered = set()
    for i, feature in enumerate(features):
        p = props(feature)
        sid = txt(p.get('idsubsls'))
        obj = label(p, 'idsubsls', i)
        problems = []
        for key, width in CODES.items():
            if not is_code(p.get(key), width):
                problems.append(f'{key} wajib teks {width} digit')
        for key, length in POLY_LENGTHS.items():
            v = p.get(key)
            if key not in p or (key in NAMES and not txt(v).strip()):
                problems.append(f'{key} tidak ada atau kosong')
            elif v is not None and (not isinstance(v, str) or len(v) > length):
                problems.append(f'{key} wajib teks maksimal {length} karakter')
        if 'tingkat' not in p or (p['tingkat'] is not None and type(p['tingkat']) is not int):
            problems.append('tingkat tidak tersedia atau bukan integer')
        joined = ''.join(txt(p.get(k)) for k in ('kdprov','kdkab','kdkec','kddesa','kdsls'))
        if p.get('idsls') != joined or sid != joined + txt(p.get('kdsubsls')):
            problems.append('ID tidak cocok dengan gabungan kode wilayah')
        if p.get('periode') and str(p['periode']) != '2026_1':
            problems.append(f"periode {p['periode']} berbeda dengan target 2026_1")
        if problems:
            schema.append(issue(obj, ' · '.join(problems)))
        if is_code(sid, 16):
            codes.add(sid[:4])
            ids[sid] += 1
        elif is_code(p.get('kdprov'), 2) and is_code(p.get('kdkab'), 2):
            codes.add(p['kdprov'] + p['kdkab'])
        if master is None:
            continue
        if is_code(sid, 16) and sid[:4] not in coverage:
            uncovered.add(sid[:4])
            continue
        if sid not in master:
            mismatch.append(issue(obj, 'ID Sub-SLS tidak ditemukan di master Sumatera Barat 2026_1.'))
            continue
        ref = master[sid]
        delta = [f'{k} = {p.get(k)!r}, master = {ref[k]!r}' for k in (*CODES, *NAMES)
                 if k != 'idsls' and p.get(k) != ref[k]]
        if delta:
            mismatch.append(issue(obj, ' · '.join(delta)))
    for sid, count in ids.items():
        if count > 1:
            duplicates.append(issue(sid, f'{count} fitur poligon menggunakan ID yang sama.'))
    master_scope = {sid for sid in (master or {}) if sid[:4] in codes}
    for sid in sorted(master_scope):
        if sid not in ids:
            absent.append(issue(sid, f"{master[sid]['nmdesa']} · {master[sid]['nmsls']} ada di master dan tidak ditemukan di poligon."))
        pairs = changes.get(sid, set())
        flag = str(master[sid]['berubah_batas'])
        desc = ', '.join(f'{c} ({s})' for c, s in sorted(pairs)) or 'tanpa relasi hirarki'
        if flag == '1':
            targets.append(issue(sid, f'berubah_batas=1 · {desc}. Cocokkan batas hasil edit dengan WS/WSS dan tetangga yang bersinggungan.'))
        if any(c == '9' for c, _ in pairs):
            code9.append(issue(sid, f'Kode 9 di hirarki · berubah_batas={flag}. Periksa bukti perubahan batas murni dan unggah Monev.'))
    result = [
        rule('I.1a','Kode dan atribut poligon',FORM+'I.1 · Materi hlm. 237, 292',
             'Struktur 17 atribut GS. Panjang kunci Sub-SLS 16 digit mengikuti spesifikasi unggah dan master. Atribut khusus diperiksa tipe saat terisi.',schema),
        rule('I.1b','Keunikan ID Sub-SLS',FORM+'I.1 · Materi hlm. 237, 293',
             'Setiap ID Sub-SLS mewakili satu fitur pada peta.',duplicates),
    ]
    available = bool(master_scope)
    reason = '' if available else ' Cakupan kabupaten tidak dapat dicocokkan dengan referensi.'
    if uncovered:
        reason += ' Di luar cakupan referensi: ' + ', '.join(sorted(uncovered)) + '.'
    master_status = None if available else 'tidak_dinilai'
    if available and uncovered and not mismatch:
        master_status = 'konfirmasi'
    result.extend([
        rule('I.1c','Peta terhadap master FRS',FORM+'I.1 · '+MASTER,
             'Kode dan nama per fitur dibandingkan persis dengan rilis 2026 Semester 1.'+reason,
             mismatch, master_status),
        rule('I.1d','Kelengkapan wilayah dalam peta',FORM+'I.1 · '+MASTER+' · Materi hlm. 237, 290',
             f'{number(len(master_scope))} ID di master untuk kabupaten/kota {", ".join(sorted(codes)) or "belum teridentifikasi"}. Uji ini mengasumsikan kiriman satu kabupaten/kota utuh.'+reason,
             absent, ('konfirmasi' if uncovered and not absent else None) if available else 'tidak_dinilai'),
        rule('I.2a','Sub-SLS dengan perubahan batas',FORM+'I.2 · '+MASTER+' · '+HIER+' · Materi hlm. 217–220',
             'Daftar kerja dari penanda berubah_batas=1. Periksa perubahan geometri dengan peta dasar dan dokumen lapangan.'+reason,
             targets, 'konfirmasi' if targets else ('sesuai' if available else 'tidak_dinilai')),
        rule('I.2b','Bukti unggah Monev Kode 9',FORM+'I.2 · '+HIER,
             f'{number(len(code9))} ID berkode 9 pada cakupan master. ' +
             ('Verifikasi unggah di Monev dan cocokkan dengan daftar batas murni.' if code9 else 'Tidak ada kandidat berkode 9 pada cakupan yang terbaca.') +
             (' Satker atensi wajib verifikasi unggah.' if codes & {'1307','1309','1310','1373'} else '') + reason,
             code9, 'konfirmasi' if code9 or codes & {'1307','1309','1310','1373'} else 'tidak_dinilai'),
    ])
    return result


def field_problem(key, kind, p):
    if key not in p:
        return 'absen'
    value = p[key]
    if value is None or (isinstance(value, str) and not value.strip()):
        return 'kosong'
    if kind == 'teks':
        if not isinstance(value, str):
            return 'perlu teks'
        width = CODES.get(key, 16 if key in ('idsubsls_origin', 'idsubsls_edited') else None)
        if width and not is_code(value, width):
            return f'perlu {width} digit'
    elif kind == 'integer':
        if type(value) is not int or not -(2**31) <= value < 2**31:
            return 'perlu integer 32 bit'
        if key.startswith('flag_') and value not in (0, 1):
            return 'harus 0 atau 1'
    elif type(value) not in (float, int) or not (-1e308 <= value <= 1e308):
        return 'perlu angka desimal'
    elif abs(value) > (90 if key.startswith('latitude') else 180):
        return 'di luar rentang koordinat'
    return None


def point_checks(features, old_ids):
    schema, baseline, changed_ids, place, duplicates, numbers = [], [], [], [], [], []
    profiles = {}
    counters = Counter()
    seen = Counter()
    buildings = defaultdict(set)
    place_tested = 0
    for i, f in enumerate(features):
        p = props(f)
        obj = label(p, 'assignment_id', i)
        fields = []
        for key, kind in POINT_FIELDS.items():
            problem = field_problem(key, kind, p)
            if problem:
                fields.append((key, problem))
                counters[key] += 1
        if fields:
            profile = tuple(fields)
            if profile not in profiles:
                grouped = defaultdict(list)
                for key, problem in fields:
                    grouped[problem].append(key)
                profiles[profile] = ' · '.join(', '.join(keys) + ' (' + problem + ')' for problem, keys in grouped.items())
            schema.append(issue(obj, profiles[profile]))
        if txt(p.get('assignment_id')).strip():
            seen[obj] += 1
        origin, edited = txt(p.get('idsubsls_origin')), txt(p.get('idsubsls_edited'))
        if old_ids is not None:
            errors = [f'{key}={p.get(key)!r}' for key in ('idsubsls_origin','idsubsls_edited')
                      if txt(p.get(key)) not in old_ids]
            if errors:
                baseline.append(issue(obj, ', '.join(errors) + ' tidak ditemukan di kolom idsubsls_25_2. Periksa master lama dan peta lapangan.'))
        if origin != edited or not origin:
            changed_ids.append(issue(obj, f'ID asal {origin or "(kosong)"} · ID tempel {edited or "(kosong)"}. Telusuri posisi bangunan dan dasar perubahan.'))
        if is_code(edited, 16):
            fields = ('kdprov','kdkab','kdkec','kddesa')
            if all(is_code(p.get(k), CODES[k]) for k in fields):
                place_tested += 1
                if ''.join(p[k] for k in fields) != edited[:10] or (p.get('idsls') and p['idsls'] != edited[:14]):
                    place.append(issue(obj, f'Kode wilayah pada atribut berbeda dengan ID tempel {edited}.'))
        uid, num = txt(p.get('unique_bang')), p.get('no_bang')
        if uid and origin and type(num) in (str,int) and str(num).isdigit():
            buildings[(origin,str(num).lstrip('0') or '0')].add(uid)
    for obj,count in seen.items():
        if count > 1:
            duplicates.append(issue(obj, f'ID assignment digunakan pada {count} fitur.'))
    for (sid, num), keys in buildings.items():
        if len(keys) > 1:
            numbers.append(issue(sid, f'Nomor bangunan {num} digunakan oleh {len(keys)} unique_bang: ' + ', '.join(sorted(keys))))
    summary = ', '.join(f'{key} ({number(counters[key])})' for key in POINT_FIELDS if counters[key])
    return [
        rule('III.3a','ID asal dan ID tempel',FORM+'III.3 · Materi hlm. 331–335',
             'ID yang berbeda memerlukan penelusuran peta lapangan dan alasan pergeseran.',changed_ids,
             'konfirmasi' if changed_ids else 'sesuai'),
        rule('III.3b','ID terhadap hirarki periode lapangan',FORM+'III.3 · '+HIER+' · Materi hlm. 331',
             'ID asal dan tempel titik ditelusuri di kolom idsubsls_25_2. Relasi yang tidak ditemukan perlu diperiksa pada master lapangan.',
             baseline,'tidak_dinilai' if old_ids is None else ('konfirmasi' if baseline else 'sesuai')),
        rule('III.3c','Kode wilayah pada titik',FORM+'III.3 · Materi hlm. 23, 335',
             f'{number(place_tested)} titik dengan kode lengkap dibandingkan terhadap ID tempel. Atribut yang hilang dirinci di Modul IV.',
             place, None if place_tested else 'tidak_dinilai'),
        rule('IV.1a','Kelengkapan dan tipe 22 atribut titik',FORM+'IV.1 dan tabel 22 atribut · Materi hlm. 335',
             f'{number(len(features))} fitur diperiksa. ' + ('Jumlah fitur bermasalah per atribut: '+summary+'.' if counters else 'Seluruh atribut tersedia dan memenuhi tipe standar.'),
             schema),
        rule('IV.1b','Keunikan assignment_id',FORM+'IV.1 · Materi hlm. 333–335',
             'Setiap assignment harus memiliki ID tersendiri.',duplicates, None if seen else 'tidak_dinilai'),
        rule('IV.1c','Nomor bangunan per Sub-SLS',FORM+'IV.1 · Materi hlm. 333–335',
             'Nomor yang sama ditelusuri pada unique_bang berbeda di Sub-SLS asal. Beberapa assignment dapat merujuk pada satu bangunan. ' +
             f'{number(len(buildings))} pasangan Sub-SLS dan nomor bangunan dapat ditelusuri.',
             numbers, None if buildings else 'tidak_dinilai'),
    ]


MANUAL = [
    ('II.1','Penyelesaian editing peta','II.1 · Materi hlm. 337–338','Catat persentase peta SLS/Sub-SLS dan desa yang selesai per 6 November 2026 sesuai tenggat kontrak serta sisa pekerjaan.'),
    ('II.2','Editing batas berpasangan','II.2 · Materi hlm. 221–236','Periksa riwayat Fix Geometries, penghapusan geometri kosong, dan pasangan SLS bersinggungan dalam desa. Cocokkan kedua sisi dengan WS/WSS.'),
    ('II.3','Bukti uji topologi akhir','II.3 · Materi hlm. 229–236','Minta keluaran Topology Checker QGIS dan hasil perbaikan gap/overlap melalui Mapshaper. Periksa batas terluar dengan layer tetangga.'),
    ('II.4','Unggah dan persetujuan peta digital','II.4 · Materi hlm. 282–305','Catat persentase unggah dan approval GS, jumlah serta ID berstatus Rejected/Invalid, berikut perbaikan yang masih berjalan.'),
    ('III.1','Presisi titik terhadap bukti lapangan','III.1 · Materi hlm. 331–333','Tumpangsusunkan titik asal dan hasil edit dengan WS/WSS dan citra. Konfirmasi posisi bangunan, khususnya di perbatasan serta pasar/mal.'),
    ('III.2','Peta dasar titik dan jumlah hasil koreksi','III.2 · Materi hlm. 331–333','Periksa titik terhadap peta 2025_2 yang telah diedit untuk perubahan batas murni. Cocokkan jumlah titik dengan unduhan awal GS kondisi 30 September 2026.'),
    ('IV.2','Unggah landmark ke GS','IV.2 · Materi hlm. 306–315, 331–335','Periksa persentase unggah landmark, riwayat penolakan dan kendala helpdesk. Konfirmasi dasar peta 2025_2 dan file akhir tanpa join 2026_1.'),
    ('V.1','Rekonsiliasi batas antarkabupaten/kota','V · Materi hlm. 320–327','Periksa layer kabupaten tetangga, rekap koordinat gap/overlap antarwilayah, draf berita acara, serta notulensi masalah dan solusi.'),
]


def audit(polygon_dict, point_dict, reference_dir):
    master = changes = old_ids = None
    try:
        mf = next(reference_dir.glob('msubsls_26_1_*.xlsx'))
        hf = next(reference_dir.glob('hirarki_sls_26_1_*.xlsx'))
        master, changes, old_ids = references(mf,hf,mf.stat().st_mtime_ns,hf.stat().st_mtime_ns)
    except StopIteration:
        pass
    poly, points = polygon_dict['features'], point_dict['features']
    checks = polygon_checks(poly,master,changes or {})
    checks.extend(point_checks(points,old_ids))
    try:
        from .spatial import spatial_checks
    except ImportError:
        from spatial import spatial_checks
    checks.extend(spatial_checks(polygon_dict,point_dict))
    for code,title,source,detail in MANUAL:
        checks.append(rule('manual-'+code,title,FORM+source,detail,status='konfirmasi'))
    return checks
