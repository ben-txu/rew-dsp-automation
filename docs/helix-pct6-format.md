# Helix / Audiotec Fischer `.pct6` preset files — field notes

Findings about the sound-setup files that the Audiotec Fischer **DSP PC-Tool 6**
writes (`.pct6`), collected while building measurement automation for a
HELIX DSP ULTRA XT. They are relevant here because the PC-Tool's Solo and Mute
controls change exactly the fields described below.

How these notes were obtained: clean-room, from our own saved files only
(no vendor code, no third-party parser), by editing one field at a time,
loading the file in the PC-Tool, and comparing screenshots and the tool's
re-saved file. Status labels:

- **verified**: reproduced with tool-written files and confirmed in the PC-Tool UI
- **observed**: seen in files, meaning not proven
- **open**: not known

Scope: PC-Tool 6.02.03, 6.03.04 (Windows) and 6.05.01 (native macOS),
mostly HELIX DSP ULTRA XT (`Dev="53"`), demo mode and a real device. Other
models are covered only where stated. Not affiliated with Audiotec Fischer;
use at your own risk.

`tools/pct6_tool.py` implements the read side of everything below (stdlib only).

---

## 1. Container (verified)

```
payload = uint32_be(len(xml)) + zlib.compress(xml, 9)
.pct6   = payload XOR "ATFV6"      (5-byte key, repeating, from byte 0)
```

- There is **no magic number**, no further header and no checksum. The first
  two bytes look like a signature (`AT`, `AU`, `AV`, …) but they are just the
  masked high bytes of the length field: XML < 64 KiB starts with `AT`,
  64–128 KiB with `AU`, and so on. **Do not test for `AU`**; check the length
  field against the decompressed length instead.
- Older files (PC-Tool 5 `.afpx`, early `.pct6`) carry the **same payload
  without the XOR mask**. Detect the generation structurally (try zlib with
  and without the mask, check the length field), never by leading bytes.
- `encode(decode(f)) == f` is byte-identical with Python's `zlib.compress(x, 9)`
  for every tool-written file we have (38 of 38, both generations).
  A writer should still decode its own output and compare before writing,
  because this depends on the zlib implementation matching the tool's.
- The PC-Tool accepts files written this way (load, edit, re-save).
- Password-protected files: no sample, **open**.

## 2. XML layout

Root `<ATF …>` with, among others:

| Element | Meaning |
|---|---|
| `<OC>` | one output channel (virtual and physical) |
| `<IC>` | one input channel |
| `<Fil>` (child of OC/IC) | one EQ or crossover slot |
| `<Vol>` (child) | channel gain |
| `<T>` (child) | delay / phase |
| `<UN>` | table of user-defined channel names |
| `<R>`, `<Route>` | routing matrices |
| `<ATFCOND>`, `<DCM>`, `<ABP>`, `<MCV2>`, … | largely opaque |

Useful `<ATF>` attributes: `V` = PC-Tool version that saved the file,
`Dev` = device id (53 = ULTRA XT, 22 = ULTRA), `OUTS` / `INS` = number of
`<OC>` / `<IC>` elements, `FN` = path the file was saved to, `NT` = note
text, `D` = save timestamp.

### 2.1 Channel addressing — only via `ON` / `IN` (verified)

- Outputs are addressed by `<OC ON="n">`, inputs by `<IC IN="n">`.
- Never address by `CN` (channel name; several channels may share one),
  by `LG` (link-group id) or by the "V1, V2, …" labels in the UI (those are
  list positions on the current tab and differ between tabs).
- On the ULTRA XT, `ON 0–17` are **virtual** channels and `ON 18–33` are the
  16 **physical** outputs: Output *k* = `ON 17+k`. On the ULTRA (Dev 22) the
  physical outputs are `ON 14–25`. General structural rule: physical outputs
  are the `<OC>` elements that carry crossover pointers (`LPi`/`HPi`);
  virtual channels have none.
