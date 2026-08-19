#!/usr/bin/env python3
from __future__ import annotations

import http.client
import http.server
import socket
import socketserver
import threading

BACKEND = ("127.0.0.1", 18000)
FRONTEND = ("127.0.0.1", 5173)
PORT = 6006
API_PREFIXES = ("/api/", "/ws/", "/health", "/files/", "/docs", "/openapi.json")


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _target(self):
        path = self.path.split("?", 1)[0]
        if path == "/favicon.ico":
            return None
        if path == "/health" or any(path.startswith(p) for p in API_PREFIXES):
            return BACKEND
        return FRONTEND

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self._proxy_websocket()
            return
        self._proxy()

    def _proxy_websocket(self):
        host, port = BACKEND
        upstream = socket.create_connection((host, port), timeout=30)
        try:
            lines = [f"{self.command} {self.path} HTTP/1.1"]
            for key, value in self.headers.items():
                if key.lower() == "host":
                    continue
                lines.append(f"{key}: {value}")
            lines.append(f"Host: {host}:{port}")
            lines.append("")
            lines.append("")
            upstream.sendall("\r\n".join(lines).encode("latin1"))
            header = b""
            while b"\r\n\r\n" not in header:
                chunk = upstream.recv(4096)
                if not chunk:
                    break
                header += chunk
            self.connection.sendall(header)
            self.close_connection = True
            done = threading.Event()

            def pump(src: socket.socket, dst: socket.socket) -> None:
                try:
                    while not done.is_set():
                        data = src.recv(65536)
                        if not data:
                            break
                        dst.sendall(data)
                except OSError:
                    pass
                finally:
                    done.set()
                    try:
                        dst.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass

            threads = [
                threading.Thread(target=pump, args=(self.connection, upstream), daemon=True),
                threading.Thread(target=pump, args=(upstream, self.connection), daemon=True),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            try:
                upstream.close()
            except OSError:
                pass

    def _proxy(self):
        target = self._target()
        if target is None:
            self.send_error(404)
            return
        host, port = target
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else None
        conn = http.client.HTTPConnection(host, port, timeout=120)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "content-length"}}
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in {"transfer-encoding", "connection", "content-length"}:
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            path = self.path.split("?", 1)[0]
            if path in {"/", "/index.html", "/runtime-config.js"}:
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        finally:
            conn.close()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_PATCH(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()

    def do_HEAD(self):
        self._proxy()


class ReuseTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with ReuseTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"gateway on :{PORT}", flush=True)
        httpd.serve_forever()
