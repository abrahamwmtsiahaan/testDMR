"""
core/template.py
Penyimpanan & pengambilan definisi template LJK (daftar kriteria + grid
kalibrasi). Disimpan sebagai satu berkas JSON per template di TEMPLATE_DIR.

Tidak ada input/print/GUI di sini — aman dipanggil dari FastAPI, sama
seperti core/omr.py.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

if getattr(sys, "frozen", False):
    DATA_DIR = Path(os.path.dirname(sys.executable)) / "data"
else:
    DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TEMPLATE_DIR = DATA_DIR / "templates"


class TemplateError(Exception):
    pass


def _nama_aman(nama: str) -> str:
    aman = re.sub(r'[\\/:*?"<>|]', "_", (nama or "").strip())
    if not aman:
        raise TemplateError("Nama template tidak boleh kosong.")
    return aman


def _path(nama: str) -> Path:
    return TEMPLATE_DIR / f"{_nama_aman(nama)}.json"


def inisialisasi_template_bawaan() -> None:
    """
    Memastikan template default (khususnya 'LJK PPTSB.json') selalu tersedia di TEMPLATE_DIR.
    Mencari berkas dari direktori kerja, folder eksekusi .exe, atau bundled data PyInstaller.
    """
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    target = TEMPLATE_DIR / "LJK PPTSB.json"
    if target.exists() and target.stat().st_size > 0:
        return

    # Cari kandidat sumber LJK PPTSB.json
    kandidat = [
        Path.cwd() / "LJK PPTSB.json",
        Path.cwd() / "data" / "templates" / "LJK PPTSB.json",
    ]
    if getattr(sys, "frozen", False):
        kandidat.extend([
            Path(sys._MEIPASS) / "LJK PPTSB.json",
            Path(os.path.dirname(sys.executable)) / "LJK PPTSB.json",
            Path(os.path.dirname(sys.executable)) / "data" / "templates" / "LJK PPTSB.json",
        ])
    else:
        root_dir = Path(__file__).resolve().parents[1]
        kandidat.extend([
            root_dir / "LJK PPTSB.json",
            root_dir / "data" / "templates" / "LJK PPTSB.json",
        ])

    for k in kandidat:
        if k.is_file():
            try:
                isi = k.read_text(encoding="utf-8")
                json.loads(isi)
                target.write_text(isi, encoding="utf-8")
                return
            except Exception:
                pass


def daftar_template() -> list[str]:
    """Nama semua template tersimpan, urut abjad."""
    inisialisasi_template_bawaan()
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in TEMPLATE_DIR.glob("*.json"))


def _validasi_kriteria(kriteria: list[dict[str, Any]]) -> None:
    if not kriteria:
        raise TemplateError("Template harus punya minimal satu bagian.")

    nama_bagian = [str(k.get("nama") or "") for k in kriteria]
    if any(not n for n in nama_bagian):
        raise TemplateError("Ada bagian tanpa nama.")
    if len(set(nama_bagian)) != len(nama_bagian):
        raise TemplateError("Nama bagian tidak boleh sama.")

    for k in kriteria:
        if not k.get("grid"):
            raise TemplateError(f"Bagian '{k['nama']}' belum dikalibrasi.")
        grid = k["grid"]
        if not all(key in grid for key in ("x0", "y0", "dx", "dy")):
            raise TemplateError(f"Grid bagian '{k['nama']}' tidak lengkap.")

        arah = k.get("arah_baca", "vertikal")
        jumlah_baris = int(k.get("jumlah_baris") or 0)
        jumlah_kolom = int(k.get("jumlah_kolom") or 0)
        jumlah_label = jumlah_kolom if arah == "horizontal" else jumlah_baris

        if jumlah_baris == 1:
            grid["dy"] = abs(float(grid.get("dx", 0.0))) or 10.0
        if jumlah_kolom == 1:
            grid["dx"] = abs(float(grid.get("dy", 0.0))) or 10.0

        label_baris = k.get("label_baris") or []
        if len(label_baris) != jumlah_label:
            raise TemplateError(
                f"Isi bulatan '{k['nama']}' ({len(label_baris)}) "
                f"tidak sesuai dengan jumlah opsi ({jumlah_label})."
            )
        if jumlah_kolom < 1 or jumlah_baris < 1:
            raise TemplateError(f"Dimensi grid bagian '{k['nama']}' tidak valid.")


def simpan_template(
    nama: str, kriteria: list[dict[str, Any]], contoh: str | None = None
) -> dict[str, Any]:
    """
    Validasi lalu simpan template sebagai JSON. Return data yang tersimpan.
    contoh: URL gambar lembar contoh (hasil pelurusan) yang dipakai saat kalibrasi,
    disimpan supaya saat template dimuat lagi, kanvas kalibrasi bisa langsung
    menampilkan gambar itu tanpa perlu scan/unggah ulang.
    """
    _validasi_kriteria(kriteria)
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    aman = _nama_aman(nama)
    data = {"nama": aman, "kriteria": kriteria, "contoh": contoh}
    _path(aman).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def muat_template(nama: str) -> dict[str, Any]:
    inisialisasi_template_bawaan()
    p = _path(nama)
    if not p.exists():
        raise TemplateError(f"Template '{nama}' tidak ditemukan.")
    return json.loads(p.read_text(encoding="utf-8"))
