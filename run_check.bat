@echo off
chcp 65001 > nul
cd /d "%~dp0"
py syntax_check.py > check_output.txt 2>&1
type check_output.txt
