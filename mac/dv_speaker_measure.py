"""
dv_speaker_measure.py — automated per-channel speaker measurements
───────────────────────────────────────────────────────────────────
Measures every channel of a multi-way (car) audio install with one
command, by combining:

    • Audiotec Fischer DSP PC-Tool → solo switching via a small HTTP→
      AutoHotkey bridge running inside a Windows VM (Parallels)
    • REW (Room EQ Wizard, native)  → RTA captures & sweeps via its
      REST API (REW Pro upgrade required)

Per channel it: solos the channel, configures the RTA (FFT length and
target averages per channel *type*, e.g. tweeter/mid/woofer), lets REW
stop itself at the target average count, saves and renames the
measurement, then moves on. At the end everything is written to one
.mdat file. A configured mic calibration file is verified (and set if
needed) before any measurement starts.

All settings live in dv_measure.ini — searched in this order:
    1. --config <file>
    2. dv_measure.ini next to this script
    3. ~/.config/dv-measure/dv_measure.ini

Usage:
    python3 dv_speaker_measure.py --mode rta
    python3 dv_speaker_measure.py --mode rta --session PreEQ --averages 32
    python3 dv_speaker_measure.py --mode sweep --only FL_Tweeter
    python3 dv_speaker_measure.py --only 1,2,9

Developed and tested against REW 5.40 Beta 129 (API 0.9.5). Endpoint
names and JSON shapes can differ between REW builds — the Swagger UI
at http://localhost:4735 is the authoritative reference for yours.
"""

from __future__ import annotations

import argparse
import configparser
import logging
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from flask import Flask, request

log = logging.getLogger("dvmeas")

LOG_FILE = Path.home() / "Library" / "Logs" / "dv_measure.log"

# ─── Config ──────────────────────────────────────────────────────────────────

@dataclass
class Config:
    rew_base:         str
    solo_bridge:      str
    callback_port:    int
    name_template:    str
    output_dir:       Path
    sweep_timeout_s:  float
    rta_default_avg:  int
    rta_fft_length:   str
    rta_mode:         str
    rta_signal:       str
    rta_use_generator: bool
    rta_timeout_s:    float
    dsp_settle_s:     float
    channels:         dict[str, int] = field(default_factory=dict)
    channel_types:    dict[str, str] = field(default_factory=dict)
    types:            dict[str, dict] = field(default_factory=dict)
    mic_cal_file:     Optional[Path] = None
    source_file:      Optional[Path] = None

    @property
    def callback_url(self) -> str:
        return f"http://127.0.0.1:{self.callback_port}"


def config_search_paths(cli_path: Optional[str]) -> list[Path]:
    paths = []
    if cli_path:
        paths.append(Path(cli_path).expanduser())
    paths.append(Path(__file__).resolve().parent / "dv_measure.ini")
    paths.append(Path.home() / ".config" / "dv-measure" / "dv_measure.ini")
    return paths


