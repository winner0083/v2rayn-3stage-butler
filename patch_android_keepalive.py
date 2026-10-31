#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Injects Full Native Android Capabilities into the Capacitor Android Project:
1. XrayBenchEngine.java:
   - Bundled libxray.so (Xray-android-arm64-v8a) process manager
   - Single-node & Asynchronous Multi-Threaded Batch Benchmark Pool (4 concurrent workers)
   - Stage 0: Real Java Socket TCP connect probe
   - Stage 1: Real libxray.so SOCKS5 (ATYP=0x03 remote DNS) -> TLS 443 -> i.ytimg.com/generate_204 (3 rounds)
   - Stage 2: Real libxray.so SOCKS5 -> TLS 443 -> speed.cloudflare.com/__down?bytes=5000000 (L041 >=128KB check)
   - Native Dual-Channel Subscription Fetcher (Direct Proxy.NO_PROXY vs Local 10808 / Self-Started libxray.so Proxy)
2. KeepAliveService.java:
   - Screen-Off PARTIAL_WAKE_LOCK + WIFI_MODE_FULL_HIGH_PERF + START_STICKY Foreground Notification
3. MainActivity.java:
   - @JavascriptInterface "AndroidKeepAlive" exposing:
     * hasNativeXray(), getXrayVersion()
     * benchNodeJson(rawUri, port, doSpeed)
     * startBatchBench(urisJsonArray, doSpeed, workers), getBatchProgressJson(), stopBatchBench()
     * probeAndFetchSubJson(targetUrl, proxyNodeRaw)
     * copyToClipboard(text), launchV2rayNG(clipText), exportOrShareFile(filename, content)
     * setKeepAlive(enabled, status), updateStatus(status)
     * isIgnoringBatteryOptimizations(), requestIgnoreBatteryOptimizations()
   - Overrides onPause()/onStop() with webView.resumeTimers()
"""
from pathlib import Path
import base64
import time

ANDROID_DIR = Path("android")
MANIFEST_PATH = ANDROID_DIR / "app" / "src" / "main" / "AndroidManifest.xml"
BUILD_GRADLE_PATH = ANDROID_DIR / "app" / "build.gradle"
PKG_DIR = ANDROID_DIR / "app" / "src" / "main" / "java" / "com" / "winnerds" / "v2rayn" / "threestage"

# Permanent deterministic signing keystore (RSA 2048, valid 30 years, alias=androiddebugkey, pass=android)
# Ensures all builds across ephemeral GitHub Actions runners share the exact same certificate so updates install in-place without uninstalling!
PERMANENT_KEYSTORE_B64 = (
    "/u3+7QAAAAIAAAABAAAAAQAPYW5kcm9pZGRlYnVna2V5AAABoY0wC2oAAAUDMIIE/zAOBgorBgEEASoCEQEBBQAEggTr5yN+03wX"
    "ILwbr3mtoZjmyvcJ4cR63iU8y8MawbN5c/URDWNQE6WzCvBH1hKdLcsTW8KFkKRKvAdQG8CyxCq9bl1ycyMRXf5aA/LU6C0LBg4n"
    "Qff2vy5FimvJuHD5q2Xb9Hd69FQdNQcXfwfctGpjMgpiLYD/2kl9krDychizhqKNH4LoLItaHVG3ho5OHIDHEfE/QXJxjJQ+H1oy"
    "tox7UzS4FnqAid7N2VBOwIbHEfPBeqDzS1fn+5e0ThI7NWstO/pPVceWcu1sVXlVRCulhlrcWAYlq05JwwC68i+dRsK/jJbz1INE"
    "y5kW6VlH3cyw6v7vAFc/YoeYukaAlv8cSQBt5tKkPhd6hbQGXdRUFATjjQEwC/oBXy4pesLN5NH3MYh4BE9EJ++5Zb15yJYM/arj"
    "DoEbwrrDMtwSZtxWBAMQipnik2OWLIU++DXG2kACemyNDwrr5hWBUIfS30R5fdNyG+3omD9d7D6XOPDP3VaRfUcIl8chvmUIkorr"
    "BuKZejA2+uZDfgG4W2Ip2kod2FoE7tzujNgz/p+3gZbkwEqVZFikHJCKFVWtF7TVd0VBJrpmgPX32JxZGvYpkrp36yK8JqfhirdS"
    "4eB0MCLHziXLPlaetd4uT41qeaOUvBEVEf5kWRpM+eFNNVQmU7z+h6K0X4uO7xigyWWXfbsS6tv6ZllIGpHFfi/6r7yumcGlp+N0"
    "7UXhfbF5hv8IWhzdvQFO87To5gCEaX4Np8pRQev/C2aZQ3UVXAi2F3pRVkpsKAqIIN2C0sj1aXj8wHe2Suy+37CYLBENA/dMCk52"
    "/IEnesVODZeAB2J0Dgn5VzHhEyswbaY53jeG1TiWPlQGsdvOx1rIrQS4f+1wlLR/8t9Mqg0hXut3fHECLUsOKohyAnmwjoFbBeYU"
    "uHjSqsyhB6NXbc+CS7CnMPwPyex6ppZEeAkcsv+TOlN7DndDkw9mEr1S29bU5LMSD6769XRd6dQ6YY8SiNgvLqVrmbupK7+xIZrP"
    "GyKrBzdMMKXPNp8LBjQYFlKKuDrJ/Gx+f0KnogvZ+73sWgVMA4SDsw91CgsmpzEy+KVT1pNBKlHTEhrsuU+Fd1DA1QUdPr2qa/CC"
    "ijwEyJp/qhfP7HoSXZVSFQguthnVAyLeeu7k+9SfKsdROpOGuCvSc//ovyGRlqhLlcIdtdU89o2airwQtVfCDZAIcW1fkpP8sb/s"
    "iWdaiYMFg72fP+EtQ9hC9/HmMumx8mjWk72WIXBlHQIYHpiV8j/gOUhwp4brYUCDHake8Bvjjs2pfNTX+iDwzEa1ghiP23pGEx7G"
    "Cuy2070bYymqoh78lYtZWulEiMYS0Ml9NsBOq4k+LTxGoWkcagSFYkvlWUGYOpkGGakD1gBGR13cfntGpF9JUjooFaCqONkNGa00"
    "+BtNb+hSgbkwYnUveS0TW649XP1FVJrDSRyMeK9Epus3JO3bpB9spW1MB6O60nWO0XSoSAWM2InI70R0AFZvqvF082hwMqX10VPj"
    "s0bJN7xwwpcEwA4yYVNn+g0Ya6k611woaGas3BrRe0I4o0f9t7cBRrMfwTCMtxE/XGtzekGNDi7XWCFr3t8B5IboguTFOH9dbdm/"
    "GvbtFoql19oZAC34OuEdopDAuh2ZSBsd2lci0nobcSE8O3N2sM7VXzDpDwlyuQ10R6HI+lcAAAABAAVYLjUwOQAAA6swggOnMIIC"
    "j6ADAgECAgQWbIqCMA0GCSqGSIb3DQEBCwUAMIGCMQswCQYDVQQGEwJDTjERMA8GA1UECBMIU2hhbmdoYWkxETAPBgNVBAcTCFNo"
    "YW5naGFpMREwDwYDVQQKEwhXaW5uZXJkczERMA8GA1UECxMIV2lubmVyZHMxJzAlBgNVBAMTHnYycmF5TiAzU3RhZ2UgQnV0bGVy"
    "IFBlcm1hbmVudDAgFw0yNjEwMzAxNDIxMzhaGA8yMDU2MTAyMjE0MjEzOFowgYIxCzAJBgNVBAYTAkNOMREwDwYDVQQIEwhTaGFu"
    "Z2hhaTERMA8GA1UEBxMIU2hhbmdoYWkxETAPBgNVBAoTCFdpbm5lcmRzMREwDwYDVQQLEwhXaW5uZXJkczEnMCUGA1UEAxMedjJy"
    "YXlOIDNTdGFnZSBCdXRsZXIgUGVybWFuZW50MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAttUtTbRhoJg2m3XzGlI/"
    "fBYJEWr9EYmyUyXyL+9RcqspktH1BzDPXL2943baGjTwGcrTzB5/Q3ulFdxWt3uxvZ7T7lmGFCgZibqn3i3wMz6FCQYaYaRWYuQ8"
    "awliaQQnfeCmMGWGQ05ShG6WD0OIW4mumWNKl1gzcagG1/dV6LmTacvezJL169S6HjIb2AKocknastHwdKzx4fCXUgUkEcQMcatU"
    "0rt/YGI8TttMiG0Z1rNnvSx+yEFvrYlDfKBi4I+9rNkHd43HxdWlggyvV0UbjKQ3JnsBKx37bgOepVVqGn2t5ppIJGNXQs4L+8Tm"
    "DzhHqmPdK2muReyLGTDwowIDAQABoyEwHzAdBgNVHQ4EFgQU6FBPJFDnVeLef71K4Z/iga5RJMQwDQYJKoZIhvcNAQELBQADggEB"
    "AJqIu5g7SNIqkruQHY8LPO7A2r93wsPIs1m9iLe43DtTiRvVgHm1mlSrpy3JmwyMGxjspi+nfnREfJgvaqCSuxtllKMaplMgf0qs"
    "t4dEhkygcUBc0hbkc1H7fLuZHqY8D99p50HdiCeUFlBS7GxCPW5w/uDLEQW4QHfI5aeyxfcOUf293IEhG8iULvK2YkkYcbPfkiiC"
    "x+GUztpLkmWjawj82I1CWHk5fOuJG+aYoGKX22iQBm9s0pZps2xVzQR5xD7oRUwvjudM+kx6jTFdqU7H/wjT9WtH0sq6atPs8Xdn"
    "1+oBPxaAZePfERhkT8P4hDZxAA3N0URF5KMnazG/uNv6YBZTZIYAscbUaHjNNORUp12rDA=="
)

KEEPALIVE_SERVICE_JAVA = r"""package com.winnerds.v2rayn.threestage;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

