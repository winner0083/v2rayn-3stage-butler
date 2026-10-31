#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2rayN 三段式管家 V2.0 — PC 真核桥接与双通道测源服务 (pc_bridge_server.py)

功能:
1. 静态托管 APP 前端 (index.html / manifest.json), 支持电脑与局域网手机访问
2. /api/probe_source?url=...&proxy=http://127.0.0.1:10808
   真实测试指定订阅源在【非代理直连 (ProxyHandler({}))】与【代理模式 (10808)】下是否可抓取,
   并返回两边耗时(ms)与解析出的有效节点数。
3. /api/sources/add
   将自定义新增的订阅源追加写入真源 订阅源.txt, 实现可扩展收集体系闭环。
4. /api/weekly_review
   读取与维护 废弃节点墓碑库 (deprecated_tombstone.json), 自动清理满 90 天 (3个月) 的废弃节点。

注意: 遵守全局铁律, 控制台输出严禁包含任何 emoji, 保证 pythonw / GBK 零崩溃。
"""
import base64
import json
import os
import time
import urllib.request
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).resolve().parent
AUTO_DIR = Path(r"D:\workbuddy\WorkSpaces\2026-09-06-20-04-30\outputs\v2rayn-auto")
TESTS_DIR = AUTO_DIR / "tests"
SOURCES_TXT = AUTO_DIR / "订阅源.txt"
TOMBSTONE_JSON = APP_DIR / "deprecated_tombstone.json"
SKILL_SCRIPTS_DIR = Path(r"C:\Users\Administrator\.workbuddy\skills\三段式测试V2.0\scripts")
HOST = "127.0.0.1"
PORT = int(os.environ.get("V2RAYN_APP_PORT", "18088"))
UA = "v2rayN/7.0 (auto-harvest-probe)"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [Bridge] {msg}", flush=True)


def count_nodes_in_payload(raw_text):
    text = (raw_text or "").strip()
    if not text:
        return 0
    if "://" not in text and "proxies:" not in text:
        try:
            pad = text + "=" * ((4 - len(text) % 4) % 4)
            text = base64.b64decode(pad).decode("utf-8", errors="ignore")
        except Exception:
            pass
    if "proxies:" in text:
        return sum(1 for ln in text.splitlines() if "server:" in ln and "port:" in ln)
    return sum(
        1 for ln in text.splitlines()
        if ln.strip().lower().startswith(("vless://", "trojan://", "ss://", "vmess://"))
    )


def fetch_via_opener(url, proxy_url=None, timeout=8):
    if proxy_url:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
    else:
        # 强制直连, 忽略系统注册表代理
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.time()
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            ms = int((time.time() - t0) * 1000)
            nodes = count_nodes_in_payload(body)
            return True, ms, nodes
    except Exception:
        return False, -1, 0


def read_real_sources():
    if not SOURCES_TXT.exists():
        return []
    res = []
    for idx, line in enumerate(SOURCES_TXT.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "|" in s:
            name, url = s.split("|", 1)
        else:
            name, url = f"external-{idx}", s
        res.append({"id": idx, "name": name.strip(), "url": url.strip(), "enabled": True})
    return res


def append_source_to_file(name, url):
    SOURCES_TXT.parent.mkdir(parents=True, exist_ok=True)
    existing = SOURCES_TXT.read_text(encoding="utf-8", errors="ignore") if SOURCES_TXT.exists() else ""
    if url in existing:
        return False
    with open(SOURCES_TXT, "a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(f"{name}|{url}\n")
    return True


def delete_sources_from_file(urls_to_remove):
    if not SOURCES_TXT.exists() or not urls_to_remove:
        return 0
    target_set = set(u.strip() for u in urls_to_remove if u and u.strip())
    lines = SOURCES_TXT.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept = []
    removed_cnt = 0
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            kept.append(ln)
            continue
        url_part = s.split("|", 1)[1].strip() if "|" in s else s
        if url_part in target_set:
            removed_cnt += 1
        else:
            kept.append(ln)
    if removed_cnt > 0:
        SOURCES_TXT.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return removed_cnt


class BridgeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/status":
            self._send_json({
                "ok": True,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "skill_truth_dir": str(SKILL_SCRIPTS_DIR),
                "sources_count": len(read_real_sources()),
            })
            return

        if parsed.path == "/api/probe_source":
            target_url = (qs.get("url") or [""])[0].strip()
            proxy_url = (qs.get("proxy") or ["http://127.0.0.1:10808"])[0].strip()
            if not target_url:
                self._send_json({"ok": False, "error": "missing url"}, 400)
                return
            d_ok, d_ms, d_cnt = fetch_via_opener(target_url, proxy_url=None, timeout=6)
            p_ok, p_ms, p_cnt = fetch_via_opener(target_url, proxy_url=proxy_url, timeout=8)
            self._send_json({
                "ok": True,
                "url": target_url,
                "directOk": d_ok,
                "directMs": d_ms,
                "directNodes": d_cnt,
                "proxyOk": p_ok,
                "proxyMs": p_ms,
                "proxyNodes": p_cnt,
            })
            return

        if parsed.path == "/api/sources":
            self._send_json({"ok": True, "sources": read_real_sources()})
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body_raw = self.rfile.read(length).decode("utf-8", errors="ignore") if length > 0 else "{}"
        try:
            payload = json.loads(body_raw)
        except Exception:
            payload = {}

        if parsed.path == "/api/sources/add":
            name = (payload.get("name") or "custom").strip()
            url = (payload.get("url") or "").strip()
            if not url:
                self._send_json({"ok": False, "error": "empty url"}, 400)
                return
            added = append_source_to_file(name, url)
            log(f"Source add requested: {name} | {url} (added={added})")
            self._send_json({"ok": True, "added": added})
            return

        if parsed.path == "/api/sources/delete":
            urls = payload.get("urls") or []
            if isinstance(urls, str):
                urls = [urls]
            removed = delete_sources_from_file(urls)
            log(f"Source delete requested: {len(urls)} target(s), removed={removed}")
            self._send_json({"ok": True, "removed": removed})
            return

        if parsed.path == "/api/bench_node":
            raw_uri = (payload.get("raw") or "").strip()
            listen_port = int(payload.get("port") or 32199)
            if not raw_uri:
                self._send_json({"ok": False, "error": "empty raw"}, 400)
                return
            try:
                if str(SKILL_SCRIPTS_DIR) not in sys.path:
                    sys.path.insert(0, str(SKILL_SCRIPTS_DIR))
                from real_bench_via_xray import parse_v2ray_link
                import real_bench_v2 as rb
                xray_bin = r"D:\火狐14.0.1\v2rayN-windows-64-SelfContained\bin\xray\xray.exe"
                node_dict = parse_v2ray_link(raw_uri)
                if not node_dict:
                    self._send_json({"latency_avg": -1, "speed_mbps": -1, "score": 0, "error": "parse_fail"})
                    return
                res = rb.run_one(node_dict, xray_bin, listen_port)
                self._send_json(res)
            except Exception as e:
                self._send_json({"latency_avg": -1, "speed_mbps": -1, "score": 0, "error": str(e)})
            return

        self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

    def _send_json(self, obj, code=200):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        pass


def main():
    log(f"Starting v2rayN 3-Stage Bridge Server on http://{HOST}:{PORT}")
    srv = ThreadingHTTPServer((HOST, PORT), BridgeHandler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("Server stopped.")


if __name__ == "__main__":
    main()
