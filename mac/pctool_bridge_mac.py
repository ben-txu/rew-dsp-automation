#!/usr/bin/env python3
"""
pctool_bridge_mac.py — HTTP → keystroke bridge for the NATIVE macOS PC-Tool
───────────────────────────────────────────────────────────────────────────
Drop-in replacement for windows/solo_bridge.py when the Audiotec Fischer
DSP PC-Tool runs natively on macOS (PC-Tool 6.05 for Mac) instead of in a
Windows VM. Same endpoints, so dv_speaker_measure.py needs no change —
only `solo_bridge = http://localhost:4737` in dv_measure.ini.

Endpoints:
    GET /health          → {"status": "ok", "pctool_running": true|false}
    GET /solo/<n>        → solos DSP channel n (1–20), idempotent
    GET /toggle-mute/<n> → toggles mute of channel n (1–16)
    GET /mute-all        → leaves solo mode → all-muted baseline restored

Keystrokes are sent with AppleScript / System Events (stdlib + osascript,
no pip packages). Every keystroke script first brings the PC-Tool to the
front and aborts if it is not frontmost, so digits never land in another
app. Afterwards the previously active app is brought back.

STATUS — read before the first run:
  * Bare digits 1…9, 0 toggling the mute of Outputs 1–10 are VERIFIED in
    the native macOS PC-Tool 6.05.01 (no text field focused).
  * The Solo modifier on macOS is NOT verified. The PC-Tool is a Qt app,
    and Qt maps the Windows "Ctrl" shortcut to the Command key on macOS,
    so the default is Command (⌘1…⌘0, ⌘⇧1…⌘⇧0). If ⌘1 does not solo
    Output 1, start with --solo-modifier control.
  * Shift+1…6 for mute of channels 11–16 is taken from the Windows
    shortcut sheet and NOT verified on macOS.
  Verify with the curl tests in README.md (macOS-native section) before
  trusting a measurement run.

Permissions (one-time, macOS asks on first use):
  System Settings → Privacy & Security → Accessibility: allow the app that
  runs this script (Terminal, iTerm, …). Automation → "System Events":
  allow as well.

Usage:
    python3 pctool_bridge_mac.py                      # 127.0.0.1:4737, ⌘
    python3 pctool_bridge_mac.py --solo-modifier control
    python3 pctool_bridge_mac.py --dry-run            # log keys, send none
"""

import argparse
import json
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

DEFAULT_BUNDLE_ID = "com.audiotec-fischer.ATF-DSP-PC-TOOL-6"
DEFAULT_PORT = 4737

# macOS virtual key codes of the top-row digits (layout-independent position)
DIGIT_KEYCODE = {"1": 18, "2": 19, "3": 20, "4": 21, "5": 23,
                 "6": 22, "7": 26, "8": 28, "9": 25, "0": 29}

# Pauses mirror the AHK scripts (ms)
SETTLE_AFTER_ACTIVATE = 0.10
GAP_BETWEEN_KEYS = 0.15

EXIT_NOT_RUNNING = 66
EXIT_NOT_FRONT = 67

ERRORS = {
    EXIT_NOT_RUNNING: "DSP PC-Tool is not running (bundle id not found)",
    EXIT_NOT_FRONT: "could not bring DSP PC-Tool to the front - keys NOT sent",
}

CFG = argparse.Namespace()   # filled in main()


def _digit(n: int) -> str:
    return "0" if n % 10 == 0 else str(n % 10)


def solo_keys(n: int) -> tuple[str, list[str]]:
    """(digit, modifiers) for the Solo hotkey of channel n (1–20)."""
    mods = [CFG.solo_modifier]
    if n > 10:
        mods.append("shift")
    return _digit(n), mods


def mute_keys(n: int) -> tuple[str, list[str]]:
    """(digit, modifiers) for the Mute toggle of channel n (1–16)."""
    return _digit(n), (["shift"] if n > 10 else [])


def _applescript(keys: list[tuple[str, list[str]]]) -> str:
    bid = CFG.bundle_id
    lines = [
        'tell application "System Events"',
        f'  if not (exists (first process whose bundle identifier is "{bid}")) then',
        f'    error "not running" number {EXIT_NOT_RUNNING}',
        '  end if',
        '  set prevApp to bundle identifier of (first process whose frontmost is true)',
        'end tell',
        f'tell application id "{bid}" to activate',
        f'delay {SETTLE_AFTER_ACTIVATE}',
        'tell application "System Events"',
    ]
    for i, (digit, mods) in enumerate(keys):
        if i:
            lines.append(f'  delay {GAP_BETWEEN_KEYS}')
        # re-check before EVERY key: never type digits into another app
        lines += [
            '  if (bundle identifier of (first process whose frontmost is true)) '
            f'is not "{bid}" then',
            f'    error "not frontmost" number {EXIT_NOT_FRONT}',
            '  end if',
        ]
        using = ""
        if mods:
            using = " using {" + ", ".join(f"{m} down" for m in mods) + "}"
        lines.append(f'  key code {DIGIT_KEYCODE[digit]}{using}')
    lines += [
        'end tell',
        'if prevApp is not missing value and prevApp is not '
        f'"{bid}" then',
        '  try',
        '    tell application id prevApp to activate',
        '  end try',
        'end if',
    ]
    return "\n".join(lines)