public class KeepAliveService extends Service {
    public static final String CHANNEL_ID = "v2rayn_3stage_keepalive_channel";
    public static final int NOTIF_ID = 10808;
    public static volatile boolean isRunning = false;
    private static volatile String lastStatusText = "Xray真核已集成 · 息屏/后台常驻守护中";

    private PowerManager.WakeLock wakeLock;
    private WifiManager.WifiLock wifiLock;
    private volatile boolean audioLoopRunning = false;
    private Thread audioThread = null;
    private AudioTrack silentTrack = null;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel(this);
        acquireLocks();
        startSilentAudioLoop();
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
                int lockType = WifiManager.WIFI_MODE_FULL_HIGH_PERF;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    lockType = WifiManager.WIFI_MODE_FULL_LOW_LATENCY;
                }
                wifiLock = wm.createWifiLock(lockType, "v2rayN3Stage::WifiWakeLock");
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

    // Plays 0-volume zero-PCM audio stream without requesting AudioFocus:
    // Prevents OEM ROMs (HyperOS/MIUI/ColorOS/OriginOS/HarmonyOS/OneUI) from freezing cgroup/sockets in background
    private synchronized void startSilentAudioLoop() {
        if (audioLoopRunning && audioThread != null && audioThread.isAlive()) return;
        audioLoopRunning = true;
        audioThread = new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    int sampleRate = 8000;
                    int minBuf = AudioTrack.getMinBufferSize(
                        sampleRate,
                        AudioFormat.CHANNEL_OUT_MONO,
                        AudioFormat.ENCODING_PCM_16BIT
                    );
                    if (minBuf <= 0) minBuf = 1600;
                    AudioAttributes attrs = new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build();
                    AudioFormat fmt = new AudioFormat.Builder()
                        .setSampleRate(sampleRate)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build();
                    silentTrack = new AudioTrack(
                        attrs,
                        fmt,
                        minBuf * 2,
                        AudioTrack.MODE_STREAM,
                        AudioManager.AUDIO_SESSION_ID_GENERATE
                    );
                    silentTrack.setVolume(0.0f);
                    silentTrack.play();
                    byte[] zeroBuf = new byte[minBuf];
                    while (audioLoopRunning) {
                        silentTrack.write(zeroBuf, 0, zeroBuf.length);
                        Thread.sleep(200);
                    }
                } catch (Exception ignored) {
                } finally {
                    try {
                        if (silentTrack != null) {
                            silentTrack.stop();
                            silentTrack.release();
                            silentTrack = null;
                        }
                    } catch (Exception ignored) {}
                }
            }
        }, "KeepAliveSilentAudio");
        audioThread.setDaemon(true);
        audioThread.start();
    }

    private synchronized void stopSilentAudioLoop() {
        audioLoopRunning = false;
        if (audioThread != null) {
            try { audioThread.interrupt(); } catch (Exception ignored) {}
            audioThread = null;
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        acquireLocks();
        startSilentAudioLoop();
        String statusText = lastStatusText;
        if (intent != null && intent.hasExtra("status")) {
            String custom = intent.getStringExtra("status");
            if (custom != null && !custom.trim().isEmpty()) {
                statusText = custom;
                lastStatusText = statusText;
            }
        }
        Notification notification = buildNotificationStatic(this, statusText);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(
                    NOTIF_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
                );
            } else {
                startForeground(NOTIF_ID, notification);
            }
        } catch (Exception e1) {
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
                } else {
                    startForeground(NOTIF_ID, notification);
                }
            } catch (Exception e2) {
                try { startForeground(NOTIF_ID, notification); } catch (Exception ignored) {}
            }
        }
        isRunning = true;
        return START_STICKY;
    }

    public static void updateNotificationStatic(Context ctx, String contentText) {
        if (ctx == null) return;
        if (contentText != null && !contentText.trim().isEmpty()) {
            lastStatusText = contentText;
        }
        try {
            createNotificationChannel(ctx);
            NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) {
                nm.notify(NOTIF_ID, buildNotificationStatic(ctx, lastStatusText));
            }
        } catch (Exception ignored) {}
    }

    public static Notification buildNotificationStatic(Context ctx, String contentText) {
        Intent notificationIntent = new Intent(ctx, MainActivity.class);
        notificationIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        PendingIntent pendingIntent = PendingIntent.getActivity(ctx, 0, notificationIntent, flags);

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(ctx, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(ctx);
        }

        builder.setContentTitle("v2rayN 三段式管家 V2.1 (Xray真核)")
               .setContentText(contentText)
               .setSmallIcon(android.R.drawable.stat_notify_sync)
               .setContentIntent(pendingIntent)
               .setOngoing(true);

        return builder.build();
    }

    public static void createNotificationChannel(Context ctx) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "v2rayN 息屏与后台常驻服务",
                NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("保持切后台与息屏状态下定时获取、Xray真核三段式测试与汇总全速运行不中断");
            channel.setShowBadge(false);
            NotificationManager manager = ctx.getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    @Override
    public void onDestroy() {
        isRunning = false;
        stopSilentAudioLoop();
        releaseLocks();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
"""

XRAY_BENCH_ENGINE_JAVA = r"""package com.winnerds.v2rayn.threestage;

import android.content.Context;
import android.content.Intent;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.PowerManager;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.Socket;
import java.net.URL;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

public class XrayBenchEngine {
    public static final String PING_HOST = "i.ytimg.com";
    public static final String PING_PATH = "/generate_204";
    public static final int PING_PORT = 443;
    public static final int LATENCY_ROUNDS = 3;

    public static final String SPEED_HOST = "speed.cloudflare.com";
    public static final String SPEED_PATH = "/__down?bytes=5000000";
    public static final int SPEED_MIN_BYTES = 128 * 1024; // L041: reject fake 24-byte empty responses

    // Async Batch Runner State
    private static volatile ExecutorService batchExecutor = null;
    private static final AtomicBoolean batchRunning = new AtomicBoolean(false);
    private static final AtomicBoolean batchPaused = new AtomicBoolean(false);
    private static final AtomicBoolean batchCancel = new AtomicBoolean(false);
    private static final AtomicInteger batchTotal = new AtomicInteger(0);
    private static final AtomicInteger batchDone = new AtomicInteger(0);
    private static final AtomicInteger batchAlive = new AtomicInteger(0);
    private static final CopyOnWriteArrayList<JSONObject> batchResults = new CopyOnWriteArrayList<>();
    private static final CopyOnWriteArrayList<String> batchLogs = new CopyOnWriteArrayList<>();

    // Async Subscription Fetcher State (Non-blocking UI bridge)
    private static final AtomicBoolean subFetchRunning = new AtomicBoolean(false);
    private static volatile String subFetchResultJson = "";
    private static volatile Thread subFetchThread = null;

    // Dedicated Benchmark WakeLock & WifiLock so CPU/WiFi never sleep mid-test
    private static volatile PowerManager.WakeLock benchWakeLock = null;
    private static volatile WifiManager.WifiLock benchWifiLock = null;
    private static volatile long lastNotifUpdateMs = 0L;

    public static boolean isAnyTaskRunning() {
        return batchRunning.get() || subFetchRunning.get();
    }

    private static synchronized void acquireBenchLocks(Context ctx) {
        if (ctx == null) return;
        Context appCtx = ctx.getApplicationContext();
        try {
            if (!KeepAliveService.isRunning) {
                Intent svc = new Intent(appCtx, KeepAliveService.class);
                svc.putExtra("status", "⚡ 正在后台执行节点实测任务...");
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    appCtx.startForegroundService(svc);
                } else {
                    appCtx.startService(svc);
                }
            }
        } catch (Exception ignored) {}
        try {
            PowerManager pm = (PowerManager) appCtx.getSystemService(Context.POWER_SERVICE);
            if (pm != null && (benchWakeLock == null || !benchWakeLock.isHeld())) {
                benchWakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "v2rayN3Stage::BenchWorkerWakeLock");
                benchWakeLock.setReferenceCounted(false);
                benchWakeLock.acquire(60 * 60 * 1000L);
            }
        } catch (Exception ignored) {}
        try {
            WifiManager wm = (WifiManager) appCtx.getSystemService(Context.WIFI_SERVICE);
            if (wm != null && (benchWifiLock == null || !benchWifiLock.isHeld())) {
                int lockType = WifiManager.WIFI_MODE_FULL_HIGH_PERF;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    lockType = WifiManager.WIFI_MODE_FULL_LOW_LATENCY;
                }
                benchWifiLock = wm.createWifiLock(lockType, "v2rayN3Stage::BenchWorkerWifiLock");
                benchWifiLock.setReferenceCounted(false);
                benchWifiLock.acquire();
            }
        } catch (Exception ignored) {}
    }

    private static synchronized void releaseBenchLocksIfIdle() {
        if (batchRunning.get() || subFetchRunning.get()) return;
        try {
            if (benchWakeLock != null && benchWakeLock.isHeld()) {
                benchWakeLock.release();
            }
        } catch (Exception ignored) {}
        try {
            if (benchWifiLock != null && benchWifiLock.isHeld()) {
                benchWifiLock.release();
            }
        } catch (Exception ignored) {}
    }

    public static File getXrayBinary(Context ctx) {
        String nativeDir = ctx.getApplicationInfo().nativeLibraryDir;
        return new File(nativeDir, "libxray.so");
    }

    public static boolean isXrayAvailable(Context ctx) {
        File f = getXrayBinary(ctx);
        return f.exists() && f.canExecute();
    }

    public static String getXrayVersion(Context ctx) {
        File f = getXrayBinary(ctx);
        if (!f.exists()) return "missing (" + f.getAbsolutePath() + ")";
        try {
            Process p = new ProcessBuilder(f.getAbsolutePath(), "version").redirectErrorStream(true).start();
            BufferedReader br = new BufferedReader(new InputStreamReader(p.getInputStream()));
            String line = br.readLine();
            p.destroy();
            return line != null ? line : "Xray-core available";
        } catch (Exception e) {
            return "error: " + e.getMessage();
        }
    }

    public static Map<String, String> parseQuery(String q) {
        Map<String, String> map = new HashMap<>();
        if (q == null || q.isEmpty()) return map;
        for (String pair : q.split("&")) {
            int idx = pair.indexOf('=');
            if (idx > 0) {
                try {
                    String k = URLDecoder.decode(pair.substring(0, idx), "UTF-8");
                    String v = URLDecoder.decode(pair.substring(idx + 1), "UTF-8");
                    map.put(k, v);
                } catch (Exception ignored) {}
            }
        }
        return map;
    }

    public static JSONObject parseNodeLink(String raw) throws Exception {
        String link = raw == null ? "" : raw.trim();
        int schemeIdx = link.indexOf("://");
        if (schemeIdx <= 0) throw new IllegalArgumentException("Invalid scheme");
        String proto = link.substring(0, schemeIdx).toLowerCase();
        String rest = link.substring(schemeIdx + 3);

        JSONObject node = new JSONObject();
        node.put("raw", link);
        node.put("protocol", proto);

        if ("vmess".equals(proto)) {
            String b64 = rest.split("#")[0].trim().replace('-', '+').replace('_', '/');
            byte[] decoded = Base64.decode(b64, Base64.DEFAULT);
            JSONObject j = new JSONObject(new String(decoded, StandardCharsets.UTF_8));
            String host = j.optString("add", "").trim();
            int port = Integer.parseInt(j.optString("port", "443").split("/")[0].replaceAll("[^0-9]", "").trim());
            node.put("host", host);
            node.put("port", port);
            node.put("uuid", j.optString("id", ""));
            node.put("name", j.optString("ps", host + ":" + port));
            JSONObject params = new JSONObject();
            params.put("net", j.optString("net", "tcp"));
            params.put("tls", j.optString("tls", ""));
            params.put("sni", j.optString("sni", host));
            params.put("host", j.optString("host", host));
            params.put("path", j.optString("path", "/"));
            params.put("aid", j.optString("aid", "0"));
            node.put("params", params);
            return node;
        }

        String remark = "";
        int hashIdx = rest.indexOf('#');
        if (hashIdx >= 0) {
            try {
                remark = URLDecoder.decode(rest.substring(hashIdx + 1), "UTF-8");
            } catch (Exception e) {
                remark = rest.substring(hashIdx + 1);
            }
            rest = rest.substring(0, hashIdx);
        }

        String query = "";
        int qIdx = rest.indexOf('?');
        if (qIdx >= 0) {
            query = rest.substring(qIdx + 1);
            rest = rest.substring(0, qIdx);
        }

        Map<String, String> qMap = parseQuery(query);
        JSONObject params = new JSONObject(qMap);
        node.put("params", params);

        String userPart = "";
        String hostPortPart = rest;
        int atIdx = rest.lastIndexOf('@');
        if (atIdx >= 0) {
            userPart = rest.substring(0, atIdx);
            hostPortPart = rest.substring(atIdx + 1);
        } else if ("ss".equals(proto)) {
            byte[] dec = Base64.decode(rest.replace('-', '+').replace('_', '/'), Base64.DEFAULT);
            String full = new String(dec, StandardCharsets.UTF_8);
            int at2 = full.lastIndexOf('@');
            if (at2 >= 0) {
                userPart = full.substring(0, at2);
                hostPortPart = full.substring(at2 + 1);
            }
        }

        try {
            userPart = URLDecoder.decode(userPart, "UTF-8");
        } catch (Exception ignored) {}

        if ("ss".equals(proto)) {
            boolean isSsVariant = "none".equals(params.optString("encryption", ""))
                || !params.optString("security", "").isEmpty()
                || (!params.optString("type", "").isEmpty() && !"tcp".equals(params.optString("type", "")));
            if (isSsVariant && !userPart.contains(":")) {
                node.put("protocol", "vless");
                node.put("uuid", userPart);
                node.put("password", userPart);
            } else {
                if (!userPart.contains(":")) {
                    try {
                        String padded = userPart.replace('-', '+').replace('_', '/');
                        while (padded.length() % 4 != 0) padded += "=";
                        byte[] dec = Base64.decode(padded, Base64.DEFAULT);
                        userPart = new String(dec, StandardCharsets.UTF_8);
                    } catch (Exception ignored) {}
                }
                int cIdx = userPart.indexOf(':');
                if (cIdx > 0) {
                    String mth = userPart.substring(0, cIdx).trim();
                    String pw = userPart.substring(cIdx + 1);
                    if ("none".equalsIgnoreCase(mth) && pw.length() >= 32) {
                        node.put("protocol", "vless");
                        node.put("uuid", pw);
                        node.put("password", pw);
                    } else {
                        node.put("method", mth);
                        node.put("password", pw);
                    }
                } else {
                    node.put("method", "chacha20-ietf-poly1305");
                    node.put("password", userPart);
                }
            }
        } else {
            node.put("uuid", userPart);
            node.put("password", userPart);
        }

        int colonIdx = hostPortPart.lastIndexOf(':');
        if (colonIdx <= 0) throw new IllegalArgumentException("Missing port");
        String host = hostPortPart.substring(0, colonIdx).trim();
        String portStr = hostPortPart.substring(colonIdx + 1).split("/")[0].trim();
        int port = Integer.parseInt(portStr);
        if (host.isEmpty()) throw new IllegalArgumentException("Empty host");

        node.put("host", host);
        node.put("port", port);
        node.put("name", remark.isEmpty() ? (proto.toUpperCase() + "-" + host + ":" + port) : remark);
        return node;
    }

    public static JSONObject buildXrayConfig(JSONObject node, int listenPort) throws Exception {
        String proto = node.getString("protocol");
        String host = node.getString("host");
        int port = node.getInt("port");
        String idOrPass = node.optString("uuid", node.optString("password", ""));
        JSONObject params = node.optJSONObject("params");
        if (params == null) params = new JSONObject();

        JSONObject config = new JSONObject();
        config.put("log", new JSONObject().put("loglevel", "none"));

        JSONArray inbounds = new JSONArray();
        inbounds.put(new JSONObject()
            .put("tag", "in")
            .put("port", listenPort)
            .put("listen", "127.0.0.1")
            .put("protocol", "socks")
            .put("settings", new JSONObject().put("auth", "noauth").put("udp", false)));
        config.put("inbounds", inbounds);

        JSONObject outbound = new JSONObject();
        outbound.put("tag", "proxy");
        outbound.put("mux", new JSONObject().put("enabled", false).put("concurrency", -1));

        JSONObject stream = new JSONObject();
        String net = params.optString("type", params.optString("net", "tcp")).toLowerCase();
        if ("raw".equals(net)) net = "tcp";
        String sec = params.optString("security", params.optString("tls", "none")).toLowerCase();
        if (sec.isEmpty()) sec = "trojan".equals(proto) ? "tls" : "none";

        if ("vless".equals(proto)) {
            outbound.put("protocol", "vless");
            JSONObject user = new JSONObject()
                .put("id", idOrPass)
                .put("alterId", 0)
                .put("encryption", "none")
                .put("security", "auto");
            String flow = params.optString("flow", "");
            if (!flow.isEmpty()) user.put("flow", flow);
            JSONObject vnext = new JSONObject()
                .put("address", host)
                .put("port", port)
                .put("users", new JSONArray().put(user));
            outbound.put("settings", new JSONObject().put("vnext", new JSONArray().put(vnext)));
        } else if ("trojan".equals(proto)) {
            outbound.put("protocol", "trojan");
            JSONObject srv = new JSONObject()
                .put("address", host)
                .put("port", port)
                .put("password", idOrPass);
            outbound.put("settings", new JSONObject().put("servers", new JSONArray().put(srv)));
        } else if ("vmess".equals(proto)) {
            outbound.put("protocol", "vmess");
            JSONObject user = new JSONObject()
                .put("id", idOrPass)
                .put("alterId", 0)
                .put("security", "auto");
            JSONObject vnext = new JSONObject()
                .put("address", host)
                .put("port", port)
                .put("users", new JSONArray().put(user));
            outbound.put("settings", new JSONObject().put("vnext", new JSONArray().put(vnext)));
        } else if ("ss".equals(proto)) {
            outbound.put("protocol", "shadowsocks");
            JSONObject srv = new JSONObject()
                .put("address", host)
                .put("port", port)
                .put("method", node.optString("method", "chacha20-ietf-poly1305"))
                .put("password", idOrPass);
            outbound.put("settings", new JSONObject().put("servers", new JSONArray().put(srv)));
        }

        stream.put("network", net);
        stream.put("security", sec);
        String sni = params.optString("sni", params.optString("host", host));
        if (sni.isEmpty()) sni = host;

        if ("tls".equals(sec)) {
            boolean allowIns = "1".equals(params.optString("allowInsecure", "0"))
                            || "true".equalsIgnoreCase(params.optString("allowInsecure", "false"))
                            || "1".equals(params.optString("insecure", "0"));
            stream.put("tlsSettings", new JSONObject()
                .put("serverName", sni)
                .put("allowInsecure", allowIns)
                .put("fingerprint", params.optString("fp", "chrome")));
        } else if ("reality".equals(sec)) {
            stream.put("realitySettings", new JSONObject()
                .put("serverName", sni)
                .put("fingerprint", params.optString("fp", "chrome"))
                .put("publicKey", params.optString("pbk", ""))
                .put("shortId", params.optString("sid", "")));
        }

        if ("ws".equals(net)) {
            String wsHost = params.optString("host", sni);
            stream.put("wsSettings", new JSONObject()
                .put("path", params.optString("path", "/"))
                .put("headers", new JSONObject().put("Host", wsHost)));
        } else if ("grpc".equals(net)) {
            stream.put("grpcSettings", new JSONObject()
                .put("serviceName", params.optString("serviceName", "")));
        } else if ("xhttp".equals(net) || "splithttp".equals(net)) {
            stream.put("xhttpSettings", new JSONObject()
                .put("path", params.optString("path", "/"))
                .put("host", params.optString("host", sni))
                .put("mode", params.optString("mode", "auto")));
        }

        outbound.put("streamSettings", stream);
        config.put("outbounds", new JSONArray().put(outbound));
        return config;
    }

    private static SSLSocketFactory getTrustAllSslFactory() throws Exception {
        TrustManager[] trustAll = new TrustManager[]{
            new X509TrustManager() {
                public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
                public void checkClientTrusted(X509Certificate[] certs, String authType) {}
                public void checkServerTrusted(X509Certificate[] certs, String authType) {}
            }
        };
        SSLContext sc = SSLContext.getInstance("TLS");
        sc.init(null, trustAll, new SecureRandom());
        return sc.getSocketFactory();
    }

    private static Socket socks5Connect(int socksPort, String targetHost, int targetPort, int timeoutMs) throws Exception {
        Socket s = new Socket();
        s.connect(new InetSocketAddress("127.0.0.1", socksPort), timeoutMs);
        s.setSoTimeout(timeoutMs);
        OutputStream out = s.getOutputStream();
        InputStream in = s.getInputStream();

        out.write(new byte[]{0x05, 0x01, 0x00});
        out.flush();
        byte[] greeting = new byte[2];
        if (in.read(greeting) != 2 || greeting[0] != 0x05 || greeting[1] != 0x00) {
            s.close();
            throw new RuntimeException("SOCKS5 auth failed");
        }

        byte[] hostBytes = targetHost.getBytes(StandardCharsets.UTF_8);
        byte[] req = new byte[4 + 1 + hostBytes.length + 2];
        req[0] = 0x05;
        req[1] = 0x01; // CONNECT
        req[2] = 0x00;
        req[3] = 0x03; // ATYP = Domain name (remote DNS resolution via Xray)
        req[4] = (byte) hostBytes.length;
        System.arraycopy(hostBytes, 0, req, 5, hostBytes.length);
        req[5 + hostBytes.length] = (byte) ((targetPort >> 8) & 0xFF);
        req[6 + hostBytes.length] = (byte) (targetPort & 0xFF);

        out.write(req);
        out.flush();

        byte[] resp = new byte[10];
        int n = in.read(resp);
        if (n < 4 || resp[1] != 0x00) {
            s.close();
            throw new RuntimeException("SOCKS5 connect rejected");
        }
        return s;
    }

    private static int httpPingThroughSocks(int socksPort, int timeoutMs) throws Exception {
        long t0 = System.currentTimeMillis();
        Socket rawSock = null;
        SSLSocket sslSock = null;
        try {
            rawSock = socks5Connect(socksPort, PING_HOST, PING_PORT, timeoutMs);
            SSLSocketFactory factory = getTrustAllSslFactory();
            sslSock = (SSLSocket) factory.createSocket(rawSock, PING_HOST, PING_PORT, true);
            sslSock.setSoTimeout(timeoutMs);
            sslSock.startHandshake();

            long tHttp = System.currentTimeMillis();
            String req = "GET " + PING_PATH + " HTTP/1.1\r\nHost: " + PING_HOST + "\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n";
            OutputStream out = sslSock.getOutputStream();
            out.write(req.getBytes(StandardCharsets.UTF_8));
            out.flush();

            byte[] buf = new byte[256];
            int r = sslSock.getInputStream().read(buf);
            long httpElapsed = System.currentTimeMillis() - tHttp;
            long totalElapsed = System.currentTimeMillis() - t0;
            if (r <= 0) return -1;
            String header = new String(buf, 0, r, StandardCharsets.UTF_8);
            if (header.contains(" 204") || header.contains(" 200")) {
                int rtt = (int) (httpElapsed > 5 ? httpElapsed : Math.max(15, totalElapsed / 3));
                return rtt;
            }
            return -1;
        } finally {
            try { if (sslSock != null) sslSock.close(); } catch (Exception ignored) {}
            try { if (rawSock != null) rawSock.close(); } catch (Exception ignored) {}
        }
    }

    private static double httpSpeedThroughSocks(int socksPort, int timeoutMs) {
        Socket rawSock = null;
        SSLSocket sslSock = null;
        try {
            rawSock = socks5Connect(socksPort, SPEED_HOST, 443, timeoutMs);
            SSLSocketFactory factory = getTrustAllSslFactory();
            sslSock = (SSLSocket) factory.createSocket(rawSock, SPEED_HOST, 443, true);
            sslSock.setSoTimeout(timeoutMs);
            sslSock.startHandshake();

            String req = "GET " + SPEED_PATH + " HTTP/1.1\r\nHost: " + SPEED_HOST + "\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n";
            OutputStream out = sslSock.getOutputStream();
            out.write(req.getBytes(StandardCharsets.UTF_8));
            out.flush();

            InputStream in = sslSock.getInputStream();
            byte[] buf = new byte[16384];
            long totalBytes = 0;
            long tStart = System.currentTimeMillis();
            boolean headerChecked = false;

            while (System.currentTimeMillis() - tStart < timeoutMs) {
                int n = in.read(buf);
                if (n <= 0) break;
                if (!headerChecked) {
                    headerChecked = true;
                    String firstChunk = new String(buf, 0, Math.min(n, 128), StandardCharsets.UTF_8);
                    if (!firstChunk.contains(" 200")) return -1.0;
                }
                totalBytes += n;
                if (totalBytes >= 5 * 1024 * 1024) break;
            }

            long elapsedMs = System.currentTimeMillis() - tStart;
            if (totalBytes < SPEED_MIN_BYTES || elapsedMs <= 0) {
                return -1.0;
            }
            double mbps = (totalBytes * 8.0) / (elapsedMs / 1000.0) / 1_000_000.0;
            return Math.round(mbps * 100.0) / 100.0;
        } catch (Exception e) {
            return -1.0;
        } finally {
            try { if (sslSock != null) sslSock.close(); } catch (Exception ignored) {}
            try { if (rawSock != null) rawSock.close(); } catch (Exception ignored) {}
        }
    }

    public static JSONObject benchOneNodeObj(Context ctx, String rawUri, int listenPort, boolean doSpeed) {
        JSONObject result = new JSONObject();
        Process xrayProc = null;
        File cfgFile = null;
        try {
            JSONObject node = parseNodeLink(rawUri);
            String host = node.getString("host");
            int port = node.getInt("port");
            result.put("name", node.optString("name", host + ":" + port));
            result.put("proto", node.optString("protocol", "vless"));
            result.put("host", host + ":" + port);
            result.put("raw", rawUri);

            // Stage 0: Real TCP Probe (1.5s timeout)
            try (Socket tcpProbe = new Socket()) {
                tcpProbe.connect(new InetSocketAddress(host, port), 1500);
                result.put("tcp_alive", true);
            } catch (Exception tcpErr) {
                result.put("tcp_alive", false);
                result.put("latency_avg", -1);
                result.put("latency_min", -1);
                result.put("latency_std", -1);
                result.put("speed_mbps", -1);
                result.put("score", 0);
                result.put("error", "tcp_timeout");
                return result;
            }

            File xrayBin = getXrayBinary(ctx);
            if (!xrayBin.exists()) {
                result.put("latency_avg", -1);
                result.put("speed_mbps", -1);
                result.put("score", 0);
                result.put("error", "xray_binary_missing");
                return result;
            }

            JSONObject xrayCfg = buildXrayConfig(node, listenPort);
            cfgFile = new File(ctx.getCacheDir(), "xray_bench_" + listenPort + ".json");
            try (FileOutputStream fos = new FileOutputStream(cfgFile)) {
                fos.write(xrayCfg.toString().getBytes(StandardCharsets.UTF_8));
            }

            ProcessBuilder pb = new ProcessBuilder(xrayBin.getAbsolutePath(), "run", "-c", cfgFile.getAbsolutePath());
            pb.directory(ctx.getCacheDir());
            xrayProc = pb.start();

            boolean socksReady = false;
            for (int i = 0; i < 15; i++) {
                Thread.sleep(80);
                try (Socket s = new Socket()) {
                    s.connect(new InetSocketAddress("127.0.0.1", listenPort), 100);
                    socksReady = true;
                    break;
                } catch (Exception ignored) {}
            }

            if (!socksReady) {
                result.put("latency_avg", -1);
                result.put("speed_mbps", -1);
                result.put("score", 0);
                result.put("error", "xray_start_fail");
                return result;
            }

            List<Integer> lats = new ArrayList<>();
            for (int r = 0; r < LATENCY_ROUNDS; r++) {
                try {
                    int ms = httpPingThroughSocks(listenPort, 5500);
                    if (ms > 0) lats.add(ms);
                } catch (Exception ignored) {}
            }

            if (lats.isEmpty()) {
                result.put("latency_avg", -1);
                result.put("latency_min", -1);
                result.put("latency_std", -1);
                result.put("speed_mbps", -1);
                result.put("score", 0);
                result.put("error", "ping_fail");
                return result;
            }

            double sum = 0;
            int minLat = Integer.MAX_VALUE;
            for (int v : lats) {
                sum += v;
                if (v < minLat) minLat = v;
            }
            double avgLat = Math.round((sum / lats.size()) * 10.0) / 10.0;
            double variance = 0;
            for (int v : lats) variance += (v - avgLat) * (v - avgLat);
            double stdLat = Math.round(Math.sqrt(variance / lats.size()) * 10.0) / 10.0;

            double spdMbps = -1.0;
            if (doSpeed) {
                spdMbps = httpSpeedThroughSocks(listenPort, 7500);
            }

            double latScore = Math.max(0.0, 100.0 - avgLat / 8.0);
            double stdScore = Math.max(0.0, 100.0 - stdLat * 2.0);
            double spdScore = spdMbps > 0 ? Math.min(100.0, spdMbps * 2.0) : 0.0;
            double score = Math.round((latScore * 0.35 + stdScore * 0.30 + spdScore * 0.35) * 10.0) / 10.0;

            result.put("latency_avg", avgLat);
            result.put("latency_min", minLat);
            result.put("latency_std", stdLat);
            result.put("latency_ok", lats.size());
            result.put("speed_mbps", spdMbps);
            result.put("score", score);
            result.put("error", "");
            return result;
        } catch (Exception e) {
            try {
                result.put("latency_avg", -1);
                result.put("speed_mbps", -1);
                result.put("score", 0);
                result.put("error", e.getMessage());
            } catch (Exception ignored) {}
            return result;
        } finally {
            if (xrayProc != null) {
                try { xrayProc.destroyForcibly(); } catch (Exception ignored) {}
            }
            if (cfgFile != null && cfgFile.exists()) {
                try { cfgFile.delete(); } catch (Exception ignored) {}
            }
        }
    }

    public static String benchOneNodeJson(Context ctx, String rawUri, int listenPort, boolean doSpeed) {
        return benchOneNodeObj(ctx, rawUri, listenPort, doSpeed).toString();
    }

    // Asynchronous Multi-Threaded Batch Benchmark Pool
    public static synchronized String startBatchBench(final Context ctx, String urisJsonArrayStr, final boolean doSpeed, int workers) {
        stopBatchBench();
        try {
            final Context appCtx = ctx != null ? ctx.getApplicationContext() : null;
            acquireBenchLocks(appCtx);
            final JSONArray arr = new JSONArray(urisJsonArrayStr);
            final int total = arr.length();
            batchTotal.set(total);
            batchDone.set(0);
            batchAlive.set(0);
            batchResults.clear();
            batchLogs.clear();
            batchCancel.set(false);
            batchPaused.set(false);
            batchRunning.set(true);
            lastNotifUpdateMs = System.currentTimeMillis();
            if (appCtx != null) {
                KeepAliveService.updateNotificationStatic(appCtx, "⚡ 正在实测节点 (0/" + total + ") · 切后台全速运行中");
            }

            final int nWorkers = Math.max(1, Math.min(6, workers));
            batchExecutor = Executors.newFixedThreadPool(nWorkers);

            for (int i = 0; i < total; i++) {
                final int idx = i;
                final String uri = arr.optString(i, "");
                batchExecutor.submit(() -> {
                    while (batchPaused.get() && !batchCancel.get()) {
                        try { Thread.sleep(150); } catch (Exception ignored) { break; }
                    }
                    if (batchCancel.get() || uri.isEmpty()) {
                        int dNow = batchDone.incrementAndGet();
                        if (dNow >= total) {
                            batchRunning.set(false);
                            releaseBenchLocksIfIdle();
                        }
                        return;
                    }
                    int port = 32200 + (idx % (nWorkers * 3)) * 2 + (int) (Thread.currentThread().getId() % 2);
                    JSONObject res = benchOneNodeObj(appCtx != null ? appCtx : ctx, uri, port, doSpeed);
                    if (batchCancel.get()) {
                        int dNow = batchDone.incrementAndGet();
                        if (dNow >= total) {
                            batchRunning.set(false);
                            releaseBenchLocksIfIdle();
                        }
                        return;
                    }
                    batchResults.add(res);
                    int doneNow = batchDone.incrementAndGet();
                    double lat = res.optDouble("latency_avg", -1);
                    String name = res.optString("name", "node");
                    String host = res.optString("host", "");
                    if (lat >= 0) {
                        batchAlive.incrementAndGet();
                        double spd = res.optDouble("speed_mbps", -1);
                        double sc = res.optDouble("score", 0);
                        batchLogs.add("PASS|[" + doneNow + "/" + total + "] " + name + " (" + host + ") -> 延迟 " + lat + "ms | 速度 " + (spd > 0 ? spd + "Mbps" : "仅延迟通") + " | 评分 " + sc);
                    } else {
                        batchLogs.add("DEAD|[" + doneNow + "/" + total + "] " + name + " (" + host + ") -> -1ms (" + res.optString("error", "ping_fail") + ")");
                    }
                    long nowMs = System.currentTimeMillis();
                    if (appCtx != null && (doneNow >= total || nowMs - lastNotifUpdateMs >= 600)) {
                        lastNotifUpdateMs = nowMs;
                        String st = doneNow >= total
                            ? ("✅ 本轮实测完成: 连通 " + batchAlive.get() + "/" + total + " 条")
                            : ("⚡ 后台实测中: " + doneNow + "/" + total + " (连通 " + batchAlive.get() + ") · 全速运行");
                        KeepAliveService.updateNotificationStatic(appCtx, st);
                    }
                    if (doneNow >= total) {
                        batchRunning.set(false);
                        releaseBenchLocksIfIdle();
                    }
                });
            }
            return new JSONObject().put("ok", true).put("total", total).toString();
        } catch (Exception e) {
            batchRunning.set(false);
            releaseBenchLocksIfIdle();
            return "{\"ok\":false,\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    public static String getBatchProgressJson() {
        try {
            JSONObject obj = new JSONObject();
            int total = batchTotal.get();
            int done = batchDone.get();
            obj.put("running", batchRunning.get() && done < total);
            obj.put("paused", batchPaused.get());
            obj.put("total", total);
            obj.put("done", done);
            obj.put("alive", batchAlive.get());

            JSONArray logsArr = new JSONArray();
            List<String> drained = new ArrayList<>(batchLogs);
            batchLogs.clear();
            for (String l : drained) logsArr.put(l);
            obj.put("newLogs", logsArr);

            // Always return incremental results so partial progress is saved in real-time (even in background)
            JSONArray resArr = new JSONArray();
            for (JSONObject r : batchResults) resArr.put(r);
            obj.put("results", resArr);
            return obj.toString();
        } catch (Exception e) {
            return "{\"running\":false}";
        }
    }

    public static void setBatchPaused(boolean paused) {
        batchPaused.set(paused);
    }

    public static synchronized void stopBatchBench() {
        batchCancel.set(true);
        batchPaused.set(false);
        batchRunning.set(false);
        if (batchExecutor != null) {
            try { batchExecutor.shutdownNow(); } catch (Exception ignored) {}
            batchExecutor = null;
        }
        releaseBenchLocksIfIdle();
    }

    public static synchronized void startAsyncSubFetch(final Context ctx, final String targetUrl, final String proxyNodeRaw) {
        stopAsyncSubFetch();
        final Context appCtx = ctx != null ? ctx.getApplicationContext() : null;
        acquireBenchLocks(appCtx);
        subFetchResultJson = "";
        subFetchRunning.set(true);
        subFetchThread = new Thread(() -> {
            try {
                String res = probeAndFetchSubJson(appCtx != null ? appCtx : ctx, targetUrl, proxyNodeRaw);
                subFetchResultJson = res;
            } catch (Exception e) {
                subFetchResultJson = "{\"ok\":false,\"directOk\":false,\"proxyOk\":false,\"body\":\"\"}";
            } finally {
                subFetchRunning.set(false);
                releaseBenchLocksIfIdle();
            }
        });
        subFetchThread.setDaemon(true);
        subFetchThread.start();
    }

    public static String getAsyncSubFetchJson() {
        if (subFetchRunning.get()) {
            return "{\"running\":true}";
        }
        return subFetchResultJson != null && !subFetchResultJson.isEmpty()
            ? subFetchResultJson
            : "{\"running\":false,\"ok\":false}";
    }

    public static synchronized void stopAsyncSubFetch() {
        subFetchRunning.set(false);
        if (subFetchThread != null) {
            try { subFetchThread.interrupt(); } catch (Exception ignored) {}
            subFetchThread = null;
        }
    }

    // Native Dual-Channel Subscription Probe & Fetcher (Zero CORS, Direct + Xray Proxy)
    private static String readStreamAsString(InputStream in, int maxBytes) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) {
            bos.write(buf, 0, n);
            if (bos.size() >= maxBytes) break;
        }
        return new String(bos.toByteArray(), StandardCharsets.UTF_8);
    }

    private static String fetchOverSocks(int socksPort, String urlStr, int timeoutMs) throws Exception {
        URL u = new URL(urlStr);
        String host = u.getHost();
        boolean isHttps = "https".equalsIgnoreCase(u.getProtocol());
        int port = u.getPort() > 0 ? u.getPort() : (isHttps ? 443 : 80);
        String path = u.getFile();
        if (path == null || path.isEmpty()) path = "/";

        Socket rawSock = null;
        Socket workSock = null;
        try {
            rawSock = socks5Connect(socksPort, host, port, timeoutMs);
            if (isHttps) {
                SSLSocketFactory factory = getTrustAllSslFactory();
                SSLSocket ssl = (SSLSocket) factory.createSocket(rawSock, host, port, true);
                ssl.setSoTimeout(timeoutMs);
                ssl.startHandshake();
                workSock = ssl;
            } else {
                workSock = rawSock;
            }
            String req = "GET " + path + " HTTP/1.1\r\nHost: " + host + "\r\nUser-Agent: v2rayN/7.0\r\nAccept: */*\r\nConnection: close\r\n\r\n";
            OutputStream out = workSock.getOutputStream();
            out.write(req.getBytes(StandardCharsets.UTF_8));
            out.flush();

            String rawResp = readStreamAsString(workSock.getInputStream(), 2 * 1024 * 1024);
            int splitIdx = rawResp.indexOf("\r\n\r\n");
            if (splitIdx < 0) return "";
            String header = rawResp.substring(0, splitIdx);
            if (!header.contains(" 200")) throw new RuntimeException("HTTP non-200");
            return rawResp.substring(splitIdx + 4);
        } finally {
            try { if (workSock != null) workSock.close(); } catch (Exception ignored) {}
            try { if (rawSock != null) rawSock.close(); } catch (Exception ignored) {}
        }
    }

    public static String probeAndFetchSubJson(Context ctx, String targetUrl, String proxyNodeRaw) {
        JSONObject out = new JSONObject();
        String body = "";
        boolean directOk = false;
        long directMs = -1;
        boolean proxyOk = false;
        long proxyMs = -1;

        // 1. Test Direct (Proxy.NO_PROXY)
        long t0 = System.currentTimeMillis();
        try {
            URL u = new URL(targetUrl);
            HttpURLConnection conn = (HttpURLConnection) u.openConnection(Proxy.NO_PROXY);
            if (conn instanceof HttpsURLConnection) {
                ((HttpsURLConnection) conn).setSSLSocketFactory(getTrustAllSslFactory());
            }
            conn.setConnectTimeout(4500);
            conn.setReadTimeout(6000);
            conn.setRequestProperty("User-Agent", "v2rayN/7.0 (Android)");
            int code = conn.getResponseCode();
            if (code >= 200 && code < 300) {
                String txt = readStreamAsString(conn.getInputStream(), 2 * 1024 * 1024);
                if (txt != null && txt.trim().length() > 10) {
                    directOk = true;
                    directMs = System.currentTimeMillis() - t0;
                    body = txt;
                }
            }
            conn.disconnect();
        } catch (Exception ignored) {}

        // 2. Test Proxy (Try local 10808 first, then temporary libxray.so on port 32091)
        long t1 = System.currentTimeMillis();
        Process tempXray = null;
        File tempCfg = null;
        try {
            int activeSocksPort = -1;
            try (Socket s = new Socket()) {
                s.connect(new InetSocketAddress("127.0.0.1", 10808), 150);
                activeSocksPort = 10808;
            } catch (Exception ignored) {}

            if (activeSocksPort < 0 && proxyNodeRaw != null && !proxyNodeRaw.trim().isEmpty()) {
                File xrayBin = getXrayBinary(ctx);
                if (xrayBin.exists()) {
                    JSONObject node = parseNodeLink(proxyNodeRaw);
                    JSONObject cfg = buildXrayConfig(node, 32091);
                    tempCfg = new File(ctx.getCacheDir(), "xray_sub_32091.json");
                    try (FileOutputStream fos = new FileOutputStream(tempCfg)) {
                        fos.write(cfg.toString().getBytes(StandardCharsets.UTF_8));
                    }
                    tempXray = new ProcessBuilder(xrayBin.getAbsolutePath(), "run", "-c", tempCfg.getAbsolutePath())
                        .directory(ctx.getCacheDir()).start();
                    for (int i = 0; i < 12; i++) {
                        Thread.sleep(80);
                        try (Socket s = new Socket()) {
                            s.connect(new InetSocketAddress("127.0.0.1", 32091), 100);
                            activeSocksPort = 32091;
                            break;
                        } catch (Exception ignored) {}
                    }
                }
            }

            if (activeSocksPort > 0) {
                String pTxt = fetchOverSocks(activeSocksPort, targetUrl, 7000);
                if (pTxt != null && pTxt.trim().length() > 10) {
                    proxyOk = true;
                    proxyMs = System.currentTimeMillis() - t1;
                    if (body.isEmpty()) body = pTxt;
                }
            }
        } catch (Exception ignored) {
        } finally {
            if (tempXray != null) {
                try { tempXray.destroyForcibly(); } catch (Exception ignored) {}
            }
            if (tempCfg != null && tempCfg.exists()) {
                try { tempCfg.delete(); } catch (Exception ignored) {}
            }
        }

        try {
            out.put("ok", true);
            out.put("directOk", directOk);
            out.put("directMs", directMs);
            out.put("proxyOk", proxyOk);
            out.put("proxyMs", proxyMs);
            out.put("body", body);
        } catch (Exception ignored) {}
        return out.toString();
    }
}
"""

MAIN_ACTIVITY_JAVA = r"""package com.winnerds.v2rayn.threestage;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class MainActivity extends BridgeActivity {
    private volatile boolean keepAliveEnabled = true;
    private volatile boolean isActivityInBackground = false;
    private ScheduledExecutorService bgPulseExecutor = null;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        startKeepAliveService("Xray真核已加载 · 息屏与后台常驻守护中");

        if (Build.VERSION.SDK_INT >= 33) {
            try {
                if (checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 10808);
                }
            } catch (Exception ignored) {}
        }

        if (getBridge() != null && getBridge().getWebView() != null) {
            WebView webView = getBridge().getWebView();
            WebSettings ws = webView.getSettings();
            ws.setMediaPlaybackRequiresUserGesture(false);
            ws.setUseWideViewPort(true);
            ws.setLoadWithOverviewMode(false);
            ws.setSupportZoom(false);
            ws.setBuiltInZoomControls(false);
            ws.setDisplayZoomControls(false);
            ws.setTextZoom(100);
            webView.setInitialScale(0);
            webView.addJavascriptInterface(new KeepAliveJsBridge(), "AndroidKeepAlive");
        }

        startNativeBackgroundHeartbeat();
    }

    private void keepWebViewAwake() {
        try {
            if (getBridge() != null && getBridge().getWebView() != null) {
                final WebView webView = getBridge().getWebView();
                webView.onResume();
                webView.resumeTimers();
                try {
                    webView.dispatchWindowVisibilityChanged(View.VISIBLE);
                } catch (Exception ignored) {}
                try {
                    java.lang.reflect.Method m = WebView.class.getDeclaredMethod("onWindowVisibilityChanged", int.class);
                    m.setAccessible(true);
                    m.invoke(webView, View.VISIBLE);
                } catch (Exception ignored) {}
            }
        } catch (Exception ignored) {}
    }

    private void scheduleBackgroundWebViewWakeups() {
        int[] delays = new int[]{30, 120, 320, 750, 1500};
        for (int d : delays) {
            mainHandler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (isActivityInBackground && (keepAliveEnabled || XrayBenchEngine.isAnyTaskRunning())) {
                        keepWebViewAwake();
                    }
                }
            }, d);
        }
    }

    private synchronized void startNativeBackgroundHeartbeat() {
        if (bgPulseExecutor != null) return;
        bgPulseExecutor = Executors.newSingleThreadScheduledExecutor();
        bgPulseExecutor.scheduleAtFixedRate(new Runnable() {
            @Override
            public void run() {
                if (!keepAliveEnabled && !XrayBenchEngine.isAnyTaskRunning()) return;
                mainHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        try {
                            if (isActivityInBackground || XrayBenchEngine.isAnyTaskRunning()) {
                                keepWebViewAwake();
                            }
                            if (getBridge() != null && getBridge().getWebView() != null) {
                                getBridge().getWebView().evaluateJavascript(
                                    "if(window.__nativeBgPulse) window.__nativeBgPulse();", null
                                );
                            }
                        } catch (Exception ignored) {}
                    }
                });
            }
        }, 250, 250, TimeUnit.MILLISECONDS);
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        if (getBridge() != null && getBridge().getWebView() != null) {
            final WebView webView = getBridge().getWebView();
            final Runnable reflowTask = new Runnable() {
                @Override
                public void run() {
                    try {
                        webView.setInitialScale(0);
                        webView.requestLayout();
                        webView.invalidate();
                        webView.evaluateJavascript("if(window.onNativeOrientationChanged) window.onNativeOrientationChanged();", null);
                    } catch (Exception ignored) {}
                }
            };
            webView.postDelayed(reflowTask, 50);
            webView.postDelayed(reflowTask, 220);
            webView.postDelayed(reflowTask, 450);
        }
    }

    @Override
    public void onResume() {
        super.onResume();
        isActivityInBackground = false;
        if (getBridge() != null && getBridge().getWebView() != null) {
            final WebView webView = getBridge().getWebView();
            keepWebViewAwake();
            final Runnable wakeRecover = new Runnable() {
                @Override
                public void run() {
                    try {
                        webView.setInitialScale(0);
                        webView.requestLayout();
                        webView.invalidate();
                        webView.evaluateJavascript("if(window.onNativeScreenResume) window.onNativeScreenResume();", null);
                    } catch (Exception ignored) {}
                }
            };
            webView.postDelayed(wakeRecover, 40);
            webView.postDelayed(wakeRecover, 260);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && getBridge() != null && getBridge().getWebView() != null) {
            final WebView webView = getBridge().getWebView();
            keepWebViewAwake();
            webView.postDelayed(new Runnable() {
                @Override
                public void run() {
                    try {
                        webView.requestLayout();
                        webView.invalidate();
                        webView.evaluateJavascript("if(window.onNativeScreenResume) window.onNativeScreenResume();", null);
                    } catch (Exception ignored) {}
                }
            }, 80);
        } else if (!hasFocus && (keepAliveEnabled || XrayBenchEngine.isAnyTaskRunning())) {
            keepWebViewAwake();
            scheduleBackgroundWebViewWakeups();
        }
    }

    @Override
    public void onPause() {
        super.onPause();
        isActivityInBackground = true;
        if (keepAliveEnabled || XrayBenchEngine.isAnyTaskRunning()) {
            keepWebViewAwake();
            scheduleBackgroundWebViewWakeups();
        }
    }

    @Override
    public void onStop() {
        super.onStop();
        isActivityInBackground = true;
        if (keepAliveEnabled || XrayBenchEngine.isAnyTaskRunning()) {
            keepWebViewAwake();
            scheduleBackgroundWebViewWakeups();
        }
    }

    @Override
    public void onBackPressed() {
        try {
            if (getBridge() != null && getBridge().getWebView() != null) {
                final WebView webView = getBridge().getWebView();
                webView.evaluateJavascript(
                    "(function(){ return window.handleAndroidBackButton ? String(window.handleAndroidBackButton()) : 'false'; })()",
                    value -> {
                        if (value == null || !value.contains("true")) {
                            moveTaskToBack(true);
                        }
                    }
                );
                return;
            }
        } catch (Exception ignored) {}
        moveTaskToBack(true);
    }

    @Override
    public void onDestroy() {
        if (bgPulseExecutor != null) {
            try { bgPulseExecutor.shutdownNow(); } catch (Exception ignored) {}
            bgPulseExecutor = null;
        }
        super.onDestroy();
    }

    private void startKeepAliveService(String statusText) {
        try {
            if (KeepAliveService.isRunning && isActivityInBackground) {
                KeepAliveService.updateNotificationStatic(this, statusText);
                return;
            }
            Intent serviceIntent = new Intent(this, KeepAliveService.class);
            serviceIntent.putExtra("status", statusText);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }
        } catch (Exception e) {
            KeepAliveService.updateNotificationStatic(this, statusText);
        }
    }

    private void stopKeepAliveService() {
        try {
            Intent serviceIntent = new Intent(this, KeepAliveService.class);
            stopService(serviceIntent);
        } catch (Exception ignored) {}
    }

    public class KeepAliveJsBridge {
        @JavascriptInterface
        public boolean hasNativeXray() {
            return XrayBenchEngine.isXrayAvailable(MainActivity.this);
        }

        @JavascriptInterface
        public String getXrayVersion() {
            return XrayBenchEngine.getXrayVersion(MainActivity.this);
        }

        @JavascriptInterface
        public String benchNodeJson(String rawUri, int listenPort, boolean doSpeed) {
            return XrayBenchEngine.benchOneNodeJson(MainActivity.this, rawUri, listenPort, doSpeed);
        }

        @JavascriptInterface
        public String startBatchBench(String urisJsonArray, boolean doSpeed, int workers) {
            return XrayBenchEngine.startBatchBench(MainActivity.this, urisJsonArray, doSpeed, workers);
        }

        @JavascriptInterface
        public String getBatchProgressJson() {
            return XrayBenchEngine.getBatchProgressJson();
        }

        @JavascriptInterface
        public void setBatchPaused(boolean paused) {
            XrayBenchEngine.setBatchPaused(paused);
        }

        @JavascriptInterface
        public void stopBatchBench() {
            XrayBenchEngine.stopBatchBench();
        }

        @JavascriptInterface
        public void startAsyncSubFetch(String targetUrl, String proxyNodeRaw) {
            XrayBenchEngine.startAsyncSubFetch(MainActivity.this, targetUrl, proxyNodeRaw);
        }

        @JavascriptInterface
        public String getAsyncSubFetchJson() {
            return XrayBenchEngine.getAsyncSubFetchJson();
        }

        @JavascriptInterface
        public void stopAsyncSubFetch() {
            XrayBenchEngine.stopAsyncSubFetch();
        }

        @JavascriptInterface
        public String probeAndFetchSubJson(String targetUrl, String proxyNodeRaw) {
            return XrayBenchEngine.probeAndFetchSubJson(MainActivity.this, targetUrl, proxyNodeRaw);
        }

        @JavascriptInterface
        public boolean copyToClipboard(String text) {
            try {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null) {
                    cm.setPrimaryClip(ClipData.newPlainText("v2rayN-nodes", text));
                    return true;
                }
            } catch (Exception ignored) {}
            return false;
        }

        @JavascriptInterface
        public String readFromClipboard() {
            try {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null && cm.hasPrimaryClip()) {
                    ClipData cd = cm.getPrimaryClip();
                    if (cd != null && cd.getItemCount() > 0) {
                        CharSequence cs = cd.getItemAt(0).coerceToText(MainActivity.this);
                        if (cs != null) return cs.toString();
                    }
                }
            } catch (Exception ignored) {}
            return "";
        }

        @JavascriptInterface
        public boolean launchV2rayNG(String clipText) {
            if (clipText != null && !clipText.isEmpty()) {
                copyToClipboard(clipText);
            }
            String[] pkgs = new String[]{
                "com.v2ray.ang",
                "moe.nb4a",
                "io.nekohasekai.sagernet",
                "com.github.metacubex.clash.meta",
                "com.github.kr328.clash",
                "io.nekohasekai.sfa",
                "com.karing.app"
            };
            for (String pkg : pkgs) {
                try {
                    Intent launch = getPackageManager().getLaunchIntentForPackage(pkg);
                    if (launch != null) {
                        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        startActivity(launch);
                        return true;
                    }
                } catch (Exception ignored) {}
            }
            return false;
        }

        @JavascriptInterface
        public String exportOrShareFile(String filename, String content) {
            String savedPath = "";
            try {
                File dlDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                if (!dlDir.exists()) dlDir.mkdirs();
                File outFile = new File(dlDir, filename);
                try (FileOutputStream fos = new FileOutputStream(outFile)) {
                    fos.write(content.getBytes(StandardCharsets.UTF_8));
                }
                savedPath = outFile.getAbsolutePath();
            } catch (Exception ignored) {}

            try {
                Intent sendIntent = new Intent(Intent.ACTION_SEND);
                sendIntent.setType("text/plain");
                sendIntent.putExtra(Intent.EXTRA_SUBJECT, filename);
                sendIntent.putExtra(Intent.EXTRA_TEXT, content);
                Intent shareIntent = Intent.createChooser(sendIntent, "导出 / 分享: " + filename);
                shareIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(shareIntent);
            } catch (Exception ignored) {}
            return savedPath;
        }

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
        public void minimizeAppToBack() {
            runOnUiThread(() -> {
                try { moveTaskToBack(true); } catch (Exception ignored) {}
            });
        }

        @JavascriptInterface
        public void pushMergedRecommendationNotification(String title, String body) {
            try {
                if (keepAliveEnabled && body != null && !body.isEmpty()) {
                    startKeepAliveService(body);
                }
                NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
                if (nm == null) return;
                String pushChannelId = "v2rayn_3stage_push_channel";
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    NotificationChannel ch = new NotificationChannel(
                        pushChannelId,
                        "三段式合并推荐推送",
                        NotificationManager.IMPORTANCE_HIGH
                    );
                    ch.setDescription("三段式测试完成后的合并数据推荐与均衡Top500通知");
                    nm.createNotificationChannel(ch);
                }
                Intent intent = new Intent(MainActivity.this, MainActivity.class);
                intent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                int flags = PendingIntent.FLAG_UPDATE_CURRENT;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    flags |= PendingIntent.FLAG_IMMUTABLE;
                }
                PendingIntent pi = PendingIntent.getActivity(MainActivity.this, 2026, intent, flags);
                Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                    ? new Notification.Builder(MainActivity.this, pushChannelId)
                    : new Notification.Builder(MainActivity.this);
                b.setContentTitle(title != null && !title.isEmpty() ? title : "🎯 三段式测试合并推荐已生成")
                 .setContentText(body != null ? body : "已确认延迟与下载速度均衡Top500，点击查看或导入v2rayNG")
                 .setSmallIcon(android.R.drawable.stat_sys_download_done)
                 .setContentIntent(pi)
                 .setAutoCancel(true);
                nm.notify(20808, b.build());
            } catch (Exception ignored) {}
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

        @JavascriptInterface
        public void setScreenOrientationMode(final String mode) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    try {
                        if ("portrait".equalsIgnoreCase(mode)) {
                            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);
                        } else if ("landscape".equalsIgnoreCase(mode)) {
                            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
                        } else {
                            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_FULL_USER);
                        }
                    } catch (Exception ignored) {}
                }
            });
        }
    }
}
"""


def patch_manifest():
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")
    xml = MANIFEST_PATH.read_text(encoding="utf-8")

    if 'android:extractNativeLibs=' not in xml:
        xml = xml.replace("<application", '<application\n        android:extractNativeLibs="true"', 1)
    else:
        xml = xml.replace('android:extractNativeLibs="false"', 'android:extractNativeLibs="true"')

    service_decl = (
        '        <service\n'
        '            android:name=".KeepAliveService"\n'
        '            android:enabled="true"\n'
        '            android:exported="false"\n'
        '            android:stopWithTask="false"\n'
        '            android:foregroundServiceType="dataSync|mediaPlayback" />\n'
    )
    if "KeepAliveService" not in xml:
        xml = xml.replace("</application>", service_decl + "    </application>")
    else:
        xml = xml.replace('android:foregroundServiceType="dataSync"', 'android:stopWithTask="false"\n            android:foregroundServiceType="dataSync|mediaPlayback"')

    queries_decl = (
        '    <queries>\n'
        '        <package android:name="com.v2ray.ang" />\n'
        '        <package android:name="moe.nb4a" />\n'
        '        <package android:name="io.nekohasekai.sagernet" />\n'
        '    </queries>\n'
    )
    if "<queries>" not in xml:
        xml = xml.replace("</manifest>", queries_decl + "</manifest>")

    perms = [
        '<uses-permission android:name="android.permission.INTERNET" />',
        '<uses-permission android:name="android.permission.WAKE_LOCK" />',
        '<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />',
        '<uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />',
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />',
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />',
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />',
        '<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />',
        '<uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />',
    ]
    perm_block = "\n".join(f"    {p}" for p in perms if p not in xml)
    if perm_block:
        xml = xml.replace("</manifest>", perm_block + "\n</manifest>")

    MANIFEST_PATH.write_text(xml, encoding="utf-8")
    print("[KeepAlivePatch] Patched AndroidManifest.xml (with extractNativeLibs=true, dataSync|mediaPlayback & queries).")


def install_permanent_keystore():
    ks_bytes = base64.b64decode(PERMANENT_KEYSTORE_B64)
    app_ks = ANDROID_DIR / "app" / "v2rayn-permanent.keystore"
    app_ks.parent.mkdir(parents=True, exist_ok=True)
    app_ks.write_bytes(ks_bytes)

    try:
        user_android_dir = Path.home() / ".android"
        user_android_dir.mkdir(parents=True, exist_ok=True)
        (user_android_dir / "debug.keystore").write_bytes(ks_bytes)
        print("[KeepAlivePatch] Installed permanent debug.keystore to ~/.android/debug.keystore")
    except Exception as e:
        print("[KeepAlivePatch] Warning writing ~/.android/debug.keystore:", e)

    print(f"[KeepAlivePatch] Installed permanent keystore to {app_ks} ({len(ks_bytes)} bytes).")


def patch_build_gradle():
    if not BUILD_GRADLE_PATH.exists():
        return
    install_permanent_keystore()
    txt = BUILD_GRADLE_PATH.read_text(encoding="utf-8")

    # Monotonically increasing versionCode (minutes since epoch offset -> strictly increases on every build)
    version_code = max(200, int(time.time() // 60) - 29000000)
    version_name = f"2.1.{version_code}"
    txt = txt.replace("versionCode 1", f"versionCode {version_code}", 1)
    txt = txt.replace('versionName "1.0"', f'versionName "{version_name}"', 1)

    signing_and_packaging = """
    signingConfigs {
        fixedSign {
            storeFile file('v2rayn-permanent.keystore')
            storePassword 'android'
            keyAlias 'androiddebugkey'
            keyPassword 'android'
            v1SigningEnabled true
            v2SigningEnabled true
        }
    }
    packagingOptions {
        jniLibs {
            useLegacyPackaging true
        }
    }
