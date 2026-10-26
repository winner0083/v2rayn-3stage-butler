#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Injects Native Android Screen-Off Background Keep-Alive Capabilities into Capacitor Android Project:
1. AndroidManifest.xml:
   - WAKE_LOCK, ACCESS_WIFI_STATE, CHANGE_WIFI_STATE, FOREGROUND_SERVICE,
     FOREGROUND_SERVICE_DATA_SYNC, POST_NOTIFICATIONS, REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
   - <service android:name=".KeepAliveService" android:foregroundServiceType="dataSync" ... />
2. KeepAliveService.java:
   - Acquires PowerManager.PARTIAL_WAKE_LOCK (CPU stays awake when screen is off)
   - Acquires WifiManager.WifiLock (Wi-Fi stays high-perf when screen is off)
   - Runs as Foreground Service with persistent status notification (START_STICKY)
3. MainActivity.java:
   - Starts KeepAliveService automatically
   - Exposes @JavascriptInterface "AndroidKeepAlive" to WebView
   - Calls webView.resumeTimers() in onPause/onStop so JS timers never freeze on screen-off
   - Provides requestIgnoreBatteryOptimizations() to open native Android whitelist prompt
"""
from pathlib import Path

ANDROID_DIR = Path("android")
MANIFEST_PATH = ANDROID_DIR / "app" / "src" / "main" / "AndroidManifest.xml"
PKG_DIR = ANDROID_DIR / "app" / "src" / "main" / "java" / "com" / "winnerds" / "v2rayn" / "threestage"

KEEPALIVE_SERVICE_JAVA = r"""package com.winnerds.v2rayn.threestage;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

public class KeepAliveService extends Service {
    public static final String CHANNEL_ID = "v2rayn_3stage_keepalive_channel";
    public static final int NOTIF_ID = 10808;
    public static volatile boolean isRunning = false;

