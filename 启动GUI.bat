@echo off
rem Security Guard Agent GUI launcher (portable)
cd /d "%~dp0"
if exist "guard_gui.exe" (
    start "" "%~dp0guard_gui.exe"
    exit /b
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0guard_gui.pyw"
) else (
    python "%~dp0guard_gui.pyw"
)
