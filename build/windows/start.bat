@echo off
rem Runs start.ps1 with Windows PowerShell (no need to change the execution policy)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
