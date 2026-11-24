---
name: insta-captions
description: Adds Instagram/TikTok/Shorts-style captions to a vertical podcast, talk-show or interview clip. The first seconds (the "hook" / "hoek") get big, bold, luxe cinematic captions placed in the free space NEXT to the speaker, with key words like money in a cinematic serif font and colour (green/gold). The rest of the clip gets clean, simple word-by-word captions in the middle of the frame with yellow emphasis words. Use this whenever the user says "Insta captions", or asks for captions, subtitles, ondertitels, "luxe captions", hook text or "captions in de stijl van ..." on a short clip, podcast cut, clipping video, interview or talking-head video, even if they do not name the skill. Also use it when they say how long the hook is ("de hoek is de eerste 5 seconden").
---

# Insta captions

Turn a raw clip into a finished captioned video: **luxe hook captions** for the opening seconds, **simple clean captions** for everything after. The look, timing and layout below were tuned step by step with a real user and then approved, so treat the defaults as *approved* and change only what the user asks to change.

## How to talk to the user
- Reply in the user's own language (so far Dutch) with **simple words and no jargon**; many users of this skill are creators without coding knowledge. If something is unclear, **ask** instead of guessing. Say plainly when something is a limit or a guess, and never claim you "watched" a video when you only inspected still frames.
- "De hoek" / "the hook" = the intro part. "Net iets langer in beeld" = a little longer on screen. Change **one thing at a time** and keep everything else identical; unrequested changes annoy users ("niet allemaal raar gaan veranderen").

## What you need from the user
1. The clip (a file, or a Google Drive link: `curl -L "https://drive.google.com/uc?export=download&id=FILE_ID"`).
2. **Where the hook ends** (seconds, or "tot de riser stopt"). If they don't know: propose the first camera cut or the first clear pause, and say that this is your proposal.
3. Caption language (default: the spoken language) and swear words (default: censor with asterisks like `f***ed`, so it stays readable but platforms don't flag it).

## Workflow
Scripts live in `scripts/` next to this file. Use a work folder in the scratchpad.

1. **Prepare**: `python3 scripts/prepare.py CLIP --work WORK` gives `probe.json` (the real picture's y-range, camera cuts) and `contact.jpg`. **Look at contact.jpg**: where does the speaker sit, which side is free (the hook side), in which shots do faces sit lower (two people / wide shot, listed as `wide` ranges)?
2. **Transcribe**: `python3 scripts/transcribe.py WORK/a.wav WORK/words.json` (needs `pip install faster-whisper`; installing may need the user's OK; the first run downloads a ~3 GB model, wait out a 429 rate limit or use `--model medium`). Show the transcript to the user and fix mistakes via `replace` in the config (e.g. "cop" → "cup") before rendering. Names, slang and swear words are often misheard.
3. **Config**: write `WORK/config.json` (fields documented at the top of `scripts/render_captions.py`): `hook_end`, `hook_side`, `key_words` (the 1–3 most important claim words for the hook; money like `$22 billion` is detected automatically), `emphasis` (yellow words after the hook), `replace`, `cuts`, `wide`.
4. **Plan**: `python3 scripts/render_captions.py plan config.json`. Check that the hook groups read naturally and the right words are `[KEY]`.
5. **Preview**: `... preview config.json WORK/prev T1 T2 ...` and **look at the images**: hook text must be in the free space and never over the face; nothing on the black bars; nothing cut off at the edge. Check several moments in the hook and several in the rest (including wide shots). Fix zone/side/wide ranges and repeat.
6. **Render**: `... render config.json`. Then pull 8–12 frames from the *final mp4* and look at them. Deliver with the file-send tool (users can't browse the sandbox) and keep the file under 30 MB (typical output is about 5 MB).
7. If the repository has a stop hook asking to commit new files, commit and push the mp4 to the working branch (no pull request unless asked).

## The look (defaults, already approved)
- **Hook**: only on the free side of the speaker, upper corner, inside the picture. Each screen has at most 3 words: row 1 two words side by side (the first more toward the middle, the second in the corner), row 2 one word below (a very long first word goes alone on row 1). A new group is a fresh screen; never stack more words. All white, Inter Black, extra bold (outline) and tight. Words follow the speech beat one by one with a ~0.16 s zoom/fade-in and a soft cross-fade between groups.
- **Key words** (money, the core claim): cinematic serif (Cinzel Black), **green** for money, **gold** for other key words, stacked big on two rows; "$22" is pulled into the very corner with "BILLION" tight underneath.
- **After the hook**: one caption at a time, centred, just below the middle of the picture (just under the face), Inter ExtraBold white, **max 2 long or 3 short words** per caption, each word pops in with a quick zoom, emphasis words yellow, on screen at least ~0.5 s where the speech allows.
- Everything stays inside the real picture and away from the platform buttons (right edge, bottom).

## Hard lessons (don't repeat)
- No zoom or reframe of the video, no rounded card or border, no overlay boxes. The user rejected all of these.
- Don't pile several lines of text on screen or scroll them up; it looked "mega slecht". One group at a time.
- Don't delay text far behind the voice to make it last longer; it feels unnatural and off-beat (at most ~0.25 s late in the hook, 0.2 s after).
- A 1 px outline is invisible, so "bolder" must be a clear step, but not so thick that letters merge ("GET" became unreadable).
- Speech at ~4 words per second means a 2–3 word caption can only average ~0.5 s on screen. That is arithmetic, not a bug; say so and offer bigger captions or a sliding window instead of silently breaking the word limit.
- Words spoken just before a camera cut flash by; the renderer shows them at the cut.

## Tuning cheat-sheet (constants in `render_captions.py`)
| User says | Change |
|---|---|
| hook text bigger / bolder | `R1, R2, KBIG, KSMALL`; `stroke=` in `wd()` (0.029 default; 0.034 starts merging letters) |
| letters closer / words closer | `tracking` and `gapk` in `wd()` |
| hook words longer on screen | `VIS` / `LAG` in `schedule_hook()` (trade-off: later = less on the beat) |
| smoother / snappier animation | `ANIM`, `XFADE`, `FOUT` in `schedule_hook()`; `anim` in `build_post()` |
| captions higher / lower | the `0.451` / `0.513` fractions in `build_post()` |
| fewer / more words per caption | the `3.0` weight limit and `weight()` in `build_post()` |
| key word look | colours `GREEN`, `GOLD`, `YELLOW`; `key_words` / `emphasis` in the config |

More detail and the reasoning behind each number: `references/style-guide.md`.
