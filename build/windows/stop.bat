@echo off
rem Runs stop.ps1 with Windows PowerShell (no need to change the execution policy)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1" %*