def load_config(cli_path: Optional[str]) -> Config:
    candidates = config_search_paths(cli_path)
    ini_path = next((p for p in candidates if p.is_file()), None)
    if ini_path is None:
        locations = "\n  ".join(str(p) for p in candidates)
        sys.exit(f"No config file found. Searched:\n  {locations}\n"
                 f"→ place dv_measure.ini next to this script.")

    cp = configparser.ConfigParser(inline_comment_prefixes=("#",))
    cp.optionxform = str          # preserve key case (channel names)
    cp.read(ini_path, encoding="utf-8")

    def get(section, key, fallback=None):
        try:
            return cp.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if fallback is not None:
                return fallback
            sys.exit(f"Config error: [{section}] {key} missing in {ini_path}")

    # [types] — measurement types: "FFT, averages" (e.g. tweeter = 64k, 128)
    types: dict[str, dict] = {}
    if cp.has_section("types"):
        for tname, tval in cp.items("types"):
            parts = [x.strip() for x in tval.split(",")]
            if len(parts) != 2 or not parts[0]:
                sys.exit(f"Config error: [types] {tname} = '{tval}' — "
                         f"expected 'FFT, averages' (e.g. 64k, 128)")
            try:
                t_avg = int(parts[1])
            except ValueError:
                sys.exit(f"Config error: [types] {tname}: averages "
                         f"'{parts[1]}' is not a number ({ini_path})")
            types[tname.strip().lower()] = {"fft": parts[0],
                                            "averages": t_avg}

    # Channels: "number[, type]"
    channels: dict[str, int] = {}
    channel_types: dict[str, str] = {}
    if cp.has_section("channels"):
        for name, val in cp.items("channels"):
            parts = [x.strip() for x in val.split(",")]
            try:
                n = int(parts[0])
            except ValueError:
                sys.exit(f"Config error: [channels] {name} = '{val}' — "
                         f"first value must be the DSP channel number ({ini_path})")
            if not 1 <= n <= 20:
                sys.exit(f"Config error: [channels] {name} = {n} "
                         f"out of range 1–20 ({ini_path})")
            channels[name] = n
            if len(parts) > 1 and parts[1]:
                t = parts[1].lower()
                if t not in types:
                    sys.exit(f"Config error: [channels] {name}: type "
                             f"'{parts[1]}' is not defined in "
                             f"[types] ({ini_path})")
                channel_types[name] = t
    if not channels:
        sys.exit(f"Config error: section [channels] missing or empty "
                 f"({ini_path}) — at least one channel required.")

    dupes = {}
    for name, n in channels.items():
        dupes.setdefault(n, []).append(name)
    conflicts = {n: names for n, names in dupes.items() if len(names) > 1}
    if conflicts:
        sys.exit(f"Config error: DSP channels assigned more than once: {conflicts}")

    mic_cal_raw = get("calibration", "mic_cal_file", "")
    mic_cal = Path(mic_cal_raw).expanduser() if mic_cal_raw.strip() else None

    try:
        cfg = Config(
            rew_base        = get("connection", "rew_base",
                                  "http://localhost:4735").rstrip("/"),
            solo_bridge     = get("connection", "solo_bridge").rstrip("/"),
            callback_port   = int(get("connection", "callback_port", "4736")),
            name_template   = get("naming", "name_template",
                                  "{session}_{channel}"),
            output_dir      = Path(get("naming", "output_dir",
                                       "~/Desktop")).expanduser(),
            sweep_timeout_s = float(get("sweep", "timeout_s", "120")),
            rta_default_avg = int(get("rta", "default_averages", "64")),
            rta_fft_length  = get("rta", "fft_length", "64k"),
            rta_mode        = get("rta", "mode", "1/48 octave"),
            rta_signal      = get("rta", "generator_signal", "Pink PN"),
            rta_use_generator = (get("rta", "use_generator", "true")
                                 .strip().lower() in ("1", "true", "yes", "on")),
            rta_timeout_s   = float(get("rta", "timeout_s", "300")),
            dsp_settle_s    = float(get("timing", "dsp_settle_s", "0.4")),
            channels        = channels,
            channel_types   = channel_types,
            types           = types,
            mic_cal_file    = mic_cal,
            source_file     = ini_path,
        )
    except ValueError as e:
        sys.exit(f"Config error in {ini_path}: {e}")

    # Validate template before the first measurement runs
    try:
        cfg.name_template.format(session="s", channel="c", mode="m",
                                 date="d", time="t", datetime="dt")
    except (KeyError, IndexError) as e:
        sys.exit(f"Config error: name_template contains unknown "
                 f"placeholder: {e}")

    return cfg


# ─── User input (terminal OR native macOS dialogs) ───────────────────────────

def _osa(script: str) -> Optional[str]:
    if sys.platform != "darwin":      # osascript is macOS-only; on other
        return None                   # platforms run from a terminal
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def osa_text(prompt: str, default: str = "") -> Optional[str]:
    p = prompt.replace('\\', '\\\\').replace('"', '\\"')
    d = default.replace('\\', '\\\\').replace('"', '\\"')
    out = _osa(f'display dialog "{p}" default answer "{d}" '
               f'with title "DV Speaker Measurement"')
    if out is None:
        return None
    marker = "text returned:"
    idx = out.find(marker)
    return out[idx + len(marker):] if idx != -1 else None


