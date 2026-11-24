# Insta captions — style guide and reasoning

Everything here came out of an iterative session with the user on a 37 s podcast clip
(a man in a chair, a second person on a couch, 4:3 picture inside a black 9:16 canvas).
The numbers are what the user finally approved ("dit is echt perfect").

## Geometry
- Canvas is 1080×1920. The real picture may be smaller (here y 555–1365, 4:3): captions must sit
  **inside** it, never on the black bars. `prepare.py` measures this (`content`).
- Hook zone (right side): x 560–1052, top = picture top + 12. Money group: x 548–1083, top = picture top − 34
  (the serif font has a tall ascent, so the glyphs still land ~10 px inside the picture).
  Left side is the mirror image.
- Simple captions: centre x, top at 45.1 % of the picture height (just under the face, about half-way);
  in wide/two-person shots 51.3 % because faces hang lower.
- Right-edge and bottom UI of TikTok/Reels: keep important text off the very bottom; the hook is in the upper
  part of the picture so it clears the buttons.

## Hook
- Grouping: consecutive non-key words in groups of up to 3 (row 1: 2 words, row 2: 1 word; a first word with ≥ 9
  letters sits alone on row 1). Key words (money, `key_words`) form their own group of 1–2 rows.
- Sizes (natural, shrunk to fit the zone width): row 1 = 120, row 2 = 190, key words 260 (shorter word) and 200 (longer).
- Fonts: Inter Black for normal words; Cinzel Black (cinematic, slightly medieval, still very readable) for key words only.
- Colours: white; money green (70,222,125); other key words gold (255,205,60).
- Look: outline stroke 0.029 × size (bolder), tracking +0.022 × size, word gap 0.10 × size (about the stroke thickness),
  soft black shadow. Tried and rejected: stroke 0.034 (letters merge), 1 px stroke (no visible change).
- Timing (`schedule_hook`): each word appears on its spoken time − 0.03 s, at least 0.07 s after the previous word; a
  group may start up to 0.25 s late so its last word stays ≥ ~0.5 s; zoom/fade-in 0.16 s (scale 0.5 → 1 with a small
  overshoot); old group fades out over 0.10 s while the new one zooms in (cross-fade 0.06 s).
  Earlier versions with up to 0.35–0.45 s lag and simultaneous word pops felt off-beat/ugly.

## After the hook
- Chunking: punctuation ends a caption; long word (≥ 6 letters) weighs 1.5, short 1.0, max total 3.0 →
  max 2 long or 3 short words. Camera cuts also end a caption; words starting < 0.35 s before a cut are shown at the cut.
- Font: Inter ExtraBold 74 px, white, soft shadow. Emphasis words (and numbers) yellow (255,214,0).
- Animation: word by word, each with a 0.10 s zoom (0.6 → 1, small overshoot) + fade; fade-out 0.10 s.
- Dwell: a caption may start up to 0.2 s late and is kept ≥ 0.5 s where possible. Average is limited by speech speed.

## Rejected experiments (and why)
- Rounded video card with border / video punched in or reframed: user did not want any change to the picture.
- Three captions stacked and scrolling up, or alternating lines, dimmed older lines: cluttered, hard to read.
- Playfair italic serif for key words: replaced by Cinzel (more cinematic / medieval, same readability).
- Serif italic + bold sans mix everywhere: user wanted ONE simple font after the hook.

## Worked examples (config.json)
**Clip 1** – one speaker in a chair, free space on his right, hook 0–5.53 s:
```json
{"hook_end": 5.5333, "hook_side": "right", "key_words": ["presidential", "pardon"],
 "cuts": [5.533, 9.133, 24.617, 27.767, 35.75], "wide": [[5.533, 9.133], [24.617, 27.767], [35.75, 99]]}
```
**Clip 2** – looped 15 s clip; close-up of a man in a white sweater, then a wide shot of two men at a table with a
crowd behind them. Only the two men count; the crowd may be covered. Hook 0–5.24 s:
```json
{"hook_end": 5.24, "hook_side": "left",
 "hook_zones": [{"from": 0, "to": 2.733, "side": "left", "zone": [28, 540, 567]},
                {"from": 2.733, "to": 99, "side": "center", "zone": [370, 785, 615]}],
 "key_words": ["amazing", "replace", "replaceable"],
 "cuts": [2.733, 9.867, 13.333, 15.2], "wide": [[2.733, 9.867]],
 "post_y": [0.55, 0.55], "post_wide": {"zone": [385, 765], "y": 0.12},
 "replace": {}, "emphasis": ["amazing", "replace", "value", "40", "busting"]}
```
Notes: when `post_y` has equal values the captions are not cut at camera cuts (their position does not change),
which avoids one-word flashes. Group builder splits non-key words evenly (no lonely words), never across a cut,
and joins a lonely last word to the key group before it. Neighbouring words with identical timestamps are spread.
