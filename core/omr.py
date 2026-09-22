"""
core/omr.py
Logika OMR murni (tanpa input/print/GUI). Aman dipanggil dari FastAPI.

Alur:
    img mentah -> luruskan_lembar() -> baca_lembar() -> hasil per kriteria
Koordinat grid pada template berada di ruang gambar HASIL LURUS (UKURAN_KANONIK).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

# ======================= KONSTANTA =======================
UKURAN_KANONIK = (2480, 3508)  # (lebar, tinggi) gambar setelah diluruskan

# Ukuran marker sebagai fraksi dari lebar gambar
MARKER_MIN_FRAKSI = 0.005
MARKER_MAX_FRAKSI = 0.035
MARKER_RASIO_MIN = 0.6
MARKER_RASIO_MAX = 1.6
MARKER_KEPADATAN_MIN = 0.55  # luas kontur / luas bounding box
AREA_MIN_FRAKSI = 0.25  # luas segiempat marker minimal thd luas gambar

# Threshold yang dicoba berurutan saat mencari marker (None = Otsu)
DAFTAR_THRESHOLD = (None, 110, 90, 70, 130)

# Ambang baca bulatan
AMBANG_KOSONG = 40.0  # (skor tertinggi - median) minimal agar dianggap terisi
AMBANG_GANDA = 0.6  # skor kedua > 60% dari selisih tertinggi => ganda
RADIUS_FRAKSI = 0.30  # radius area tengah bulatan thd jarak antar bulatan

# Kode status per kolom
STATUS_TERISI = "terisi"
STATUS_KOSONG = "kosong"
STATUS_GANDA = "ganda"

# Karakter di teks hasil untuk kolom bermasalah
KARAKTER_KOSONG = "_"
KARAKTER_GANDA = "?"


# ======================= UTILITAS =======================
def baca_gambar(path: str | Path) -> np.ndarray | None:
    """cv2.imread yang aman untuk path unicode (Windows)."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def tulis_gambar(path: str | Path, img: np.ndarray) -> bool:
    """cv2.imwrite yang aman untuk path unicode (Windows)."""
    ext = Path(path).suffix or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        return False
    buf.tofile(str(path))
    return True


def _urutkan_titik(pts: np.ndarray) -> np.ndarray:
    """Urutkan 4 titik: kiri-atas, kanan-atas, kanan-bawah, kiri-bawah."""
    pts = np.asarray(pts, dtype="float32").reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype="float32",
    )


