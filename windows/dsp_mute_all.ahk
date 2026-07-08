#Requires AutoHotkey v2.0
; ─────────────────────────────────────────────────────────────────────────────
; dsp_mute_all.ahk — restores the all-muted state after a measurement run.
;
; Verified PC-Tool semantics: exiting solo mode RESTORES the underlying
; per-channel mute flags. The measurement script only ever touches solo
; (never the flags), and requires the user to confirm an all-muted
; baseline at startup — so exiting solo is sufficient to end silent.
;
; Sequence: idempotent solo of channel 1 (helper first, so the state is
; deterministic even if ch1 was already soloed), then solo-off.
; ─────────────────────────────────────────────────────────────────────────────

WIN_TITLE := "DSP PC-Tool"          ; must match dsp_solo.ahk

SetTitleMatchMode 2

if !WinExist(WIN_TITLE) {
    ExitApp 66
}
WinActivate WIN_TITLE
if !WinWaitActive(WIN_TITLE, , 2) {
    ExitApp 67
}
Sleep 100
Send "^2"        ; helper solo — deterministic pre-state
Sleep 150
Send "^1"        ; solo channel 1
Sleep 150
Send "^1"        ; solo off → underlying flags restored → all muted
ExitApp 0
