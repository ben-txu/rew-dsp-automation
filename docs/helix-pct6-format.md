# Helix / Audiotec Fischer `.pct6` preset files — field notes

Findings about the sound-setup files that the Audiotec Fischer **DSP PC-Tool 6**
writes (`.pct6`), for **all 33 device models** on the PC-Tool 6.05 start
list (HELIX, BRAX and MATCH). They are relevant here because the PC-Tool's
Solo and Mute controls change exactly the fields described below.

How these notes were obtained: clean-room, from our own saved files only
(no vendor code, no third-party parser), by editing one field at a time,
loading the file in the PC-Tool, and comparing screenshots and the tool's
re-saved file. Status labels:

- **verified**: reproduced with tool-written files and confirmed in the PC-Tool UI
- **observed**: seen in files, meaning not proven
- **open**: not known

Scope: PC-Tool 6.02.03, 6.03.04 (Windows) and 6.05.01 (native macOS).
The container, the root attributes, the channel layout (2.1), the FX fields
(section 4) and the sample-rate rule hold for every model; they were checked
on default demo files of all 33 models (PC-Tool 6.05.01 demo mode). The
detailed per-field semantics in 2.2–2.8 were worked out on the HELIX DSP
ULTRA XT (`Dev="53"`, demo and a real device) and the ULTRA (`Dev="22"`);
the file format is shared across all product lines, but where a statement
was only tested on those models it says so. Not affiliated with Audiotec
Fischer; use at your own risk.

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
- **Physical outputs are the `<OC>` elements that carry crossover pointers
  (`LPi`/`HPi`)**; virtual channels (and the digital-output pair, where a
  model has one) have none. This structural rule gives exactly the analog
  output count of every one of the 33 models (checked on their demo
  files). The physical outputs are always one contiguous `ON` block, and
  Output *k* is the *k*-th physical `<OC>` in `ON` order. Where they sit
  differs per model:
  - models with a virtual-channel layer: the physical block comes **last**
    (ULTRA XT `ON 18–33`, ULTRA / ULTRA S / BRAX 96 `ON 14–25`, V EIGHTEEN
    `ON 22–41`, MATCH UP 8 `ON 11–19`, …; full table in section 5);
  - models without one (DSP.3, DSP.3S, MINI, MINI MK2, BRAX 192): the
    physical block comes **first** (`ON 0…n−1`), followed by two
    non-physical `<OC>`;
  - MATCH M 5DSP MK2 and ISM 400.2: physical outputs only.
  `pct6_tool.py channels` applies this rule; never hard-code an offset.
- `OUTS` = virtual channels + analog outputs + 2 if the model has a digital
  output pair; `INS` = analog inputs + 2 per digital/card input pair
  (descriptor counting rule; matches the file on every model checked).
- Inputs on the ULTRA XT: `IN 0–11` = Main Input 1–12, `12/13` = Digital In
  L/R, `14/15` = AUX L/R, `16/17` = USB L/R.

### 2.2 `MT` — the mute flag is inverted (verified)

`<OC MT="1">` means **audible**, `MT="0"` means **muted**, the opposite of
what the attribute name and the "Mute" button suggest.

