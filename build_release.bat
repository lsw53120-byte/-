@echo off
setlocal
cd /d "%~dp0"

call build_exe.bat
if errorlevel 1 goto :failed

set "RELEASE_DIR=release\SearchConsoleHelper"
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"
if errorlevel 1 goto :failed

copy /y "dist\SearchConsoleHelper.exe" "%RELEASE_DIR%\SearchConsoleHelper.exe" >nul
if errorlevel 1 goto :failed
copy /y "UserGuide.txt" "%RELEASE_DIR%\UserGuide.txt" >nul
if errorlevel 1 goto :failed
copy /y "PrivacyNotice.txt" "%RELEASE_DIR%\PrivacyNotice.txt" >nul
if errorlevel 1 goto :failed
copy /y "BuyerChecklist.txt" "%RELEASE_DIR%\BuyerChecklist.txt" >nul
if errorlevel 1 goto :failed

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -LiteralPath 'release\SearchConsoleHelper' -DestinationPath 'release\SearchConsoleHelper_Windows.zip' -Force"
if errorlevel 1 goto :failed

echo.
echo Release package complete: release\SearchConsoleHelper_Windows.zip
echo Private tokens, databases, settings, reports, and Chrome profiles are excluded.
pause
exit /b 0

:failed
echo.
echo Build failed. Review the error above.
pause
exit /b 1