def osa_choice(prompt: str, buttons: list[str], default: str) -> Optional[str]:
    p = prompt.replace('"', '\\"')
    btns = ", ".join(f'"{b}"' for b in buttons)
    out = _osa(f'display dialog "{p}" buttons {{{btns}}} '
               f'default button "{default}" with title "DV Speaker Measurement"')
    if out is None:
        return None
    marker = "button returned:"
    idx = out.find(marker)
    return out[idx + len(marker):] if idx != -1 else None


def ask_text(prompt: str, default: str = "") -> str:
    if sys.stdin.isatty():
        suffix = f" [{default}]" if default else ""
        ans = input(f"{prompt}{suffix}: ").strip()
        return ans or default
    val = osa_text(prompt, default)
    if val is None:
        log.error("Input cancelled.")
        sys.exit(1)
    return val.strip() or default


def ask_confirm_all_muted() -> bool:
    """User must confirm the all-muted baseline in DSP PC-Tool.
    Solo-off restores the underlying mute flags, so a muted baseline
    guarantees a silent end state after the run."""
    prompt = ("Confirm: ALL channels in DSP PC-Tool are currently MUTED "
              "(required for a safe end-of-run state)")
    if sys.stdin.isatty():
        ans = input(prompt + " [y/N]: ").strip().lower()
        return ans in ("y", "yes", "j", "ja")
    choice = osa_choice(prompt + "?", ["Cancel", "Yes"], "Yes")
    return choice == "Yes"


def ask_mode() -> str:
    if sys.stdin.isatty():
        ans = input("Measurement mode — [s]weep or [r]ta? [s]: ").strip().lower()
        return "rta" if ans.startswith("r") else "sweep"
    choice = osa_choice("Select measurement mode:", ["Cancel", "RTA", "Sweep"],
                        "Sweep")
    if choice in (None, "Cancel"):
        sys.exit(0)
    return choice.lower()


def handle_existing_measurements(rew: "Rew", choice) -> bool:
    """Checks REW's measurement list before the run. Anything already in
    the list would be included in the session .mdat by 'Save all'."""
    existing = rew.measurement_uuids()
    if not existing:
        log.info("REW measurement list is empty.")
        return True
    n = len(existing)
    if choice is None:
        if sys.stdin.isatty():
            ans = input(f"REW already contains {n} measurement(s); they "
                        f"would be included in the session .mdat.\n"
                        f"[k]eep / [d]elete (unsaved data is lost) / "
                        f"[a]bort? [k]: ").strip().lower()
            choice = {"d": "delete", "a": "abort"}.get(ans[:1], "keep")
        else:
            btn = osa_choice(f"REW already contains {n} measurement(s); "
                             f"they would be included in the session file.",
                             ["Abort", "Delete", "Keep"], "Keep")
            choice = {"Keep": "keep", "Delete": "delete"}.get(btn, "abort")
    if choice == "abort":
        log.error("Aborted — save or clear the REW measurement list first.")
        return False
    if choice == "delete":
        failed = 0
        for u in existing:
            try:
                rew.call("DELETE", f"/measurements/{u}")
            except Exception as e:
                failed += 1
                log.warning("Delete failed for %s: %s", u, e)
        if failed:
            log.error("%d measurement(s) could not be deleted — aborting "
                      "to avoid a mixed session file.", failed)
            return False
        log.info("Deleted %d pre-existing measurement(s).", n)
    else:
        log.info("Keeping %d pre-existing measurement(s) — they will be "
                 "part of the session .mdat.", n)
    return True


def notify(title: str, text: str) -> None:
    """macOS notification; no-op on other platforms."""
    if sys.platform != "darwin":
        return
    t = title.replace('"', '\\"')
    x = text.replace('"', '\\"')
    subprocess.run(["osascript", "-e",
                    f'display notification "{x}" with title "{t}"'],
                   check=False)