Verified in the native macOS PC-Tool 6.05.01 (ULTRA XT demo; the
`MT` field itself is present on every model's outputs): with no text
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
  **Every sample-count field uses the device's own processing rate**
  (48, 96 or 192 kHz, see section 5): delays, `<DCM><DC>` values and the
  FX boost frequency (section 4). Never convert without knowing the model.
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

## 4. FX: Augmented Bass Processing (`<ABP>`) and Center Processing (`<STX>`) — all models

Worked out by toggling one FX control at a time in demo mode and diffing the
saves. **Verified on all 33 models** (PC-Tool 6.05.01) unless noted.

| Field | Meaning | Evidence |
|---|---|---|
| `<STX CMOD>` | RealCenter (Center Processing): 0 off, 1 on | verified, 32 models; **ISM 400.2 has no `<STX>` element and no Center page** |
| `<ABP SWBP>` | Dynamic Bass Enhancement **bypass**: 1 = disabled, 0 = enabled | verified, all models |
| `<ABP SWS>` | SubXpander **bypass**: 1 = disabled, 0 = enabled | verified on V EIGHTEEN, ULTRA XT, DSP.3S, BRAX 192 |
| `<ABP AM>` | automatic frequency adjustment: 1 = on (boost frequency becomes 35 Hz) | verified on V EIGHTEEN, ULTRA XT, DSP.3S, BRAX 192 |
| `<ABP BF1>` = `<ABP BF2>` | boost frequency as **2π·f / device rate** (radians per sample) | verified at 48, 96 and 192 kHz |
| `<ABP B>` | dynamic boost gain in dB (integer UI steps) | verified on V EIGHTEEN, ULTRA XT, BRAX 192 |
| `<ABP HT>`, `<ABP RT>` | −5 / 1.2 whenever DBE is off **or** `B > 0`; 0 / 1 only with DBE on and `B = 0` | observed; meaning (threshold/ratio?) **open** |
| `LF`, `LT`, `SWIN1`, `SWOUT1`, `SWOUT2` | unchanged by every FX control | **open** |

- Enabling DBE always gives the same five changes: `SWBP 1→0`, `HT −5→0`,
  `RT 1.2→1`, and `BF1`/`BF2` from the 40 Hz default to 20 Hz.
- Boost frequency examples: 40 Hz is `0.005235987755982989` at 48 kHz,
  `0.0026179938779914945` at 96 kHz and `0.0013089969389957472` at 192 kHz.
  The tool's float printing can differ in the 17th digit, so compare with a
  relative tolerance (≈1e-15), never as strings.
- The FX blocks act on fixed channels per model (table in section 5). On
  MATCH M 5DSP MK2 both act on the shared "[E] Subwoofer" output, and the UI
  warns that Center Processing disables the subwoofer output.

## 5. Model reference (all 33 models)

`Dev` and `AV` come from each model's default demo file (PC-Tool 6.05.01);
rate and analog in/out from the start-screen spec panel; the physical `ON`
block from `pct6_tool.py channels` on the demo file. "Virtual" is the
number of virtual channels (0 = no Virtual tab). FX targets are as labelled
in the UI (letters or numbers are the UI's own names).

| Model | Dev | AV | Rate | Analog in/out | INS/OUTS | Physical ON | Virtual | ABP target | Center target |
|---|---|---|---|---|---|---|---|---|---|
| BRAX DSP 192 kHz | 17 | X9 | 192 kHz | 8/12 | 14/14 | 0–11 | 0 | Output K+L | Output F |
| BRAX DSP 96 kHz | 43 | Y5 | 96 kHz | 8/12 | 14/26 | 14–25 | 12 | Virtual K+L | Virtual E |
| HELIX DSP ULTRA XT | 53 | X2 | 96 kHz | 12/16 | 18/34 | 18–33 | 16 | Virtual 15+16 | Virtual 5 |
| HELIX DSP ULTRA S | 39 | A4 | 96 kHz | 8/12 | 12/26 | 14–25 | 12 | Virtual K+L | Virtual E |
| HELIX DSP ULTRA | 22 | A4 | 96 kHz | 8/12 | 12/26 | 14–25 | 12 | Virtual K+L | Virtual E |
| HELIX DSP PRO MK3 | 30 | R5 | 96 kHz | 8/10 | 12/22 | 12–21 | 10 | Virtual I+J | Virtual E |
| HELIX DSP.3S | 33 | Y5 | 96 kHz | 6/8 | 10/10 | 0–7 | 0 | Channel H | Channel G |
| HELIX DSP.3 | 21 | Y5 | 96 kHz | 6/8 | 10/10 | 0–7 | 0 | Channel H | Channel G |
| HELIX DSP MINI MK2 | 31 | V5 | 96 kHz | 4/6 | 8/8 | 0–5 | 0 | Channel F | Channel E |
| HELIX DSP MINI | 19 | V5 | 96 kHz | 4/6 | 8/8 | 0–5 | 0 | Channel F | Channel E |
| HELIX P SIX DSP ULTIMATE | 32 | P8 | 96 kHz | 6/12 | 10/24 | 12–23 | 12 | Virtual E+F | Virtual G |
| HELIX V EIGHTEEN DSP | 38 | V3 | 48 kHz | 18/20 | 22/42 | 22–41 | 20 | Virtual 17+18 | Virtual 5 |
| HELIX V TWELVE DSP MK2 | 35 | Y5 | 48 kHz | 12/14 | 16/30 | 16–29 | 14 | Virtual K+L | Virtual E |
| HELIX V TWELVE DSP | 25 | Y5 | 48 kHz | 12/14 | 16/30 | 16–29 | 14 | Virtual K+L | Virtual E |
| HELIX V EIGHT DSP ULTIMATE | 44 | X2 | 48 kHz | 12/14 | 18/30 | 16–29 | 14 | Virtual 9+10 | Virtual 5 |
| HELIX V EIGHT DSP MK2 | 24 | M7 | 48 kHz | 8/10 | 12/22 | 12–21 | 10 | Virtual G+H | Virtual E |
| HELIX M SIX DSP | 34 | X7 | 48 kHz | 6/10 | 10/20 | 10–19 | 10 | Virtual I+J | Virtual E |
| HELIX M FOUR DSP | 26 | X7 | 48 kHz | 6/10 | 10/20 | 10–19 | 10 | Virtual I+J | Virtual E |
| HELIX ISM 400.2DSP | 45 | X2 | 48 kHz | 2/1 | 2/1 | 0 | 0 | Amp Out A | — |
| HELIX AMPLIFY 206 DSP | 46 | X2 | 48 kHz | 6/8 | 10/16 | 8–15 | 8 | Virtual G+H | Virtual E |
| MATCH UP 10DSP MK2 | 48 | N7 | 48 kHz | 8/11 | 12/24 | 13–23 | 11 | Virtual I+J | Virtual E |
| MATCH UP 10DSP | 28 | N7 | 48 kHz | 8/11 | 12/24 | 13–23 | 11 | Virtual I+J | Virtual E |
| MATCH UP 10DSP 24V | 40 | N7 | 48 kHz | 8/11 | 12/24 | 13–23 | 11 | Virtual I+J | Virtual E |
| MATCH UP 8DSP MK2 | 49 | S6 | 48 kHz | 6/9 | 10/20 | 11–19 | 9 | Virtual G+H | Virtual E |
| MATCH UP 8DSP | 37 | S6 | 48 kHz | 6/9 | 10/20 | 11–19 | 9 | Virtual G+H | Virtual E |
| MATCH UP 8BMW MK2 | 50 | S6 | 48 kHz | 6/9 | 10/20 | 11–19 | 9 | Virtual G+H | Virtual E |
| MATCH UP 8BMW | 41 | S6 | 48 kHz | 6/9 | 10/20 | 11–19 | 9 | Virtual G+H | Virtual E |
| MATCH UP 6DSP MK2 | 51 | X3 | 48 kHz | 6/7 | 10/16 | 9–15 | 7 | Virtual F+G | Virtual E |
| MATCH UP 6DSP | 42 | X3 | 48 kHz | 6/7 | 10/16 | 9–15 | 7 | Virtual F+G | Virtual E |
| MATCH UP 4DSP | 47 | X1 | 48 kHz | 4/5 | 6/13 | 8–12 | 8 | Virtual G+H | Virtual E |
| MATCH M 5.4DSP | 29 | N6 | 48 kHz | 4/9 | 6/18 | 9–17 | 9 | Virtual H+I | Virtual E |
| MATCH M 5DSP MK2 | 23 | N5 | 48 kHz | 4/7 | 6/7 | 0–6 | 0 | [E] Subwoofer | [E] Subwoofer |
| MATCH PP 86DSP MK2 | 36 | T3 | 48 kHz | 6/9 | 10/20 | 11–19 | 9 | Virtual G+H | Virtual E |

All models are 64-bit. Three rate classes: 192 kHz (BRAX DSP 192 kHz only),
96 kHz (BRAX 96, ULTRA / ULTRA S / ULTRA XT, PRO MK3, DSP.3 / DSP.3S, MINI /
MINI MK2, P SIX ULTIMATE) and 48 kHz (all V-series, M FOUR / M SIX,
ISM 400.2, AMPLIFY 206 and every MATCH model).

### 5.1 Root attributes across models (observed on the demo files)

- `Dev` is the model id (table above). `AV` is a version tag of the
  model's DSP program; it is **not** unique per model (`X2` = ULTRA XT,
  V EIGHT ULTIMATE, ISM 400.2, AMPLIFY 206; `Y5` = BRAX 96, DSP.3/3S,
  V TWELVE/MK2). Whether the PC-Tool refuses a file with a mismatching `AV`
  is **open**.
- `VM` and `VCO` are **absent** (not 0) on models without virtual channels
  (DSP.3S, ISM 400.2, MATCH M 5DSP MK2 checked).
- `IGM="1"` on P SIX ULTIMATE, ISM 400.2 and MATCH M 5DSP MK2, `2` elsewhere
  (meaning **open**). `TM="1"` on ISM 400.2, `2` elsewhere.
- Same root attribute set and element types on HELIX, BRAX and MATCH: the
  format is shared across product lines.

### 5.2 Model families and capabilities (from the PC-Tool 6.05 device files)

Static facts read from the device-definition files that ship with
PC-Tool 6.05 (counts only; no vendor data is reproduced here). They are not
device-confirmed.

- **Identical DSP parameter maps** (a setup's channel and parameter
  structure should carry over between members; hardware differences are
  invisible in the file apart from `Dev`):
  ULTRA = ULTRA S; MATCH UP 6DSP = UP 6DSP MK2; MATCH UP 8DSP = UP 8DSP MK2 =
  UP 8BMW = UP 8BMW MK2; MATCH UP 10DSP = UP 10DSP 24V = UP 10DSP MK2;
  M FOUR ≈ M SIX (same map, DSP images differ in one byte). Near-twins that
  are **not** identical: DSP.3 / DSP.3S, MINI / MINI MK2, V TWELVE /
  V TWELVE MK2, V EIGHT MK2 / V EIGHT ULTIMATE.
- **Output EQ:** 31 biquad stages per output in all models, of which the UI
  exposes 30 bands (the 31st is unexplained).
- **Crossover:** 9 biquad stages per output, except DSP MINI and MINI MK2
  (7), which suggests a lower maximum slope there.
- **Input EQ:** 16 stages per input, except BRAX DSP 192 kHz (11).
- **Group EQ / delay layer** (front L/R, rear L/R, centre front/rear,
  sub 1/2): present in exactly the 26 models with a virtual-channel layer;
  absent on BRAX 192, DSP.3, DSP.3S, MINI, MINI MK2, ISM 400.2 and
  M 5DSP MK2. MATCH UP 6 has 7 groups (no centre rear).
- **No per-output EQ-bypass and phase-invert DSP module** on ULTRA XT and
  P SIX ULTIMATE (the other 31 models have both). On those two the tool
  presumably realises EQ bypass and phase through coefficients
  (inference).
- **USB audio** only on V EIGHT ULTIMATE and ULTRA XT.
- **No digital output pair** (inferred from the routing dimensions) on
  AMPLIFY 206, M FOUR, M SIX, P SIX ULTIMATE, M 5.4, M 5DSP MK2, UP 4 and
  ISM 400.2; this matches their `OUTS` = virtual + analog.
- **MATCH UP 4DSP** is the only model with more virtual channels (8) than
  outputs (5).
- Amplifier models additionally carry thermal gain reduction,
  power-supply control and (several) bridging/compensation blocks that
  have no counterpart in the standalone DSPs; none of these are exposed as
  `.pct6` fields that we have identified.

### 5.3 MATCH UP 8BMW / 8BMW MK2: built-in BMW template

Starting either model in demo mode asks whether to load a preconfigured
sound setup for a BMW HiFi system (option 676). Answering *Yes* produces a
file that differs from the plain default in 898 values (output EQ bands,
input EQ frequencies, channel names, delays, link groups, gains, routing,
and DBE enabled at 35 Hz). The template is **identical** on both models;
the only difference between the two saved files is `Dev` (41 vs 50). It is
a vendor starting point, not a vehicle-specific tune: the dialog itself
says the EQs are not adapted to the individual car.

## 6. Practical consequences for measurement runs

- Solo/mute hotkeys only change `MT`; they are safe for measuring as long as
  nothing is saved or deployed in between (2.3).
- Before a run, the "all muted" baseline can be prepared as a preset and
  checked offline: every physical output must have `MT="0"`
  (`python3 tools/pct6_tool.py check-muted baseline.pct6`).
- `python3 tools/pct6_tool.py channels setup.pct6` prints Output *k* ↔ `ON` ↔
  name for any of the 33 models (it also names the model from `Dev`), which
  gives the channel numbers for `dv_measure.ini` `[channels]`.
- Keep the PC-Tool window free of focused text fields while the automation
  sends number keys (2.2).
