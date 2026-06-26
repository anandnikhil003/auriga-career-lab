"""1080x1080 opportunity cards with Pillow only.

Includes a self-contained, spec-correct QR encoder (byte mode, ECC M, versions
1-6) verified to decode with an independent decoder. No external QR library.

Card elements: header/logo, category badge, ranked opportunities with country +
funding + deadline badges, and a QR code to the #1 pick's official link.

Public API unchanged: render_category_card(category, opps) -> path | None
"""
from __future__ import annotations

import config
from models import Opportunity

# ───────────────────────── QR ENCODER (pure Python) ─────────────────────────
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x; _LOG[_x] = _i; _x <<= 1
    if _x & 0x100: _x ^= 0x11d
for _i in range(255, 512): _EXP[_i] = _EXP[_i - 255]
def _gmul(a, b): return 0 if a == 0 or b == 0 else _EXP[(_LOG[a] + _LOG[b]) % 255]
def _rs_gen(n):
    g = [1]
    for i in range(n):
        ng = [0] * (len(g) + 1)
        for j in range(len(g)):
            ng[j] ^= g[j]; ng[j + 1] ^= _gmul(g[j], _EXP[i])
        g = ng
    return g
def _rs_encode(data, n):
    msg = list(data) + [0] * n; g = _rs_gen(n)
    for i in range(len(data)):
        c = msg[i]
        if c:
            for j in range(len(g)): msg[i + j] ^= _gmul(g[j], c)
    return msg[len(data):]
# (ec_per_block, num_blocks, data_per_block, total_data, remainder_bits)
_TBL = {1: (10, 1, 16, 16, 0), 2: (16, 1, 28, 28, 7), 3: (26, 1, 44, 44, 7),
        4: (18, 2, 32, 64, 7), 5: (24, 2, 43, 86, 7), 6: (16, 4, 27, 108, 7)}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
def _codewords(text):
    b = text.encode()
    for v in range(1, 7):
        ec, nb, dpb, total, rem = _TBL[v]
        if 4 + 8 + 8 * len(b) <= total * 8:
            bits = []
            def put(val, n):
                for i in range(n - 1, -1, -1): bits.append((val >> i) & 1)
            put(4, 4); put(len(b), 8)
            for byte in b: put(byte, 8)
            for _ in range(min(4, total * 8 - len(bits))): bits.append(0)
            while len(bits) % 8: bits.append(0)
            cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
            pad = [0xEC, 0x11]; i = 0
            while len(cw) < total: cw.append(pad[i % 2]); i += 1
            blocks = [cw[j * dpb:(j + 1) * dpb] for j in range(nb)]
            ecb = [_rs_encode(bl, ec) for bl in blocks]
            out = []
            for i in range(dpb):
                for bl in blocks:
                    if i < len(bl): out.append(bl[i])
            for i in range(ec):
                for eb in ecb: out.append(eb[i])
            return v, out, rem
    raise ValueError("URL too long for v6 QR")
def _function_map(v):
    size = 17 + 4 * v
    m = [[None] * size for _ in range(size)]; fn = [[False] * size for _ in range(size)]
    def setm(r, c, val): m[r][c] = val; fn[r][c] = True
    def finder(r, c):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if 0 <= rr < size and 0 <= cc < size:
                    if 0 <= dr < 7 and 0 <= dc < 7:
                        setm(rr, cc, 1 if (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4)) else 0)
                    else:
                        setm(rr, cc, 0)
    finder(0, 0); finder(0, size - 7); finder(size - 7, 0)
    for i in range(size):
        if m[6][i] is None: setm(6, i, 1 if i % 2 == 0 else 0)
        if m[i][6] is None: setm(i, 6, 1 if i % 2 == 0 else 0)
    for r in _ALIGN[v]:
        for c in _ALIGN[v]:
            if fn[r][c]: continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    setm(r + dr, c + dc, 1 if (abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0)) else 0)
    setm(size - 8, 8, 1)
    for i in range(9):
        if not fn[8][i]: fn[8][i] = True
        if not fn[i][8]: fn[i][8] = True
    for i in range(7): fn[size - 1 - i][8] = True
    for i in range(8): fn[8][size - 1 - i] = True
    return size, m, fn
