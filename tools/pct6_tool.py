#!/usr/bin/env python3
"""
pct6_tool.py — read Audiotec Fischer DSP PC-Tool sound-setup files (.pct6)
──────────────────────────────────────────────────────────────────────────
Stdlib only. Format notes: docs/helix-pct6-format.md

    python3 pct6_tool.py decode   setup.pct6 [out.xml]   # XML to file or stdout
    python3 pct6_tool.py encode   in.xml out.pct6        # masked v6 container
    python3 pct6_tool.py channels setup.pct6             # outputs, names, mute
    python3 pct6_tool.py check-muted setup.pct6          # exit 0 = all physical
                                                         # outputs muted

This tool never talks to the PC-Tool or a device. `encode` re-decodes its
own result and refuses to write if the round trip differs.
"""

import argparse
import re
import sys
import zlib
from pathlib import Path

KEY = b"ATFV6"

# <OC CN="…"> output channel name enum (index, not dropdown position)
OUTPUT_NAMES = [
    "Not assigned", "Front L Full", "Front R Full", "Front L High",
    "Front R High", "Front L Mid", "Front R Mid", "Front L Low",
    "Front R Low", "Front Center Full", "Front Center High",
    "Front Center Low", "F Sum", "Rear L Full", "Rear R Full",
    "Rear L High", "Rear R High", "Rear L Mid", "Rear R Mid", "Rear L Low",
    "Rear R Low", "Rear Fill Full", "Rear Fill High", "Rear Fill Low",
    "Rear Sum", "Subwoofer 1", "Subwoofer 2", "Subwoofer 3", "Subwoofer 4",
    "Line Out 1", "Line Out 2", "Line Out 3", "Line Out 4", "Line Out 5",
    "Line Out 6", "Line Out 7", "Line Out 8", "Subwoofer L", "Subwoofer R",
    "Pass Through 1", "Pass Through 2", "Pass Through 3", "Pass Through 4",
    "Pass Through 5", "Pass Through 6", "Bridge Mode", "Surround L Full",
    "Surround R Full", "Front Subwoofer L", "Front Subwoofer R",
    "Pass Through 7", "Pass Through 8", "Pass Through 9", "Pass Through 10",
    "Pass Through 11", "Pass Through 12", "User defined Name",
]
USER_DEFINED = 56


def _xor(data: bytes) -> bytes:
    return bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(data))


def _unpack(payload: bytes) -> bytes:
    n = int.from_bytes(payload[:4], "big")
    xml = zlib.decompress(payload[4:])
    if len(xml) != n:
        raise ValueError(f"length field {n} != decoded length {len(xml)}")
    return xml


def decode(container: bytes) -> tuple[bytes, str]:
    """Return (xml, generation). generation is 'v6' (masked) or 'legacy'.

    Detection is structural (zlib + length field), never by leading bytes:
    the apparent 'AT'/'AU' signature is just the masked length field.
    """
    errors = []
    for gen, payload in (("v6", _xor(container)), ("legacy", container)):
        try:
            return _unpack(payload), gen
        except (zlib.error, ValueError) as e:
            errors.append(f"{gen}: {e}")
    raise ValueError("not a readable .pct6/.afpx container ("
                     + "; ".join(errors) + ")")


def encode(xml: bytes, generation: str = "v6") -> bytes:
    payload = len(xml).to_bytes(4, "big") + zlib.compress(xml, 9)
    out = _xor(payload) if generation == "v6" else payload
    back, gen = decode(out)
    if back != xml or gen != generation:
        raise RuntimeError("self-check failed: encoded file does not decode "
                           "back to the input; nothing written")
    return out


def _attrs(tag_body: str) -> dict:
    return dict(re.findall(r'(\w+)="([^"]*)"', tag_body))


