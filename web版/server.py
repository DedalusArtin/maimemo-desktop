# -*- coding: utf-8 -*-
"""
墨墨开放 API Web端 - 本地服务器
- 端口 8790,自动打开浏览器
- /api/v1/* 代理到 https://open.maimemo.com/open/api/v1/* (带 Bearer token)
- token 与桌面版共享(../config.json)
"""
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(os.path.dirname(BASE), "config.json")  # 与桌面版共享
API_TARGET = "https://open.maimemo.com/open"
PORT = 8790


def load_token():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return (json.load(f).get("token") or "").strip()
    except Exception:
        return ""


def save_token(tok):
    cfg = {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        pass
    cfg["token"] = tok
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, data, ctype="application/json; charset=utf-8"):
        if isinstance(data, bytes):
            body = data
        else:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_index(self):
        with open(os.path.join(BASE, "index.html"), "rb") as f:
            self._send(200, f.read(), "text/html; charset=utf-8")

    def _proxy(self, p, method):
        tok = load_token()
        url = API_TARGET + p.path
        if p.query:
            url += "?" + p.query
        headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        if tok:
            headers["Authorization"] = "Bearer " + tok
        body = None
        if method in ("POST", "DELETE"):
            ln = int(self.headers.get("Content-Length") or 0)
            if ln:
                body = self.rfile.read(ln)
                headers["Content-Type"] = self.headers.get("Content-Type", "application/json")
        try:
            r = requests.request(method, url, headers=headers, data=body, timeout=20)
            try:
                data = r.json()
            except Exception:
                data = {"raw": r.text[:2000]}
            return self._send(r.status_code, data)
        except Exception as e:
            return self._send(502, {"error": str(e)})

    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/":
            return self._serve_index()
        if p.path == "/api/config":
            return self._send(200, {"token": load_token()})
        if p.path.startswith("/api/v1/"):
            return self._proxy(p, "GET")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path)
        if p.path == "/api/config":
            ln = int(self.headers.get("Content-Length") or 0)
            tok = (json.loads(self.rfile.read(ln) or b"{}").get("token") or "").strip()
            save_token(tok)
            return self._send(200, {"ok": True})
        if p.path.startswith("/api/v1/"):
            return self._proxy(p, "POST")
        self._send(404, {"error": "not found"})

    def do_DELETE(self):
        p = urlparse(self.path)
        if p.path.startswith("/api/v1/"):
            return self._proxy(p, "DELETE")
        self._send(404, {"error": "not found"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("墨墨开放API Web端: http://127.0.0.1:%d  (Ctrl+C 退出)" % PORT)
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:%d" % PORT)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
