@echo off
echo Installing dependencies...
pip install rich pyinstaller

echo Building exe...
pyinstaller --onefile --name LogViewer --console log_viewer.py

echo Done! Exe is at dist\LogViewer.exe
pause
