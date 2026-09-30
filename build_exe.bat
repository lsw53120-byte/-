@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
py -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "SearchConsole진단도구" ^
  --collect-all customtkinter ^
  --collect-all selenium ^
  --add-data "data\indexed_history.json;data" ^
  main.py
if errorlevel 1 exit /b 1
echo.
echo 빌드 완료: dist\SearchConsole진단도구.exe
echo 사용자 데이터는 실행파일과 분리되어 %%LOCALAPPDATA%%\SearchConsoleTool 에 저장됩니다.
pause
