#!/usr/bin/env python3
"""Word-level transcript with faster-whisper.

Usage:
    python3 transcribe.py AUDIO.wav OUT.json [--model large-v3] [--language en]

Needs:  pip install faster-whisper     (the user may need to approve this install)

Notes learned the hard way:
  * Audio is read from a 16 kHz mono WAV with the stdlib `wave` module and passed as a numpy
    array.  Passing a file path makes faster-whisper call PyAV, and new PyAV versions broke
    that call ("unexpected keyword argument 'metadata_errors'").
  * The first run downloads the model (~3 GB for large-v3) from huggingface.co.  On shared IPs
    that can answer "429 Too Many Requests".  This script waits and retries.  If it keeps
    failing, use --model medium (or small) instead.
  * The transcript is machine-made: names, slang and swear words are sometimes wrong.  Always
    show it to the user for a check before burning it into a video.

Output format (list of segments):
    [{"start":0.0,"end":2.4,"text":"...","words":[{"w":" This","s":0.0,"e":0.06}, ...]}, ...]
"""
import argparse, json, sys, time, wave


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('audio')
    ap.add_argument('out')
    ap.add_argument('--model', default='large-v3')
    ap.add_argument('--language', default=None, help='e.g. en, nl. Default: auto-detect')
    a = ap.parse_args()

    import numpy as np
    from faster_whisper import WhisperModel

    model = None
    for attempt in range(8):
        try:
            model = WhisperModel(a.model, device='cpu', compute_type='int8')
            break
        except Exception as e:  # noqa
            if '429' in str(e) or 'Too Many Requests' in str(e):
                print(f'huggingface rate limit, waiting 60 s (try {attempt + 1}/8)...', file=sys.stderr)
                time.sleep(60)
                continue
            raise
    if model is None:
        sys.exit('could not download the model; try --model medium')

    w = wave.open(a.audio)
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, info = model.transcribe(audio, word_timestamps=True, beam_size=5, language=a.language)
    print(f'language: {info.language} ({info.language_probability:.2f})')
    out = []
    for s in segs:
        print(f'[{s.start:6.2f}-{s.end:6.2f}] {s.text.strip()}')
        out.append(dict(start=s.start, end=s.end, text=s.text.strip(),
                        words=[dict(w=x.word, s=x.start, e=x.end) for x in s.words]))
    json.dump(out, open(a.out, 'w'), ensure_ascii=False, indent=1)
    print('saved', a.out)


if __name__ == '__main__':
    main()
