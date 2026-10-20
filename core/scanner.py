import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


from typing import Callable, Optional
import time


class ScannerError(Exception):
    pass


def _pantau_proses_scan(
    proc: subprocess.Popen,
    folder: Path,
    pola_glob: str,
    jumlah: int = 0,
    callback_progress: Optional[Callable[[int, int, str], None]] = None,
    timeout_inaktif: Optional[float] = 30.0,
    timeout_maks: Optional[float] = None,
) -> tuple[int, str, str]:
    """
    Memantau berkas gambar baru yang dihasilkan scanner secara real-time.
    Memanggil callback_progress setiap kali ada lembar baru yang selesai dipindai.
    """
    waktu_mulai = time.time()
    waktu_terakhir_aktivitas = time.time()
    waktu_terakhir_laporan = time.time()
    terdeteksi = set()

    if callback_progress:
        if jumlah and jumlah > 0:
            callback_progress(0, jumlah, f"Scanner: Memulai pemindaian {jumlah} lembar...")
        else:
            callback_progress(0, 0, "Scanner: Memulai pemindaian otomatis dari ADF (dinamis)...")

    while proc.poll() is None:
        sekarang = time.time()
        ada_file_baru = False
        for p in glob.glob(pola_glob):
            if p not in terdeteksi:
                try:
                    if os.path.getsize(p) > 0:
                        terdeteksi.add(p)
                        ada_file_baru = True
                        waktu_terakhir_aktivitas = sekarang
                        n = len(terdeteksi)
                        if callback_progress:
                            if jumlah and jumlah > 0:
                                callback_progress(
                                    n, jumlah, f"Scanner: Memindai lembar {n}/{jumlah}..."
                                )
                            else:
                                callback_progress(
                                    n, 0, f"Scanner: Lembar ke-{n} berhasil dipindai..."
                                )
                except OSError:
                    pass

        # Berikan status berkala jika proses scanner masih aktif berjalan
        if not ada_file_baru and (sekarang - waktu_terakhir_laporan >= 5.0):
            waktu_terakhir_laporan = sekarang
            durasi = int(sekarang - waktu_mulai)
            menit, detik = divmod(durasi, 60)
            teks_durasi = f"{menit}m {detik:02d}s" if menit > 0 else f"{detik}s"
            if callback_progress:
                n = len(terdeteksi)
                if n > 0:
                    if jumlah and jumlah > 0:
                        callback_progress(
                            n, jumlah, f"Scanner: Sedang memindai ({n}/{jumlah} lembar, berjalan {teks_durasi})..."
                        )
                    else:
                        callback_progress(
                            n, 0, f"Scanner: Sedang memindai ({n} lembar selesai, berjalan {teks_durasi})..."
                        )
                else:
                    callback_progress(
                        0,
                        jumlah if (jumlah and jumlah > 0) else 0,
                        f"Scanner: Mesin scanner sedang aktif memindai lembar di ADF ({teks_durasi})...",
                    )

        # Cek batas waktu tidak ada respons
        if timeout_inaktif is not None and (sekarang - waktu_terakhir_aktivitas > timeout_inaktif):
            proc.kill()
            raise ScannerError(
                f"Scanner tidak merespons selama {int(timeout_inaktif)} detik "
                "(kemungkinan mesin masuk mode Sleep atau kabel USB tertidur). "
                "Silakan tekan tombol Power di mesin scanner atau cabut-colok kabel USB, lalu coba lagi."
            )
        if timeout_maks is not None and (sekarang - waktu_mulai > timeout_maks):
            proc.kill()
            raise ScannerError("Batas waktu pemindaian maksimal terlampaui.")

        time.sleep(0.3)

    stdout, stderr = proc.communicate()
    for p in glob.glob(pola_glob):
        if p not in terdeteksi:
            try:
                if os.path.getsize(p) > 0:
                    terdeteksi.add(p)
            except OSError:
                pass

    return proc.returncode, stdout or "", stderr or ""


