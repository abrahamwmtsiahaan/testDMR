@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   BUILD LJK READER KE EXECUTABLE WINDOWS (.EXE)
echo ========================================================
echo.

:: Pindah ke folder script (windows_build/)
cd /d "%~dp0"

:: 1. Cek apakah Python terpasang di Windows
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python tidak terdeteksi di sistem PATH Windows!
    echo Silakan unduh dan pasang Python (versi 3.10 - 3.12 direkomendasikan) dari python.org.
    echo Pastikan centang "Add Python to PATH" saat menginstall.
    echo.
    pause
    exit /b 1
)

echo [1/4] Memeriksa virtual environment lokal di windows_build\venv_win...
if not exist "venv_win" (
    echo Membuat virtual environment khusus build...
    python -m venv venv_win
    if errorlevel 1 (
        echo [ERROR] Gagal membuat virtual environment.
        pause
        exit /b 1
    )
)

echo [2/4] Mengaktifkan virtual environment...
call venv_win\Scripts\activate.bat

echo [3/4] Menginstall dependencies dari requirements.txt...
python -m pip install --upgrade pip
pip install -r ..\requirements.txt
pip install pyinstaller

echo [4/4] Menjalankan PyInstaller...
:: Hapus direktori build dan dist lama jika ada
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

pyinstaller --noconfirm --workpath "build" --distpath "dist" "app.spec"

if errorlevel 1 (
    echo.
    echo [ERROR] Terjadi kesalahan saat proses build PyInstaller!
    echo Silakan periksa pesan error di atas.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo  BUILD BERHASIL!
echo ========================================================
echo  File executable (.exe) tersimpan di:
echo  %~dp0dist\LJK_Reader.exe
echo.
echo  Catatan:
echo  1. Anda cukup menyalin file 'LJK_Reader.exe' ke komputer target Windows.
echo  2. Saat pertama kali dijalankan, aplikasi akan otomatis membuka browser
echo     (http://127.0.0.1:8000) dan membuat folder 'data' serta 'hasil_scan_gambar'.
echo  3. Jika ingin mengubah URL REST API, buat file '.env' di sebelah 'LJK_Reader.exe'.
echo ========================================================
echo.
pause
