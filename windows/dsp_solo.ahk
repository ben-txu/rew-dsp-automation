#Requires AutoHotkey v2.0
; ─────────────────────────────────────────────────────────────────────────────
; dsp_solo.ahk — solos a DSP PC-Tool channel, idempotent.
;
; Usage:   AutoHotkey.exe dsp_solo.ahk <channel 1-20>
;
; Channels 1–10  → Ctrl + 1..0          (Solo per Audiotec Fischer docs)
; Channels 11–20 → Ctrl + Shift + 1..0
;
; Two hard-won lessons are baked in here:
;
; 1. ControlSend is NOT used. It drops the Ctrl modifier with this app,
;    so the bare digit arrives — which is the MUTE hotkey in DSP
;    PC-Tool. WinActivate + Send is deterministic inside the VM.
;
; 2. Ctrl+N is a TOGGLE: pressing it on an already-soloed channel turns
;    solo OFF. Since AHK cannot read the solo state, the operation is
;    made state-independent by first soloing a helper channel, then the
;    target. Under exclusive-solo semantics every starting state ends
;    with exactly the target channel soloed. The helper plays alone for
;    ~150 ms — well inside the settle time before any measurement.
;
; Check the exact window title with AutoHotkey's "Window Spy"
; (right-click the AHK tray icon) and adjust WIN_TITLE if needed.
; Partial title match is enabled.
; ─────────────────────────────────────────────────────────────────────────────

WIN_TITLE := "DSP PC-Tool"          ; ← adjust after checking with Window Spy

SetTitleMatchMode 2

if (A_Args.Length < 1) {
    ExitApp 64                       ; usage error
}

ch := Integer(A_Args[1])
if (ch < 1 || ch > 20) {
    ExitApp 65                       ; channel out of range
}

if !WinExist(WIN_TITLE) {
    ExitApp 66                       ; window not found
}

SoloKeys(n) {
    if (n <= 10) {
        digit := (n = 10) ? "0" : String(n)
        return "^" digit             ; Ctrl+digit
    }
    digit := (n = 20) ? "0" : String(n - 10)
    return "^+" digit                ; Ctrl+Shift+digit
}

WinActivate WIN_TITLE
if !WinWaitActive(WIN_TITLE, , 2) {
    ExitApp 67                       ; could not activate
}
Sleep 100

; 1) Solo a helper channel (any channel other than the target)
helper := (ch = 1) ? 2 : 1
Send SoloKeys(helper)
Sleep 150

; 2) Solo the target — final state is now independent of the start state
Send SoloKeys(ch)

ExitApp 0
