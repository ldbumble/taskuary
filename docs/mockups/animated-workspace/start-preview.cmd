@echo off
title Taskuary 3D mockup preview
cd /d "%~dp0..\..\.."
echo Open this address in your browser:
echo http://127.0.0.1:8766/docs/mockups/animated-workspace/
echo.
echo Keep this window open while viewing the mockup.
echo Press Ctrl+C to stop the preview server.
echo.
python -m http.server 8766 --bind 127.0.0.1
pause
