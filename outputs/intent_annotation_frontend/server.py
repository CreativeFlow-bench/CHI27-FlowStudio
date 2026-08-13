#!/usr/bin/env python3
import json
import os
import tempfile
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SUBMISSIONS = ROOT / "submissions"
ACCOUNTS = {"coder_1", "coder_2", "coder_3", "coder_4", "coder_5"}


class Handler(SimpleHTTPRequestHandler):
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
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "submission"]:
            return self.get_submission(parts[2])
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "submission"]:
            return self.post_submission(parts[2])
        self.send_error(404, "Not found")

    def get_submission(self, account):
        if account not in ACCOUNTS:
            return self.send_json({"error": "invalid account"}, status=400)
        path = SUBMISSIONS / f"{account}.json"
        if not path.exists():
            return self.send_json({"exists": False, "account": account, "cases": []})
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return self.send_json({"exists": True, **payload})

    def post_submission(self, account):
        if account not in ACCOUNTS:
            return self.send_json({"error": "invalid account"}, status=400)
        length = int(self.headers.get("Content-Length", "0"))
        if length > 20_000_000:
            return self.send_json({"error": "payload too large"}, status=413)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return self.send_json({"error": "invalid json"}, status=400)

        cases = payload.get("cases")
        if not isinstance(cases, list):
            return self.send_json({"error": "cases must be a list"}, status=400)

        SUBMISSIONS.mkdir(exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        saved = {
            "account": account,
            "saved_at": now,
            "case_count": len(cases),
            "done_count": sum(1 for item in cases if item.get("annotation_done")),
            "cases": cases,
        }

        fd, tmp_name = tempfile.mkstemp(prefix=f".{account}.", suffix=".json", dir=SUBMISSIONS)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(saved, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_name, SUBMISSIONS / f"{account}.json")
        return self.send_json({"ok": True, "account": account, "saved_at": now, "case_count": len(cases), "done_count": saved["done_count"]})

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    os.chdir(ROOT)
    port = int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"FlowStudio annotator serving on 0.0.0.0:{port}", flush=True)
    server.serve_forever()
