@echo off
setlocal
chcp 65001 >nul
echo ============================================================
echo   v2rayN 3-Stage Butler - Local APK Build (CI-equivalent)
echo ============================================================

echo [1/6] Syncing web assets to www ...
if not exist www mkdir www
copy /Y index.html www\index.html >nul
copy /Y manifest.json www\manifest.json >nul

echo [2/6] Checking Node.js / Capacitor dependencies ...
where node >nul 2>nul || (echo [ERR] Node.js not found in PATH & exit /b 1)
if not exist node_modules ( call npm install )

echo [3/6] Initializing / syncing Capacitor Android platform ...
if not exist android ( call npx cap add android ) else ( call npx cap sync android )

echo [4/6] Downloading Xray-Core arm64-v8a (libxray.so) ...
set "XRAY_ZIP=xray-android-arm64-v8a.zip"
set "XRAY_URL=https://github.com/XTLS/Xray-core/releases/latest/download/Xray-android-arm64-v8a.zip"
set "XRAY_URL_MIRROR=https://gh-proxy.com/https://github.com/XTLS/Xray-core/releases/latest/download/Xray-android-arm64-v8a.zip"
if not exist "android\app\src\main\jniLibs\arm64-v8a" mkdir "android\app\src\main\jniLibs\arm64-v8a"
curl.exe -sSL --connect-timeout 15 --max-time 300 -o "%XRAY_ZIP%" "%XRAY_URL%" || curl.exe -sSL --connect-timeout 15 --max-time 300 -o "%XRAY_ZIP%" "%XRAY_URL_MIRROR%"
if not exist "%XRAY_ZIP%" (echo [ERR] libxray download failed & exit /b 1)
powershell -NoProfile -Command "Expand-Archive -Path '%XRAY_ZIP%' -DestinationPath 'android\app\src\main\jniLibs\arm64-v8a' -Force"
move /Y "android\app\src\main\jniLibs\arm64-v8a\xray" "android\app\src\main\jniLibs\arm64-v8a\libxray.so" >nul
del /q "%XRAY_ZIP%"

echo [5/6] Patching native engine / keystore / version ...
python patch_android_keepalive.py
if errorlevel 1 (echo [ERR] patch_android_keepalive.py failed & exit /b 1)

echo [6/6] Building Android Debug APK via Gradle ...
cd android
call gradlew.bat assembleDebug
cd ..
copy /Y "android\app\build\outputs\apk\debug\app-debug.apk" "v2rayN-3Stage-Butler-v2.0.apk"
echo.
echo [DONE] APK output: %CD%\v2rayN-3Stage-Butler-v2.0.apk
endlocal
