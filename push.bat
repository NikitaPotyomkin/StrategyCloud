@echo off
cd /d "%~dp0"
git add .
git commit -m "upd"
git push
