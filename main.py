"""
main.py
Entry point FastAPI untuk aplikasi LJK Reader.

Struktur folder yang diasumsikan (buat foldernya kalau belum ada):

    main.py
    core/
        __init__.py
        omr.py
        scanner.py
        template.py
        sesi.py
    web/                    <- index.html, app.js, style.css taruh di sini
    data/                    <- dibuat otomatis saat aplikasi jalan
        templates/           <- JSON tiap template
        media/
            contoh/          <- lembar contoh (hasil scan/unggah, sudah diluruskan)
            sesi/<id>/lurus/ <- gambar tiap lembar per sesi, sudah diluruskan
        state/
            sesi/<id>.json   <- hasil bacaan + detail per sesi (tidak disajikan publik)

Jalankan dengan:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000
lalu buka http://localhost:8000
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import omr, scanner
from core import sesi as sesi_mod
from core import template as tpl

# ======================= SETUP FOLDER =======================
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(os.path.dirname(sys.executable))
    DATA_DIR = APP_DIR / "data"
else:
    BASE_DIR = Path(__file__).resolve().parent
    APP_DIR = BASE_DIR
    DATA_DIR = BASE_DIR / "data"

WEB_DIR = BASE_DIR / "static"
MEDIA_DIR = DATA_DIR / "media"
CONTOH_DIR = MEDIA_DIR / "contoh"
HASIL_SCAN_DIR = APP_DIR / "hasil_scan_gambar"
HASIL_SIMPAN_DIR = DATA_DIR / "hasil_simpan"

CONTOH_DIR.mkdir(parents=True, exist_ok=True)
HASIL_SCAN_DIR.mkdir(parents=True, exist_ok=True)
HASIL_SIMPAN_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="LJK Reader")

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


# ======================= PENANGANAN ERROR =======================
# Semua error "diketahui" (nama template salah, sesi hilang, scanner tidak
# ada, dst.) dikembalikan sebagai 400 + {"detail": "..."} — persis format
# yang diharapkan app.js (lihat fungsi api() di app.js).
@app.exception_handler(tpl.TemplateError)
@app.exception_handler(sesi_mod.SesiError)
@app.exception_handler(scanner.ScannerError)
@app.exception_handler(ValueError)
def _tangani_error_domain(request, exc: Exception):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ======================= HALAMAN UTAMA =======================
@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


def normalisasi_api_url(url: str) -> str:
    """Jika URL hanya berisi host/port (mis. http://localhost:6005), otomatis tambahkan path /api/v1/dmr/olah."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.path or parsed.path == "/":
            url = url.rstrip("/") + "/api/v1/dmr/olah"
    except Exception:
        pass
    return url


def ambil_api_url_env() -> str:
    """Ambil URL endpoint REST API dari file .env (variabel: api_url) atau os.environ."""
    raw_url = ""
    env_file = APP_DIR / ".env"
    if not env_file.exists():
        env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip().lower() == "api_url":
                        clean_v = v.strip().strip("'\"")
                        if clean_v:
                            raw_url = clean_v
                            break
        except Exception:
            pass

    if not raw_url:
        val = os.environ.get("api_url") or os.environ.get("API_URL")
        if val and val.strip():
            raw_url = val.strip()

    return normalisasi_api_url(raw_url) if raw_url else ""


# ======================= SKEMA REQUEST =======================
class TemplateIn(BaseModel):
    nama: str
    kriteria: list[dict[str, Any]]
    contoh: Optional[str] = None


class SesiScanIn(BaseModel):
    template: str
    jumlah: int = 1


class KoreksiIn(BaseModel):
    template: str
    sesi: str
    no: int
    bagian: str
    kolom: int
    indeks: Optional[int] = None


class EksporIn(BaseModel):
    kolom: list[str]
    baris: list[dict[str, Any]]


class SimpanDmrIn(BaseModel):
    sesi: Optional[str] = None
    endpoint_url: Optional[str] = None
    data: list[dict[str, Any]]
    lembar_dipilih: Optional[list[int]] = None


# ======================= STATUS SCANNER =======================
@app.get("/api/status")
def status():
    aktif = scanner.scanner_aktif()
    return {"scanner": aktif.nama if aktif else None}


# ======================= LEMBAR CONTOH (KALIBRASI) =======================
def _simpan_contoh(img: np.ndarray) -> dict[str, Any]:
    """Luruskan gambar contoh lalu simpan; ini gambar yang dipakai kanvas kalibrasi,
    jadi koordinat grid yang dihasilkan operator otomatis dalam ruang gambar lurus,
    sama seperti yang diasumsikan core/omr.py."""
    img_lurus, metode = omr.luruskan_lembar(img)
    nama_berkas = f"{uuid.uuid4().hex[:12]}.png"
    omr.tulis_gambar(CONTOH_DIR / nama_berkas, img_lurus)
    return {"url": f"/media/contoh/{nama_berkas}", "koreksi": metode}


@app.post("/api/contoh/scan")
def contoh_scan():
    aktif = scanner.scanner_aktif()
    if not aktif:
        raise scanner.ScannerError("Scanner tidak terdeteksi.")
    with tempfile.TemporaryDirectory() as tmp:
        hasil = aktif.scan_batch(Path(tmp), "contoh", 1)
        if not hasil:
            raise scanner.ScannerError("Tidak ada lembar terbaca dari scanner.")
        img = omr.baca_gambar(hasil[0])
        if img is None:
            raise scanner.ScannerError("Gagal membaca hasil scan.")
    return _simpan_contoh(img)


@app.post("/api/contoh")
async def contoh_unggah(file: UploadFile = File(...)):
    gambar = sesi_mod.dari_unggahan(file.filename, await file.read())
    if not gambar:
        raise HTTPException(400, "Berkas tidak bisa dibaca sebagai gambar/PDF.")
    _, img = gambar[0]
    return _simpan_contoh(img)


# ======================= TEMPLATE =======================
@app.get("/api/template")
def daftar_template():
    return tpl.daftar_template()


@app.get("/api/template/{nama}")
def muat_template(nama: str):
    return tpl.muat_template(nama)


@app.post("/api/template/{nama}")
def simpan_template(nama: str, body: TemplateIn):
    return tpl.simpan_template(nama, body.kriteria, body.contoh)


# ======================= SESI: SCAN / UNGGAH =======================
@app.post("/api/sesi/scan")
def sesi_scan(body: SesiScanIn):
    aktif = scanner.scanner_aktif()
    if not aktif:
        raise scanner.ScannerError("Scanner tidak terdeteksi.")
    with tempfile.TemporaryDirectory() as tmp:
        path_hasil = aktif.scan_batch(Path(tmp), "lembar", body.jumlah)
        if not path_hasil:
            raise scanner.ScannerError("Tidak ada lembar terbaca dari scanner.")
        gambar = []
        for p in path_hasil:
            img = omr.baca_gambar(p)
            if img is not None:
                gambar.append((p.name, img))
        return sesi_mod.proses_lembar(body.template, gambar)


@app.post("/api/sesi/unggah")
async def sesi_unggah(template: str, files: list[UploadFile] = File(...)):
    gambar: list[tuple[str, np.ndarray]] = []
    for f in files:
        gambar.extend(sesi_mod.dari_unggahan(f.filename, await f.read()))
    if not gambar:
        raise HTTPException(
            400, "Tidak ada berkas yang bisa dibaca sebagai gambar/PDF."
        )
    return sesi_mod.proses_lembar(template, gambar)


# ======================= KOREKSI MANUAL =======================
@app.post("/api/koreksi")
def koreksi(body: KoreksiIn):
    hasil_kriteria = sesi_mod.terapkan_koreksi(
        body.template, body.sesi, body.no, body.bagian, body.kolom, body.indeks
    )
    return {"teks": hasil_kriteria["teks"], "detail": hasil_kriteria}


# ======================= EKSPOR CSV =======================
@app.post("/api/ekspor")
def ekspor(body: EksporIn):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=body.kolom, extrasaction="ignore")
    writer.writeheader()
    for baris in body.baris:
        writer.writerow(baris)
    # BOM (utf-8-sig) supaya Excel di Windows membuka karakter non-ASCII dengan benar
    isi = buf.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(isi),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hasil_scan_ljk.csv"},
    )


