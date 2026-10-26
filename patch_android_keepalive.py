#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Injects:
1. Native Android Xray-Core Benchmark Engine (XrayBenchEngine.java + bundled libxray.so)
   - Line-by-line Java port of real_bench_via_xray.py + real_bench_v2.py
   - Stage 0: Real TCP socket connect probe
   - Stage 1: Spawns real libxray.so child process -> raw SOCKS5 (ATYP=0x03 remote DNS) ->
              TLS 443 -> https://i.ytimg.com/generate_204 (3 rounds: avg / min / std)
              Dead/unreachable nodes genuinely return latency_avg = -1, score = 0!
   - Stage 2: Raw SOCKS5 -> TLS 443 -> https://speed.cloudflare.com/__down?bytes=5000000
              (with L041 minimum 128KB payload check) -> real Mbps download speed
2. Screen-Off KeepAliveService.java (PARTIAL_WAKE_LOCK + WifiLock + ForegroundService)
3. MainActivity.java (@JavascriptInterface AndroidKeepAlive + WebView.resumeTimers())
4. AndroidManifest.xml (extractNativeLibs="true" + permissions) & build.gradle (useLegacyPackaging true)
"""
from pathlib import Path

ANDROID_DIR = Path("android")
MANIFEST_PATH = ANDROID_DIR / "app" / "src" / "main" / "AndroidManifest.xml"
BUILD_GRADLE_PATH = ANDROID_DIR / "app" / "build.gradle"
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
        String statusText = "Xray真核已集成 · 息屏后台守护中";
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

        builder.setContentTitle("v2rayN 三段式管家 V2.0 (Xray真核)")
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
            channel.setDescription("保持息屏状态下定时获取、Xray真核三段式测试与汇总不中断");
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

XRAY_BENCH_ENGINE_JAVA = r"""package com.winnerds.v2rayn.threestage;

