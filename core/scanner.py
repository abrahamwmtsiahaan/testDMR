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


class ScannerNAPS2(ScannerBase):
    """Windows (dan Linux): NAPS2.Console. Pakai WIA/TWAIN/ESCL sesuai driver."""
    nama = "NAPS2"

    def _exe(self):
        kandidat = [
            shutil.which("NAPS2.Console"),
            shutil.which("naps2"),
            r"C:\Program Files\NAPS2\NAPS2.Console.exe",
            r"C:\Program Files (x86)\NAPS2\NAPS2.Console.exe",
        ]
        for k in kandidat:
            if k and os.path.exists(k):
                return k
        return None

    def tersedia(self):
        return self._exe() is not None

    def scan_batch(self, folder, prefix, jumlah, dpi=300):
        exe = self._exe()
        if not exe:
            raise ScannerError("NAPS2 belum terpasang. Unduh gratis di naps2.com atau pakai mode Upload.")
        # {nnn} = penomoran otomatis NAPS2
        keluaran = str(folder / f"{prefix}_$(nnn).png")
        cmd = [exe, "-o", keluaran, "--noprofile", "--driver", "wia",
               "--source", "feeder", "--dpi", str(dpi), "--force"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise ScannerError(f"Scan gagal: {(r.stderr or r.stdout).strip()[-300:]}")
        hasil = sorted(Path(p) for p in glob.glob(str(folder / f"{prefix}_*.png")))
        return hasil[:jumlah] if jumlah else hasil


def daftar_backend() -> list[ScannerBase]:
    urutan = [ScannerSANE(), ScannerNAPS2()] if sys.platform.startswith("linux") \
        else [ScannerNAPS2(), ScannerSANE()]
    return [b for b in urutan if b.tersedia()]


def scanner_aktif() -> ScannerBase | None:
    b = daftar_backend()
    return b[0] if b else None