def send(keys: list[tuple[str, list[str]]]) -> tuple[bool, str]:
    desc = " ".join("+".join(m + [d]) for d, m in keys)
    if CFG.dry_run:
        print(f"[bridge] dry-run: {desc}")
        return True, desc
    r = subprocess.run(["osascript", "-e", _applescript(keys)],
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        return True, desc
    err = r.stderr.strip()
    for code, msg in ERRORS.items():
        if f"({code})" in err:
            return False, msg
    if "not allowed" in err or "1002" in err or "-1743" in err:
        return False, ("macOS blocked the keystrokes - allow this terminal "
                       "under Privacy & Security → Accessibility/Automation")
    return False, f"osascript failed: {err}"


def pctool_running() -> bool:
    if CFG.dry_run:
        return True
    r = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to return exists '
         f'(first process whose bundle identifier is "{CFG.bundle_id}")'],
        capture_output=True, text=True, timeout=5)
    return r.stdout.strip() == "true"


def do_solo(ch: int) -> tuple[bool, str]:
    # Ctrl/⌘+N is a TOGGLE and the bridge cannot read the solo state:
    # solo a helper channel first, then the target → end state is
    # "exactly ch soloed" whatever the start state (exclusive solo).
    helper = 2 if ch == 1 else 1
    return send([solo_keys(helper), solo_keys(ch)])


def do_mute_all() -> tuple[bool, str]:
    # helper solo (deterministic pre-state), solo 1, solo 1 again = solo off.
    # Leaving solo restores the per-channel mute flags → all-muted baseline.
    return send([solo_keys(2), solo_keys(1), solo_keys(1)])


def do_toggle_mute(ch: int) -> tuple[bool, str]:
    return send([mute_keys(ch)])


class Handler(BaseHTTPRequestHandler):

    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _channel(self, raw: str, hi: int):
        try:
            ch = int(raw)
        except ValueError:
            self._reply(400, {"error": f"invalid channel '{raw}'"})
            return None
        if not 1 <= ch <= hi:
            self._reply(400, {"error": f"channel must be 1-{hi}"})
            return None
        return ch

    def _result(self, ok: bool, info: str, **extra) -> None:
        if ok:
            self._reply(200, {"status": "ok", "keys": info, **extra})
        else:
            self._reply(500, {"error": info, **extra})

    def do_GET(self):  # noqa: N802
        parts = [p for p in self.path.split("/") if p]
        if parts == ["health"]:
            self._reply(200, {"status": "ok",
                              "pctool_running": pctool_running(),
                              "solo_modifier": CFG.solo_modifier})
            return
        if parts == ["mute-all"]:
            ok, info = do_mute_all()
            self._result(ok, info, action="mute-all")
            return
        if len(parts) == 2 and parts[0] == "toggle-mute":
            ch = self._channel(parts[1], 16)
            if ch is not None:
                ok, info = do_toggle_mute(ch)
                self._result(ok, info, action="toggle-mute", channel=ch)
            return
        if len(parts) == 2 and parts[0] == "solo":
            ch = self._channel(parts[1], 20)
            if ch is not None:
                ok, info = do_solo(ch)
                self._result(ok, info, channel=ch)
            return
        self._reply(404, {"error": "unknown endpoint",
                          "usage": "/health, /solo/<1-20>, "
                                   "/toggle-mute/<1-16> or /mute-all"})

    def log_message(self, fmt, *args):
        print(f"[bridge] {time.strftime('%H:%M:%S')} {fmt % args}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="HTTP bridge for the native macOS DSP PC-Tool "
                    "(same API as windows/solo_bridge.py)")
    p.add_argument("--bind", default="127.0.0.1",
                   help="listen address (default 127.0.0.1 = this Mac only)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--solo-modifier", choices=["command", "control"],
                   default="command",
                   help="modifier of the Solo hotkey (default command; "
                        "unverified, see docstring)")
    p.add_argument("--bundle-id", default=DEFAULT_BUNDLE_ID,
                   help="bundle identifier of the PC-Tool app")
    p.add_argument("--dry-run", action="store_true",
                   help="log the key sequences instead of sending them")
    args = p.parse_args()
    CFG.__dict__.update(vars(args))

    if sys.platform != "darwin" and not args.dry_run:
        sys.exit("This bridge is for macOS. On Windows use windows/solo_bridge.py.")

    class SingleInstanceServer(HTTPServer):
        allow_reuse_address = False   # second instance fails fast

    try:
        server = SingleInstanceServer((args.bind, args.port), Handler)
    except OSError:
        sys.exit(f"Port {args.port} already in use - is the bridge already "
                 "running?")
    print(f"[bridge] PC-Tool bundle: {args.bundle_id}")
    print(f"[bridge] Solo modifier:  {args.solo_modifier}"
          f"{'  (DRY RUN)' if args.dry_run else ''}")
    if not args.dry_run and not pctool_running():
        print("[bridge] WARNING: PC-Tool is not running yet")
    print(f"[bridge] Listening on {args.bind}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[bridge] stopped")


if __name__ == "__main__":
    main()