# ─── Naming ──────────────────────────────────────────────────────────────────

_INVALID = re.compile(r'[/\\:*?"<>|]')

def sanitize(s: str) -> str:
    return _INVALID.sub("_", s).strip()


def build_name(cfg: Config, *, session: str, channel: str, mode: str) -> str:
    now = datetime.now()
    return sanitize(cfg.name_template.format(
        session=session, channel=channel, mode=mode,
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H-%M"),
        datetime=now.strftime("%Y-%m-%d_%H-%M"),
    ))


def build_output_path(cfg: Config, session: str) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return str(cfg.output_dir / (sanitize(f"{session}_{stamp}") + ".mdat"))


# ─── DSP Solo via HTTP→AHK bridge ────────────────────────────────────────────

def bridge_health(cfg: Config) -> bool:
    try:
        return requests.get(f"{cfg.solo_bridge}/health", timeout=3).ok
    except requests.RequestException:
        return False


def mute_all_channels(cfg: Config) -> None:
    """Mute all DSP channels via the bridge (safe end state after a run)."""
    r = requests.get(f"{cfg.solo_bridge}/mute-all", timeout=10)
    if not r.ok:
        detail = ""
        try:
            detail = r.json().get("error", "")
        except ValueError:
            pass
        raise RuntimeError(f"mute-all failed: HTTP {r.status_code} {detail}")


def solo_dsp_channel(cfg: Config, n: int) -> None:
    r = requests.get(f"{cfg.solo_bridge}/solo/{n}", timeout=10)
    if not r.ok:
        detail = ""
        try:
            detail = r.json().get("error", "")
        except ValueError:
            pass
        raise RuntimeError(f"Solo ch{n} failed: HTTP {r.status_code} {detail}")


def _collect_strings(obj, found: list) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _collect_strings(v, found)
    elif isinstance(obj, str):
        found.append(obj)


