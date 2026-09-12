#!/usr/bin/env python3
"""
caps_stego.py — CAPS_matter_To_tHe_VIEW

Visor-ghost stego-wormhole codec. The VIEW's case IS the payload.

  upper = 1, lower = 0, one bit per A-Za-z. Non-alpha = cover only.
  Bytes are 8 bits big-endian. NUL-padded, stripped on decode.

Private chaos cloak for Hop step 4 — NOT public hygiene. See HOP_PROTOCOL.md
Appendix A. Decays with the wormhole; Visor ghost keeps low classes from mirroring it.

Usage:
  python3 tools/provenance/caps_stego.py encode "tools/provenance/dna_tag.py" --cover cover.txt
  python3 tools/provenance/caps_stego.py decode ~/dna_tag.py
  python3 tools/provenance/caps_stego.py check ~/dna_tag.py --expect tools/provenance/dna_tag.py
  python3 tools/provenance/caps_stego.py visor-view --file ~/dna_tag.py --class recruit  --dir ~
  python3 tools/provenance/caps_stego.py visor-view --file ~/dna_tag.py --class architect --dir ~

Stdlib only. Read-only aside from stdout. Never writes hop shims — that's hop #4's job.
"""

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: provenance
# DEPS: re,argparse,pathlib,json
# ROLE: CAPS stego codec for Visor-ghost wormholes (case bits over archival prose)
# AUTHOR: Buffy (Codebuff) — stego patch via Visor/SLaSHdotHIDE
# SESSION: 2026-09-08
# TIER: 2
# FKA: tools/provenance/dna_tag.py companion
# DECAY: — (codec itself is permanent; shims it encodes decay)
# [/DNA_TAG]

import argparse
import re
import sys
import json
from pathlib import Path

_HOME = Path.home()
_VISOR_HOME = _HOME / ".SLaSHdotHIDEfiles"

# Letter-case bit codec — alpha only becomes carrier, punctuation/space filtered
# This keeps archival prose looking natural while carrying exact bytes (slashes, dots, underscores)
_LETTER_RE = re.compile(r"[A-Za-z]")

DEFAULT_COVER = (
    "This file was relocated during the great consolidation. "
    "Please update your imports to the canonical path noted below. "
    "The archival view preserves the original maiden name for history. "
    "If you arrived via an old link, the wormhole will forward you for a time. "
    "Update your imports. The ghost view hides the forward for lower classes. "
    "This notice will decay after the hop window. "
    "Visit HOP_PROTOCOL.md appendix A for the full story and Visor mask details. "
)

# Make cover longer if payload is long — repeat with variations so it still reads like prose
_COVER_VARIANTS = [
    DEFAULT_COVER,
    "The relocation honors the backtag maiden name and the forward wormhole together. ",
    "Agents with agents, models with models, tools with tools, cubs with subs, projects together. ",
    "One pillar per hop, prove before next, log or it did not move, decay or die. ",
]

def _cover_for(bits_needed: int) -> str:
    """Repeat variants until we have enough alpha chars for bits_needed."""
    s = "".join(_COVER_VARIANTS)
    while len([c for c in s if c.isalpha()]) < bits_needed:
        s += " " + _COVER_VARIANTS[len(s) % len(_COVER_VARIANTS)]
    return s

def _bits_from_bytes(payload: bytes) -> str:
    return "".join(f"{b:08b}" for b in payload)

