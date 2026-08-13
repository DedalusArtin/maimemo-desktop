@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONPATH=
title 墨墨开放API Web端
"G:\miniconda\envs\dedalus_hermes\python.exe" server.py
pause