- Inputs on the ULTRA XT: `IN 0–11` = Main Input 1–12, `12/13` = Digital In
  L/R, `14/15` = AUX L/R, `16/17` = USB L/R.

### 2.2 `MT` — the mute flag is inverted (verified)

`<OC MT="1">` means **audible**, `MT="0"` means **muted**, the opposite of
what the attribute name and the "Mute" button suggest.

Verified in the native macOS PC-Tool 6.05.01 (ULTRA XT demo): with no text
field focused, pressing the number key `3` flipped only `ON=20` (Output 3)
`MT 1 → 0`; pressing `0` flipped `ON=27` (Output 10). So the bare number keys
`1…9, 0` toggle the mute of Outputs 1–10, and a digit typed into a field that
did not take focus silently mutes or unmutes an output.

The meaning of `MT` on `<IC>` was not tested.

### 2.3 Solo is destructive (verified)

The file has **no solo attribute**. The PC-Tool implements Solo by setting
`MT="0"` on all *other* outputs; the soloed channel keeps `MT="1"`. There is
no remembered state (unlike the EQ bypass, see 2.6). While the app is
running, leaving solo mode restores the previous mute flags. A preset
**saved or sent to the device while a channel is soloed** cannot be told
apart from one where those channels were muted on purpose.

Rule for any measurement automation: **never save or deploy while in solo**,
and end every run with solo switched off.

### 2.4 Channel names `CN` and `<UN>` (verified)

`CN` is an index into a fixed enum, **not** the position in the dropdown
(newer entries were appended to the enum but sorted into the dropdown).

Output enum (`<OC CN>`, 0–56):

```
 0 Not assigned       15 Rear L High       30 Line Out 2        45 Bridge Mode
 1 Front L Full       16 Rear R High       31 Line Out 3        46 Surround L Full
 2 Front R Full       17 Rear L Mid        32 Line Out 4        47 Surround R Full
 3 Front L High       18 Rear R Mid        33 Line Out 5        48 Front Subwoofer L
 4 Front R High       19 Rear L Low        34 Line Out 6        49 Front Subwoofer R
 5 Front L Mid        20 Rear R Low        35 Line Out 7        50 Pass Through 7
 6 Front R Mid        21 Rear Fill Full    36 Line Out 8        51 Pass Through 8
 7 Front L Low        22 Rear Fill High    37 Subwoofer L       52 Pass Through 9
 8 Front R Low        23 Rear Fill Low     38 Subwoofer R       53 Pass Through 10
 9 Front Center Full  24 Rear Sum          39 Pass Through 1    54 Pass Through 11
10 Front Center High  25 Subwoofer 1       40 Pass Through 2    55 Pass Through 12
11 Front Center Low   26 Subwoofer 2       41 Pass Through 3    56 User defined Name
12 F Sum              27 Subwoofer 3       42 Pass Through 4
13 Rear L Full        28 Subwoofer 4       43 Pass Through 5
14 Rear R Full        29 Line Out 1        44 Pass Through 6
```

Out-of-range codes show an **empty** name field (no error).

Inputs (`<IC CN>`, 0–77) use a **different** enum: 0–8 as above, index 9 is
an extra slot that shows "Not assigned", from 10 on it is the output enum
shifted by one with input wording ("Line In", "R Sum"), and from 38 on it is
input-only (Digital In, Opt. In/Sub, AUX, HEC, MEC, AUX2, ASD, Subwoofer L/R,
Surround L/R Full, Front Subwoofer L/R, USB L/R). Invalid input codes show
"Not assigned". Two inputs with the same valid `CN`: the lower `IN` keeps the
name, the higher one shows "Not assigned" (the value stays in the file).

