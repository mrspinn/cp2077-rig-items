@echo off
rem Drag rig mod zips/rars/7z files (or .archive files) onto this file.
rem Writes RigItems.zip next to this file. Uses rigs.json from this folder if present.
setlocal
set "HERE=%~dp0"
if "%~1"=="" (
  echo Drag one or more rig mod files onto rigitems.bat.
  pause
  exit /b 1
)
set "PYTHONPATH=%HERE%;%PYTHONPATH%"
set "RIGS="
if exist "%HERE%rigs.json" set RIGS=--rigs "%HERE%rigs.json"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% -m rigitems build %* -o "%HERE%RigItems.zip" %RIGS%
pause