def output_channels(xml: str) -> list[dict]:
    """All <OC> elements with ON, name, mute state and physical flag."""
    user_names = {}
    for m in re.finditer(r"<UN\s+([^>]*?)/>", xml):
        a = _attrs(m.group(1))
        if "UNENU" in a:
            user_names[a["UNENU"]] = a.get("UNENA", "")   # last one wins
    chans = []
    for m in re.finditer(r"<OC\s+([^>]*)>", xml):
        a = _attrs(m.group(1))
        cn = int(a.get("CN", "0"))
        if cn == USER_DEFINED:
            name = user_names.get(a.get("ON"), "User Defined Name")
        elif 0 <= cn < len(OUTPUT_NAMES):
            name = OUTPUT_NAMES[cn]
        else:
            name = ""                                     # tool shows empty
        chans.append({
            "on": int(a["ON"]),
            "name": name,
            # MT is inverted: 1 = audible, 0 = muted
            "muted": a.get("MT") == "0",
            # physical outputs carry crossover pointers, virtual ones do not
            "physical": "HPi" in a or "LPi" in a,
            "eq_bands": int(a.get("Finit", "0")),
            "link_group": a.get("LG", "0"),
        })
    chans.sort(key=lambda c: c["on"])
    out_no = 0
    for c in chans:
        if c["physical"]:
            out_no += 1
            c["output"] = out_no
        else:
            c["output"] = None
    return chans


def _load(path: str) -> tuple[str, str]:
    xml, gen = decode(Path(path).read_bytes())
    return xml.decode("utf-8"), gen


def _root(xml: str) -> dict:
    m = re.search(r"<ATF\s+([^>]*)>", xml)
    return _attrs(m.group(1)) if m else {}


def cmd_decode(args) -> int:
    xml, gen = decode(Path(args.file).read_bytes())
    if args.out:
        Path(args.out).write_bytes(xml)
        print(f"{args.out}: {len(xml)} bytes XML ({gen} container)")
    else:
        sys.stdout.write(xml.decode("utf-8"))
    return 0


def cmd_encode(args) -> int:
    xml = Path(args.xml).read_bytes()
    out = Path(args.out)
    if out.exists() and not args.force:
        print(f"{out} exists (use --force to overwrite)", file=sys.stderr)
        return 2
    out.write_bytes(encode(xml, args.generation))
    print(f"{out}: written ({args.generation}), self-check OK")
    return 0


def cmd_channels(args) -> int:
    xml, gen = _load(args.file)
    r = _root(xml)
    print(f"PC-Tool {r.get('V', '?')}  Dev={r.get('Dev', '?')}  "
          f"OUTS={r.get('OUTS', '?')}  INS={r.get('INS', '?')}  ({gen})")
    print(f"{'Output':>6}  {'ON':>3}  {'state':<7} {'EQ':>3}  {'LG':>3}  name")
    for c in output_channels(xml):
        if not (c["physical"] or args.all):
            continue
        label = str(c["output"]) if c["physical"] else "virt"
        state = "muted" if c["muted"] else "audible"
        print(f"{label:>6}  {c['on']:>3}  {state:<7} {c['eq_bands']:>3}  "
              f"{c['link_group']:>3}  {c['name']}")
    return 0


def cmd_check_muted(args) -> int:
    xml, _ = _load(args.file)
    loud = [c for c in output_channels(xml) if c["physical"] and not c["muted"]]
    if not loud:
        print("OK: all physical outputs are muted (MT=0)")
        return 0
    print("NOT all muted — audible physical outputs:")
    for c in loud:
        print(f"  Output {c['output']} (ON {c['on']}): {c['name']}")
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("decode", help="print or save the XML")
    s.add_argument("file"); s.add_argument("out", nargs="?")
    s.set_defaults(fn=cmd_decode)
    s = sub.add_parser("encode", help="pack XML into a .pct6 container")
    s.add_argument("xml"); s.add_argument("out")
    s.add_argument("--generation", choices=["v6", "legacy"], default="v6")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_encode)
    s = sub.add_parser("channels", help="list outputs: number, ON, mute, name")
    s.add_argument("file")
    s.add_argument("--all", action="store_true",
                   help="include virtual channels")
    s.set_defaults(fn=cmd_channels)
    s = sub.add_parser("check-muted",
                       help="exit 0 if every physical output is muted")
    s.add_argument("file")
    s.set_defaults(fn=cmd_check_muted)
    args = p.parse_args()
    try:
        return args.fn(args)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