# ======================= BINERISASI =======================
def _biner_gelap(img: np.ndarray, batas: int | None = None) -> np.ndarray:
    """
    Biner area gelap dari channel R.
    Oranye (cetakan) terang di channel R, hitam (border/marker) dan pensil gelap.
    batas=None -> pakai Otsu, dibatasi maksimal 110 supaya oranye tidak ikut.
    """
    r = cv2.GaussianBlur(img[:, :, 2], (5, 5), 0)
    if batas is None:
        otsu, _ = cv2.threshold(r, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        batas = min(int(otsu), 110)
    _, biner = cv2.threshold(r, batas, 255, cv2.THRESH_BINARY_INV)
    return biner


# ======================= DETEKSI MARKER =======================
def _kandidat_marker(biner: np.ndarray, lebar: int) -> np.ndarray:
    """Kumpulkan pusat kontur yang mirip kotak solid berukuran marker."""
    biner = cv2.morphologyEx(
        biner, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    )
    kontur, _ = cv2.findContours(biner, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_sisi = lebar * MARKER_MIN_FRAKSI
    max_sisi = lebar * MARKER_MAX_FRAKSI

    hasil = []
    for c in kontur:
        x, y, w, h = cv2.boundingRect(c)
        if not (min_sisi <= w <= max_sisi and min_sisi <= h <= max_sisi):
            continue
        if not (MARKER_RASIO_MIN <= w / float(h) <= MARKER_RASIO_MAX):
            continue
        if cv2.contourArea(c) / float(w * h) < MARKER_KEPADATAN_MIN:
            continue
        hasil.append((x + w / 2.0, y + h / 2.0))
    return np.array(hasil, dtype="float32").reshape(-1, 2)


def _pilih_empat_sudut(pts: np.ndarray) -> np.ndarray | None:
    """
    Dari kumpulan titik, pilih 1 titik paling ke pojok di tiap kuadran.
    Kuadran ditentukan dari tengah sebaran titik, bukan tengah gambar,
    sehingga tetap benar walau kertas bergeser.
    """
    if len(pts) < 4:
        return None

    tx = (pts[:, 0].min() + pts[:, 0].max()) / 2.0
    ty = (pts[:, 1].min() + pts[:, 1].max()) / 2.0

    def terbaik(mask, skor, fungsi):
        kandidat = pts[mask]
        if len(kandidat) == 0:
            return None
        return kandidat[fungsi(range(len(kandidat)), key=lambda i: skor(kandidat[i]))]

    kiri, atas = pts[:, 0] < tx, pts[:, 1] < ty
    tl = terbaik(kiri & atas, lambda p: p[0] + p[1], min)
    tr = terbaik(~kiri & atas, lambda p: p[0] - p[1], max)
    br = terbaik(~kiri & ~atas, lambda p: p[0] + p[1], max)
    bl = terbaik(kiri & ~atas, lambda p: p[0] - p[1], min)

    if any(p is None for p in (tl, tr, br, bl)):
        return None
    return np.array([tl, tr, br, bl], dtype="float32")


def _valid_segiempat(sudut: np.ndarray, lebar: int, tinggi: int) -> bool:
    """Cek 4 titik masuk akal: berbeda, luas cukup besar, sisi berhadapan mirip."""
    if len({tuple(p) for p in sudut}) < 4:
        return False
    if cv2.contourArea(sudut) < AREA_MIN_FRAKSI * lebar * tinggi:
        return False
    atas = np.linalg.norm(sudut[1] - sudut[0])
    bawah = np.linalg.norm(sudut[2] - sudut[3])
    kiri = np.linalg.norm(sudut[3] - sudut[0])
    kanan = np.linalg.norm(sudut[2] - sudut[1])
    if min(atas, bawah, kiri, kanan) < 1:
        return False
    if max(atas, bawah) / min(atas, bawah) > 1.25:
        return False
    if max(kiri, kanan) / min(kiri, kanan) > 1.25:
        return False
    return True


def deteksi_marker(img: np.ndarray, debug_path: str | Path | None = None):
    """
    Cari 4 kotak hitam di sudut LJK.
    Mencoba beberapa threshold sampai ada yang menghasilkan 4 sudut valid.
    Return array 4x2 (TL, TR, BR, BL) atau None.
    """
    tinggi, lebar = img.shape[:2]
    for batas in DAFTAR_THRESHOLD:
        biner = _biner_gelap(img, batas)
        pts = _kandidat_marker(biner, lebar)
        sudut = _pilih_empat_sudut(pts)
        if sudut is not None and _valid_segiempat(sudut, lebar, tinggi):
            if debug_path:
                vis = img.copy()
                for p in sudut:
                    cv2.circle(vis, (int(p[0]), int(p[1])), 30, (0, 255, 0), 8)
                for p in pts:
                    cv2.circle(vis, (int(p[0]), int(p[1])), 12, (255, 0, 0), 3)
                tulis_gambar(debug_path, vis)
            return sudut
    if debug_path:
        tulis_gambar(
            debug_path, _biner_gelap(img)
        )  # bantu diagnosis: apa yang dilihat program
    return None


# ======================= DETEKSI BORDER (FALLBACK) =======================
def deteksi_border(img: np.ndarray):
    """Fallback: cari kontur segiempat besar (border hitam)."""
    tinggi, lebar = img.shape[:2]
    for batas in DAFTAR_THRESHOLD:
        biner = _biner_gelap(img, batas)
        biner = cv2.dilate(biner, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
        kontur, _ = cv2.findContours(biner, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        terbaik, luas_max = None, 0.0
        for c in kontur:
            luas = cv2.contourArea(c)
            if luas < 0.15 * lebar * tinggi:
                continue
            approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
            if len(approx) == 4 and luas > luas_max:
                terbaik, luas_max = approx.reshape(4, 2), luas
        if terbaik is not None:
            sudut = _urutkan_titik(terbaik)
            if _valid_segiempat(sudut, lebar, tinggi):
                return sudut
    return None


# ======================= LURUSKAN =======================
def luruskan_lembar(img: np.ndarray, debug_path: str | Path | None = None):
    """
    Luruskan gambar berdasarkan 4 marker (fallback: border besar).
    Return (gambar_lurus, metode).
    metode: 'marker' | 'border' | 'tidak_terkoreksi'
    Bila semua gagal, gambar ASLI dikembalikan (tidak diubah ukurannya).
    """
    metode = "marker"
    sumber = deteksi_marker(img, debug_path)
    if sumber is None:
        metode = "border"
        sumber = deteksi_border(img)
    if sumber is None:
        return img, "tidak_terkoreksi"

    lebar, tinggi = UKURAN_KANONIK
    tujuan = np.array(
        [[0, 0], [lebar - 1, 0], [lebar - 1, tinggi - 1], [0, tinggi - 1]],
        dtype="float32",
    )
    M = cv2.getPerspectiveTransform(sumber, tujuan)
    hasil = cv2.warpPerspective(
        img, M, (lebar, tinggi), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255)
    )
    return hasil, metode


# ======================= BACA GRID =======================
def peta_gelap(img_lurus: np.ndarray) -> np.ndarray:
    """
    Peta 'kegelapan' 0..255 (tinggi = gelap) dari channel R.
    Cetakan oranye punya R tinggi sehingga hampir tidak muncul; pensil/grafit muncul jelas.
    """
    r = cv2.GaussianBlur(img_lurus[:, :, 2], (3, 3), 0)
    return np.clip(255 - r.astype(np.int16), 0, 255).astype(np.uint8)


def posisi_bulatan(grid: dict, kolom: int, baris: int):
    """Generator (c, b, cx, cy) pusat semua bulatan pada grid."""
    for c in range(kolom):
        for b in range(baris):
            yield c, b, grid["x0"] + c * grid["dx"], grid["y0"] + b * grid["dy"]


def radius_sel(grid: dict) -> float:
    """Radius area tengah bulatan (piksel)."""
    dx = abs(float(grid.get("dx", 0.0)))
    dy = abs(float(grid.get("dy", 0.0)))
    step = min(dx, dy) if (dx >= 1.0 and dy >= 1.0) else max(dx, dy, 10.0)
    return max(RADIUS_FRAKSI * step, 3.0)


def _skor_area(gelap: np.ndarray, cx: int, cy: int, r: int) -> float:
    """Hitung rata-rata kegelapan di satu kotak area bulatan."""
    tinggi, lebar = gelap.shape
    x1, x2 = max(cx - r, 0), min(cx + r + 1, lebar)
    y1, y2 = max(cy - r, 0), min(cy + r + 1, tinggi)
    patch = gelap[y1:y2, x1:x2]
    return float(patch.mean()) if patch.size else 0.0


def baca_grid(
    gelap: np.ndarray,
    grid: dict,
    kolom: int,
    baris: int,
    label: list[str],
    ambang_kosong: float = AMBANG_KOSONG,
    ambang_ganda: float = AMBANG_GANDA,
    arah_baca: str = "vertikal",
) -> dict:
    r = int(radius_sel(grid))
    teks, detail = [], []

    jumlah_item = baris if arah_baca == "horizontal" else kolom
    jumlah_opsi = kolom if arah_baca == "horizontal" else baris

    for i in range(jumlah_item):
        skor = np.zeros(jumlah_opsi, dtype="float64")
        for j in range(jumlah_opsi):
            c = j if arah_baca == "horizontal" else i
            b = i if arah_baca == "horizontal" else j
            cx = int(round(grid["x0"] + c * grid["dx"]))
            cy = int(round(grid["y0"] + b * grid["dy"]))
            skor[j] = _skor_area(gelap, cx, cy, r)

        urut = np.argsort(skor)[::-1]
        tertinggi = skor[urut[0]]
        kedua = skor[urut[1]] if jumlah_opsi > 1 else 0.0
        median = float(np.median(skor))

        if tertinggi - median < ambang_kosong:
            status, indeks, ch = STATUS_KOSONG, None, KARAKTER_KOSONG
        elif jumlah_opsi > 1 and (kedua - median) > ambang_ganda * (tertinggi - median):
            status, indeks, ch = STATUS_GANDA, None, KARAKTER_GANDA
        else:
            status, indeks = STATUS_TERISI, int(urut[0])
            ch = str(label[indeks])

        teks.append(ch)
        detail.append(
            {
                "status": status,
                "indeks": indeks,
                "skor": [round(float(s), 1) for s in skor],
            }
        )
    return {"teks": "".join(teks), "kolom": detail}


# ======================= PRATINJAU =======================
def gambar_pratinjau(
    img_lurus: np.ndarray, kriteria: list[dict], hasil: dict
) -> np.ndarray:
    vis = img_lurus.copy()
    for k in kriteria:
        g = k["grid"]
        rad = radius_sel(g)
        kolom_hasil = hasil[k["nama"]]["kolom"]
        arah = k.get("arah_baca", "vertikal")

        for c, b, cx, cy in posisi_bulatan(g, k["jumlah_kolom"], k["jumlah_baris"]):
            cx, cy = int(round(cx)), int(round(cy))
            item_idx = b if arah == "horizontal" else c
            opsi_idx = c if arah == "horizontal" else b
            info = kolom_hasil[item_idx]

            if info["status"] == STATUS_TERISI and info["indeks"] == opsi_idx:
                cv2.circle(vis, (cx, cy), int(rad * 1.6), (0, 200, 0), 4)
            elif info["status"] == STATUS_GANDA:
                cv2.circle(vis, (cx, cy), int(rad), (0, 0, 255), 2)
            else:
                cv2.circle(vis, (cx, cy), 2, (170, 170, 170), -1)

        for idx, info in enumerate(kolom_hasil):
            if info["status"] == STATUS_KOSONG:
                if arah == "horizontal":
                    cx = int(round(g["x0"] - 0.9 * abs(g["dx"])))
                    cy = int(round(g["y0"] + idx * g["dy"]))
                else:
                    cx = int(round(g["x0"] + idx * g["dx"]))
                    cy = int(round(g["y0"] - 0.9 * abs(g["dy"])))
                cv2.circle(vis, (cx, cy), 5, (0, 200, 255), -1)
    return vis


# ======================= KOREKSI MANUAL =======================
def terapkan_koreksi(
    hasil_kriteria: dict, kolom_ke: int, indeks: int | None, label: list[str]
) -> dict:
    """
    Ubah satu kolom secara manual (dipakai UI saat operator mengklik bulatan).
      indeks=None -> kosongkan kolom
      indeks=n    -> pilih bulatan ke-n
    Mengembalikan hasil_kriteria yang sudah diperbarui (teks ikut diperbarui).
    """
    kolom = hasil_kriteria["kolom"]
    if not (0 <= kolom_ke < len(kolom)):
        raise IndexError("kolom di luar jangkauan")
    if indeks is None:
        kolom[kolom_ke].update({"status": STATUS_KOSONG, "indeks": None})
    else:
        if not (0 <= indeks < len(label)):
            raise IndexError("indeks bulatan di luar jangkauan")
        kolom[kolom_ke].update({"status": STATUS_TERISI, "indeks": int(indeks)})
    kolom[kolom_ke]["manual"] = True

    hasil_kriteria["teks"] = "".join(
        KARAKTER_KOSONG
        if k["status"] == STATUS_KOSONG
        else KARAKTER_GANDA
        if k["status"] == STATUS_GANDA
        else str(label[k["indeks"]])
        for k in kolom
    )
    return hasil_kriteria


# ======================= API UTAMA =======================
def baca_lembar(
    img_bgr: np.ndarray,
    kriteria: list[dict],
    path_lurus: str | Path | None = None,
    path_pratinjau: str | Path | None = None,
    path_debug_marker: str | Path | None = None,
) -> dict:
    """
    Proses 1 lembar dari gambar mentah sampai hasil.

    kriteria: list dict dengan kunci
        nama, jumlah_kolom, jumlah_baris, label_baris, grid{x0,y0,dx,dy}

    Return:
      {
        "koreksi": "marker|border|tidak_terkoreksi",
        "hasil": { nama: {"teks": str, "kolom": [...]}, ... },
        "perlu_cek": bool,       # ada kolom kosong/ganda pada bagian yang bukan opsional
      }
    """
    img_lurus, metode = luruskan_lembar(img_bgr, debug_path=path_debug_marker)
    gelap = peta_gelap(img_lurus)

    hasil = {}
    for k in kriteria:
        if not k.get("grid"):
            raise ValueError(f"Kriteria '{k['nama']}' belum dikalibrasi")
        hasil[k["nama"]] = baca_grid(
            gelap,
            k["grid"],
            k["jumlah_kolom"],
            k["jumlah_baris"],
            k["label_baris"],
            arah_baca=k.get("arah_baca", "vertikal"),
        )

    if path_lurus:
        tulis_gambar(path_lurus, img_lurus)
    if path_pratinjau:
        tulis_gambar(path_pratinjau, gambar_pratinjau(img_lurus, kriteria, hasil))

    perlu_cek = metode == "tidak_terkoreksi" or any(
        k["status"] == STATUS_GANDA for h in hasil.values() for k in h["kolom"]
    )
    return {"koreksi": metode, "hasil": hasil, "perlu_cek": perlu_cek}


def baca_file(path: str | Path, kriteria: list[dict], **kw) -> dict | None:
    """Versi praktis: baca dari path file. Return None bila gambar gagal dibaca."""
    img = baca_gambar(path)
    if img is None:
        return None
    return baca_lembar(img, kriteria, **kw)


def ringkas_teks(hasil: dict) -> dict[str, str]:
    """{nama: teks} untuk dimasukkan ke CSV/tabel."""
    return {nama: h["teks"] for nama, h in hasil.items()}