class ScannerBase:
    nama = "dasar"

    def tersedia(self) -> bool:
        raise NotImplementedError

    def scan_batch(
        self,
        folder: Path,
        prefix: str,
        jumlah: int = 0,
        dpi: int = 300,
        callback_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[Path]:
        """Scan `jumlah` lembar dari ADF. Jika jumlah <= 0, scan sampai ADF kosong. Return daftar file hasil."""
        raise NotImplementedError


class ScannerSANE(ScannerBase):
    """Ubuntu/Linux: scanimage. Tanpa sudo (user harus ada di grup 'scanner')."""
    _cache_device: Optional[tuple[str, str, float]] = None

    @property
    def nama(self) -> str:
        try:
            _, desc = self._cari_device()
            return f"SANE ({desc})"
        except Exception:
            return "SANE (scanimage)"

    def tersedia(self):
        return shutil.which("scanimage") is not None

    def _cari_device(self, force_refresh: bool = False) -> tuple[str, str]:
        now = time.time()
        if not force_refresh and self._cache_device and (now - self._cache_device[2] < 10.0):
            return self._cache_device[0], self._cache_device[1]

        r = subprocess.run(["scanimage", "-L"], capture_output=True, text=True)
        matches = re.findall(r"device `([^']+)' is a (.*)", r.stdout)
        kandidat = []
        for dev, desc in matches:
            dev_l = dev.lower()
            desc_l = desc.lower()
            if dev_l.startswith("v4l") or "webcam" in desc_l or "virtual device" in desc_l:
                continue
            kandidat.append((dev, desc.strip()))

        if not kandidat:
            m = re.search(r"device `([^']+)'", r.stdout)
            if m and not m.group(1).startswith("v4l"):
                kandidat.append((m.group(1), "Scanner"))

        if not kandidat:
            raise ScannerError("Scanner tidak ditemukan. Cek kabel USB dan pastikan mesin menyala.")

        # Prioritaskan scanner dokumen ADF USB (Fujitsu, Brother, dsb.)
        terpilih = kandidat[0]
        for dev, desc in kandidat:
            d_lower = (dev + " " + desc).lower()
            if "fujitsu" in d_lower or "brother" in d_lower:
                terpilih = (dev, desc)
                break

        self._cache_device = (terpilih[0], terpilih[1], now)
        return terpilih

    def _tentukan_source(self, device: str) -> Optional[str]:
        dev_l = device.lower()
        if "fujitsu" in dev_l:
            return "ADF Front"
        elif "brother" in dev_l:
            return "Automatic Document Feeder(left aligned)"
        
        try:
            r = subprocess.run(
                ["scanimage", f"--device-name={device}", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = r.stdout + r.stderr
            if "ADF Front" in out:
                return "ADF Front"
            elif "Automatic Document Feeder(left aligned)" in out:
                return "Automatic Document Feeder(left aligned)"
            elif "Automatic Document Feeder" in out:
                return "Automatic Document Feeder"
            elif "ADF" in out:
                return "ADF"
        except Exception:
            pass
        return None

    def _tentukan_mode(self, device: str) -> Optional[str]:
        dev_l = device.lower()
        if "fujitsu" in dev_l:
            return "Color"
        elif "brother" in dev_l:
            return "24bit Color"
        
        try:
            r = subprocess.run(
                ["scanimage", f"--device-name={device}", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = r.stdout + r.stderr
            if "24bit Color" in out:
                return "24bit Color"
            elif "Color" in out:
                return "Color"
        except Exception:
            pass
        return "Color"

    def scan_batch(
        self,
        folder,
        prefix,
        jumlah=0,
        dpi=300,
        callback_progress=None,
    ):
        device, desc = self._cari_device()
        pola = str(folder / f"{prefix}_%03d.png")
        cmd = [
            "scanimage", f"--device-name={device}",
            f"--resolution={dpi}", "--format=png",
            f"--batch={pola}", "--batch-start=1",
        ]
        source = self._tentukan_source(device)
        if source:
            cmd.insert(2, f"--source={source}")
        mode = self._tentukan_mode(device)
        if mode:
            cmd.insert(3, f"--mode={mode}")

        if jumlah and jumlah > 0:
            cmd.append(f"--batch-count={jumlah}")

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        ret, stdout, stderr = _pantau_proses_scan(
            proc,
            folder,
            str(folder / f"{prefix}_*.png"),
            jumlah=jumlah,
            callback_progress=callback_progress,
            timeout_inaktif=30.0,
        )
        if ret not in (0, 7):      # 7 = ADF habis (normal di Brother), 0 = normal
            gabungan_err = (stderr + " " + stdout).lower()
            if "out of documents" not in gabungan_err:
                raise ScannerError(f"Scan gagal (kode {ret}): {stderr.strip()[-300:]}")

        files = sorted(Path(p) for p in glob.glob(str(folder / f"{prefix}_*.png")))
        if jumlah and jumlah > 0:
            files = files[:jumlah]

        try:
            from . import omr
            for f in files:
                img = omr.baca_gambar(f)
                if img is not None:
                    pangkas = omr.pangkas_putih_bawah(img)
                    if pangkas.shape != img.shape:
                        omr.tulis_gambar(f, pangkas)
        except Exception:
            pass
        return files


import xml.etree.ElementTree as ET


class ScannerNAPS2(ScannerBase):
    """Windows (dan Linux): NAPS2.Console. Mendukung Profil GUI NAPS2 dan deteksi device WIA/TWAIN/ESCL."""
    nama = "NAPS2"

    def _exe(self):
        app_dir = Path(os.path.dirname(sys.executable)) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        kandidat = [
            shutil.which("NAPS2.Console"),
            shutil.which("naps2"),
            r"C:\Program Files\NAPS2\NAPS2.Console.exe",
            r"C:\Program Files (x86)\NAPS2\NAPS2.Console.exe",
            str(Path.home() / "AppData" / "Local" / "Programs" / "NAPS2" / "NAPS2.Console.exe"),
            str(app_dir / "NAPS2.Console.exe"),
            str(app_dir / "naps2" / "NAPS2.Console.exe"),
        ]
        for k in kandidat:
            if k and os.path.exists(k):
                return k
        return None

    def tersedia(self):
        return self._exe() is not None

    def _baca_daftar_profil(self, exe: str) -> list[dict[str, str]]:
        """Membaca daftar profil tersimpan di NAPS2 (dari profiles.xml)."""
        candidates = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "NAPS2" / "profiles.xml")
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            candidates.append(Path(localappdata) / "NAPS2" / "profiles.xml")
        progdata = os.environ.get("ProgramData")
        if progdata:
            candidates.append(Path(progdata) / "NAPS2" / "profiles.xml")

        exe_p = Path(exe)
        candidates.append(exe_p.parent / "profiles.xml")
        candidates.append(exe_p.parent / "Data" / "profiles.xml")
        candidates.append(Path.home() / "AppData" / "Roaming" / "NAPS2" / "profiles.xml")
        candidates.append(Path.home() / ".config" / "naps2" / "profiles.xml")

        profils = []
        for p in candidates:
            if p.is_file():
                try:
                    tree = ET.parse(p)
                    root = tree.getroot()
                    for sp in root.findall(".//ScanProfile"):
                        disp = sp.find("DisplayName")
                        disp_name = disp.text.strip() if (disp is not None and disp.text) else ""
                        dev = sp.find(".//Device/Name")
                        dev_name = dev.text.strip() if (dev is not None and dev.text) else ""
                        drv = sp.find("DriverName")
                        drv_name = drv.text.strip().lower() if (drv is not None and drv.text) else ""
                        nama_profil = disp_name or dev_name
                        if nama_profil:
                            profils.append({
                                "name": nama_profil,
                                "device": dev_name,
                                "driver": drv_name,
                            })
                    if profils:
                        break
                except Exception:
                    pass
        return profils

    def _cari_device_cli(self, exe: str) -> list[tuple[str, str]]:
        """Mencari nama scanner yang terhubung lewat CLI naps2.console --listdevices."""
        hasil = []
        # Driver yang didukung Windows: WIA, TWAIN, eSCL
        for drv in ["wia", "twain", "escl"]:
            try:
                r = subprocess.run([exe, "--listdevices", "--driver", drv],
                                   capture_output=True, text=True, timeout=8)
                for baris in (r.stdout or "").splitlines():
                    baris = baris.strip()
                    if not baris or baris.lower().startswith(("error", "warning", "exception", "failed", "unhandled")):
                        continue
                    if baris.lower().startswith("name:"):
                        baris = baris[5:].strip()
                    elif baris.lower().startswith("id:"):
                        continue
                    if baris and (drv, baris) not in hasil:
                        hasil.append((drv, baris))
            except Exception:
                pass

        if not hasil:
            try:
                r = subprocess.run([exe, "--listdevices"],
                                   capture_output=True, text=True, timeout=8)
                for baris in (r.stdout or "").splitlines():
                    baris = baris.strip()
                    if not baris or baris.lower().startswith(("error", "warning", "exception", "failed", "unhandled")):
                        continue
                    if baris.lower().startswith("name:"):
                        baris = baris[5:].strip()
                    elif baris.lower().startswith("id:"):
                        continue
                    if baris and ("wia", baris) not in hasil:
                        hasil.append(("wia", baris))
            except Exception:
                pass

        return hasil

    def scan_batch(self, folder, prefix, jumlah=0, dpi=300, callback_progress=None):
        exe = self._exe()
        if not exe:
            raise ScannerError("NAPS2 belum terpasang. Unduh gratis di naps2.com atau pakai mode Upload.")

        # {nnn} = penomoran otomatis NAPS2
        keluaran = str(folder / f"{prefix}_$(nnn).png")

        # Susun daftar variasi perintah pemindaian berdasarkan prioritas
        perintah_kandidat = []

        # 1. Gunakan Profil NAPS2 yang sudah tersimpan di GUI jika ada
        profil_tersimpan = self._baca_daftar_profil(exe)
        for prof in profil_tersimpan:
            nama_p = prof["name"]
            # Coba sesuai konfigurasi profil
            perintah_kandidat.append([exe, "-o", keluaran, "-p", nama_p, "--source", "feeder", "--dpi", str(dpi), "--force"])
            # Fallback TWAIN (scanner Brother di Windows sangat stabil menggunakan driver TWAIN)
            perintah_kandidat.append([exe, "-o", keluaran, "-p", nama_p, "--driver", "twain", "--source", "feeder", "--dpi", str(dpi), "--force"])
            perintah_kandidat.append([exe, "-o", keluaran, "-p", nama_p, "--driver", "wia", "--source", "feeder", "--dpi", str(dpi), "--force"])
            # Jika 1 lembar atau feeder tidak ada/kosong, coba glass / tanpa argumen source
            if jumlah == 1:
                perintah_kandidat.append([exe, "-o", keluaran, "-p", nama_p, "--source", "glass", "--dpi", str(dpi), "--force"])
                perintah_kandidat.append([exe, "-o", keluaran, "-p", nama_p, "--driver", "twain", "--source", "glass", "--dpi", str(dpi), "--force"])
                perintah_kandidat.append([exe, "-o", keluaran, "-p", nama_p, "--dpi", str(dpi), "--force"])

        # 2. Gunakan profil default / most-recently-used di NAPS2 tanpa flag --profile
        perintah_kandidat.append([exe, "-o", keluaran, "--source", "feeder", "--dpi", str(dpi), "--force"])
        perintah_kandidat.append([exe, "-o", keluaran, "--driver", "twain", "--source", "feeder", "--dpi", str(dpi), "--force"])
        if jumlah == 1:
            perintah_kandidat.append([exe, "-o", keluaran, "--source", "glass", "--dpi", str(dpi), "--force"])
            perintah_kandidat.append([exe, "-o", keluaran, "--dpi", str(dpi), "--force"])

        # 3. Jika profil belum dibuat, deteksi device scanner secara otomatis dari CLI
        devices = self._cari_device_cli(exe)
        for drv, dev_name in devices:
            perintah_kandidat.append([exe, "-o", keluaran, "--noprofile", "--driver", drv, "--device", dev_name, "--source", "feeder", "--dpi", str(dpi), "--force"])
            if drv != "twain":
                perintah_kandidat.append([exe, "-o", keluaran, "--noprofile", "--driver", "twain", "--device", dev_name, "--source", "feeder", "--dpi", str(dpi), "--force"])
            if jumlah == 1:
                perintah_kandidat.append([exe, "-o", keluaran, "--noprofile", "--driver", drv, "--device", dev_name, "--source", "glass", "--dpi", str(dpi), "--force"])
                perintah_kandidat.append([exe, "-o", keluaran, "--noprofile", "--driver", drv, "--device", dev_name, "--dpi", str(dpi), "--force"])

        pesan_error_terakhir = ""
        ada_perangkat_terdeteksi = bool(profil_tersimpan or devices)

        for cmd in perintah_kandidat:
            try:
                # Bersihkan berkas PNG parsial jika ada dari percobaan sebelumnya
                for f in glob.glob(str(folder / f"{prefix}_*.png")):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                ret, stdout, stderr = _pantau_proses_scan(
                    proc,
                    folder,
                    str(folder / f"{prefix}_*.png"),
                    jumlah=jumlah,
                    callback_progress=callback_progress,
                )
                if ret == 0:
                    hasil = sorted(Path(p) for p in glob.glob(str(folder / f"{prefix}_*.png")))
                    if hasil:
                        return hasil[:jumlah] if (jumlah and jumlah > 0) else hasil
                else:
                    err = (stderr or stdout or "").strip()
                    if err:
                        pesan_error_terakhir = err
                    if "no device was specified" not in err.lower():
                        ada_perangkat_terdeteksi = True
            except ScannerError:
                raise
            except Exception as e:
                pesan_error_terakhir = str(e)

        # Cek apakah ada file yang sempat tersimpan
        hasil = sorted(Path(p) for p in glob.glob(str(folder / f"{prefix}_*.png")))
        if hasil:
            return hasil[:jumlah] if (jumlah and jumlah > 0) else hasil

        # Format pesan error yang solutif bagi pengguna
        if not ada_perangkat_terdeteksi or "no device was specified" in pesan_error_terakhir.lower():
            raise ScannerError(
                "Scanner fisik belum terhubung atau belum dikonfigurasi di NAPS2.\n"
                "Solusi:\n"
                "1. Pastikan kabel USB scanner terhubung ke laptop/PC & scanner sudah menyala.\n"
                "2. Buka aplikasi NAPS2 di Windows, klik menu 'Profiles' -> 'New', pilih scanner Anda lalu klik 'Save'.\n"
                "3. Atau gunakan tombol 'Unggah gambar' jika ingin mengunggah file hasil scan secara manual."
            )
        elif "could not be found" in pesan_error_terakhir.lower() or "not found" in pesan_error_terakhir.lower():
            raise ScannerError(
                "Scanner Brother tidak ditemukan oleh sistem ('The selected scanner could not be found').\n"
                "Solusi:\n"
                "1. Buka aplikasi NAPS2 (ada di taskbar Anda) -> klik Profiles -> klik Edit profil Brother:\n"
                "   - Ubah Driver dari WIA ke TWAIN.\n"
                "   - Klik tombol 'Choose Device' dan pilih 'TW-Brother...'.\n"
                "2. Pastikan aplikasi VueScan sudah DITUTUP agar koneksi USB tidak terkunci.\n"
                "3. ATAU CARA TERCEPAT: Scan dari VueScan, lalu cukup klik tombol 'Unggah gambar' di samping."
            )
        elif "feeder" in pesan_error_terakhir.lower() and ("empty" in pesan_error_terakhir.lower() or "paper" in pesan_error_terakhir.lower()):
            raise ScannerError("Kertas tidak terdeteksi di ADF (Feeder). Masukkan lembar kertas ke penampung ADF scanner lalu coba lagi.")
        else:
            ringkas = pesan_error_terakhir[-300:] if pesan_error_terakhir else "Periksa sambungan kabel & driver scanner."
            raise ScannerError(f"Scan gagal: {ringkas}")


def daftar_backend() -> list[ScannerBase]:
    urutan = [ScannerSANE(), ScannerNAPS2()] if sys.platform.startswith("linux") \
        else [ScannerNAPS2(), ScannerSANE()]
    return [b for b in urutan if b.tersedia()]


def scanner_aktif() -> ScannerBase | None:
    b = daftar_backend()
    return b[0] if b else None
