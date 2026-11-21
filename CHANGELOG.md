# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- **Native macOS PC-Tool support**: `mac/pctool_bridge_mac.py` (+ double-
  click launcher `mac/PC-Tool-Bridge.command`) serves the same endpoints as
  the Windows bridge on `localhost:4737` and sends the Solo/Mute hotkeys
  via System Events — no Parallels VM or AutoHotkey needed. It checks that
  the PC-Tool is frontmost before every key and restores the previous app
  afterwards. Bare-digit mute is verified on PC-Tool 6.05.01 for Mac; the
  Solo modifier (default ⌘, `--solo-modifier control` as fallback) and
  Shift-mute for 11–16 are not yet verified on macOS. `--dry-run` mode.
- `docs/helix-pct6-format.md`: notes on the PC-Tool `.pct6` preset format
  (container, channel addressing, inverted `MT` mute flag, destructive
  Solo, name enums, filter/crossover codes, bypass, gain/delay storage,
  load+save side effects) with a reference for all 33 PC-Tool 6.05 models
  (device id, rate, physical output block, virtual channels, FX targets,
  model families) and the ABP/RealCenter FX fields.
- `tools/pct6_tool.py`: stdlib reader/writer for `.pct6` files
  (`decode`, `encode` with self-check, `channels`, `check-muted`); knows
  all 33 models and finds the physical outputs structurally on each.

### Fixed (macOS bridge, found in the first end-to-end test)
- The bridge could not be restarted for a while after stopping it (port
  in TIME_WAIT); it now uses `SO_REUSEADDR`, which keeps the
  single-instance guard on macOS.
- Focus was not returned to the previously active app; the restore now
  waits 0.3 s and uses System Events.
- Launcher runs Python unbuffered so the request log shows up live.

### Verified
- All 20 keyboard shortcuts from the PC-Tool help page tested on macOS
  (README table): ⌘ instead of Ctrl; F11 swallowed by macOS; help text
  for ⇧F1–F6 wrong (selects 10+n); `O` (RTA always on top) has no effect;
  `D` has no effect in macOS full screen.
- Recheck: `D` also has no effect in the normal RTA window; `O` still has
  no effect (the setting *DSP PC-Tool Config → RTA window mode* is the
  alternative; not tested).
- Native macOS PC-Tool 6.05.01 (ULTRA XT demo): ⌘ solo incl. ⌘⇧ for
  11–20, idempotent re-solo, digit and Shift-digit mute, mute-all, keys
  into a full-screen PC-Tool in another Space, focus return.

## [0.0.2] — 2026-07-11

### Added
- **Group measurements**: define `[pairs]` (e.g. both tweeters) and
  `[branches]` (e.g. a full three-way side) in the config; groups are
  measured by unmuting their members from the confirmed all-muted
  baseline instead of soloing. Select at startup or via
  `--scope pairs|branches [--only <group>]`. Group settings resolve
  from an explicit type token, a uniform member type, or the `[rta]`
  defaults. Members are limited to DSP channels 1–16 (mute hotkeys
  stop there).
- **REW signal generator support**: the script can drive REW's
  generator during RTA captures (`use_generator = true`) — signal
  selectable globally or per channel type (third field in `[types]`),
  periodic-noise sequence length matched automatically to the
  channel's FFT length, Play/Stop commands discovered from the API.
- `CHANGELOG.md`.

### Changed
- Generator signal names use REW's compact API identifiers
  (e.g. `pinkpn` instead of "Pink PN"); the config default was updated.
- Config errors for group definitions point out the commented-out-
  channel case and recommend `--only` instead.
- The "RTA stopped" log line no longer claims a stop reason the API
  does not report.

### Fixed
- A failing session save can no longer skip the final mute-all: the
  `.mdat` export is skipped cleanly when there is nothing to save, and
  save errors are logged without aborting the safe end state.
- Generator signal selection uses POST (PUT returned 404).

## [0.0.1]

First public release: unattended per-channel RTA/sweep measurements
(solo via HTTP→AutoHotkey bridge), per-type FFT/averages, automatic
naming and single-file `.mdat` export, mic-cal enforcement, pre-run
measurement-list check, mic calibration modes (enforce a cal file,
leave untouched, or enforce none), all-muted baseline confirmation with
restored end state, single-instance bridge guard. Bench-tested against a Helix
DSP Ultra XT and REW 5.40 Beta 129 (API 0.9.5).