def _mask(k, r, c):
    return [(r + c) % 2 == 0, r % 2 == 0, c % 3 == 0, (r + c) % 3 == 0,
            (r // 2 + c // 3) % 2 == 0, ((r * c) % 2 + (r * c) % 3) == 0,
            (((r * c) % 2 + (r * c) % 3) % 2) == 0, (((r + c) % 2 + (r * c) % 3) % 2) == 0][k]
def _format_bits(k):
    data = (0 << 3) | k; val = data << 10; g = 0b10100110111
    for i in range(14, 9, -1):
        if (val >> i) & 1: val ^= g << (i - 10)
    return ((data << 10) | val) ^ 0b101010000010010
def _traverse(size, fn):
    cells = []; up = True; col = size - 1
    while col > 0:
        if col == 6: col -= 1
        for i in range(size):
            r = (size - 1 - i) if up else i
            for c in (col, col - 1):
                if not fn[r][c]: cells.append((r, c))
        up = not up; col -= 2
    return cells
def _place_format(m, size, k):
    fmt = _format_bits(k); gb = lambda i: (fmt >> i) & 1
    for i in range(6): m[i][8] = gb(i)
    m[7][8] = gb(6); m[8][8] = gb(7); m[8][7] = gb(8)
    for i in range(9, 15): m[8][14 - i] = gb(i)
    for i in range(8): m[8][size - 1 - i] = gb(i)
    for i in range(8, 15): m[size - 15 + i][8] = gb(i)
    m[size - 8][8] = 1
def _penalty(mat):
    n = len(mat); p = 0
    cols = [[mat[r][c] for r in range(n)] for c in range(n)]
    for line in mat + cols:
        run = 1
        for i in range(1, n):
            if line[i] == line[i - 1]: run += 1
            else:
                if run >= 5: p += 3 + (run - 5)
                run = 1
        if run >= 5: p += 3 + (run - 5)
    for r in range(n - 1):
        for c in range(n - 1):
            if mat[r][c] == mat[r][c + 1] == mat[r + 1][c] == mat[r + 1][c + 1]: p += 3
    p1 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]; p2 = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    for r in range(n):
        for c in range(n - 10):
            seg = [mat[r][c + i] for i in range(11)]
            if seg == p1 or seg == p2: p += 40
    for c in range(n):
        for r in range(n - 10):
            seg = [mat[r + i][c] for i in range(11)]
            if seg == p1 or seg == p2: p += 40
    dark = sum(sum(r) for r in mat)
    p += 10 * (abs(dark * 20 // (n * n) - 10))
    return p
def qr_matrix(text):
    v, cw, rem = _codewords(text); size, m, fn = _function_map(v)
    bits = []
    for byte in cw:
        for i in range(7, -1, -1): bits.append((byte >> i) & 1)
    bits += [0] * rem
    for (r, c), b in zip(_traverse(size, fn), bits): m[r][c] = b
    best = None; bp = None
    for k in range(8):
        mm = [row[:] for row in m]
        for r in range(size):
            for c in range(size):
                if not fn[r][c] and _mask(k, r, c): mm[r][c] ^= 1
        _place_format(mm, size, k)
        pen = _penalty(mm)
        if bp is None or pen < bp: bp = pen; best = mm
    return best
def qr_image(text, scale=8, border=4, fg=(17, 17, 17), bg=(255, 255, 255)):
    from PIL import Image, ImageDraw
    m = qr_matrix(text); n = len(m); side = (n + 2 * border) * scale
    img = Image.new("RGB", (side, side), bg); d = ImageDraw.Draw(img)
    for r in range(n):
        for c in range(n):
            if m[r][c]:
                x = (c + border) * scale; y = (r + border) * scale
                d.rectangle([x, y, x + scale - 1, y + scale - 1], fill=fg)
    return img

# ───────────────────────────── CARD RENDERING ──────────────────────────────
SIZE = 1080
PAD = 64
THEME = {
    "stem":         ((16, 64, 102), (8, 26, 46), (96, 200, 245)),
    "ug_research":  ((22, 74, 44), (9, 32, 20), (130, 222, 150)),
    "ai_cs":        ((44, 26, 86), (16, 9, 38), (176, 146, 255)),
    "scholarships": ((96, 56, 14), (40, 23, 6), (245, 192, 96)),
    "conferences":  ((96, 20, 56), (40, 8, 26), (255, 134, 178)),
}
_FLAG_COLOR = {
    "germany": (0, 0, 0), "canada": (216, 30, 30), "switzerland": (210, 30, 30),
    "japan": (210, 30, 40), "saudi": (20, 120, 60), "usa": (40, 70, 160),
    "india": (240, 140, 30), "israel": (40, 90, 200), "korea": (40, 90, 200),
    "china": (216, 30, 30), "türkiye": (216, 30, 30), "turkey": (216, 30, 30),
    "hungary": (40, 130, 80), "italy": (40, 140, 80), "brunei": (235, 200, 40),
    "remote": (90, 110, 130), "global": (90, 110, 130),
}


def _font(path, size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _vgradient(img, top, bottom):
    from PIL import Image
    g = Image.new("RGB", (1, SIZE))
    for y in range(SIZE):
        t = y / (SIZE - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    img.paste(g.resize((SIZE, SIZE)), (0, 0))


def _wrap(d, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= max_w: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines


def _round(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def _flag_color(country):
    c = (country or "").lower()
    for k, v in _FLAG_COLOR.items():
        if k in c: return v
    return (110, 120, 140)


def _badge(d, x, y, text, font, fg, bg, padx=14, pady=8):
    w = d.textlength(text, font=font)
    h = font.size
    _round(d, [x, y, x + w + 2 * padx, y + h + 2 * pady], (h + 2 * pady) // 2, bg)
    d.text((x + padx, y + pady - 2), text, font=font, fill=fg)
    return x + w + 2 * padx


import re as _re


def _slug(program: str) -> str:
    m = _re.search(r"\(([^)]+)\)", program)          # acronym in parentheses
    base = m.group(1) if m else program.split(" — ")[0]
    sl = _re.sub(r"[^a-z0-9]+", "", base.lower())
    return (sl or "opp")[:18]


def _card_header(d, img, category, accent, sub):
    f_logo = _font(config.FONT_BOLD, 30)
    f_meta = _font(config.FONT_REG, 24)
    f_badge = _font(config.FONT_BOLD, 22)
    _round(d, [PAD, PAD, PAD + 54, PAD + 54], 14, accent)
    d.text((PAD + 14, PAD + 8), "A", font=_font(config.FONT_BOLD, 38), fill=(15, 15, 15))
    d.text((PAD + 70, PAD + 4), "AURIGA CAREER LAB", font=f_logo, fill=(255, 255, 255))
    d.text((PAD + 70, PAD + 34), sub, font=f_meta, fill=(205, 205, 205))
    label = config.CATEGORIES.get(category, category).upper()
    bw = d.textlength(label, font=f_badge)
    _round(d, [SIZE - PAD - bw - 32, PAD + 6, SIZE - PAD, PAD + 46], 20, accent)
    d.text((SIZE - PAD - bw - 16, PAD + 12), label, font=f_badge, fill=(15, 15, 15))


def render_cover_card(category, opps):
    """Cover slide: title + numbered list of the 5 programs. -> 0_cover.png"""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    top, bottom, accent = THEME.get(category, THEME["stem"])
    img = Image.new("RGB", (SIZE, SIZE)); _vgradient(img, top, bottom)
    d = ImageDraw.Draw(img)
    _card_header(d, img, category, accent, config.TODAY.isoformat())

    label = config.CATEGORIES.get(category, category)
    f_title = _font(config.FONT_BOLD, 60)
    f_item = _font(config.FONT_BOLD, 38)
    f_foot = _font(config.FONT_REG, 28)
    for i, ln in enumerate(_wrap(d, f"Top {len(opps)} {label} Opportunities", f_title, SIZE - 2 * PAD)):
        d.text((PAD, PAD + 96 + i * 66), ln, font=f_title, fill=(255, 255, 255))
    y = PAD + 250
    d.line([PAD, y, SIZE - PAD, y], fill=accent, width=3); y += 36
    for i, o in enumerate(opps, 1):
        d.ellipse([PAD, y + 4, PAD + 44, y + 48], fill=accent)
        d.text((PAD + 13, y + 6), str(i), font=f_item, fill=(15, 15, 15))
        name = _wrap(d, o.program.split(" — ")[0].split(" (")[0], f_item, SIZE - 2 * PAD - 70)[0]
        d.text((PAD + 66, y + 6), name, font=f_item, fill=(255, 255, 255))
        y += 100
    d.line([PAD, SIZE - 96, SIZE - PAD, SIZE - 96], fill=accent, width=2)
    d.text((PAD, SIZE - 76), "@AurigaCareerLab  ·  Swipe for details & QR links →",
           font=f_foot, fill=(225, 225, 225))

    out_dir = config.CARDS_DIR / category
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "0_cover.png"
    img.save(out, "PNG")
    return str(out)


def render_opportunity_card(category, opp, rank):
    """One opportunity per slide, with its OWN QR -> <rank>_<slug>.png"""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    top, bottom, accent = THEME.get(category, THEME["stem"])
    img = Image.new("RGB", (SIZE, SIZE)); _vgradient(img, top, bottom)
    d = ImageDraw.Draw(img)
    _card_header(d, img, category, accent, f"#{rank} of {config.PER_CATEGORY}")

    f_title = _font(config.FONT_BOLD, 52)
    f_org = _font(config.FONT_REG, 30)
    f_badge = _font(config.FONT_BOLD, 24)
    f_body = _font(config.FONT_REG, 30)
    f_meta = _font(config.FONT_REG, 24)

    y = PAD + 96
    for ln in _wrap(d, opp.program.split(" — ")[0], f_title, SIZE - 2 * PAD)[:3]:
        d.text((PAD, y), ln, font=f_title, fill=(255, 255, 255)); y += 60
    y += 6
    d.text((PAD, y), opp.organization, font=f_org, fill=(210, 210, 210)); y += 56

    # badges: country, funding, deadline
    bx = PAD
    fc = _flag_color(opp.country)
    _round(d, [bx, y, bx + 16, y + 32], 6, fc)
    ctry = (opp.country or "Global")
    d.text((bx + 24, y + 3), ctry, font=f_badge, fill=(230, 230, 230))
    nx = bx + 24 + d.textlength(ctry, font=f_badge) + 24
    if opp.is_funded:
        nx = _badge(d, nx, y - 2, "FULLY FUNDED", f_badge, (15, 40, 20), (150, 220, 150)) + 14
    dl = opp.deadline.isoformat() if opp.deadline else "Rolling"
    _badge(d, nx, y - 2, "Deadline: " + dl, f_badge, (20, 20, 20), accent)
    y += 70

    # short description
    desc = opp.description or opp.eligibility or opp.funding
    if desc:
        for ln in _wrap(d, desc, f_body, SIZE - 2 * PAD)[:3]:
            d.text((PAD, y), ln, font=f_body, fill=(235, 235, 235)); y += 42

    # QR (integer scale, no resampling)
    try:
        q = qr_image(opp.official_url, scale=6, border=2)
        qw, qh = q.size
        qx, qy = SIZE - PAD - qw, SIZE - PAD - qh - 36
        _round(d, [qx - 16, qy - 16, qx + qw + 16, qy + qh + 52], 18, (255, 255, 255))
        img.paste(q, (qx, qy))
        d.text((qx - 4, qy + qh + 8), "Scan to apply", font=f_meta, fill=(15, 15, 15))
    except Exception:
        pass

    d.text((PAD, SIZE - 76), f"@AurigaCareerLab  ·  {config.CATEGORIES.get(category, category)}",
           font=f_meta, fill=(220, 220, 220))

    out_dir = config.CARDS_DIR / category
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{rank}_{_slug(opp.program)}.png"
    img.save(out, "PNG")
    return str(out)


def slide_filenames(opps):
    """Deterministic ordered slide filenames for a set of picks (cover first)."""
    return ["0_cover.png"] + [f"{rank}_{_slug(o.program)}.png"
                              for rank, o in enumerate(opps, 1)]


def render_category_cards(category, opps):
    """Cover + one slide per opportunity. Returns ordered list of image paths.
    Clears any stale slides from a previous run first."""
    out_dir = config.CARDS_DIR / category
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        try:
            old.unlink()
        except Exception:
            pass
    paths = []
    cover = render_cover_card(category, opps)
    if cover:
        paths.append(cover)
    for rank, opp in enumerate(opps, 1):
        pth = render_opportunity_card(category, opp, rank)
        if pth:
            paths.append(pth)
    return paths