# ======================= SESI: AMBIL STATE =======================
@app.get("/api/sesi/terakhir")
def sesi_terakhir():
    data = sesi_mod.sesi_terakhir()
    if not data:
        raise HTTPException(404, "Belum ada sesi yang tersimpan.")
    return data


@app.get("/api/sesi/{sesi_id}")
def muat_sesi(sesi_id: str):
    return sesi_mod.muat_sesi(sesi_id)


# ======================= 4. SIMPAN & HIT REST API =======================
@app.post("/api/simpan-dmr")
def simpan_dmr(body: SimpanDmrIn, request: Request):
    waktu_obj = datetime.datetime.now()
    waktu_str = waktu_obj.strftime("%Y%m%d_%H%M%S")
    sesi_id = body.sesi or "manual"

    # 1. Simpan gambar hasil scan ke hasil_scan_gambar jika sesi tersedia
    gambar_tersimpan = []
    if body.sesi:
        folder_lurus = MEDIA_DIR / "sesi" / body.sesi / "lurus"
        if folder_lurus.exists():
            for idx, p in enumerate(body.data, start=1):
                # Prioritaskan nomor lembar asli dari lembar_dipilih atau atribut item
                no_lembar = (
                    body.lembar_dipilih[idx - 1]
                    if body.lembar_dipilih and (idx - 1) < len(body.lembar_dipilih)
                    else p.get("no_lembar", p.get("lembar_no", idx))
                )
                try:
                    no_lembar_int = int(no_lembar)
                except Exception:
                    no_lembar_int = idx

                src_file = folder_lurus / f"{no_lembar_int:03d}.png"
                if src_file.exists():
                    nomor_safe = re.sub(r"[^\w\-]", "_", str(p.get("nomor_peserta", no_lembar_int)))
                    nama_safe = re.sub(r"[^\w\-]", "_", str(p.get("nama_peserta", f"peserta_{no_lembar_int}")))
                    kode_safe = re.sub(r"[^\w\-]", "_", str(p.get("kode_soal", "soal")))
                    dst_name = f"{waktu_str}_{no_lembar_int:03d}_{nomor_safe}_{nama_safe}_{kode_safe}.png"
                    dst_file = HASIL_SCAN_DIR / dst_name
                    shutil.copy2(src_file, dst_file)
                    gambar_tersimpan.append(dst_name)

    # 2. Hit REST API DMR
    api_hasil = None
    api_status_code = None
    api_error = None

    url = ambil_api_url_env() or normalisasi_api_url((body.endpoint_url or "").strip()) or "http://localhost:6005/api/v1/dmr/olah"
    cleaned_data = []
    for p in body.data:
        cleaned_item = {k: v for k, v in p.items() if k not in ("no_lembar", "lembar_no")}
        cleaned_data.append(cleaned_item)

    if url:
        try:
            # Pakai User-Agent sesuai browser klien yang memanggil endpoint (misal Chrome / Edge)
            browser_ua = request.headers.get("user-agent") or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
            req_headers = {
                "Content-Type": "application/json",
                "User-Agent": browser_ua,
                "Accept": "application/json, text/plain, */*",
            }
            accept_lang = request.headers.get("accept-language")
            if accept_lang:
                req_headers["Accept-Language"] = accept_lang

            data_bytes = json.dumps(cleaned_data, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers=req_headers,
                method="POST",
            )
            
            import ssl
            ssl_ctx = ssl.create_default_context()
            try:
                with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
                    api_status_code = resp.getcode()
                    body_bytes = resp.read()
                    try:
                        api_hasil = json.loads(body_bytes.decode("utf-8"))
                    except Exception:
                        api_hasil = {"raw": body_bytes.decode("utf-8", errors="replace")}
            except urllib.error.URLError as ssl_err:
                if "CERTIFICATE_VERIFY_FAILED" in str(ssl_err):
                    unverified_ctx = ssl._create_unverified_context()
                    with urllib.request.urlopen(req, timeout=15, context=unverified_ctx) as resp:
                        api_status_code = resp.getcode()
                        body_bytes = resp.read()
                        try:
                            api_hasil = json.loads(body_bytes.decode("utf-8"))
                        except Exception:
                            api_hasil = {"raw": body_bytes.decode("utf-8", errors="replace")}
                else:
                    raise
        except urllib.error.HTTPError as e:
            api_status_code = e.code
            err_bytes = e.read()
            try:
                api_hasil = json.loads(err_bytes.decode("utf-8"))
            except Exception:
                api_hasil = {"raw": err_bytes.decode("utf-8", errors="replace")}
            api_error = f"HTTP Error {e.code}"
        except Exception as e:
            api_status_code = 0
            err_msg = str(e)
            if url:
                err_msg = err_msg.replace(url, "")
            api_error = f"Gagal menghubungi server REST API: {err_msg.strip()}"

    # 3. Simpan data hasil scan & respon ke data/hasil_simpan/
    nama_berkas_simpan = f"simpan_{waktu_str}_{sesi_id}.json"
    path_berkas_simpan = HASIL_SIMPAN_DIR / nama_berkas_simpan
    rekaman = {
        "waktu": waktu_obj.isoformat(),
        "sesi": body.sesi,
        "total_peserta": len(cleaned_data),
        "endpoint_url": url,
        "gambar_tersimpan": gambar_tersimpan,
        "data": cleaned_data,
        "api_status_code": api_status_code,
        "api_response": api_hasil,
        "api_error": api_error,
    }
    path_berkas_simpan.write_text(
        json.dumps(rekaman, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    sukses_kirim = api_status_code in (200, 201) and not api_error
    pesan = (
        f"Hasil scan {len(cleaned_data)} peserta berhasil disimpan lokal dan diproses REST API."
        if sukses_kirim
        else (
            f"Hasil scan {len(cleaned_data)} peserta aman tersimpan di lokal, namun REST API gagal dihubungi ({api_error})."
            if api_error
            else f"Hasil scan {len(cleaned_data)} peserta berhasil disimpan lokal."
        )
    )

    return {
        "sukses": sukses_kirim,
        "tersimpan_lokal": True,
        "pesan": pesan,
        "file_simpan": nama_berkas_simpan,
        "jumlah_gambar_tersimpan": len(gambar_tersimpan),
        "api_status_code": api_status_code,
        "api_response": api_hasil,
        "api_error": api_error,
    }


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)
