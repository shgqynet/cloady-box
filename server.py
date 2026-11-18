#!/usr/bin/env python3
"""Cloady box 状态面板服务（仅标准库）

GET  /                面板页面（HTTP Basic 认证）
GET  /api/status      当前状态 JSON（Basic 认证），附带本容器自身指标
GET  /api/history     最近状态快照（Basic 认证）
POST /api/push        采集端推送状态（Bearer 推送令牌）
GET  /healthz         无认证探活
"""
import base64
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA_DIR = os.environ.get("DATA_DIR", "/data")
ENV_FILE = os.environ.get("PANEL_ENV_FILE", os.path.join(DATA_DIR, "panel.env"))


def _load_env_file(path):
    """从卷里的 panel.env 读取密钥，避免密码进 git / compose。"""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


_load_env_file(ENV_FILE)
STATUS_PATH = os.path.join(DATA_DIR, "status.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.jsonl")
PANEL_USER = os.environ.get("PANEL_USER", "willie")
PANEL_PASS = os.environ.get("PANEL_PASS", "")
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "")
PORT = int(os.environ.get("PANEL_PORT", "80"))
PAGE_PATH = os.environ.get("PAGE_PATH", "/usr/local/share/panel/dashboard.html")
HISTORY_MAX = 500


def cg(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def self_metrics():
    usage_usec = None
    for line in (cg("/sys/fs/cgroup/cpu.stat", "") or "").splitlines():
        if line.startswith("usage_usec"):
            usage_usec = int(line.split()[1])
    mem = cg("/sys/fs/cgroup/memory.current")
    try:
        with open("/proc/uptime") as f:
            host_up = float(f.read().split()[0])
    except OSError:
        host_up = None
    started = int(time.time() - host_up) if host_up else None
    return {
        "cpu_seconds": round(usage_usec / 1e6, 2) if usage_usec else None,
        "mem_mib": round(int(mem) / 2**20, 1) if mem else None,
        "host_uptime_s": host_up,
        "since": started,
    }


def read_status():
    try:
        with open(STATUS_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {"updated": None, "hosts": [], "services": [], "note": "尚无采集数据"}
    data["box"] = self_metrics()
    return data


class Handler(BaseHTTPRequestHandler):
    server_version = "cldybox-panel/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # 少写日志，省流量
        pass

    # ---------- helpers ----------
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Basic ") or not PANEL_PASS:
            return False
        try:
            user, _, pw = base64.b64decode(hdr[6:]).decode().partition(":")
        except Exception:
            return False
        return user == PANEL_USER and pw == PANEL_PASS

    def _need_auth(self):
        self._send(401, {"error": "auth required"}, extra={"WWW-Authenticate": 'Basic realm="servers"'})

    # ---------- routes ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            return self._send(200, {"ok": True, "ts": int(time.time())})
        if not self._authorized():
            return self._need_auth()
        if path in ("/", "/index.html"):
            try:
                with open(PAGE_PATH, "rb") as f:
                    page = f.read()
            except OSError:
                return self._send(500, {"error": "page missing"})
            return self._send(200, page, "text/html; charset=utf-8")
        if path == "/api/status":
            return self._send(200, read_status())
        if path.startswith("/files/"):
            rel = path[len("/files/"):].strip("/")
            base = os.path.realpath(os.path.join(DATA_DIR, "www"))
            target = os.path.realpath(os.path.join(base, rel or "index.html"))
            if not target.startswith(base + os.sep) and target != base:
                return self._send(403, {"error": "forbidden"})
            if os.path.isdir(target):
                target = os.path.join(target, "index.html")
            try:
                with open(target, "rb") as f:
                    blob = f.read()
            except OSError:
                return self._send(404, {"error": "not found"})
            ctype = "text/html; charset=utf-8"
            if target.endswith(".json"):
                ctype = "application/json; charset=utf-8"
            elif target.endswith((".txt", ".csv", ".md", ".log")):
                ctype = "text/plain; charset=utf-8"
            elif target.endswith(".png"):
                ctype = "image/png"
            elif target.endswith((".jpg", ".jpeg")):
                ctype = "image/jpeg"
            return self._send(200, blob, ctype)
        if path == "/api/history":
            rows = []
            try:
                with open(HISTORY_PATH) as f:
                    for line in f.readlines()[-60:]:
                        try:
                            rows.append(json.loads(line))
                        except ValueError:
                            pass
            except OSError:
                pass
            return self._send(200, {"history": rows})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] != "/api/push":
            return self._send(404, {"error": "not found"})
        hdr = self.headers.get("Authorization", "")
        if not PUSH_TOKEN or hdr != "Bearer " + PUSH_TOKEN:
            return self._send(401, {"error": "bad token"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._send(400, {"error": "bad length"})
        if length <= 0 or length > 512 * 1024:
            return self._send(400, {"error": "bad body"})
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except ValueError:
            return self._send(400, {"error": "bad json"})
        payload["received"] = int(time.time())
        payload.setdefault("updated", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        tmp = STATUS_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, STATUS_PATH)
        try:
            with open(HISTORY_PATH, "a") as f:
                f.write(json.dumps({"t": payload["received"], "hosts": [
                    {"id": h.get("id"), "status": h.get("status")} for h in payload.get("hosts", [])]}) + "\n")
            if os.path.getsize(HISTORY_PATH) > 256 * 1024:
                with open(HISTORY_PATH) as f:
                    keep = f.readlines()[-HISTORY_MAX:]
                with open(HISTORY_PATH, "w") as f:
                    f.writelines(keep)
        except OSError:
            pass
        return self._send(200, {"ok": True, "hosts": len(payload.get("hosts", []))})


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    print(f"panel listening on :{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
