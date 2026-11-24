#!/usr/bin/env python3
"""insta-captions renderer: luxe hook captions + simple word-by-word captions for the rest.

Usage:
    python3 render_captions.py plan    config.json     # print the hook groups + caption chunks
    python3 render_captions.py preview config.json OUTDIR T1 T2 ...   # still frames with captions
    python3 render_captions.py render  config.json     # write the finished mp4

config.json (all times in seconds):
{
  "video":    "/path/clip.mp4",
  "words":    "/path/words.json",            # from transcribe.py
  "out":      "/path/clip_captions.mp4",
  "hook_end": 5.53,                          # where the hook ends (the "hoek"); usually a cut or pause
  "hook_side": "right",                      # side of the speaker that is free: "right" or "left"
  "key_words": ["presidential", "pardon"],   # hook words that get the cinematic font (gold).
                                             #   money ($22, billion...) is detected automatically (green)
  "emphasis":  ["pardon", "crypto"],         # words coloured yellow in the simple captions
  "replace":   {"cop": "cup"},               # fix transcript mistakes (lowercase word -> text)
  "cuts":      [5.53, 9.13],                 # camera cuts (from prepare.py probe.json)
  "wide":      [[5.53, 9.13]],               # optional: time ranges where faces sit LOWER in the frame
  "content":   [555, 1364],                  # optional: y-range of the real picture (from probe.json)
  "hook_layout": "fill",                     # "fill" (default): 3-4 words on screen at once, one common size per group,
                                             #         words appear as they are said (no word alone, no huge/tiny contrast)
                                             # "corner": 2+1 rows in the free corner (clip 1 look: big key words, 1-2 word groups)
                                             # "band": ONE row in a band along the top of the picture, for clips
                                             #         with no free side (close-ups, many people, wide shots)
  "hook_zone": [40, 1040, 567],              # optional [x0, x1, y_top] override of the hook area
  "hook_zones": [{"from": 0, "to": 2.7, "side": "left"|"right"|"center", "zone": [28, 520, 567]}, ...],
                                             # optional: a different free area per shot (time range, side, [x0,x1,y_top]);
                                             #   "band": [x0,x1,y_top] = a wide one-row strip used when a very long word
                                             #   would make a group tiny (put it where no head is, e.g. above the heads)
  "post_wide": {"zone": [80, 1000], "bottom": 0.47},
                                             # optional: in the wide shots put the simple captions in this x-range
                                             #   (e.g. in the gap BETWEEN two people). "bottom": the caption block ends at
                                             #   this height (e.g. just above a table); or "y": top of the block.
                                             #   "stack": true  (only on request!) puts words under each other if they do not fit side by side
  "post_y":    [0.451, 0.451]                # optional: caption top as a fraction of the picture height
                                             #   [normal shots, wide shots]. Default = just above the middle of the picture.
                                             #   Talking head: put it just UNDER the head (e.g. 0.55 when the chin is at ~0.5)
}
Everything else (sizes, timings) has defaults tuned with the user, see references/style-guide.md.
"""
import json, os, re, subprocess, sys, glob, math
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, '..', 'assets', 'fonts')
W, H, FPS = 1080, 1920, 30
CANVAS_VF = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"

WHITE = (255, 255, 255)
YELLOW = (255, 214, 0)     # emphasis in the simple captions
GREEN = (70, 222, 125)     # money in the hook
GOLD = (255, 205, 60)      # other key words in the hook


# ---------------------------------------------------------------- fonts / sprites
def _font_path(name):
    p = os.path.join(FONT_DIR, name)
    if os.path.exists(p):
        return p
    g = glob.glob('/usr/share/fonts/**/' + name, recursive=True)
    if g:
        return g[0]
    sys.exit(f'font missing: {name}')


BLK = _font_path('Inter-Black.otf')       # hook words
XB = _font_path('Inter-ExtraBold.otf')    # simple captions
CIN = _font_path('cinzel900.woff')        # cinematic / slightly medieval, only for the key words


