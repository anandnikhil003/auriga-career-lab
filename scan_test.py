"""Safety check: decode every opportunity's QR and confirm it encodes that
opportunity's official URL. Additive — reuses (does not modify) the QR encoder.

Primary check is dependency-free: rebuild the QR matrix from the URL via
cards.qr_matrix(), then decode it back with a self-decoder and compare. If
OpenCV (cv2) is installed it ALSO image-decodes the rendered slide PNGs.

  python main.py --scan-test     (exit 1 on any mismatch)
"""
from __future__ import annotations

import json

import cards
import config

_FMT_XOR = 0b101010000010010


def _decode_matrix(m) -> str:
    """Decode a byte-mode QR matrix (v1-9) back to its text. Mirror of the
    encoder's placement; uses cards' own function-map/traverse/mask."""
    size = len(m)
    v = (size - 17) // 4
    _, _, fn = cards._function_map(v)
    # read 15 format bits in the exact cells cards._place_format wrote them
    gb = ([m[i][8] for i in range(6)] + [m[7][8], m[8][8], m[8][7]]
          + [m[8][14 - i] for i in range(9, 15)])
    raw = 0
    for i, b in enumerate(gb):
        raw |= (b << i)
    mask = ((raw ^ _FMT_XOR) >> 10) & 7
    # read data region in the same zig-zag order, unmasking
    bits = [m[r][c] ^ (1 if cards._mask(mask, r, c) else 0) for (r, c) in cards._traverse(size, fn)]
    ec, nb, dpb, total, rem = cards._TBL[v]
    ncw = nb * dpb + nb * ec
    allcw = [int("".join(map(str, bits[i * 8:i * 8 + 8])), 2) for i in range(ncw)]
    # de-interleave the data codewords back into per-block order
    inter = allcw[:nb * dpb]
    blocks = [[0] * dpb for _ in range(nb)]
    idx = 0
    for i in range(dpb):
        for b in range(nb):
            blocks[b][i] = inter[idx]; idx += 1
    data_cw = [c for blk in blocks for c in blk]
    db = []
    for cw in data_cw:
        for k in range(7, -1, -1):
            db.append((cw >> k) & 1)
    mode = int("".join(map(str, db[0:4])), 2)
    if mode != 4:  # byte mode
        return f"<mode {mode}>"
    length = int("".join(map(str, db[4:12])), 2)
    out = bytearray()
    pos = 12
    for _ in range(length):
        out.append(int("".join(map(str, db[pos:pos + 8])), 2))
        pos += 8
    return out.decode("utf-8", "replace")


def _cv2():
    try:
        import cv2  # noqa
        return cv2
    except Exception:
        return None


def scan() -> tuple[bool, list]:
    data = json.loads(config.SOURCES_FILE.read_text(encoding="utf-8"))
    cv2 = _cv2()
    rows = []
    all_ok = True
    for o in data.get("opportunities", []):
        url = o["official_url"]
        try:
            decoded = _decode_matrix(cards.qr_matrix(url))
            ok = decoded == url
        except Exception as e:  # noqa: BLE001
            ok, decoded = False, f"ERR {e}"
        if not ok:
            all_ok = False
        rows.append((o.get("category", "?"), o["program"], url, ok, decoded))
    return all_ok, rows


def cv2_check_slides() -> tuple[int, int]:
    """Optional image-level decode of generated slide PNGs (if cv2 available)."""
    cv2 = _cv2()
    if cv2 is None:
        return (-1, -1)
    import glob
    ok = tot = 0
    for png in glob.glob(str(config.CARDS_DIR / "*" / "*.png")):
        if png.endswith("0_cover.png"):
            continue
        tot += 1
        try:
            data, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(png))
            ok += 1 if data else 0
        except Exception:
            pass
    return ok, tot


def run() -> int:
    all_ok, rows = scan()
    fails = [r for r in rows if not r[3]]
    print(f"SCAN-TEST: {len(rows)-len(fails)}/{len(rows)} QR codes encode the correct URL")
    for cat, prog, url, ok, dec in fails:
        print(f"  FAIL [{cat}] {prog[:40]} expected={url} decoded={dec}")
    ok, tot = cv2_check_slides()
    if tot >= 0:
        print(f"cv2 image-level: {ok}/{tot} rendered slide PNGs decode")
    else:
        print("cv2 not installed — skipped image-level check (matrix round-trip above is authoritative)")
    print("RESULT:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1
