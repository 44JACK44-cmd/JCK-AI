@echo off
title NEXUS AI - Instalar VS Build Tools (C++)
echo ============================================================
echo  Instalando Visual Studio Build Tools con workload C++
echo  Requiere: aceptar el popup de Control de Cuentas de Usuario
echo  Duracion estimada: 10-20 minutos (descarga ~2-3 GB)
echo ============================================================
echo.

set "LOG=%TEMP%\vsbuild-nexus.log"

winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --silent ^
  --accept-package-agreements --accept-source-agreements ^
  --override "--wait --quiet --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" > "%LOG%" 2>&1

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo [ERROR] winget devolvio codigo %ERRORLEVEL%. Log: %LOG%
  type "%LOG%"
  pause
  exit /b 1
)

echo.
echo [OK] Instalacion completada. Buscando link.exe ...
set "LINK_FOUND=0"
for /f "delims=" %%i in ('dir /b /s "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\*\bin\Hostx64\x64\link.exe" 2^>nul') do set "LINK_FOUND=1"

if "%LINK_FOUND%"=="1" (
  echo [OK] Compilador MSVC encontrado. Ya puedes compilar NEXUS AI con:
  echo      npm run build --workspace=apps/windows
) else (
  echo [AVISO] link.exe no encontrado aun; puede tardar en registrarse.
)
echo.
pause