User-defined names: `CN="56"` plus a child of the top-level `<UN>` table,
`<UN UNENA="name" UNENU="ON"/>`, where `UNENU` is the channel's `ON` (not a
table position). `CN=56` without a matching entry shows "User Defined Name".
With duplicate `UNENU` the last entry wins (the tool drops the others on
save). The tool **parses** `&gt;`/`&apos;` in names but writes them
**unescaped**; compare text fields semantically, not byte-wise.

### 2.5 Filter slots `<Fil>` (verified)

- Physical outputs: 32 `<Fil>` elements; slots 0–29 are EQ bands, slot 30 is
  the crossover low-pass and slot 31 the high-pass. Virtual channels: 30
  slots, **no crossover**. Inputs: 15 EQ slots, no crossover. `Finit` is the
  number of EQ bands (`Finit="0"` = no EQ, e.g. pass-through channels, which
  are still routed and active). Slot order in the file is positional and does
  not depend on the UI sort setting.
- Attributes: `T` type, `F` frequency (Hz), `G` gain (dB; for crossovers the
  slope as a negative dB/oct value), `Q`, `I` (1 = inverted filter),
  `FilBy` / `FilBBR` (see 2.6).
- `T` codes: 1 = Fine EQ (a full band using F, G and Q, **not** "unused"),
  3 = low shelf, 4 = high shelf, 17 = peaking, 19 = all-pass 1st order,
  20 = all-pass 2nd order. Crossovers come in pairs, LP = odd / HP = even:
  7/8 self-defined (uses `Q`), 9/10 Butterworth, 11/12 Bessel,
  13/14 Chebyshev, 15/16 Linkwitz-Riley. Slopes: Butterworth, Bessel and
  Chebyshev 6–42 dB/oct in steps of 6, Linkwitz-Riley 12/24/36 dB/oct,
  0 = off.
- A free EQ slot is `T="1"` with `G="0"`. Gaps between used slots are normal;
  the tool creates them itself.
- Changing the filter type in the UI **overwrites `Q`** with a type-specific
  default.

### 2.6 Bypass model (verified)

Three levels: `<OC EqBy="1">` = global EQ bypass of the channel (sets
`FilBy="1"` on EQ slots 0–29, leaves the crossover slots alone);
`FilBy` = effective bypass of one slot; `FilBBR` = the slot's remembered
individual bypass, so the tool can restore it when the global bypass is
lifted. An individual bypass is the pair `FilBy=1, FilBBR=1`;
`FilBy=0, FilBBR=1` never occurs in tool-written files.

### 2.7 Gain, delay, phase, polarity

- `<Vol L="…">` stores linear gain, `L = 10^(dB/20)` (verified). The tool
  recomputes it on save (last-digit float changes). Typed channel-gain entry
  in 6.05.01 does **not** reliably honour the 0.10 dB resolution setting
  (observed: −1.23 → −1.00, −2.7 → −2.00, −1.5 kept). The "Channel Gain
  Resolution" setting is app-local, not stored in the preset.
- `<T T="…">` stores delay in **samples**, not ms (verified on the ULTRA XT
  at 96 kHz: 1.00 ms → 96). The ms value shown in the UI is rounded.
  The sample rate depends on the device (48 or 96 kHz on HELIX/MATCH models,
  192 kHz on BRAX DSP 192 kHz); never convert without knowing the model.
- `<T P="…">` = phase rotation in degrees (observed grid of 5.625°; range
  **open**). `CINV="1"` = polarity inverted.
- `DG` = delay group id: the tool copies a delay value to all outputs of the
  same group. Equal `DG` does **not** guarantee equal stored values in
  existing files.
- `TM` (root) = time-alignment method; switching it in the UI silently
  rewrites the delay values.

### 2.8 Linked channels (verified)

Editing one channel while outputs are linked (`LG`) copies the **whole slot**
to the linked channels, including its `FilBy` bypass flag. A tool that writes
one channel of a linked group therefore produces a file the tool may
overwrite on the next touch. Unlinking clears only the affected channel's
`LG`; a group left with a single member is dissolved (`LG="0"`).