import android.content.Context;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
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

    public static File getXrayBinary(Context ctx) {
        String nativeDir = ctx.getApplicationInfo().nativeLibraryDir;
        File f = new File(nativeDir, "libxray.so");
        return f;
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
            return line != null ? line : "available";
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
            String b64 = rest.split("#")[0].trim();
            byte[] decoded = Base64.decode(b64, Base64.DEFAULT);
            JSONObject j = new JSONObject(new String(decoded, StandardCharsets.UTF_8));
            String host = j.optString("add", "").trim();
            int port = Integer.parseInt(j.optString("port", "443").split("/")[0].trim());
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
            byte[] dec = Base64.decode(rest, Base64.DEFAULT);
            String full = new String(dec, StandardCharsets.UTF_8);
            int at2 = full.lastIndexOf('@');
            if (at2 >= 0) {
                userPart = full.substring(0, at2);
                hostPortPart = full.substring(at2 + 1);
            }
        }

        if ("ss".equals(proto)) {
            if (!userPart.contains(":")) {
                try {
                    String padded = userPart;
                    while (padded.length() % 4 != 0) padded += "=";
                    byte[] dec = Base64.decode(padded, Base64.URL_SAFE | Base64.DEFAULT);
                    userPart = new String(dec, StandardCharsets.UTF_8);
                } catch (Exception ignored) {}
            }
            int cIdx = userPart.indexOf(':');
            if (cIdx > 0) {
                node.put("method", userPart.substring(0, cIdx));
                node.put("password", userPart.substring(cIdx + 1));
            } else {
                node.put("method", "chacha20-ietf-poly1305");
                node.put("password", userPart);
            }
        } else {
            try {
                userPart = URLDecoder.decode(userPart, "UTF-8");
            } catch (Exception ignored) {}
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

    // Exact port of real_bench_v2.py socks5_connect (ATYP=0x03 remote DNS resolution via Xray)
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
        req[3] = 0x03; // ATYP = Domain name (let Xray resolve DNS remotely)
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
            throw new RuntimeException("SOCKS5 connect rejected: " + (n > 1 ? resp[1] : -1));
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

            String req = "GET " + PING_PATH + " HTTP/1.1\r\nHost: " + PING_HOST + "\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n";
            OutputStream out = sslSock.getOutputStream();
            out.write(req.getBytes(StandardCharsets.UTF_8));
            out.flush();

            byte[] buf = new byte[256];
            int r = sslSock.getInputStream().read(buf);
            long elapsed = System.currentTimeMillis() - t0;
            if (r <= 0) return -1;
            String header = new String(buf, 0, r, StandardCharsets.UTF_8);
            if (header.contains(" 204") || header.contains(" 200")) {
                return (int) elapsed;
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

    public static String benchOneNodeJson(Context ctx, String rawUri, int listenPort, boolean doSpeed) {
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
                return result.toString();
            }

            // Stage 1: Spawn real libxray.so process
            File xrayBin = getXrayBinary(ctx);
            if (!xrayBin.exists()) {
                result.put("latency_avg", -1);
                result.put("speed_mbps", -1);
                result.put("score", 0);
                result.put("error", "xray_binary_missing");
                return result.toString();
            }

            JSONObject xrayCfg = buildXrayConfig(node, listenPort);
            cfgFile = new File(ctx.getCacheDir(), "xray_bench_" + listenPort + ".json");
            try (FileOutputStream fos = new FileOutputStream(cfgFile)) {
                fos.write(xrayCfg.toString().getBytes(StandardCharsets.UTF_8));
            }

            ProcessBuilder pb = new ProcessBuilder(xrayBin.getAbsolutePath(), "run", "-c", cfgFile.getAbsolutePath());
            pb.directory(ctx.getCacheDir());
            xrayProc = pb.start();

            // Wait up to 1200ms for local SOCKS5 port to listen
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
                return result.toString();
            }

            // 3 rounds of real generate_204 over Xray SOCKS5 tunnel
            List<Integer> lats = new ArrayList<>();
            for (int r = 0; r < LATENCY_ROUNDS; r++) {
                try {
                    int ms = httpPingThroughSocks(listenPort, 6000);
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
                return result.toString();
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
                spdMbps = httpSpeedThroughSocks(listenPort, 8000);
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
            return result.toString();
        } catch (Exception e) {
            try {
                result.put("latency_avg", -1);
                result.put("speed_mbps", -1);
                result.put("score", 0);
                result.put("error", e.getMessage());
            } catch (Exception ignored) {}
            return result.toString();
        } finally {
            if (xrayProc != null) {
                try { xrayProc.destroyForcibly(); } catch (Exception ignored) {}
            }
            if (cfgFile != null && cfgFile.exists()) {
                try { cfgFile.delete(); } catch (Exception ignored) {}
            }
        }
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
        startKeepAliveService("Xray真核已加载 · 息屏守护运行中");

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

    # Ensure extractNativeLibs="true" on <application so libxray.so is extracted with 0755 permissions
    if 'android:extractNativeLibs=' not in xml:
        xml = xml.replace("<application", '<application\n        android:extractNativeLibs="true"', 1)
    else:
        xml = xml.replace('android:extractNativeLibs="false"', 'android:extractNativeLibs="true"')

    service_decl = (
        '        <service\n'
        '            android:name=".KeepAliveService"\n'
        '            android:enabled="true"\n'
        '            android:exported="false"\n'
        '            android:foregroundServiceType="dataSync" />\n'
    )
    if "KeepAliveService" not in xml:
        xml = xml.replace("</application>", service_decl + "    </application>")

    perms = [
        '<uses-permission android:name="android.permission.INTERNET" />',
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
    print("[KeepAlivePatch] Patched AndroidManifest.xml (with extractNativeLibs=true).")


def patch_build_gradle():
    if not BUILD_GRADLE_PATH.exists():
        return
    txt = BUILD_GRADLE_PATH.read_text(encoding="utf-8")
    packaging_snippet = """
    packagingOptions {
        jniLibs {
            useLegacyPackaging true
        }
    }
"""
    if "useLegacyPackaging" not in txt:
        txt = txt.replace("android {", "android {" + packaging_snippet, 1)
        BUILD_GRADLE_PATH.write_text(txt, encoding="utf-8")
        print("[KeepAlivePatch] Patched app/build.gradle with useLegacyPackaging=true.")


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
