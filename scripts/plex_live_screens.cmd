@echo off
rem Scheduled by Windows Task Scheduler (task "Plex live screens"). See scripts\plex_live_screens.py.
cd /d "%~dp0.."
if not exist etl-manual mkdir etl-manual
echo === %date% %time% >> etl-manual\live_screens.log
"C:\Python312\python.exe" scripts\plex_live_screens.py --load >> etl-manual\live_screens.log 2>&1
echo exit %errorlevel% >> etl-manual\live_screens.log
