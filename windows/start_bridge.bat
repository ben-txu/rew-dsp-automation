@echo off
rem ── start_bridge.bat ─────────────────────────────────────────────
rem Starts the DSP solo bridge. Put a SHORTCUT to this file into the
rem Startup folder (Win+R -> shell:startup) so it launches with
rem Windows. Uses pythonw.exe for a windowless background process;
rem change to python.exe if you want a visible console for debugging.

cd /d "%~dp0"
start "DSP Solo Bridge" /min pythonw.exe solo_bridge.py
