@echo off
echo Installing dependencies...
pip install rich pyinstaller

echo Killing running instances...
taskkill /F /IM LogViewer.exe

echo Building exe...
pyinstaller LogViewer.spec

echo Done! Exe is at dist\LogViewer.exe
