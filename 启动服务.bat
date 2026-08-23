@echo off
rem Security Guard Agent - start service only (portable)
cd /d "%~dp0"
if exist "guard.exe" (
    start "SecurityGuardServer" "%~dp0guard.exe"
) else (
    where go >nul 2>nul
    if %errorlevel%==0 (
        start "SecurityGuardServer" cmd /k "cd /d %~dp0 && go run main.go"
    ) else (
        echo [ERROR] guard.exe not found and no Go toolchain. 1>&2
        pause
    )
)
