#Requires AutoHotkey v2.0
; ─────────────────────────────────────────────────────────────────────────────
; dsp_mute_toggle.ahk — toggles a single channel's MUTE flag.
;
; Usage:   AutoHotkey.exe dsp_mute_toggle.ahk <channel 1-16>
;
; Bare digits 1–0 toggle mute for channels 1–10, Shift+1–6 for 11–16
; (per the official shortcut sheet; no mute hotkeys exist above 16).
; Toggles are only deterministic from a known state — the measurement
; script enforces the all-muted baseline before group runs.
; ─────────────────────────────────────────────────────────────────────────────

WIN_TITLE := "DSP PC-Tool"          ; must match dsp_solo.ahk

SetTitleMatchMode 2

if (A_Args.Length < 1) {
    ExitApp 64
}
ch := Integer(A_Args[1])
if (ch < 1 || ch > 16) {
    ExitApp 65
}
if !WinExist(WIN_TITLE) {
    ExitApp 66
}
WinActivate WIN_TITLE
if !WinWaitActive(WIN_TITLE, , 2) {
    ExitApp 67
}
Sleep 100
if (ch <= 10) {
    digit := (ch = 10) ? "0" : String(ch)
    Send digit
} else {
    Send "+" String(ch - 10)
}
ExitApp 0
