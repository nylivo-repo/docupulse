@echo off
rem Runs status.ps1 with Windows PowerShell (no need to change the execution policy)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0status.ps1" %*
