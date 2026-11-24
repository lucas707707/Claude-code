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
  "content":   [555, 1364]                   # optional: y-range of the real picture (from probe.json)
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


def build_zone(lines, x0, x1, y_top, align, gs, ge, fade, anim, s0, gap):
    """Lay out rows of words inside a zone; shrink a row if it does not fit; stack rows downward."""
    zw = x1 - x0
    items, y = [], y_top
    for ln in lines:
        scale = 1.0
        for _ in range(3):
            ws = [text_width(w['text'], font(w['path'], w['size'] * scale), w.get('tracking', 0) * scale) + 2 * _st(w, scale) for w in ln]
            gaps = [_gap(w, scale) for w in ln[:-1]]
            total = sum(ws) + sum(gaps)
            if total > zw:
                scale *= zw / total
            else:
                break
        sprites = [make_sprite(w['text'], w['path'], w['size'] * scale, w.get('tracking', 0) * scale,
                               w.get('color', WHITE), _st(w, scale)) for w in ln]
        asc = max(s[2] for s in sprites)
        desc = max(s[3] for s in sprites)
        x = x0 if align == 'left' else (x1 - total if align == 'right' else x0 + (zw - total) / 2)
        base = y + asc
        for i, (sp, pad, a, d) in enumerate(sprites):
            it = Item()
            it.sprite = sp
            it.x = int(round(x - pad))
            it.y = int(round(base - a - pad))
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
        self.key_words = {letters(k) for k in cfg.get('key_words', [])}
        self.emphasis = {letters(k) for k in cfg.get('emphasis', [])}
        replace = {letters(k): v for k, v in cfg.get('replace', {}).items()}
        self.words = load_words(cfg['words'], replace)
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
            out.append(dict(text=display(w['t']).upper(), start=max(w['s'] - 0.03, -0.03),
                            key=is_key, color=color, n=len(letters(w['t'])) or len(c)))
            prev_key = is_key and (money or unit)
        return out

    def hook_groups(self, toks):
        """Non-key words in groups of up to 3; key words (money, claims) in their own stacked group."""
        groups, i = [], 0
        while i < len(toks):
            if toks[i]['key']:
                run = [toks[i]]
                while i + len(run) < len(toks) and toks[i + len(run)]['key'] and len(run) < 2:
                    run.append(toks[i + len(run)])
                groups.append(dict(key=True, toks=run))
                i += len(run)
            else:
                run = []
                while i + len(run) < len(toks) and not toks[i + len(run)]['key'] and len(run) < 3:
                    run.append(toks[i + len(run)])
                groups.append(dict(key=False, toks=run))
                i += len(run)
        return groups

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
        toks = self.hook_tokens()
        groups = self.hook_groups(toks)
        self.hook_plan = []
        for g in groups:
            t = g['toks']
            gap, zn = -8, z0
            if g['key']:
                if len(t) == 1:
                    rows = [[self.wd(t[0], KBIG, CIN, t[0]['color'])]]
                else:
                    a, b = t
                    sa, sb = (KBIG, KSMALL) if a['n'] <= b['n'] else (KSMALL, KBIG)
                    rows = [[self.wd(a, sa, CIN, a['color'])], [self.wd(b, sb, CIN, b['color'])]]
                if any('$' in x['text'] for x in t):
                    zn, gap = zm, -104        # the "$" has a long descender: pull row 2 up tight
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
            new = build_zone(rows, zn[0], zn[1], zn[2], align, 0, 0, fade=0.08, anim=0.18, s0=0.5, gap=gap)
            self.hookg.append(new)
            self.items += new
            self.hook_plan.append(' '.join(x['text'] for x in t) + ('   [KEY]' if g['key'] else ''))
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

    def is_wide(self, t):
        return any(a <= t < b for a, b in self.wide)

    def build_post(self):
        post = [dict(w) for w in self.words if w['s'] >= self.hook_end - 0.05]
        # words that start just before a camera cut would flash by; show them at the cut
        for w in post:
            for c in self.cuts:
                if 0 < c - w['s'] < 0.35:
                    w['e'] = max(w['e'], c + 0.12)
                    w['s'] = c

        def weight(w):
            return 1.5 if len(re.sub(r'[^A-Za-z0-9$]', '', w['t'])) >= 6 else 1.0

        def crosses(a, b):
            return any(a['s'] < c <= b['s'] + 0.001 for c in self.cuts)

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
            sh = self.shot_of(ch[0]['s'])
            sp = ch[0]['s'] - 0.07
            gs = sp if pg is None or sh != ps else min(max(sp, pg + MIN_DWELL), sp + MAX_LAG)
            nc = self.next_cut(ch[0]['s'])
            if gs > nc - 0.4:
                gs = max(sp, nc - 0.4)
            tl.append((gs, sh, sp))
            pg, ps = gs, sh
        self.dwell = []
        for k, ch in enumerate(chunks):
            gs, sh, sp = tl[k]
            nxt = tl[k + 1][0] if k + 1 < len(chunks) and tl[k + 1][1] == sh else 99
            ge = min(nxt, self.next_cut(ch[0]['s']), ch[-1]['e'] + (gs - sp) + 0.9)
            self.dwell.append(ge - gs)
            lag = gs - sp
            specs = []
            for w in ch:
                lc = letters(w['t'])
                is_emph = lc in self.emphasis or '$' in w['t'] or re.fullmatch(r'\d[\d,.]*', core(w['t'])) is not None
                specs.append(dict(text=display(w['t']), path=XB, size=74, start=max(w['s'] + lag - 0.06, gs),
                                  color=YELLOW if is_emph else WHITE))
            y = self.cy0 + int(self.ch * (0.513 if self.is_wide(ch[0]['s']) else 0.451))
            self.items += build_zone([specs], 80, 1000, y, 'center', gs, ge, fade=0.10, anim=0.10, s0=0.6, gap=0)

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
