@echo off
rem Scheduled by Windows Task Scheduler (task "Plex live screens", hourly), which runs the
rem copy in the primary folder C:\F\Parasol\plex-to-big-query (branch main): merge, then
rem `git pull` there, for a change to reach the task. Runbook: docs\PLEX_SCREEN_EXTRACTION.md.
rem Exit codes: 0 all screens loaded, 1 a screen failed (others still loaded), 75 the
rem previous run still holds etl-manual\plex_web.lock.
cd /d "%~dp0.."
if not exist etl-manual mkdir etl-manual
rem keep the log under ~5 MB: roll it to .1 (one generation)
for %%F in (etl-manual\live_screens.log) do if %%~zF GTR 5000000 move /y etl-manual\live_screens.log etl-manual\live_screens.log.1 >nul
echo === %date% %time% >> etl-manual\live_screens.log
"C:\Python312\python.exe" scripts\plex_live_screens.py --load >> etl-manual\live_screens.log 2>&1
set rc=%errorlevel%
echo exit %rc% >> etl-manual\live_screens.log
exit /b %rc%
