@echo off
REM One-click launcher for Windows: locates Git Bash and hands over to run.sh
REM (the MSYS bash in Git's usr\bin, NOT C:\Windows\System32\bash.exe which is WSL)

setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title travel_system dev

set "BASH_EXE="

for %%P in (
  "%ProgramFiles%\Git\bin\bash.exe"
  "%ProgramFiles(x86)%\Git\bin\bash.exe"
  "%LocalAppData%\Programs\Git\bin\bash.exe"
) do (
  if not defined BASH_EXE if exist "%%~P" set "BASH_EXE=%%~P"
)

if not defined BASH_EXE (
  for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\GitForWindows" /v InstallPath 2^>nul ^| findstr /i "InstallPath"') do (
    if exist "%%B\bin\bash.exe" set "BASH_EXE=%%B\bin\bash.exe"
  )
)

if not defined BASH_EXE (
  for /f "delims=" %%P in ('where bash 2^>nul') do (
    if not defined BASH_EXE (
      echo %%P | findstr /i /c:"system32" /c:"windowsapps" >nul || set "BASH_EXE=%%P"
    )
  )
)

if not defined BASH_EXE (
  echo [error] Git Bash not found.
  echo         Install Git for Windows first: https://git-scm.com/download/win
  echo.
  pause
  exit /b 1
)

"%BASH_EXE%" "%~dp0run.sh" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo [run] launcher exited with code %RC%
  pause
)

exit /b %RC%
