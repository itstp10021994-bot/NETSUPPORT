@echo off
REM Build standalone .exe files for Windows (run this on a Windows machine).
REM Output lands in packaging\dist\ : classroom-hub.exe and classroom-student.exe

cd /d "%~dp0"

python -m pip install --upgrade pyinstaller
if errorlevel 1 goto :err

echo.
echo ^>^> Building hub (teacher console)...
python -m PyInstaller hub.spec --distpath .\dist --workpath .\build --noconfirm
if errorlevel 1 goto :err

echo.
echo ^>^> Building student agent...
python -m PyInstaller student.spec --distpath .\dist --workpath .\build --noconfirm
if errorlevel 1 goto :err

echo.
echo Done. Executables in packaging\dist\:
dir /b .\dist
goto :eof

:err
echo Build failed.
exit /b 1