def _bytes_from_bits(bits: str) -> bytes:
    # trim trailing incomplete byte + strip NUL padding
    n = (len(bits) // 8) * 8
    bits = bits[:n]
    out = bytearray()
    for i in range(0, len(bits), 8):
        out.append(int(bits[i:i+8], 2))
    return bytes(out).rstrip(b"\x00")

def encode(payload: str, cover: str | None = None) -> str:
    """
    Returns stego text with same non-alpha as cover, alpha case = payload bits.
    Payload is UTF-8 bytes, NUL-padded to fill remaining alpha slots modulo 8.
    """
    raw = payload.encode("utf-8")
    bits = _bits_from_bytes(raw)
    # Need alpha == bits length rounded up to multiple of 8 (eat trailing NULs nicely on decode)
    need = ((len(bits) + 7) // 8) * 8
    if cover is None:
        cover = _cover_for(need)
    alpha_count = sum(1 for c in cover if c.isalpha())
    if alpha_count < need:
        cover = _cover_for(need)  # ignore short custom cover
        alpha_count = sum(1 for c in cover if c.isalpha())
    # pad bits with zeros (NUL bytes) to consume the cover if it was longer than needed — still decodes clean after rstrip
    bits = bits.ljust(alpha_count if alpha_count % 8 == 0 else ((alpha_count // 8 + 1) * 8), "0")
    # distribute bits over alpha positions only
    out = []
    bi = 0
    for ch in cover:
        if ch.isalpha() and bi < len(bits):
            # preserve original letter shape, just set case to bit
            base = ch.lower()
            out.append(base.upper() if bits[bi] == "1" else base.lower())
            bi += 1
        else:
            # non-alpha or exhausted bits: leave as-is but lowercase the trailing carrier so it doesn't look like payload
            # (keep cover's look roughly intact)
            out.append(ch)
        if bi >= len(bits) and ch.isalpha():
            # beyond payload: render remaining alpha lower for visual quiet
            # we already did one above — switch remaining loop to lower-only by not flipping
            pass
    # the above kept cover verbatim after bits exhausted — now normalize tail alpha to lower for calmer look
    # Re-walk once more if we padded: tail should be lower, not mixed
    # (already lower after bi==len(bits) for alpha that fell after, so fine)
    return "".join(out)

def _carrier_bits(text: str) -> str:
    """Extract bits from A-Za-z case: upper=1 lower=0."""
    return "".join("1" if c.isupper() else "0" for c in text if c.isalpha())

def decode(text: str) -> str:
    """
    Extracts case bits from alpha only and decodes to UTF-8 string.
    Looks for the STEGO fence first (```caps-stego …```) if present,
    otherwise decodes the whole file/docstring-ish portion.
    """
    # Prefer fenced block if file was a wormhole — fences keep non-stego caps out
    fenced = _extract_fence(text)
    if fenced is not None:
        text = fenced
    else:
        # No fence: try docstring-ish head (first triple-quote block) else whole text
        m = re.search(r'"""(.*?)"""', text, re.S)
        if m:
            # only decode the docstring noise; code caps would corrupt bitstream
            # If multiple docstrings, only first is stego carrier
            text = m.group(1)
    bits = _carrier_bits(text)
    raw = _bytes_from_bits(bits)
    # Decode, but tolerate non-utf8 truncation: strip trailing incomplete char
    for trim in (0, 1, 2, 3):
        try:
            return raw[: len(raw) - trim].decode("utf-8").rstrip("\x00").strip() if trim else raw.decode("utf-8").rstrip("\x00").strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").rstrip("\x00").strip()

_DOT_FENCE_RE = re.compile(r"```caps-stego\s*\n(.*?)```", re.S)

def _extract_fence(text: str):
    m = _DOT_FENCE_RE.search(text)
    return m.group(1) if m else None

def decode_file(path: str | Path) -> str:
    p = Path(path).expanduser() if isinstance(path, (str, Path)) else Path(str(path))
    # allow calling with Path object or string; also handle .caps sidecar fallback
    if hasattr(path, "read_text"):
        try:
            return decode(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    return decode(p.read_text(encoding="utf-8", errors="replace"))

def _decode_path_arg(path_arg) -> str:
    """Coerce CLI path arg (str or Path) to decoded string."""
    p = Path(str(path_arg)).expanduser()
    return decode(p.read_text(encoding="utf-8", errors="replace"))

def check(path: str | Path, expect: str | None = None) -> dict:
    found = decode_file(path)
    return {"path": str(path), "decoded": found, "expect": expect or "", "ok": (found == expect) if expect is not None else bool(found)}

# Visor ghost/view hook — reuses existing Visor masks if available, with a stego-specific mask
def visor_view(path: str | Path, entity: str = "recruit_01", visor_dir: str | Path | None = None) -> dict:
    """
    Returns what Visor thinks `entity` should see for `path`, plus the decoded stego path.
    GHOST/TOMBSTONE for low classes — they get \"*moved — see vault*\"; Architect/etc gets SHOW + decoded.
    """
    p = Path(path).expanduser().resolve()
    decoded = decode_file(p)
    # Try Visor if installed
    action = None
    mask_name = None
    try:
        sys.path.insert(0, str(_HOME / "RootBase"))
        from visor import Visor  # .SLaSHdotHIDEfiles/visor.py is importable via path shenanigan; fallback below
        v = Visor()
        ok, msg = v.may(str(p), entity, "read")
    except Exception:
        # Fallback: _VISOR_HOME/visor.py path
        try:
            import importlib.util
            vp = _VISOR_HOME / "visor.py"
            spec = importlib.util.spec_from_file_location("visor_mod", str(vp))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            v = mod.Visor()
            ok, msg = v.may(str(p), entity, "read")
        except Exception as e:
            return {"file": str(p), "entity": entity, "visor": f"unavailable ({e})", "decoded": decoded, "display": decoded or "*ghost*"}
    # Evaluate visibility action for stego wormholes specifically — check masks/stego.json
    try:
        stego_mask_path = _VISOR_HOME / "masks" / "stego.json"
        if stego_mask_path.exists():
            m = json.loads(stego_mask_path.read_text())
            # simple: presence means stego_wormholes are GHOST for class >= 3
            action = v.masks.evaluate(str(p), 3 if "recruit" in entity or "worker" in entity else 0, "", v.environment())
            action = getattr(action, "value", str(action))
        else:
            # ask visor what it does with this path today
            act = v.masks.evaluate(str(p), 3 if "recruit" in entity else 0, "", v.environment())
            action = getattr(act, "value", str(act))
        mask_name = v.mask_for(entity).get("mask_name") if hasattr(v, "mask_for") else None
    except Exception:
        pass
    # Presentation rule
    if action == "ghost":
        display = "*moved — see HOP_PROTOCOL.md Appendix A — vault holds forward*"
    elif action == "hide":
        display = "*ghosted*"
    else:
        display = decoded or "*no stego*"
    return {"file": str(p), "entity": entity, "mask": mask_name, "action": action, "decoded": decoded, "display": display}


def main():
    ap = argparse.ArgumentParser(description="CAPS stego — case bits over archival prose (Visor-ghost hop shims)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    enc = sub.add_parser("encode", help="Encode payload into cover (caps bits)")
    enc.add_argument("payload", help="canonical path, e.g. tools/provenance/dna_tag.py")
    enc.add_argument("--cover", help="cover text/file; default: archival prose")
    enc.add_argument("--out", help="write stego text to file instead of stdout")

    dec = sub.add_parser("decode", help="Decode stego from file (caps -> path)")
    dec.add_argument("path", help="wormhole file to decode")

    chk = sub.add_parser("check", help="Decode and compare to expected")
    chk.add_argument("path", help="wormhole file")
    chk.add_argument("--expect", required=True, help="expected canonical path")

    vw = sub.add_parser("visor-view", help="What Visor would show for an entity (GHOST vs SHOW) + decoded")
    vw.add_argument("--file", required=True)
    vw.add_argument("--entity", default="recruit_01")
    vw.add_argument("--dir", default=str(_HOME))

    args = ap.parse_args()

    if args.cmd == "encode":
        cover_text = None
        if args.cover:
            cp = Path(args.cover)
            cover_text = cp.read_text(encoding="utf-8", errors="replace") if cp.exists() else args.cover
        stego = encode(args.payload, cover_text)
        if args.out:
            Path(args.out).write_text(stego, encoding="utf-8")
            print(f"wrote stego to {args.out} ({len(stego)} chars, {_carrier_bits(stego).count('0')+_carrier_bits(stego).count('1')} carrier bits)")
        else:
            print(stego)

    elif args.cmd == "decode":
        print(_decode_path_arg(args.path))

    elif args.cmd == "check":
        # normalize: if file is json stub with _caps_stego, decode that field's case too
        try:
            import json as _js
            raw = Path(str(args.path)).expanduser().read_text(encoding="utf-8", errors="replace")
            try:
                j = _js.loads(raw)
                if isinstance(j, dict) and "_caps_stego" in j:
                    # j['_caps_stego'] already is stego case text — decode it directly
                    found = decode(j["_caps_stego"])
                    r = {"path": str(args.path), "decoded": found, "expect": args.expect, "ok": found == args.expect, "via": "_caps_stego field"}
                    print(json.dumps(r, indent=2))
                    sys.exit(0 if r["ok"] else 1)
            except Exception:
                pass
        except Exception:
            pass
        r = check(args.path, args.expect)
        print(json.dumps(r, indent=2))
        sys.exit(0 if r["ok"] else 1)

    elif args.cmd == "visor-view":
        print(json.dumps(visor_view(args.file, args.entity, args.dir), indent=2))


if __name__ == "__main__":
    main()
