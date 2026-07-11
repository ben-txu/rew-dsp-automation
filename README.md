# rew-dsp-automeasure

Automated per-channel speaker measurements for multi-way (car) audio installs,
combining **REW (Room EQ Wizard)** and the **Audiotec Fischer DSP PC-Tool**.

One command measures every channel of your install: it solos each channel in
DSP PC-Tool, runs an RTA capture (or a sweep) in REW, auto-stops at a target
average count, names the measurement, and saves everything into a single
`.mdat` file. FFT length and average count are configurable **per driver
type** (e.g. tweeters at 64k FFT, mids at 128k, woofers/subs at 256k).

```
┌─────────────────────────── macOS ───────────────────────────┐
│                                                              │
│  dv_speaker_measure.py ── REST API ──▶ REW (native, Pro)     │
│          │                             ▲ measurement audio   │
│          │ HTTP                        │ via mic + interface │
│          ▼                                                   │
│  ┌───── Parallels VM (Windows) ─────┐                        │
│  │  solo_bridge.py ──▶ AutoHotkey ──▶ DSP PC-Tool (Solo)     │
│  └──────────────────────────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

The split is deliberate: REW does the timing-critical audio I/O natively on
macOS, while the PC-Tool only receives control keystrokes — a job a VM handles
fine.

## Features

- **One-button multi-channel runs** — RTA or sweep, all channels or a subset
  (`--only FL_Tweeter` / `--only 1,2,9`)
- **Group measurements** — define `[pairs]` (e.g. both tweeters) and
  `[branches]` (e.g. a full three-way side) in the config; groups are
  measured by unmuting their members from the all-muted baseline instead
  of soloing (channels 1–16 only, since mute hotkeys stop there).
  Select the scope at startup or via `--scope pairs|branches`
- **Per-type measurement settings** — assign each channel a type
  (tweeter/mid/woofer/…), each type gets its own FFT length and target
  average count
- **Deterministic RTA stop** — REW's own `stopAt` mechanism ends each capture
  at exactly the configured average count; the script polls `/rta/status`
- **Automatic naming** — measurements are renamed via their UUID right after
  capture (`{session}_{channel}` by default, template configurable)
- **Clean session files** — if REW's measurement list is not empty at
  startup, the script asks whether to keep the existing measurements
  (they end up in the session .mdat), delete them, or abort
  (`--existing keep|delete` skips the prompt)
- **Mic-cal enforcement** — if a calibration file is configured, the script
  verifies it is loaded for the current input before every run, sets it if
  necessary, and refuses to measure otherwise
- **Idempotent solo switching** — the AutoHotkey side is safe against the
  Solo hotkey's toggle behaviour and against ControlSend's modifier loss
  (both learned the hard way; see Troubleshooting)
- **External or internal test signal** — play pink noise from the head
  unit (`use_generator = false`), or let the script drive REW's signal
  generator: signal selectable globally (`generator_signal`) or per
  channel type (third field in `[types]`), with a best-effort attempt to
  match periodic-noise length to the channel's FFT. The generator path is
  adaptive (command names are read from the API) but *less field-tested*
  than the external-signal path — check `curl localhost:4735/generator/signals`
  for your build's exact signal names (compact identifiers like `pinkpn`, not display names)
- **Calibration modes** — `mic_cal_file` accepts a path (enforce), empty
  (don't touch), or `none` (enforce measuring without a cal file)
- **Safe end state** — the script asks you to confirm an *all-muted*
  baseline at startup (skip with `--assume-muted`); exiting solo mode
  restores the underlying mute flags, so the run ends silent
  (`GET /mute-all` on the bridge; skip with `--no-final-mute`)

## Requirements

| Where | What |
|---|---|
| macOS | Python 3, `pip3 install flask requests`, REW with the **Pro upgrade** (the API's POST endpoints are Pro-gated), API server enabled (port 4735) |
| Parallels VM (Windows) | DSP PC-Tool, AutoHotkey **v2**, Python 3 (stdlib only — no pip packages) |
| Hardware | Measurement mic + interface on the Mac side |

The tool is developed and used on macOS with the PC-Tool in a Parallels
VM, but nothing in it is Mac-specific in principle: on a native Windows
machine, run REW, the PC-Tool, the bridge and the script side by side and
set `solo_bridge = http://localhost:4737`. This is **untested** — run the
script from a terminal (the native dialogs are macOS-only) and expect to
verify the curl tests yourself. Reports welcome.