@lru_cache(maxsize=None)
def font(path, size):
    return ImageFont.truetype(path, max(8, int(round(size))))


def text_width(txt, f, tracking):
    if tracking == 0:
        return f.getlength(txt)
    return sum(f.getlength(c) for c in txt) + tracking * (len(txt) - 1)


def make_sprite(txt, path, size, tracking=0, color=WHITE, stroke=0):
    f = font(path, size)
    asc, desc = f.getmetrics()
    pad = 30
    w = int(math.ceil(text_width(txt, f, tracking))) + 2 * stroke + pad * 2
    h = asc + desc + pad * 2 + 2 * stroke
    mask = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(mask)
    if tracking == 0:
        d.text((pad + stroke, pad + stroke), txt, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
    else:
        x = pad + stroke
        for c in txt:
            d.text((x, pad + stroke), c, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
            x += f.getlength(c) + tracking
    sh = mask.filter(ImageFilter.GaussianBlur(6 + size * 0.03)).point(lambda v: int(min(255, v * 1.15)))
    shadow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    shadow.putalpha(sh.point(lambda v: int(v * 0.7)))
    sh2 = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    sh2.paste(shadow, (0, 4))
    txtimg = Image.new('RGBA', (w, h), tuple(color) + (0,))
    txtimg.putalpha(mask)
    return Image.alpha_composite(sh2, txtimg), pad + stroke, asc + stroke, desc + stroke


class Item:
    pass


def ease_back(p):
    p = max(0.0, min(1.0, p))
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def _st(w, scale):
    return int(round(w.get('stroke', 0) * w['size'] * scale))


def _gap(w, scale):
    if 'gapk' in w:
        return w['size'] * scale * w['gapk']
    return max(w['size'] * scale * 0.26, 8)


def _fit(ln, zw):
    """Scale at which a row fits the zone. Returns (scale, widths, gaps, total); widths/total are those of the last
    measuring pass, exactly as the approved first version computed them (keep: it decides the exact x position)."""
    scale = 1.0
    for _ in range(3):
        ws = [text_width(w['text'], font(w['path'], w['size'] * scale), w.get('tracking', 0) * scale) + 2 * _st(w, scale) for w in ln]
        gaps = [_gap(w, scale) for w in ln[:-1]]
        total = sum(ws) + sum(gaps)
        if total > zw:
            scale *= zw / total
        else:
            break
    return scale, ws, gaps, total


def build_zone(lines, x0, x1, y_top, align, gs, ge, fade, anim, s0, gap, uniform=False):
    """Lay out rows of words inside a zone; shrink a row if it does not fit; stack rows downward.
    uniform=True: every row of the group gets the same scale (the smallest one), so no row looks much
    smaller/thinner than the others."""
    zw = x1 - x0
    fits = [_fit(ln, zw) for ln in lines]
    scales = [f[0] for f in fits]
    if uniform and scales:
        scales = [min(scales)] * len(scales)
    items, y = [], y_top
    for ln, fit, scale in zip(lines, fits, scales):
        if uniform:        # fresh measurement at the final scale
            ws = [text_width(w['text'], font(w['path'], w['size'] * scale), w.get('tracking', 0) * scale) + 2 * _st(w, scale) for w in ln]
            gaps = [_gap(w, scale) for w in ln[:-1]]
            total = sum(ws) + sum(gaps)
        else:
            _, ws, gaps, total = fit
        sprites = [make_sprite(w['text'], w['path'], w['size'] * scale, w.get('tracking', 0) * scale,
                               w.get('color', WHITE), _st(w, scale)) for w in ln]
        asc = max(s_[2] for s_ in sprites)
        desc = max(s_[3] for s_ in sprites)
        x = x0 if align == 'left' else (x1 - total if align == 'right' else x0 + (zw - total) / 2)
        base = y + asc
        for i, (sp, pad, a_, d_) in enumerate(sprites):
            it = Item()
            it.sprite = sp
            it.x = int(round(x - pad))
            it.y = int(round(base - a_ - pad))
            it.start = ln[i]['start']
            it.gs, it.ge, it.fade, it.anim, it.s0 = gs, ge, fade, anim, s0
            it.cx = it.x + sp.width / 2
            it.cy = it.y + sp.height / 2
            items.append(it)
            x += ws[i] + (gaps[i] if i < len(gaps) else 0)
        y = base + desc + gap
    return items


# ---------------------------------------------------------------- transcript helpers
CENSOR = {'fuck': 'f***', 'shit': 's**t', 'piss': 'p***', 'bitch': 'b****', 'cunt': 'c***', 'dick': 'd***',
          'bastard': 'b******', 'asshole': 'a*****'}
UNITS = {'billion', 'million', 'trillion', 'thousand', 'percent', 'dollars', 'bucks'}


def core(tok):
    return re.sub(r'[^a-z0-9$%]', '', tok.lower())


def letters(tok):
    return re.sub(r'[^a-z]', '', tok.lower())


def censor(tok):
    low = letters(tok)
    for stem, rep in CENSOR.items():
        if low.startswith(stem):
            m = re.search(stem, tok, flags=re.I)
            if m:
                return tok[:m.start()] + rep + tok[m.end():]
    return tok


def load_words(path, replace):
    data = json.load(open(path))
    words = []
    for seg in data:
        for w in seg['words']:
            t = w['w'].strip()
            if not t:
                continue
            # merge "U" + ".S." -> "U.S."
            if t.startswith('.') and words and not re.search(r'[.,?!]$', words[-1]['t']):
                words[-1]['t'] += t
                words[-1]['e'] = w['e']
                continue
            words.append(dict(t=t, s=w['s'], e=w['e']))
    # speech recognition sometimes gives two neighbouring words the same start time; spread them out
    for i in range(1, len(words) - 1):
        if words[i]['s'] >= words[i + 1]['s'] - 0.02 and words[i]['e'] >= words[i]['s']:
            words[i]['s'] = max(words[i - 1]['s'] + 0.1, words[i + 1]['s'] - 0.25)
    for w in words:
        key = letters(w['t'])
        if key in replace:
            tail = re.search(r'[.,?!]+$', w['t'])
            w['t'] = replace[key] + (tail.group(0) if tail else '')
    return words


def display(tok):
    return censor(tok).rstrip('.,?!;:') if not re.fullmatch(r'(?:[A-Za-z]\.)+', tok.rstrip(',?!')) else tok.rstrip(',?!')


# ---------------------------------------------------------------- the project
class Project:
    def __init__(self, cfg):
        self.cfg = cfg
        self.video = cfg['video']
        self.hook_end = float(cfg['hook_end'])
        self.side = cfg.get('hook_side', 'right')
        self.cuts = [float(c) for c in cfg.get('cuts', [])]
        self.wide = [tuple(r) for r in cfg.get('wide', [])]
        self.cap_cuts = []                                  # set below once post_y is known
        c = cfg.get('content')
        if not c:
            pj = os.path.join(os.path.dirname(os.path.abspath(cfg['words'])), 'probe.json')
            if os.path.exists(pj):
                b = json.load(open(pj))['content']
                c = [b['y0'], b['y1']]
            else:
                c = [0, H]
        self.cy0, self.cy1 = int(c[0]), int(c[1])
        self.ch = self.cy1 - self.cy0
        self.post_y = cfg.get('post_y', [0.451, 0.451])
        self.key_words = {letters(k) for k in cfg.get('key_words', [])}
        self.emphasis = {letters(k) for k in cfg.get('emphasis', [])}
        replace = {letters(k): v for k, v in cfg.get('replace', {}).items()}
        self.words = load_words(cfg['words'], replace)
        self.cap_cuts = [c for c in self.cuts
                         if (self.post_y[0] != self.post_y[1] or cfg.get('post_wide')) and self.is_wide(c - 0.01) != self.is_wide(c + 0.01)]
        self.duration = self._duration()
        self.items = []
        self.hookg = []
        self.build_hook()
        self.build_post()

    def _duration(self):
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', self.video],
                             capture_output=True, text=True).stdout.strip()
        return float(out)

    # ----- hook -----------------------------------------------------------
    def hook_tokens(self):
        toks = [w for w in self.words if w['s'] < self.hook_end - 0.05]
        out, prev_key = [], False
        for w in toks:
            c = core(w['t'])
            money = ('$' in w['t']) or bool(re.fullmatch(r'\$?\d[\d,.]*[kmb]?', c))
            unit = letters(w['t']) in UNITS and prev_key
            is_key = money or unit or letters(w['t']) in self.key_words
            color = GREEN if (money or unit) else GOLD
            st = max(w['s'] - 0.03, -0.03)
            for cc in self.cuts:                       # spoken just before a cut -> shown at the cut
                if 0 < cc - w['s'] < 0.3:
                    st = cc
            out.append(dict(text=display(w['t']).upper(), start=st,
                            key=is_key, color=color, n=len(letters(w['t'])) or len(c)))
            prev_key = is_key and (money or unit)
        return out

    def hook_groups(self, toks):
        """Non-key words in balanced groups of up to 3 (no lonely single words if it can be avoided, and
        never across a camera cut); key words (money, claims) in their own stacked group of 1-2 words."""
        def crosses(a, b):
            return any(a['start'] < c <= b['start'] for c in self.cuts)
        groups, i = [], 0
        while i < len(toks):
            if toks[i]['key']:
                run = [toks[i]]
                while (i + len(run) < len(toks) and toks[i + len(run)]['key'] and len(run) < 2
                       and not crosses(run[-1], toks[i + len(run)])):
                    run.append(toks[i + len(run)])
                groups.append(dict(key=True, toks=run))
                i += len(run)
            else:
                j = i
                while j < len(toks) and not toks[j]['key'] and not (j > i and crosses(toks[j - 1], toks[j])):
                    j += 1
                run = toks[i:j]
                n = -(-len(run) // 3)
                base, extra = divmod(len(run), n)
                k = 0
                for q in range(n):
                    size = base + (1 if q < extra else 0)
                    groups.append(dict(key=False, toks=run[k:k + size]))
                    k += size
                i = j
        # a lonely last word after a key word joins that key group (e.g. "REPLACING" + "THEM")
        if (len(groups) >= 2 and not groups[-1]['key'] and len(groups[-1]['toks']) == 1
                and groups[-2]['key'] and len(groups[-2]['toks']) == 1
                and not crosses(groups[-2]['toks'][0], groups[-1]['toks'][0])):
            t = groups[-1]['toks'][0]
            t['key'], t['color'] = True, groups[-2]['toks'][0]['color']
            groups[-2]['toks'].append(t)
            groups.pop()
        return groups

    def fill_groups(self, toks):
        """3-4 consecutive words per screen (never one word alone), never across a camera cut."""
        def crosses(a, b):
            return any(a['start'] < c <= b['start'] for c in self.cuts)
        segs, cur = [], []
        for t in toks:
            if cur and crosses(cur[-1], t):
                segs.append(cur)
                cur = []
            cur.append(t)
        if cur:
            segs.append(cur)
        groups = []
        for seg in segs:
            n = max(1, -(-len(seg) // 4))
            base, extra = divmod(len(seg), n)
            k = 0
            for q in range(n):
                size = base + (1 if q < extra else 0)
                groups.append(seg[k:k + size])
                k += size
        return groups

    def fill_rows(self, ws, zw):
        """Pack words into rows (greedy). The size is chosen so that the longest single word still fits."""
        def width(w, sc):
            return (text_width(w['text'], font(w['path'], w['size'] * sc), w.get('tracking', 0) * sc)
                    + 2 * int(round(w.get('stroke', 0) * w['size'] * sc)))
        s0 = min(1.0, min(zw / width(w, 1.0) for w in ws))
        rows, cur, cw = [], [], 0.0
        for w in ws:
            ww, gp = width(w, s0), w['size'] * s0 * w['gapk']
            if cur and cw + gp + ww > zw:
                rows.append(cur)
                cur, cw = [w], ww
            else:
                cw += (gp if cur else 0) + ww
                cur.append(w)
        rows.append(cur)
        return rows, s0

    def wd(self, tok, size, path=BLK, color=None):
        return dict(text=tok['text'], path=path, size=size, start=tok['start'], color=color or WHITE,
                    stroke=0.029, tracking=0.022 * size, gapk=0.10)

    def build_hook(self):
        R1, R2, KBIG, KSMALL = 120, 190, 260, 200
        cy0 = self.cy0
        right = self.side == 'right'
        zone = self.cfg.get('hook_zone')            # optional [x0, x1, y_top]
        z0 = tuple(zone) if zone else ((560, 1052, cy0 + 12) if right else (W - 1052, W - 560, cy0 + 12))
        zm = (548, 1083, cy0 - 34) if right else (max(W - 1083, 4), W - 548, cy0 - 34)  # money: tight in the corner
        align = 'right' if right else 'left'
        layout = self.cfg.get('hook_layout', 'fill')
        band = layout == 'band'
        BAND, BANDK = 105, 125                      # natural size of a band row (shrunk to fit the width)
        zb = tuple(zone) if zone else (40, 1040, cy0 + 12)
        toks = self.hook_tokens()
        if layout == 'fill':
            self.build_hook_fill(toks, z0, align)
            return
        groups = self.hook_groups(toks)
        self.hook_plan = []
        for g in groups:
            t = g['toks']
            gap, zn, al = -8, z0, align
            ze = next((z for z in self.cfg.get('hook_zones', []) if z['from'] <= t[0]['start'] + 0.03 < z['to']), None)
            if ze:                                    # a different free area in this shot
                zn, al = tuple(ze['zone']), ze.get('side', 'right')      # 'left', 'right' or 'center'
            if g['key']:
                if len(t) == 1:
                    rows = [[self.wd(t[0], KBIG, CIN, t[0]['color'])]]
                else:
                    a, b = t
                    sa, sb = (KBIG, KSMALL) if a['n'] <= b['n'] else (KSMALL, KBIG)
                    rows = [[self.wd(a, sa, CIN, a['color'])], [self.wd(b, sb, CIN, b['color'])]]
                if any('$' in x['text'] for x in t):
                    zn, gap = (tuple(ze.get('money_zone', ze['zone'])) if ze else zm), -104   # "$" has a long descender: pull row 2 up tight
            else:
                a = t[0]
                long_first = a['n'] >= 9
                if len(t) == 3:
                    rows = ([[self.wd(a, R1)], [self.wd(t[1], R2), self.wd(t[2], R2)]] if long_first
                            else [[self.wd(a, R1), self.wd(t[1], R1)], [self.wd(t[2], R2)]])
                elif len(t) == 2:
                    rows = ([[self.wd(a, R1)], [self.wd(t[1], R2)]] if long_first
                            else [[self.wd(a, R1), self.wd(t[1], R1)]])
                else:
                    rows = [[self.wd(a, R1)]]
            if band:                                  # one row, all words of the group side by side
                rows = [[self.wd(x, BANDK if x['key'] else BAND, CIN if x['key'] else BLK, x['color'] if x['key'] else None)
                         for x in t]]
                zn, gap = (tuple(ze['zone']) if ze else zb), -8
            new = build_zone(rows, zn[0], zn[1], zn[2], al, 0, 0, fade=0.08, anim=0.18, s0=0.5, gap=gap)
            self.hookg.append(new)
            self.items += new
            self.hook_plan.append(' '.join(x['text'] for x in t) + ('   [KEY]' if g['key'] else ''))
        self.schedule_hook()

    def build_hook_fill(self, toks, z0, align):
        """Hook layout "fill": 3-4 words on screen at once, one common size per group, words appear as they are said."""
        self.hook_plan = []
        for g in self.fill_groups(toks):
            ze = next((z for z in self.cfg.get('hook_zones', []) if z['from'] <= g[0]['start'] + 0.03 < z['to']), None)
            zn, al = z0, align
            if ze:
                zn, al = tuple(ze['zone']), ze.get('side', 'right')
            zw = zn[1] - zn[0]
            ns = 0.2 * zw                                   # natural size follows the width of the free area
            ws = []
            for t in g:
                if t['key']:
                    d = self.wd(t, ns * 1.08, CIN, t['color'])
                else:
                    d = self.wd(t, ns)
                d['stroke'], d['tracking'] = 0.022, 0.02 * d['size']      # a bit less bold than the corner layout
                ws.append(d)
            rows, s0 = self.fill_rows(ws, zw)
            if ze and ze.get('band') and s0 < 0.6:
                # a very long word would make the whole group tiny in this narrow area: use one row in a wide band
                # (above the heads) instead, at the same natural size
                zn, al, rows = tuple(ze['band']), 'center', [ws]
            new = build_zone(rows, zn[0], zn[1], zn[2], al, 0, 0, fade=0.08, anim=0.18, s0=0.5, gap=-4, uniform=True)
            self.hookg.append(new)
            self.items += new
            self.hook_plan.append(' '.join(x['text'] for x in g))
        self.schedule_hook()

    def schedule_hook(self):
        VIS, LAG, ANIM, XFADE, FOUT = 0.50, 0.25, 0.16, 0.06, 0.10
        spk = [(min(i.start for i in g), max(i.start for i in g)) for g in self.hookg]
        gs = []
        for k, (f, l) in enumerate(spk):
            if k == 0:
                g0 = f
            else:
                need = max(spk[k - 1][1], gs[k - 1]) + VIS
                g0 = min(max(f, need), f + LAG)
            gs.append(g0)
        for k, g in enumerate(self.hookg):
            a = gs[k]
            nxt = gs[k + 1] if k + 1 < len(self.hookg) else self.hook_end - 0.02 - XFADE
            b = nxt + XFADE
            prev = None
            for it in g:
                it.gs, it.ge, it.anim, it.fade = a, b, ANIM, FOUT
                it.start = max(it.start, a if prev is None else prev + 0.07)   # word by word, never two at once
                prev = it.start

    # ----- everything after the hook -----------------------------------------
    def shot_of(self, t):
        return sum(1 for c in self.cuts if c <= t + 0.001)

    def next_cut(self, t):
        c = [c for c in self.cuts if c > t + 0.001]
        return min(c) if c else 99

    def cap_shot_of(self, t):
        return sum(1 for c in self.cap_cuts if c <= t + 0.001)

    def cap_next_cut(self, t):
        c = [c for c in self.cap_cuts if c > t + 0.001]
        return min(c) if c else 99

    def is_wide(self, t):
        return any(a <= t < b for a, b in self.wide)

    def build_post(self):
        post = [dict(w) for w in self.words if w['s'] >= self.hook_end - 0.05]
        # words that start just before a camera cut would flash by; show them at the cut
        for w in post:
            for c in self.cap_cuts:
                if 0 < c - w['s'] < 0.35:
                    w['e'] = max(w['e'], c + 0.12)
                    w['s'] = c

        def weight(w):
            return 1.5 if len(re.sub(r'[^A-Za-z0-9$]', '', w['t'])) >= 6 else 1.0

        def crosses(a, b):
            return any(a['s'] < c <= b['s'] + 0.001 for c in self.cap_cuts)

        chunks, cur, tot = [], [], 0.0            # max 2 long words or 3 short words per caption
        for w in post:
            x = weight(w)
            if cur and (crosses(cur[-1], w) or tot + x > 3.0):
                chunks.append(cur)
                cur, tot = [], 0.0
            cur.append(w)
            tot += x
            if re.search(r'[.,?!]$', w['t']):
                chunks.append(cur)
                cur, tot = [], 0.0
        if cur:
            chunks.append(cur)
        self.chunks = chunks

        MIN_DWELL, MAX_LAG = 0.5, 0.2             # borrow a little time so short captions stay readable
        tl, pg, ps = [], None, None
        for ch in chunks:
            sh = self.cap_shot_of(ch[0]['s'])
            sp = ch[0]['s'] - 0.07
            gs = sp if pg is None or sh != ps else min(max(sp, pg + MIN_DWELL), sp + MAX_LAG)
            nc = self.cap_next_cut(ch[0]['s'])
            if gs > nc - 0.4:
                gs = max(sp, nc - 0.4)
            tl.append((gs, sh, sp))
            pg, ps = gs, sh
        self.dwell = []
        for k, ch in enumerate(chunks):
            gs, sh, sp = tl[k]
            nxt = tl[k + 1][0] if k + 1 < len(chunks) and tl[k + 1][1] == sh else 99
            ge = min(nxt, self.cap_next_cut(ch[0]['s']), ch[-1]['e'] + (gs - sp) + 0.9)
            self.dwell.append(ge - gs)
            lag = gs - sp
            specs = []
            for w in ch:
                lc = letters(w['t'])
                is_emph = lc in self.emphasis or '$' in w['t'] or re.fullmatch(r'\d[\d,.]*', core(w['t'])) is not None
                specs.append(dict(text=display(w['t']), path=XB, size=74, start=max(w['s'] + lag - 0.06, gs),
                                  color=YELLOW if is_emph else WHITE))
            pw = self.cfg.get('post_wide')
            rows, x0, x1, y_bottom = [specs], 80, 1000, None
            if pw and self.is_wide(ch[0]['s']):          # wide shot: keep captions in the free gap between the people
                x0, x1 = pw['zone']
                if pw.get('stack') and len(specs) > 1:
                    def row_w(r):
                        return sum(font(XB, 74).getlength(sp['text']) for sp in r) + 0.26 * 74 * (len(r) - 1)
                    zw = x1 - x0
                    if row_w(specs) > zw:                 # does not fit side by side: use two rows, or one word per row
                        splits = [([specs[:k], specs[k:]]) for k in range(1, len(specs))]
                        best = min(splits, key=lambda r: max(row_w(r[0]), row_w(r[1])))
                        rows = best if max(row_w(best[0]), row_w(best[1])) <= zw * 1.1 else [[sp] for sp in specs]
                if 'bottom' in pw:
                    y_bottom = self.cy0 + int(self.ch * pw['bottom'])
                    y = 0
                else:
                    y = self.cy0 + int(self.ch * pw['y'])
            else:
                y = self.cy0 + int(self.ch * (self.post_y[1] if self.is_wide(ch[0]['s']) else self.post_y[0]))
            if y_bottom is not None:                     # measure the block, then put its bottom on y_bottom
                probe = build_zone(rows, x0, x1, 0, 'center', 0, 1, fade=0.1, anim=0.1, s0=0.6, gap=0)
                y = y_bottom - max(it.y + it.sprite.height - 30 for it in probe)
            self.items += build_zone(rows, x0, x1, y, 'center', gs, ge, fade=0.10, anim=0.10, s0=0.6, gap=0)

    # ----- drawing ----------------------------------------------------------
    @staticmethod
    def item_state(it, t):
        if t < it.gs or t > it.ge:
            return None
        p = (t - it.start) / it.anim
        if p < 0:
            return None
        p = min(p, 1.0)
        ga = max(0.0, min(1.0, (it.ge - t) / it.fade)) if it.fade else 1.0
        return round(p, 3), round(ga, 3)

    def frame_state(self, t):
        key, draws = [], []
        for it in self.items:
            st = self.item_state(it, t)
            if st is not None:
                key.append((id(it), st))
                draws.append((it, st))
        return tuple(key), draws

    def layer(self, t, draws=None):
        if draws is None:
            _, draws = self.frame_state(t)
        layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        for it, (p, ga) in draws:
            sc = it.s0 + (1 - it.s0) * ease_back(p)
            alpha = min(1.0, p * 3.0) * ga
            spr = it.sprite
            if abs(sc - 1.0) > 0.004:
                spr = spr.resize((max(1, int(spr.width * sc)), max(1, int(spr.height * sc))), Image.LANCZOS)
            ox, oy = int(it.cx - spr.width / 2), int(it.cy - spr.height / 2)
            if alpha < 0.999:
                a = spr.getchannel('A').point(lambda v, al=alpha: int(v * al))
                spr = spr.copy()
                spr.putalpha(a)
            if ox >= 0 and oy >= 0 and ox + spr.width <= W and oy + spr.height <= H:
                layer.alpha_composite(spr, (ox, oy))
            else:
                layer.paste(spr, (ox, oy), spr)
        return layer


# ---------------------------------------------------------------- commands
def cmd_plan(P):
    print(f'content box y {P.cy0}-{P.cy1}   hook ends {P.hook_end}s   side: {P.side}')
    print('\nHOOK groups (<=3 words per screen; [KEY] = cinematic font):')
    for g, line in zip(P.hookg, P.hook_plan):
        print(f'  {g[0].gs:5.2f}-{g[0].ge:5.2f}  {line}')
    print(f'\nSIMPLE captions: {len(P.chunks)} captions, avg time on screen {sum(P.dwell) / len(P.dwell):.2f}s')
    for ch, d in zip(P.chunks, P.dwell):
        print(f'  {ch[0]["s"]:6.2f}  {d:4.2f}s  {" ".join(display(w["t"]) for w in ch)}')


def base_canvas(P, t, path):
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{t:.3f}', '-i', P.video, '-frames:v', '1',
                    '-vf', CANVAS_VF, path], check=True)
    return Image.open(path).convert('RGBA')


def cmd_preview(P, outdir, times):
    os.makedirs(outdir, exist_ok=True)
    for t in times:
        bf = os.path.join(outdir, f'_base_{t}.png')
        im = base_canvas(P, t, bf)
        os.remove(bf)
        im.alpha_composite(P.layer(t))
        im.crop((0, max(P.cy0 - 10, 0), W, min(P.cy1 + 10, H))).convert('RGB').save(
            os.path.join(outdir, f'p_{t}.jpg'), quality=88)
    print('previews in', outdir)


def cmd_render(P):
    out = P.cfg['out']
    fc = f"[0:v]fps={FPS},{CANVAS_VF}[v];[v][1:v]overlay=0:0:format=auto,format=yuv420p[out]"
    cmd = ['ffmpeg', '-y', '-v', 'error', '-i', P.video, '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}',
           '-r', str(FPS), '-i', '-', '-filter_complex', fc, '-map', '[out]', '-map', '0:a?', '-t', f'{P.duration:.3f}',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-maxrate', '9M', '-bufsize', '18M',
           '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    last_key, last_bytes = None, None
    for i in range(int(P.duration * FPS)):
        t = i / FPS
        key, draws = P.frame_state(t)
        if key != last_key:            # text layers are cached while nothing changes
            last_bytes = P.layer(t, draws).tobytes()
            last_key = key
        p.stdin.write(last_bytes)
    p.stdin.close()
    p.wait()
    print('written', out, f'{os.path.getsize(out) / 1e6:.1f} MB')


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, cfg = sys.argv[1], json.load(open(sys.argv[2]))
    P = Project(cfg)
    if cmd == 'plan':
        cmd_plan(P)
    elif cmd == 'preview':
        cmd_preview(P, sys.argv[3], [float(x) for x in sys.argv[4:]])
    elif cmd == 'render':
        cmd_render(P)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
