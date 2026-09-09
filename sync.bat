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
        echo .vscode/
        echo .idea/
        echo *.log
        echo .DS_Store
        echo Thumbs.db
    ) > .gitignore
    echo [SETUP] .gitignore created.
)

:: ── Get current branch ────────────────────
for /f %%i in ('git branch --show-current 2^>nul') do set CURRENT_BRANCH=%%i
if "%CURRENT_BRANCH%"=="" (
    echo [ERROR] No branch found. Creating main...
    git branch -M main
    set CURRENT_BRANCH=main
)
echo [INFO] Current branch: %CURRENT_BRANCH%

:: ── Sync ──────────────────────────────────
echo.
echo [1/3] Adding changes...
git add .

set msg=update
set /p msg=Enter commit message (or press Enter for 'update'): 
if "%msg%"=="" set msg=update

echo [2/3] Committing...
git commit -m "%msg%" --no-verify

:: ── Pull latest changes (avoid conflicts) ──
echo [INFO] Pulling latest changes from remote...
git pull origin %CURRENT_BRANCH% --no-rebase --allow-unrelated-histories
if errorlevel 1 (
    echo [WARN] Pull failed. Continuing with push...
)

:: ── Push to GitHub ────────────────────────
echo [3/3] Pushing to GitHub...
git push origin %CURRENT_BRANCH% --force-with-lease
if errorlevel 1 (
    echo [WARN] Push rejected. Trying force push...
    git push origin %CURRENT_BRANCH% --force
    if errorlevel 1 (
        echo [ERROR] Force push failed. Check your connection and permissions.
        pause
        exit /b 1
    )
)

:: ── Set upstream (first push) ─────────────
git branch --set-upstream-to=origin/%CURRENT_BRANCH% %CURRENT_BRANCH% >nul 2>&1

echo.
echo ===========================================
echo   ✅ DONE! admin-panel/ is now on GitHub.
echo   🌐 Repo: https://github.com/TheLecxo/Donate-Notifer
echo   📂 On server: bash admin-panel/manager.sh  then option 2
echo ===========================================
pause