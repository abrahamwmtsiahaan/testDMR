"""
core/sesi.py
Orkestrasi satu sesi pemindaian LJK: mengubah kumpulan lembar mentah
(gambar atau PDF) menjadi hasil bacaan per lembar memakai core/omr.py dan
sebuah template (core/template.py), menyimpan hasilnya, serta menerapkan
koreksi manual dari operator.

Tidak ada input/print/GUI di sini — aman dipanggil dari FastAPI.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import numpy as np

from . import omr
from . import template as tpl

if getattr(sys, "frozen", False):
    DATA_DIR = Path(os.path.dirname(sys.executable)) / "data"
else:
    DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MEDIA_DIR = (
    DATA_DIR / "media" / "sesi"
)  # gambar lurus per lembar (disajikan via /media)
STATE_DIR = DATA_DIR / "state" / "sesi"  # data hasil bacaan per sesi (tidak disajikan)


class SesiError(Exception):
    pass


# ======================= BACA BERKAS UNGGAHAN =======================
def dari_unggahan(nama_file: str, data: bytes) -> list[tuple[str, np.ndarray]]:
    """
    Ubah satu berkas unggahan (gambar atau PDF, PDF bisa multi-halaman)
    menjadi daftar (nama_tampilan, gambar_bgr) — satu entri per lembar.
    """
    ext = Path(nama_file or "").suffix.lower()
    if ext == ".pdf":
        return _dari_pdf(nama_file, data)

    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    return [(nama_file, img)]


def _dari_pdf(
    nama_file: str, data: bytes, dpi: int = 300
) -> list[tuple[str, np.ndarray]]:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise SesiError(
            "Berkas PDF diunggah tapi paket 'pymupdf' belum terpasang "
            "(jalankan: pip install pymupdf)."
        ) from e

    hasil: list[tuple[str, np.ndarray]] = []
    dok = fitz.open(stream=data, filetype="pdf")
    try:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for i, halaman in enumerate(dok, start=1):
            pix = halaman.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            label = nama_file if len(dok) == 1 else f"{nama_file}#{i}"
            hasil.append((label, img))
    finally:
        dok.close()
    return hasil


# ======================= PENYIMPANAN STATE SESI =======================
def _path_state(sesi_id: str) -> Path:
    return STATE_DIR / f"{sesi_id}.json"


def _simpan_state(data: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _path_state(data["sesi"]).write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _muat_state(sesi_id: str) -> dict[str, Any]:
    p = _path_state(sesi_id)
    if not p.exists():
        raise SesiError(
            f"Sesi '{sesi_id}' tidak ditemukan (mungkin server sudah direstart)."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def muat_sesi(sesi_id: str) -> dict[str, Any]:
    """Muat data sesi berdasarkan id."""
    return _muat_state(sesi_id)


def sesi_terakhir() -> Optional[dict[str, Any]]:
    """Ambil data sesi yang paling baru diproses."""
    if not STATE_DIR.exists():
        return None
    files = sorted(
        STATE_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True
    )
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


# ======================= PROSES LEMBAR =======================
def proses_lembar(
    nama_template: str,
    gambar: list[tuple[str, np.ndarray]],
    callback_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """
    gambar: daftar (nama_file, img_bgr) mentah, satu per lembar, urut sesuai input.
    Baca tiap lembar dengan kriteria template, simpan gambar hasil pelurusan
    ke disk, simpan state sesi, dan kembalikan {sesi, template, lembar:[...]}.
    """
    if not gambar:
        raise SesiError("Tidak ada lembar untuk diproses.")

    t = tpl.muat_template(nama_template)
    kriteria = t["kriteria"]

    sesi_id = uuid.uuid4().hex[:12]
    folder_lurus = MEDIA_DIR / sesi_id / "lurus"
    folder_lurus.mkdir(parents=True, exist_ok=True)

    total = len(gambar)
    lembar = []
    for i, (nama_file, img) in enumerate(gambar, start=1):
        if callback_progress:
            callback_progress({
                "tipe": "progress",
                "fase": "proses",
                "saat_ini": i,
                "total": total,
                "pesan": f"Python memproses lembar {i}/{total} ({nama_file})...",
            })
        path_lurus = folder_lurus / f"{i:03d}.png"
        hasil = omr.baca_lembar(img, kriteria, path_lurus=path_lurus)
        lembar.append(
            {
                "no": i,
                "file": nama_file,
                "koreksi": hasil["koreksi"],
                "perlu_cek": hasil["perlu_cek"],
                "teks": omr.ringkas_teks(hasil["hasil"]),
                "detail": hasil["hasil"],
                "lurus": f"/media/sesi/{sesi_id}/lurus/{i:03d}.png",
            }
        )

    if callback_progress:
        callback_progress({
            "tipe": "progress",
            "fase": "selesai",
            "saat_ini": total,
            "total": total,
            "pesan": f"Selesai memproses {total} lembar. Memuat hasil...",
        })

    data = {"sesi": sesi_id, "template": nama_template, "lembar": lembar}
    _simpan_state(data)
    return data


# ======================= KOREKSI MANUAL =======================
def terapkan_koreksi(
    nama_template: str,
    sesi_id: str,
    no: int,
    bagian: str,
    kolom: int,
    indeks: Optional[int],
) -> dict[str, Any]:
    """Terapkan satu koreksi manual, simpan ulang state sesi, return hasil_kriteria terbaru."""
    t = tpl.muat_template(nama_template)
    k = next((x for x in t["kriteria"] if x["nama"] == bagian), None)
    if k is None:
        raise SesiError(f"Bagian '{bagian}' tidak ada pada template '{nama_template}'.")

    data = _muat_state(sesi_id)
    l = next((x for x in data["lembar"] if x["no"] == no), None)
    if l is None:
        raise SesiError(f"Lembar no. {no} tidak ditemukan di sesi ini.")
    if bagian not in l["detail"]:
        raise SesiError(f"Bagian '{bagian}' tidak ada pada hasil lembar no. {no}.")

    try:
        hasil_kriteria = omr.terapkan_koreksi(
            l["detail"][bagian], kolom, indeks, k["label_baris"]
        )
    except IndexError as e:
        raise SesiError(str(e)) from e

    l["detail"][bagian] = hasil_kriteria
    l["teks"][bagian] = hasil_kriteria["teks"]
    l["perlu_cek"] = l["koreksi"] == "tidak_terkoreksi" or any(
        kolom_hasil["status"] == "ganda"
        for h in l["detail"].values()
        for kolom_hasil in h["kolom"]
    )

    _simpan_state(data)
    return hasil_kriteria
