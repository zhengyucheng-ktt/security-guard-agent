@echo off
rem Security Guard Agent - build Docker image (requires Docker Desktop)
cd /d "%~dp0"
docker build -t security-guard-agent:latest .
echo.
echo Run:
echo   docker run -d --name guard -p 8080:8080 -v %cd%\docker-config:/app security-guard-agent
echo.
echo (first run will create config files in docker-config\)
pause
