"""Penyajian nama kolom yang konsisten untuk layar, laporan, dan CSV."""
import re
from markupsafe import Markup, escape
from audit import CODES, NAMES, POINT_FIELDS, POLY_LENGTHS

COLUMNS = sorted(set(CODES) | set(NAMES) | set(POINT_FIELDS) | set(POLY_LENGTHS) | {
    "id_perub", "ket_perub", "idsubsls_25_2", "idsubsls_26_1", "unique_bang",
    "flag_psls", "flag_repair_initial", "berubah_batas", "level_6_full_code",
    "periode", "tingkat",
})
# "periode" and "tingkat" also occur in ordinary Indonesian prose.
TOKEN = re.compile(r"\b(" + "|".join(c for c in COLUMNS if c not in {"periode","tingkat"})
                   + r"|(?:periode|tingkat)(?= (?:wajib|tidak tersedia|20\d{2}_)))\b")


SENTENCES = {
    "Struktur 17 atribut GS. Panjang kunci Sub-SLS 16 digit mengikuti spesifikasi unggah dan master. Atribut khusus diperiksa tipe saat terisi.":
        "Peta diperiksa terhadap 17 kolom yang disyaratkan Geospatial System (GS). Kode Sub-SLS harus terdiri dari 16 digit. Untuk kolom khusus yang terisi, pemeriksaan juga melihat jenis nilainya.",
    "Kode dan nama per fitur dibandingkan persis dengan rilis 2026 Semester 1.":
        "Kode dan nama wilayah pada setiap poligon dibandingkan dengan master FRS Semester I 2026. Rincian menampilkan nilai pada peta dan nilai pembanding di master.",
    "Daftar kerja dari penanda berubah_batas=1.": "Daftar ini memuat Sub-SLS yang ditandai mengalami perubahan batas di master (berubah_batas = 1).",
    "ID asal dan tempel titik ditelusuri di kolom idsubsls_25_2.": "Kode wilayah asal dan kode wilayah hasil penempatan titik dicari pada kolom idsubsls_25_2 dalam hierarki.",
    "ID yang berbeda memerlukan penelusuran peta lapangan dan alasan pergeseran.": "Bandingkan Sub-SLS asal (idsubsls_origin) dengan Sub-SLS hasil penempatan titik (idsubsls_edited). Jika kodenya berbeda, periksa posisi bangunan pada peta lapangan dan tanyakan alasan perubahannya.",
    "Tipe, koordinat WGS 84, penutupan cincin, geometri kosong, dan validitas GEOS.": "Setiap wilayah harus berbentuk poligon dengan koordinat yang valid. Pemeriksaan mencari poligon kosong, garis batas yang tidak menutup, serta batas yang berpotongan dengan dirinya sendiri.",
    "Perulangan simpul dalam satu cincin diperiksa dengan mengecualikan simpul penutup.": "Pemeriksaan mencari titik sudut yang muncul berulang pada satu garis batas. Titik awal boleh diulang di akhir untuk menutup poligon.",
    "Setiap pasangan beririsan luas positif diperiksa, termasuk lintas desa. Sentuhan garis batas diperbolehkan.": "Dua wilayah ditandai jika menutupi sebagian area yang sama, termasuk ketika keduanya berada di desa berbeda. Wilayah bertetangga boleh berbagi garis batas.",
    "Membandingkan kesamaan spasial dua fitur, termasuk urutan simpul yang berbeda.": "Pemeriksaan mencari dua poligon yang menutupi wilayah yang sama persis, meskipun titik sudutnya dicatat dalam urutan berbeda.",
    "Memeriksa tipe Point serta rentang dan kelengkapan koordinat.": "Setiap bangunan harus diwakili oleh satu titik dengan koordinat bujur dan lintang yang lengkap dan berada dalam rentang yang sah.",
    "Cakupan target mengikuti level_6_full_code pada titik dan daftar ID terdaftar di Monev.": "Titik menjadi target jika kode Sub-SLS pada kolom level_6_full_code tercantum dalam daftar perubahan batas murni di Monev.",
    "approval GS": "persetujuan di Geospatial System (GS)",
    "gap/overlap": "celah atau tumpang tindih",
    "layer tetangga": "peta wilayah tetangga",
    "tanpa join 2026_1": "sebelum digabung dengan atribut peta Semester I 2026",
    "Tumpangsusunkan": "Bandingkan posisi",
}


def narrative(value):
    for original, description in SENTENCES.items():
        if original in value:
            value = value.replace(original,description)
    value = re.sub(r"Nomor yang sama ditelusuri pada unique_bang berbeda di Sub-SLS asal\. Beberapa assignment dapat merujuk pada satu bangunan\. ([\d.]+) pasangan Sub-SLS dan nomor bangunan dapat ditelusuri\.",
                   r"Pemeriksaan mencakup \1 kombinasi Sub-SLS asal dan nomor bangunan. Dalam satu Sub-SLS, setiap nomor bangunan (no_bang) seharusnya merujuk pada satu ID bangunan (unique_bang). Jika satu nomor merujuk pada beberapa ID, cocokkan dengan daftar bangunan petugas. Beberapa penugasan boleh merujuk pada ID bangunan yang sama.",value)
    value = re.sub(r"Nomor bangunan (\d+) digunakan oleh (\d+) unique_bang: ",r"Nomor bangunan \1 tercatat pada \2 ID bangunan berbeda (unique_bang). Cocokkan ID berikut dengan daftar bangunan petugas: ",value)
    return (value.replace("Keunikan assignment_id","Keunikan ID penugasan (assignment_id)")
            .replace("Setiap assignment harus memiliki ID tersendiri.","Setiap penugasan harus memiliki ID tersendiri pada kolom assignment_id.")
            .replace("perlu integer 32 bit","harus berupa bilangan bulat 32 bit")
            .replace("(absen)","(kolom tidak ditemukan)")
            .replace("wajib integer","harus berupa bilangan bulat")
            .replace("ID tempel","ID Sub-SLS hasil penempatan titik")
            .replace("ID assignment","ID penugasan"))


def marked(value):
    parts = TOKEN.split(narrative(value))
    return Markup("").join(Markup("<code>{}</code>").format(s) if i % 2 else escape(s)
                           for i,s in enumerate(parts))


def plain(value):
    return TOKEN.sub(lambda m: "`" + m[0] + "`", narrative(value))
