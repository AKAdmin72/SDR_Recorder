@echo off
setlocal

cd /d "%~dp0"

git add -A

set "COMMIT_MSG="
set /p COMMIT_MSG=Commit message:
if "%COMMIT_MSG%"=="" (
    echo Commit message cannot be empty. Aborting.
    exit /b 1
)

git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo Commit failed or nothing to commit. Aborting push.
    exit /b 1
)

git push

echo Done.
