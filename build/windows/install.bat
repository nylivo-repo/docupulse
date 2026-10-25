@echo off
rem Runs install.ps1 with Windows PowerShell (no need to change the execution policy)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
