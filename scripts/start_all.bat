@echo off
REM Windows用: 受付とクイズを同時に起動する
setlocal
python "%~dp0start_all_windows.py"
exit /b %ERRORLEVEL%
