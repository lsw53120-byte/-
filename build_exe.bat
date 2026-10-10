@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found. Install 64-bit Python 3.11 first.
  exit /b 1
)

py -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

py -m PyInstaller --noconfirm --clean --onefile --windowed --name SearchConsoleHelper --paths "%CD%" --collect-all customtkinter --collect-all selenium --collect-submodules automation --collect-submodules core --collect-submodules gui --collect-submodules reports --collect-submodules storage --collect-submodules utils --hidden-import reports.html_report main.py
if errorlevel 1 exit /b 1

start /wait "" "dist\SearchConsoleHelper.exe" --smoke-test
if errorlevel 1 (
  echo Packaged executable smoke test failed.
  exit /b 1
)

echo.
echo Build complete: dist\SearchConsoleHelper.exe
echo User data is stored separately under LOCALAPPDATA\SearchConsoleTool.
