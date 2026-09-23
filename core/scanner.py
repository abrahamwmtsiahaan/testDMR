import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


class ScannerError(Exception):
    pass


class ScannerBase:
    nama = "dasar"

    def tersedia(self) -> bool:
        raise NotImplementedError

    def scan_batch(self, folder: Path, prefix: str, jumlah: int, dpi: int = 300) -> list[Path]:
        """Scan `jumlah` lembar dari ADF. Return daftar file hasil, terurut."""
        raise NotImplementedError


class ScannerSANE(ScannerBase):
    """Ubuntu/Linux: scanimage. Tanpa sudo (user harus ada di grup 'scanner')."""
    nama = "SANE (scanimage)"

    def tersedia(self):
        return shutil.which("scanimage") is not None

    def _cari_device(self):
        r = subprocess.run(["scanimage", "-L"], capture_output=True, text=True)
        m = re.search(r"device `(.*?)'", r.stdout)
        if not m:
            raise ScannerError("Scanner tidak ditemukan. Cek kabel USB dan pastikan mesin menyala.")
        return m.group(1)

    def scan_batch(self, folder, prefix, jumlah, dpi=300):
        device = self._cari_device()
        pola = str(folder / f"{prefix}_%03d.png")
        cmd = [
            "scanimage", f"--device-name={device}",
            "--source=Automatic Document Feeder(left aligned)",
            f"--resolution={dpi}", "--format=png",
            f"--batch={pola}", "--batch-start=1", f"--batch-count={jumlah}",
        ]
        r = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        if r.returncode not in (0, 7):      # 7 = ADF habis (normal)
            raise ScannerError(f"Scan gagal (kode {r.returncode}): {r.stderr.strip()[-300:]}")
        return sorted(Path(p) for p in glob.glob(str(folder / f"{prefix}_*.png")))


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

    def scan_batch(self, folder, prefix, jumlah, dpi=300):
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
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if r.returncode == 0:
                    hasil = sorted(Path(p) for p in glob.glob(str(folder / f"{prefix}_*.png")))
                    if hasil:
                        return hasil[:jumlah] if jumlah else hasil
                else:
                    err = (r.stderr or r.stdout or "").strip()
                    if err:
                        pesan_error_terakhir = err
                    if "no device was specified" not in err.lower():
                        ada_perangkat_terdeteksi = True
            except subprocess.TimeoutExpired:
                pesan_error_terakhir = "Waktu pemindaian scanner habis (timeout 120 detik)."
            except Exception as e:
                pesan_error_terakhir = str(e)

        # Cek apakah ada file yang sempat tersimpan
        hasil = sorted(Path(p) for p in glob.glob(str(folder / f"{prefix}_*.png")))
        if hasil:
            return hasil[:jumlah] if jumlah else hasil

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
