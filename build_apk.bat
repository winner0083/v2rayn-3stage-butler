@echo off
setlocal
echo [1/4] Syncing web assets to www folder...
if not exist www mkdir www
copy /Y index.html www\index.html >nul
copy /Y manifest.json www\manifest.json >nul

echo [2/4] Checking Node.js and Capacitor dependencies...
if not exist node_modules (
    call npm install
)

echo [3/4] Initializing / syncing Capacitor Android platform...
if not exist android (
    call npx cap add android
) else (
    call npx cap sync android
)

echo [4/4] Building Android Debug APK via Gradle...
if exist android\gradlew.bat (
    pushd android
    call gradlew.bat assembleDebug
    popd
    echo.
    echo [DONE] APK output path: android\app\build\outputs\apk\debug\app-debug.apk
) else (
    echo [WARN] Android folder not initialized or Android SDK not found.
)
endlocal
