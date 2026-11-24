#!/usr/bin/env python3
"""Step 1 of insta-captions: look at a clip before captioning it.

Usage:
    python3 prepare.py CLIP.mp4 --work WORKDIR [--transcribe] [--model large-v3]

Writes into WORKDIR:
    probe.json    duration, fps, size, content box (where the real picture sits inside the
                  1080x1920 canvas), camera cuts
    contact.jpg   a contact sheet of ~12 frames (cropped to the real picture) so you can SEE
                  where the speaker sits and where the free space is
    a.wav         16 kHz mono audio (input for transcription)
    words.json    word-level transcript (only with --transcribe)

Why a content box?  Podcast clips are often a 4:3 or 16:9 picture sitting in the middle of a
black 9:16 canvas.  Captions must live INSIDE the picture (not on the black bars), so the
renderer needs to know where the picture is.
"""
import argparse, json, os, re, subprocess, sys
from PIL import Image, ImageDraw

W, H = 1080, 1920
CANVAS_VF = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def probe(path):
    out = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
               'stream=width,height,r_frame_rate:format=duration', '-of', 'json', path]).stdout
    j = json.loads(out)
    st = j['streams'][0]
    num, den = st['r_frame_rate'].split('/')
    return dict(width=st['width'], height=st['height'], fps=float(num) / float(den),
                duration=float(j['format']['duration']))


def grab(path, t, out, vf=CANVAS_VF):
    run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{t:.3f}', '-i', path, '-frames:v', '1', '-vf', vf, out])


def content_box(path, duration, work):
    """Find the rows/columns that are not black, over several frames."""
    y0s, y1s, x0s, x1s = [], [], [], []
    for k in (0.2, 0.4, 0.6, 0.8):
        f = os.path.join(work, f'_box{k}.png')
        grab(path, duration * k, f)
        g = Image.open(f).convert('L').point(lambda v: 255 if v > 22 else 0)
        bb = g.getbbox()
        if bb:
            x0s.append(bb[0]); y0s.append(bb[1]); x1s.append(bb[2]); y1s.append(bb[3])
        os.remove(f)
    if not y0s:
        return dict(x0=0, y0=0, x1=W, y1=H)
    return dict(x0=min(x0s), y0=min(y0s), x1=max(x1s), y1=max(y1s))


def find_cuts(path, box, threshold=0.25):
    ch = box['y1'] - box['y0']
    vf = f"{CANVAS_VF},crop={W}:{ch}:0:{box['y0']},select='gt(scene,{threshold})',showinfo"
    r = subprocess.run(['ffmpeg', '-v', 'info', '-i', path, '-vf', vf, '-f', 'null', '-'],
                       capture_output=True, text=True)
    return [round(float(x), 3) for x in re.findall(r'pts_time:([0-9.]+)', r.stderr)]


def contact_sheet(path, duration, box, work, n=12):
    ch = box['y1'] - box['y0']
    tw = 360
    th = int(ch * tw / W)
    cols = 4
    rows = (n + cols - 1) // cols
    sheet = Image.new('RGB', (tw * cols, th * rows))
    for i in range(n):
        t = duration * (i + 0.5) / n
        f = os.path.join(work, f'_c{i}.png')
        grab(path, t, f, vf=f"{CANVAS_VF},crop={W}:{ch}:0:{box['y0']},scale={tw}:{th}")
        im = Image.open(f).convert('RGB')
        ImageDraw.Draw(im).text((6, 6), f'{t:.1f}s', fill=(255, 255, 0))
        sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
        os.remove(f)
    sheet.save(os.path.join(work, 'contact.jpg'), quality=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('clip')
    ap.add_argument('--work', required=True)
    ap.add_argument('--transcribe', action='store_true')
    ap.add_argument('--model', default='large-v3')
    ap.add_argument('--scene', type=float, default=0.25, help='camera-cut sensitivity (lower = more cuts)')
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)

    info = probe(a.clip)
    box = content_box(a.clip, info['duration'], a.work)
    cuts = find_cuts(a.clip, box, a.scene)
    contact_sheet(a.clip, info['duration'], box, a.work)
    wav = os.path.join(a.work, 'a.wav')
    run(['ffmpeg', '-y', '-v', 'error', '-i', a.clip, '-vn', '-ac', '1', '-ar', '16000', wav])
    out = dict(info, content=box, cuts=cuts)
    json.dump(out, open(os.path.join(a.work, 'probe.json'), 'w'), indent=1)
    print(json.dumps(out, indent=1))
    print('contact sheet:', os.path.join(a.work, 'contact.jpg'))

    if a.transcribe:
        here = os.path.dirname(os.path.abspath(__file__))
        subprocess.run([sys.executable, os.path.join(here, 'transcribe.py'), wav,
                        os.path.join(a.work, 'words.json'), '--model', a.model], check=True)


if __name__ == '__main__':
    main()