## 3. What the PC-Tool changes on a plain load + save

Byte identity *through* the PC-Tool does not exist. Always compare
semantically. Seen on load + save without user edits:

- `V`, `D`, `FN` and the `<ATFCOND>` version stamps are updated; 6.05.01
  rewrites `AV` (e.g. `06000000 → X2`) and sorts attributes alphabetically.
- Floats are re-printed (`4.3 → 4.2999999999999998`), `<Vol L>` recomputed.
- `<UN/>` may be expanded to `<UN><UN UNENA="" UNENU="0"/></UN>` or dropped.
- 6.05.01 adds per-channel blocks and drops some older ones when reading a
  6.03.04 file. After one 6.05.01 save, a second load + save changes only
  `D`, `FN` and the `ATFCOND` date (stable across an app restart).
- 6.05.01 (ULTRA XT demo) flipped `MT 0 → 1` on two unused virtual channels
  (`ON 16/17`, `CN 0`).

## 4. Device reference (static, from the PC-Tool 6.05 device descriptors)

Physical analog in/out and processing rate per model, as shown on the
6.05.01 start screen (demo, not a measured device clock):

| Model | Analog in/out | Rate |
|---|---|---|
| HELIX DSP ULTRA XT | 12/16 | 96 kHz |
| HELIX DSP ULTRA / ULTRA S | 8/12 | 96 kHz |
| HELIX DSP PRO MK3 | 8/10 | 96 kHz |
| HELIX DSP.3 / DSP.3S | 6/8 | 96 kHz |
| HELIX DSP MINI / MINI MK2 | 4/6 | 96 kHz |
| HELIX P SIX DSP ULTIMATE | 6/12 | 96 kHz |
| HELIX V EIGHTEEN DSP | 18/20 | 48 kHz |
| HELIX V TWELVE DSP / MK2 | 12/14 | 48 kHz |
| HELIX V EIGHT DSP ULTIMATE | 12/14 | 48 kHz |
| HELIX V EIGHT DSP MK2 | 8/10 | 48 kHz |
| HELIX M SIX / M FOUR DSP | 6/10 | 48 kHz |
| HELIX AMPLIFY 206 DSP | 6/8 | 48 kHz |
| BRAX DSP 192 kHz | 8/12 | 192 kHz |
| BRAX DSP 96 kHz | 8/12 | 96 kHz |
| MATCH UP 10DSP (all) | 8/11 | 48 kHz |
| MATCH UP 8DSP / 8BMW (all) | 6/9 | 48 kHz |
| MATCH UP 6DSP / MK2 | 6/7 | 48 kHz |
| MATCH UP 4DSP | 4/5 | 48 kHz |
| MATCH M 5.4DSP | 4/9 | 48 kHz |
| MATCH M 5DSP MK2 | 4/7 | 48 kHz |
| MATCH PP 86DSP MK2 | 6/9 | 48 kHz |
| HELIX ISM 400.2DSP | 2/1 | 48 kHz |

All models in the 6.05 descriptors offer 31 output EQ stages, of which the UI
exposes 30 bands (the 31st is unexplained). The root `OUTS`/`INS` counts
include virtual and digital channels, so they are larger than the analog
counts (ULTRA XT: `OUTS="34"`, `INS="18"`).

## 5. Practical consequences for measurement runs

- Solo/mute hotkeys only change `MT`; they are safe for measuring as long as
  nothing is saved or deployed in between (2.3).
- Before a run, the "all muted" baseline can be prepared as a preset and
  checked offline: every physical output must have `MT="0"`
  (`python3 tools/pct6_tool.py check-muted baseline.pct6`).
- `python3 tools/pct6_tool.py channels setup.pct6` prints Output *k* ↔ `ON` ↔
  name, which gives the channel numbers for `dv_measure.ini` `[channels]`.
- Keep the PC-Tool window free of focused text fields while the automation
  sends number keys (2.2).