def ensure_mic_cal(rew: "Rew", cfg: Config) -> bool:
    """Ensures the configured mic calibration file is loaded in REW.
    Returns False (aborting the run) if that cannot be achieved — better
    no measurement run than an uncalibrated one."""
    want = str(cfg.mic_cal_file)
    if not cfg.mic_cal_file.is_file():
        log.error("Mic calibration file not found: %s", want)
        return False

    def loaded() -> bool:
        try:
            data = rew.call("GET", "/audio/input-cal")
        except Exception as e:
            log.warning("/audio/input-cal not readable: %s", e)
            return False
        vals: list[str] = []
        _collect_strings(data, vals)
        norm = want.replace("\\", "/").lower()
        return any(v.replace("\\", "/").lower() == norm for v in vals)

    if loaded():
        log.info("Mic calibration active: %s", cfg.mic_cal_file.name)
        return True

    log.info("Mic calibration not loaded — trying to set it…")
    try:
        data = rew.call("GET", "/audio/input-cal")
    except Exception as e:
        log.error("Calibration not verifiable (%s) — aborting.", e)
        return False
    slots: list = []

    def _cal_slots(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if (isinstance(v, str) and "cal" in k.lower()
                        and "file" in k.lower()):
                    slots.append((obj, k))
                else:
                    _cal_slots(v)
        elif isinstance(obj, list):
            for v in obj:
                _cal_slots(v)

    _cal_slots(data)
    if len(slots) == 1:
        parent, key = slots[0]
        parent[key] = want
        try:
            rew.call("PUT", "/audio/input-cal", json=data)
        except Exception as e:
            log.error("Setting calibration failed: %s", e)
            return False
        if loaded():
            log.info("Mic calibration set: %s",
                     cfg.mic_cal_file.name)
            return True
        log.error("Calibration not active after PUT — please check in "
                  "REW (Preferences → Mic/Meter).")
        return False
    log.error("Cal file field in /audio/input-cal not unambiguously "
              "identifiable (candidates: %s). Raw object: %s — please "
              "report the field name or load the calibration manually "
              "in REW.", [k for _, k in slots], data)
    return False


# ─── Callback server (receives REW webhook POSTs) ────────────────────────────

class CallbackServer:
    def __init__(self, port: int):
        self.port = port
        self.app = Flask(__name__)
        self.app.logger.setLevel(logging.WARNING)

        self.sweep_done = threading.Event()

        @self.app.post("/measure-events")
        def measure_events():
            data = request.get_json(force=True, silent=True) or {}
            log.debug("measure event: %s", data)
            # REW POSTs the ProcessResult here when the sweep completes
            self.sweep_done.set()
            return ("", 200)

    def run(self):
        self.app.run(host="127.0.0.1", port=self.port,
                     debug=False, use_reloader=False, threaded=True)


# ─── REW API helpers ─────────────────────────────────────────────────────────

class Rew:
    def __init__(self, cfg: Config):
        self.base = cfg.rew_base
        self.cb   = cfg.callback_url

    def call(self, method: str, path: str, **kw) -> dict:
        r = requests.request(method, f"{self.base}{path}", timeout=10, **kw)
        if not r.ok:
            raise RuntimeError(
                f"{method} {path} → {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except ValueError:
            return {}

    def measurement_uuids(self) -> set:
        try:
            data = self.call("GET", "/measurements")
        except Exception as e:
            log.warning("Measurement list not readable: %s", e)
            return set()
        items = data.values() if isinstance(data, dict) else data
        uuids = set()
        for it in items or []:
            if isinstance(it, dict) and it.get("uuid"):
                uuids.add(it["uuid"])
        return uuids

    def rename_new_measurements(self, before: set, title: str) -> None:
        """Renames all measurements created since `before`."""
        new = set()
        t0 = time.time()
        while time.time() - t0 < 5:
            new = self.measurement_uuids() - before
            if new:
                break
            time.sleep(0.3)
        if not new:
            log.warning("No new measurement found — rename "
                        "skipped (%s)", title)
            return
        for u in new:
            try:
                self.call("PUT", f"/measurements/{u}",
                          json={"title": title})
            except Exception as e:
                log.warning("Rename failed (%s): %s", title, e)


# ─── Sweep ───────────────────────────────────────────────────────────────────

def do_sweep(rew: Rew, cfg: Config, name: str, server: CallbackServer) -> None:
    before = rew.measurement_uuids()
    server.sweep_done.clear()
    rew.call("POST", "/measure/command",
             json={"command": "SPL",
                   "resultUrl": f"{rew.cb}/measure-events"})
    log.info("  Sweep running, waiting for completion…")
    if not server.sweep_done.wait(timeout=cfg.sweep_timeout_s):
        raise TimeoutError(
            f"Sweep '{name}' did not finish within {cfg.sweep_timeout_s}s")
    rew.rename_new_measurements(before, name)
    log.info("  Sweep saved: %s", name)


# ─── RTA ─────────────────────────────────────────────────────────────────────

def configure_rta(rew: Rew, cfg: Config, target_averages: int,
                  fft_length: Optional[str] = None) -> None:
    rew.call("PUT", "/rta/configuration", json={
        "mode":        cfg.rta_mode,
        "fftLength":   fft_length or cfg.rta_fft_length,
        "averaging":   "Forever",
        "stopAt":      True,
        "stopAtValue": target_averages,
    })


def rta_running(rew: Rew) -> Optional[bool]:
    """True/False from /rta/status, None if unreadable."""
    try:
        st = rew.call("GET", "/rta/status")
    except Exception as e:
        log.debug("rta/status not readable: %s", e)
        return None
    for key in ("running", "isRunning", "rtaRunning"):
        if key in st:
            return bool(st[key])
    log.debug("rta/status without running field: %s", st)
    return None


def do_rta(rew: Rew, cfg: Config, name: str, target_averages: int) -> None:
    before = rew.measurement_uuids()

    if cfg.rta_use_generator:
        rew.call("POST", "/generator/command",
                 json={"command": "Play", "signal": cfg.rta_signal})
    rew.call("POST", "/rta/command", json={"command": "Start"})

    t0 = time.time()
    while time.time() - t0 < 5:
        if rta_running(rew):
            break
        time.sleep(0.25)

    log.info("  RTA running, REW will stop itself after %d averages…",
             target_averages)
    t0 = time.time()
    stopped = False
    while time.time() - t0 < cfg.rta_timeout_s:
        time.sleep(0.5)
        if rta_running(rew) is False:
            stopped = True
            break
    if stopped:
        log.info("  RTA stopped (target averages reached)")
    else:
        log.warning("  RTA did not stop by itself within %.0fs – stopping "
                    "manually and saving anyway", cfg.rta_timeout_s)
        rew.call("POST", "/rta/command", json={"command": "Stop"})

    rew.call("POST", "/rta/command", json={"command": "Save current"})
    if cfg.rta_use_generator:
        rew.call("POST", "/generator/command", json={"command": "Stop"})
    rew.rename_new_measurements(before, name)
    log.info("  RTA snapshot saved: %s", name)


# ─── Save & subscriptions ────────────────────────────────────────────────────

def save_all(rew: Rew, path: str) -> None:
    rew.call("POST", "/measurements/command",
             json={"command": "Save all", "parameters": [path]})
    log.info("All measurements saved → %s", path)



# ─── Main ────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", help="Path to dv_measure.ini")
    p.add_argument("--mode", choices=["sweep", "rta"])
    p.add_argument("--session")
    p.add_argument("--averages", type=int)
    p.add_argument("--only",
                   help="Measure only these channels: name or DSP number, "
                        "comma-separated (e.g. --only flt | --only 1,2,9)")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--no-final-mute", action="store_true",
                   help="Skip muting all DSP channels at the end")
    p.add_argument("--assume-muted", action="store_true",
                   help="Skip the all-channels-muted confirmation")
    p.add_argument("--existing", choices=["keep", "delete"],
                   help="How to handle pre-existing REW measurements "
                        "(skips the prompt)")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def resolve_targets(cfg: Config, only_arg: Optional[str]) -> Optional[dict[str, int]]:
    """
    Resolve --only into {name: channel}. Accepts channel names (case-
    insensitive) and/or DSP channel numbers, comma-separated.
    Examples: --only flt   --only 1   --only 1,2,9   --only flt,sub1
    Returns None on error (after logging).
    """
    if not only_arg:
        return dict(cfg.channels)

    by_number = {v: k for k, v in cfg.channels.items()}
    by_lower  = {k.lower(): k for k in cfg.channels}

    targets: dict[str, int] = {}
    for token in (t.strip() for t in only_arg.split(",")):
        if not token:
            continue
        if token.lower() in by_lower:
            name = by_lower[token.lower()]
        else:
            try:
                num = int(token)
            except ValueError:
                log.error("Unknown channel '%s'. Available: %s "
                          "(or channel numbers %s)",
                          token, list(cfg.channels),
                          sorted(by_number))
                return None
            if num not in by_number:
                log.error("Channel number %d is not assigned in the config. "
                          "Assigned: %s", num, sorted(by_number))
                return None
            name = by_number[num]
        targets[name] = cfg.channels[name]
    if not targets:
        log.error("--only matched no channels.")
        return None
    return targets


def main() -> int:
    args = parse_args()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)],
    )

    cfg = load_config(args.config)
    log.info("Config loaded: %s (%d channels)",
             cfg.source_file, len(cfg.channels))

    rew = Rew(cfg)

    # ── Preflight ────────────────────────────────────────────────────────────
    try:
        v = rew.call("GET", "/version")
        log.info("Connected to REW: %s", v.get("message", v))
    except Exception:
        msg = f"REW API not reachable at {cfg.rew_base} — is the API server enabled?"
        log.error(msg)
        notify("Speaker Measurement — error", msg)
        return 1

    if not bridge_health(cfg):
        msg = (f"Solo bridge not reachable at {cfg.solo_bridge} — "
               "is the VM running with start_bridge.bat?")
        log.error(msg)
        notify("Speaker Measurement — error", msg)
        return 1
    log.info("Solo-Bridge OK: %s", cfg.solo_bridge)

    if cfg.mic_cal_file is not None and not ensure_mic_cal(rew, cfg):
        notify("Speaker Measurement — error",
               "Mic calibration not loaded — run aborted.")
        return 1

    if not args.assume_muted:
        if not ask_confirm_all_muted():
            log.error("Aborted: mute all channels in DSP PC-Tool first, "
                      "then retry (or pass --assume-muted).")
            return 1
        log.info("All-muted baseline confirmed.")

    # ── Interactive inputs ───────────────────────────────────────────────────
    if not handle_existing_measurements(rew, args.existing):
        return 1

    mode = args.mode or ask_mode()
    session = args.session or ask_text(
        "Session label (e.g. PreEQ_Driver)",
        default=datetime.now().strftime("%Y%m%d_%H%M"),
    )
    log.info("Mode: %s | Session: %s", mode, session)

    # ── Channel selection ────────────────────────────────────────────────────
    targets = resolve_targets(cfg, args.only)
    if targets is None:
        return 1
    log.info("Channels to measure: %s",
             ", ".join(f"{n} (ch {c})" for n, c in targets.items()))

    # ── RTA plan: FFT & averages per channel (by type) ───────────────────────
    plan: dict[str, tuple[str, int]] = {}
    target_averages = 0
    if mode == "rta":
        untyped = [n for n in targets if n not in cfg.channel_types]
        if args.averages:
            target_averages = args.averages
        elif untyped:
            ans = ask_text(f"RTA averages (channels without type: "
                           f"{', '.join(untyped)})",
                           default=str(cfg.rta_default_avg))
            try:
                target_averages = int(ans)
            except ValueError:
                log.error("Invalid averages value: %s", ans)
                return 1
        else:
            target_averages = cfg.rta_default_avg
        for n in targets:
            t = cfg.channel_types.get(n)
            if t:
                ti = cfg.types[t]
                fft = ti["fft"]
                avg = args.averages or ti["averages"]
            else:
                fft = cfg.rta_fft_length
                avg = target_averages
            plan[n] = (fft, avg)
            log.info("  %-12s → FFT %-5s %4d Averages%s",
                     n, fft, avg, f"  [{t}]" if t else "")

    # ── Callback-Server + REW vorbereiten ────────────────────────────────────
    server = CallbackServer(cfg.callback_port)
    threading.Thread(target=server.run, daemon=True).start()
    time.sleep(0.4)

    # RTA is configured per channel inside the measurement loop (see plan)

    # ── Measurement loop ─────────────────────────────────────────────────────
    failures: list[str] = []
    for channel_name, ch in targets.items():
        name = build_name(cfg, session=session,
                          channel=channel_name, mode=mode)
        log.info("→ %s  (DSP ch %d, %s)", name, ch, mode)
        try:
            solo_dsp_channel(cfg, ch)
            time.sleep(cfg.dsp_settle_s)
            if mode == "sweep":
                do_sweep(rew, cfg, name, server)
            else:
                fft, avg = plan[channel_name]
                configure_rta(rew, cfg, avg, fft)
                do_rta(rew, cfg, name, avg)
        except Exception as e:
            log.error("  %s failed: %s — continuing", name, e)
            failures.append(channel_name)

    if not args.no_save:
        save_all(rew, build_output_path(cfg, session))

    if not args.no_final_mute:
        try:
            mute_all_channels(cfg)
            log.info("All DSP channels muted.")
        except Exception as e:
            log.warning("Final mute-all failed: %s — please "
                        "mute manually in DSP PC-Tool.", e)

    if failures:
        notify("Speaker Measurement — finished with errors",
               f"Failed: {', '.join(failures)}")
        log.warning("Finished, but with failures: %s", failures)
    else:
        notify("Speaker Measurement", f"All {len(targets)} channels measured ({mode}).")
        log.info("Done — all %d channels OK.", len(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
