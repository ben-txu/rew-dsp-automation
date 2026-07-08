#!/usr/bin/env python3
"""
solo_bridge.py — HTTP → AutoHotkey bridge (runs INSIDE the Windows VM)
──────────────────────────────────────────────────────────────────────
Endpoints:
    GET /health        → {"status": "ok"}
    GET /solo/<n>      → solos DSP channel n (1–20)
    GET /mute-all      → mutes all DSP channels

Requires: Python 3 (stdlib only), AutoHotkey v2,
dsp_solo.ahk and dsp_mute_all.ahk next to this file.
Start via start_bridge.bat (shortcut it into shell:startup).
"""

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = 4737

AHK_EXE_CANDIDATES = [
    r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe",
    r"C:\Program Files\AutoHotkey\v2\AutoHotkey32.exe",
    r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
]

SOLO_SCRIPT = Path(__file__).with_name("dsp_solo.ahk")
MUTE_SCRIPT = Path(__file__).with_name("dsp_mute_all.ahk")

AHK_ERRORS = {
    64: "usage error (no channel argument)",
    65: "channel out of range (1-20)",
    66: "DSP PC-Tool window not found - is it running? Title correct?",
    67: "could not activate DSP PC-Tool window",
}


def find_ahk() -> str:
    for c in AHK_EXE_CANDIDATES:
        if Path(c).exists():
            return c
    sys.exit("AutoHotkey v2 not found - install it or edit AHK_EXE_CANDIDATES.")


AHK_EXE = find_ahk()


def run_ahk(script: Path, *args: str):
    return subprocess.run([AHK_EXE, str(script), *args],
                          capture_output=True, timeout=10)


class Handler(BaseHTTPRequestHandler):

    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parts = [p for p in self.path.split("/") if p]

        if parts == ["health"]:
            self._reply(200, {"status": "ok"})
            return

        if parts == ["mute-all"]:
            r = run_ahk(MUTE_SCRIPT)
            if r.returncode == 0:
                self._reply(200, {"status": "ok", "action": "mute-all"})
            else:
                msg = AHK_ERRORS.get(r.returncode,
                                     f"AHK exit code {r.returncode}")
                self._reply(500, {"error": msg, "action": "mute-all"})
            return

        if len(parts) == 2 and parts[0] == "solo":
            try:
                ch = int(parts[1])
            except ValueError:
                self._reply(400, {"error": f"invalid channel '{parts[1]}'"})
                return
            if not 1 <= ch <= 20:
                self._reply(400, {"error": "channel must be 1-20"})
                return
            r = run_ahk(SOLO_SCRIPT, str(ch))
            if r.returncode == 0:
                self._reply(200, {"status": "ok", "channel": ch})
            else:
                msg = AHK_ERRORS.get(r.returncode,
                                     f"AHK exit code {r.returncode}")
                self._reply(500, {"error": msg, "channel": ch})
            return

        self._reply(404, {"error": "unknown endpoint",
                          "usage": "/health, /solo/<1-20> or /mute-all"})

    def log_message(self, fmt, *args):
        print(f"[bridge] {self.address_string()} {fmt % args}")


def main() -> None:
    for script in (SOLO_SCRIPT, MUTE_SCRIPT):
        if not script.exists():
            sys.exit(f"Missing {script} - keep it next to this file.")
    print(f"[bridge] AHK:    {AHK_EXE}")
    print(f"[bridge] Listening on 0.0.0.0:{PORT}  (Ctrl+C to stop)")
    class SingleInstanceServer(HTTPServer):
        allow_reuse_address = False   # second instance fails fast instead of stacking

    try:
        server = SingleInstanceServer(("0.0.0.0", PORT), Handler)
    except OSError:
        sys.exit(f"Port {PORT} already in use - the bridge is already "
                 f"running. Kill it first: taskkill /IM pythonw.exe /F")
    server.serve_forever()


if __name__ == "__main__":
    main()
