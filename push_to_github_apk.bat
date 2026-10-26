@echo off
setlocal
echo ============================================================
echo   Option B: Push to GitHub Actions for Automatic APK Build
echo ============================================================
echo.
if not exist www mkdir www
copy /Y index.html www\index.html >nul
copy /Y manifest.json www\manifest.json >nul

if not exist .git (
    echo [1/3] Initializing Git repository...
    git init
    git branch -M main
)

echo [2/3] Staging all project files...
git add index.html www/index.html manifest.json www/manifest.json package.json capacitor.config.json pc_bridge_server.py build_apk.bat push_to_github_apk.bat .github/workflows/build-apk.yml
git commit -m "feat: v2rayN 3-stage butler v2.0 extensible sources, dual-channel probe, 90-day purge"

echo.
echo [3/3] Ready to push to GitHub!
echo Run the following commands with your GitHub repository URL:
echo   git remote add origin https://github.com/YOUR_USERNAME/v2rayn-3stage-app.git
echo   git push -u origin main
echo.
echo Once pushed, open your GitHub repo -> Actions tab -> download v2rayN-3Stage-Butler-v2.0-debug-apk!
endlocal
