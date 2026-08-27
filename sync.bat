@echo off
setlocal enabledelayedexpansion
cls
echo ===========================================
echo   SYNC  admin-panel/  TO GITHUB
echo ===========================================

cd /d "%~dp0"

:: ── Git init ──────────────────────────────
if not exist ".git" (
    echo [SETUP] Initializing git...
    git init
    git branch -M main
)

:: ── Remote ────────────────────────────────
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    set /p REMOTE_URL=Enter GitHub repo URL for admin-panel e.g. https://github.com/TheLecxo/NatsukiAIBot : 
    git remote add origin "!REMOTE_URL!"
    echo [SETUP] Remote set.
)

:: ── .gitignore ────────────────────────────
if not exist ".gitignore" (
    echo [SETUP] Creating .gitignore...
    (
        echo node_modules/
        echo dist/
        echo .env
        echo *.env
        echo .bun/
    ) > .gitignore
    echo [SETUP] .gitignore created.
)

:: ── Sync ──────────────────────────────────
echo.
echo [1/3] Adding changes...
git add .

set msg=update
set /p msg=Enter commit message (or press Enter for 'update'): 
if "%msg%"=="" set msg=update

echo [2/3] Committing...
git commit -m "%msg%" --no-verify

echo [3/3] Pushing to GitHub...
git push origin main --force-with-lease
if errorlevel 1 (
    echo [WARN] Push rejected. Force pushing...
    git push origin main --force
)

echo.
echo ===========================================
echo   DONE! admin-panel/ is now on GitHub.
echo   On server: bash admin-panel/manager.sh  then option 2
echo ===========================================
pause