    private PowerManager.WakeLock wakeLock;
    private WifiManager.WifiLock wifiLock;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        acquireLocks();
    }

    private void acquireLocks() {
        try {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm != null && (wakeLock == null || !wakeLock.isHeld())) {
                wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "v2rayN3Stage::CpuWakeLock");
                wakeLock.setReferenceCounted(false);
                wakeLock.acquire();
            }
        } catch (Exception ignored) {}

        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wm != null && (wifiLock == null || !wifiLock.isHeld())) {
                wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "v2rayN3Stage::WifiWakeLock");
                wifiLock.setReferenceCounted(false);
                wifiLock.acquire();
            }
        } catch (Exception ignored) {}
    }

    private void releaseLocks() {
        try {
            if (wakeLock != null && wakeLock.isHeld()) {
                wakeLock.release();
            }
        } catch (Exception ignored) {}
        try {
            if (wifiLock != null && wifiLock.isHeld()) {
                wifiLock.release();
            }
        } catch (Exception ignored) {}
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        acquireLocks();
        String statusText = "定时获取 · 定时测试 · 定时汇总 息屏后台守护中";
        if (intent != null && intent.hasExtra("status")) {
            String custom = intent.getStringExtra("status");
            if (custom != null && !custom.trim().isEmpty()) {
                statusText = custom;
            }
        }
        Notification notification = buildNotification(statusText);
        startForeground(NOTIF_ID, notification);
        isRunning = true;
        return START_STICKY;
    }

    private Notification buildNotification(String contentText) {
        Intent notificationIntent = new Intent(this, MainActivity.class);
        notificationIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        PendingIntent pendingIntent = PendingIntent.getActivity(this, 0, notificationIntent, flags);

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }

        builder.setContentTitle("v2rayN 三段式管家 V2.0 (息屏运行中)")
               .setContentText(contentText)
               .setSmallIcon(android.R.drawable.stat_notify_sync)
               .setContentIntent(pendingIntent)
               .setOngoing(true);

        return builder.build();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "v2rayN 息屏后台常驻服务",
                NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("保持息屏状态下定时获取、三段式测试与汇总不中断");
            channel.setShowBadge(false);
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    @Override
    public void onDestroy() {
        isRunning = false;
        releaseLocks();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
"""

MAIN_ACTIVITY_JAVA = r"""package com.winnerds.v2rayn.threestage;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    private volatile boolean keepAliveEnabled = true;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        startKeepAliveService("四项定时任务与息屏唤醒锁已就绪");

        if (getBridge() != null && getBridge().getWebView() != null) {
            WebView webView = getBridge().getWebView();
            webView.getSettings().setMediaPlaybackRequiresUserGesture(false);
            webView.addJavascriptInterface(new KeepAliveJsBridge(), "AndroidKeepAlive");
        }
    }

    @Override
    public void onPause() {
        super.onPause();
        if (keepAliveEnabled && getBridge() != null && getBridge().getWebView() != null) {
            // Prevent Android WebView from suspending JS timers when screen turns off
            getBridge().getWebView().resumeTimers();
        }
    }

    @Override
    public void onStop() {
        super.onStop();
        if (keepAliveEnabled && getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().resumeTimers();
        }
    }

    private void startKeepAliveService(String statusText) {
        try {
            Intent serviceIntent = new Intent(this, KeepAliveService.class);
            serviceIntent.putExtra("status", statusText);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }
        } catch (Exception ignored) {}
    }

    private void stopKeepAliveService() {
        try {
            Intent serviceIntent = new Intent(this, KeepAliveService.class);
            stopService(serviceIntent);
        } catch (Exception ignored) {}
    }

    public class KeepAliveJsBridge {
        @JavascriptInterface
        public boolean setKeepAlive(boolean enabled, String statusText) {
            keepAliveEnabled = enabled;
            if (enabled) {
                startKeepAliveService(statusText);
            } else {
                stopKeepAliveService();
            }
            return keepAliveEnabled;
        }

        @JavascriptInterface
        public void updateStatus(String statusText) {
            if (keepAliveEnabled) {
                startKeepAliveService(statusText);
            }
        }

        @JavascriptInterface
        public boolean isIgnoringBatteryOptimizations() {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
                return pm != null && pm.isIgnoringBatteryOptimizations(getPackageName());
            }
            return true;
        }

        @JavascriptInterface
        public void requestIgnoreBatteryOptimizations() {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                try {
                    PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
                    if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                        Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                        intent.setData(Uri.parse("package:" + getPackageName()));
                        startActivity(intent);
                    }
                } catch (Exception ignored) {}
            }
        }
    }
}
"""


def patch_manifest():
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")
    xml = MANIFEST_PATH.read_text(encoding="utf-8")

    # 1. Inject Foreground Service inside <application ...>
    service_decl = (
        '        <service\n'
        '            android:name=".KeepAliveService"\n'
        '            android:enabled="true"\n'
        '            android:exported="false"\n'
        '            android:foregroundServiceType="dataSync" />\n'
    )
    if "KeepAliveService" not in xml:
        xml = xml.replace("</application>", service_decl + "    </application>")

    # 2. Inject Permissions before </manifest>
    perms = [
        '<uses-permission android:name="android.permission.WAKE_LOCK" />',
        '<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />',
        '<uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />',
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />',
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />',
        '<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />',
        '<uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />',
    ]
    perm_block = "\n".join(f"    {p}" for p in perms if p not in xml)
    if perm_block:
        xml = xml.replace("</manifest>", perm_block + "\n</manifest>")

    MANIFEST_PATH.write_text(xml, encoding="utf-8")
    print("[KeepAlivePatch] Patched AndroidManifest.xml successfully.")


def write_java_classes():
    PKG_DIR.mkdir(parents=True, exist_ok=True)
    (PKG_DIR / "KeepAliveService.java").write_text(KEEPALIVE_SERVICE_JAVA, encoding="utf-8")
    (PKG_DIR / "MainActivity.java").write_text(MAIN_ACTIVITY_JAVA, encoding="utf-8")
    print("[KeepAlivePatch] Wrote KeepAliveService.java and MainActivity.java successfully.")


if __name__ == "__main__":
    patch_manifest()
    write_java_classes()