Developed and tested against **REW 5.40 Beta 129 (API 0.9.5)**, DSP PC-Tool
with the Solo hotkeys (Ctrl+1…0 / Ctrl+Shift+1…0), Parallels shared
networking. REW's endpoint names and JSON shapes can differ between builds —
the Swagger UI at `http://localhost:4735` is the authoritative reference for
yours, and REW's error responses list valid values.

## Setup

### 1. Windows VM

1. Install [AutoHotkey v2](https://www.autohotkey.com) and Python 3
   (python.org installer or the Python install manager; check "Add to PATH"
   or verify the `pythonw` alias works).
2. Copy the `windows/` folder somewhere permanent, e.g. `C:\dsp-bridge\`.
3. **Verify the window title:** right-click the AHK tray icon → *Window Spy*
   → click the DSP PC-Tool window → put the actual title into `WIN_TITLE`
   in `dsp_solo.ahk` (a partial match is enough).
4. Run `start_bridge.bat`. On first launch, allow the Windows Firewall
   prompt (private networks is sufficient).
5. **Autostart:** Win+R → `shell:startup` → place a *shortcut* to
   `start_bridge.bat` there (a shortcut, not the file — the .bat locates its
   sibling files via its own path).
6. **Pin the VM's IP.** Parallels' DHCP has no per-VM reservations; set a
   static IP inside Windows instead (admin terminal):

   ```
   netsh interface ipv4 set address name="Ethernet" static 10.211.55.200 255.255.255.0 10.211.55.1
   netsh interface ipv4 set dnsservers name="Ethernet" static 10.211.55.1
   ```

   (Gateway/DNS `10.211.55.1` is the Parallels shared-network router; the
   Mac itself is `.2`. Pick an address well above the DHCP lease range.)

Test from the Mac:

```
curl http://10.211.55.200:4737/health    → {"status": "ok"}
curl http://10.211.55.200:4737/solo/1    → channel 1 goes solo in PC-Tool
curl http://10.211.55.200:4737/solo/1    → run twice: channel 1 must STAY solo
curl http://10.211.55.200:4737/mute-all  → with an all-muted baseline: silent
```

### 2. macOS

1. `pip3 install flask requests`
2. `cp mac/dv_measure.example.ini mac/dv_measure.ini` and edit: bridge IP,
   your channel map, types, mic cal file path.
3. REW → Preferences → API → enable the API server.
4. In REW, select your measurement interface **explicitly** as input rather
   than "Default Device" — otherwise the calibration follows whatever macOS
   considers the default input that day.
5. Optional: `chmod +x mac/Measure.command` for a double-click launcher.

## Usage

```
cd mac
python3 dv_speaker_measure.py --mode rta                  # full run, prompts for session
python3 dv_speaker_measure.py --mode rta --session PreEQ  # no prompts
python3 dv_speaker_measure.py --mode rta --only 1         # single channel by number
python3 dv_speaker_measure.py --mode sweep --only FL_Tweeter,Sub
python3 dv_speaker_measure.py --mode rta --averages 32    # global override
```

At startup the script prints a per-channel plan (FFT length, averages, type)
before the first measurement — check it. The final `.mdat` lands in
`output_dir` as `<session>_<timestamp>.mdat`. A log is written to
`~/Library/Logs/dv_measure.log`.

### Choosing averages (why the defaults are what they are)

At REW's 93.75 % RTA overlap, consecutive FFT frames share 93.75 % of their
samples. The statistically independent information therefore depends only on
the **average count**, not the FFT length: ~`1 + (N−1)/16` independent
frames. Equal counts give equal per-bin quality; larger FFTs (finer
low-frequency resolution) just take proportionally longer. Hence the default
of **128 averages for every type** — roughly 12 s per tweeter (64k), 24 s per
mid (128k), 49 s per woofer (256k) at 48 kHz. Raise the woofer count for
reference runs; low frequencies carry the worst ambient noise.

If you play the test signal from the head unit, ordinary pink noise works.
REW's *periodic* pink noise (Pink PN, exported at your chain's sample rate
with the period matching the FFT length) converges much faster — but only if
the playback chain does **not** resample, which breaks periodicity.

## Safety

The script solos **tweeters** and plays full-range test signal through them.
Start with conservative levels and do not change the volume during a run
(relative channel levels are the point of the exercise). Measure with the
engine and HVAC off; check the noise floor with the signal muted first.

## Troubleshooting

Most of these were found the hard way during development:

- **Solo mutes instead of soloing** → AutoHotkey's `ControlSend` drops the
  Ctrl modifier with this app; the bare digit is PC-Tool's *mute* hotkey.
  The shipped `dsp_solo.ahk` uses `WinActivate` + `Send` for this reason —
  don't "optimize" it back.
- **Second solo on the same channel turns solo off** → Ctrl+N is a toggle.
  The shipped script solos a helper channel first, making the end state
  independent of the start state. Requires exclusive solo semantics (verify:
  solo 1, then solo 2 → only 2 may remain soloed).
- **`401 A Pro upgrade license is required`** → the Pro license must be
  activated in *this* REW install: REW → Pro Upgrades → paste license code →
  Verify license.
- **`404` on an endpoint / `400 … is not a recognised …`** → your REW build
  names things differently. The 400 responses include `validValues`; the
  Swagger UI at `localhost:4735` shows the full schema. Known-good against
  5.40 Beta 129: `PUT /rta/configuration` (`mode` like `RTA 1/48 octave`,
  `fftLength` like `64k`, `averaging`, `stopAt`, `stopAtValue`),
  `POST /rta/command` (`Start`/`Stop`/`Save current`),
  `POST /measurements/command` (`Save all`, path in `parameters[0]`),
  `PUT /measurements/{uuid}` (`title`), `PUT /audio/input-cal`
  (`calDataAllInputs.calFilePath`), `resultUrl` on `POST /measure/command`.
- **Bridge unreachable from the Mac but `curl localhost:4737/health` works
  in the VM** → Windows Firewall profile. Check the network is "Private",
  or add a port rule:
  `netsh advfirewall firewall add rule name="DSP Solo Bridge" dir=in action=allow protocol=TCP localport=4737 profile=private,domain`
- **Bridge not running at all** → start it once visibly
  (`python solo_bridge.py` in a CMD window) and read the actual error:
  AutoHotkey path, missing `dsp_solo.ahk`, or Python alias issues.
- **`Cal file field … not unambiguously identifiable`** → your REW build's
  `/audio/input-cal` schema differs; the log prints the raw object — open an
  issue with it.
- **Channels 11–20** use Ctrl+Shift — verify once with
  `curl …/solo/11` if your install uses them.
- **Brief channel 2/1 blip during mute-all** — expected, not a bug:
  the sequence moves the solo to a helper channel and then to channel 1
  before exiting solo (each audible for ~150 ms). This is what makes
  the end state independent of whatever was soloed before.

## Repository layout

```
mac/
  dv_speaker_measure.py     the orchestrator (runs on macOS)
  dv_measure.example.ini    copy to dv_measure.ini and edit
  Measure.command           double-click launcher
windows/
  solo_bridge.py            HTTP→AHK bridge (runs inside the VM, stdlib only)
  dsp_solo.ahk              sends the Solo hotkey to DSP PC-Tool
  dsp_mute_all.ahk          mutes all channels (end-of-run state)
  start_bridge.bat          starts the bridge; shortcut this into shell:startup
```

## License

MIT — see [LICENSE](LICENSE). Not affiliated with Audiotec Fischer or the
author of REW. Use at your own risk; see the Safety section.