"""
    if "useLegacyPackaging" not in txt:
        txt = txt.replace("android {", "android {" + signing_and_packaging, 1)

    if "signingConfig signingConfigs.fixedSign" not in txt:
        txt = txt.replace(
            "buildTypes {\n        release {",
            "buildTypes {\n        debug {\n            signingConfig signingConfigs.fixedSign\n        }\n        release {\n            signingConfig signingConfigs.fixedSign"
        )

    BUILD_GRADLE_PATH.write_text(txt, encoding="utf-8")
    print(f"[KeepAlivePatch] Patched app/build.gradle with fixedSign keystore & versionCode={version_code} ({version_name}).")


def write_java_classes():
    PKG_DIR.mkdir(parents=True, exist_ok=True)
    (PKG_DIR / "KeepAliveService.java").write_text(KEEPALIVE_SERVICE_JAVA, encoding="utf-8")
    (PKG_DIR / "XrayBenchEngine.java").write_text(XRAY_BENCH_ENGINE_JAVA, encoding="utf-8")
    (PKG_DIR / "MainActivity.java").write_text(MAIN_ACTIVITY_JAVA, encoding="utf-8")
    print("[KeepAlivePatch] Wrote KeepAliveService.java, XrayBenchEngine.java, and MainActivity.java.")


if __name__ == "__main__":
    patch_manifest()
    patch_build_gradle()
    write_java_classes()
