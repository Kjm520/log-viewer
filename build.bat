@echo off
echo Installing dependencies...
pip install rich pyinstaller

echo Killing running instances...
taskkill /F /IM LogViewer.exe

echo Building exe...
pyinstaller --onefile --name LogViewer --console log_viewer.py

echo Done! Exe is at dist\LogViewer.exe
pause
