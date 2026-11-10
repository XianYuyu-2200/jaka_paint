@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Create the project environment first: python -m venv .venv
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm JAKA_Paint.spec
if errorlevel 1 goto failed
echo Built: "%~dp0dist\JAKA_Paint\JAKA_Paint.exe"
echo Distribute the entire dist\JAKA_Paint folder, including _internal.
pause
exit /b 0
:failed
echo Build failed. See the error above.
pause
exit /b 1
