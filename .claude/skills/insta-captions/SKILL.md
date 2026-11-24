---
name: insta-captions
description: Adds Instagram/TikTok/Shorts-style captions to a vertical podcast, talk-show or interview clip. The first seconds (the "hook" / "hoek") get big, bold, luxe cinematic captions placed in the free space NEXT to the speaker, with key words like money in a cinematic serif font and colour (green/gold). The rest of the clip gets clean, simple word-by-word captions in the middle of the frame with yellow emphasis words. Use this whenever the user says "Insta captions", or asks for captions, subtitles, ondertitels, "luxe captions", hook text or "captions in de stijl van ..." on a short clip, podcast cut, clipping video, interview or talking-head video, even if they do not name the skill. Also use it when they say how long the hook is ("de hoek is de eerste 5 seconden").
---

# Insta captions

Turn a raw clip into a finished captioned video: **luxe hook captions** for the opening seconds, **simple clean captions** for everything after. The look, timing and layout below were tuned step by step with a real user and then approved, so treat the defaults as *approved* and change only what the user asks to change.

## How to talk to the user
- Reply in the user's own language (so far Dutch) with **simple words and no jargon**; many users of this skill are creators without coding knowledge. If something is unclear, **ask** instead of guessing. Say plainly when something is a limit or a guess, and never claim you "watched" a video when you only inspected still frames.
- "De hoek" / "the hook" = the intro part. "Net iets langer in beeld" = a little longer on screen. Change **one thing at a time** and keep everything else identical; unrequested changes annoy users ("niet allemaal raar gaan veranderen").

## Step 0: ask the user a few questions first
The skill does not have to be fully automatic; a few short questions beat a wrong guess. Ask them **together, in simple Dutch** (use the AskUserQuestion tool if you have it, otherwise plain text), and skip anything the user already told you:
1. **The clip** (a file, or a Google Drive link: `curl -L "https://drive.google.com/uc?export=download&id=FILE_ID"`).
2. **Where does the hook end?** Ask for the last sentence of the hook, or the second. If they don't know: propose the first camera cut or the first clear pause and say that this is your proposal. (If the clip is a loop, the hook is the start that comes back around.)
3. **Who are the main person(s)?** Only they matter for placement: text may cover background people, but **never a main person's head**.
4. **Which words are the most important in the hook?** Suggest 2–4 yourself (money, the core claim) and let them correct you.
5. Only if unclear: caption language (default: the spoken language) and swear words (default: censor with asterisks like `f***ed`).
After transcribing, **show the transcript and ask them to point out wrong words**, especially at the end of the hook; speech recognition mishears slang and similar words ("replaceable" became "replacing them"). When the user typed what is said, use their wording over the transcript.

## Workflow
Scripts live in `scripts/` next to this file. Use a work folder in the scratchpad.

1. **Prepare**: `python3 scripts/prepare.py CLIP --work WORK` gives `probe.json` (the real picture's y-range, camera cuts) and `contact.jpg`. **Look at contact.jpg and then at bigger frames of every shot**: where do the main people sit and where is free space *per shot*? One speaker with free space beside them → `hook_side`. Different shots need different spots → `hook_zones` (e.g. left of the speaker in the close-up, in the gap BETWEEN two people in a wide shot). No free side at all → `hook_layout: "band"` (one row along the top). Shots where people sit lower/farther away are `wide` ranges. Also note where the head ends in each shot (captions go just under it) and where a table or similar edge is (captions can sit just above it).
2. **Transcribe**: `python3 scripts/transcribe.py WORK/a.wav WORK/words.json` (needs `pip install faster-whisper`; installing may need the user's OK; the first run downloads a ~3 GB model, wait out a 429 rate limit or use `--model medium`). Show the transcript to the user and fix mistakes via `replace` in the config (e.g. "cop" → "cup") before rendering. Names, slang and swear words are often misheard.
3. **Config**: write `WORK/config.json` (fields documented at the top of `scripts/render_captions.py`): `hook_end`, `hook_side`, `hook_zones`, `hook_layout`, `key_words` (the 1–3 most important claim words for the hook; money like `$22 billion` is detected automatically), `emphasis` (yellow words after the hook), `replace`, `cuts`, `wide`, `post_y`, `post_wide`. If the user did not give the hook text, the first question above fixes `hook_end`.
4. **Plan**: `python3 scripts/render_captions.py plan config.json`. Check that the hook groups read naturally and the right words are `[KEY]`.
5. **Preview**: `... preview config.json WORK/prev T1 T2 ...` and **look at the images**: hook text must be in the free space and never over the face; nothing on the black bars; nothing cut off at the edge. Check several moments in the hook and several in the rest (including wide shots). Fix zone/side/wide ranges and repeat.
6. **Render**: `... render config.json`. Then pull 8–12 frames from the *final mp4* and look at them. Deliver with the file-send tool (users can't browse the sandbox) and keep the file under 30 MB (typical output is about 5 MB).
7. If the repository has a stop hook asking to commit new files, commit and push the mp4 to the working branch (no pull request unless asked).

## The look (defaults, already approved)
- **Hook (default layout `fill`)**: only in the free area next to the main person(s) (or between two people), inside the picture. **3–4 words on screen at once, never one word alone**; the group builds up word by word at the moment each word is said, then the next group takes over with a soft cross-fade. All words of a group have **one common size**, so nothing is huge next to something tiny; the size follows the width of the free area (0.2 × width) and is only shrunk if one long word needs it. White Inter Black, a bit less bold than before (outline 0.022), tight. Key words (money, core claim) use the cinematic serif (Cinzel Black, gold, money green) at about the same size, not bigger. If a very long word would make a group tiny in a narrow area, that group goes in one wide row (`band` in `hook_zones`, e.g. above the heads).
- **Older layout `corner`** (clip 1 look): 2+1 rows in the upper corner, key words huge and stacked ("$22" in the very corner with "BILLION" tight underneath). Only use it when the user asks for that look; users later found its size contrast too extreme ("bijna te groot" next to "heel dun") and single-word screens too empty.
- **After the hook**: one caption at a time, centred, one line, Inter ExtraBold white, **max 2 long or 3 short words** per caption, each word pops in with a quick zoom, emphasis words yellow, on screen at least ~0.5 s where the speech allows. **Height: by default just above the middle of the picture** (`post_y` 0.451). **Talking head: just under the person's head** (not over the face; raise `post_y` until the caption clears the chin). **Two people at a table / wide shot: just above the table** (`post_wide` with `bottom`), same size and same single line as everywhere else. Only change the height, not the look: a slight overlap with bodies is fine, heads are not. **Stacking two words under each other (`stack`) is an option for when the user asks for it; it is not the default.**
- Everything stays inside the real picture and away from the platform buttons (right edge, bottom).

## Hard lessons (don't repeat)
- No zoom or reframe of the video, no rounded card or border, no overlay boxes. The user rejected all of these.
- Don't pile several lines of text on screen or scroll them up; it looked "mega slecht". One group at a time.
- Don't delay text far behind the voice to make it last longer; it feels unnatural and off-beat (at most ~0.25 s late in the hook, 0.2 s after).
- Hook screens with one huge word or one tiny thin word were rejected: keep one size per group, 3–4 words, and match the spoken timing.
- A 1 px outline is invisible, so "bolder" must be a clear step, but not so thick that letters merge ("GET" became unreadable).
- Speech at ~4 words per second means a 2–3 word caption can only average ~0.5 s on screen. That is arithmetic, not a bug; say so and offer bigger captions or a sliding window instead of silently breaking the word limit.
- Words spoken just before a camera cut flash by; the renderer shows them at the cut.
- **Never put text over a main person's head.** In a wide shot with two people at a table, hook and captions go in the gap *between* them at head height (`hook_zones` + `post_wide`), with a margin on both sides: a person leaning forward moves their head 50+ px, so check several frames, not one. A little overlap with a body or hands is acceptable only if it truly cannot be avoided.
- Captions in a wide shot with two people: change only the HEIGHT (just above the table), never the size or the layout. A narrow zone plus stacked rows was called "extreem aangepast" and had to be reverted; offer stacking only if the user asks.
- Placement is judged from big frames, not the contact sheet; the first version of a placement was wrong twice (text touching a cap, captions across a man's arms).

## Tuning cheat-sheet (constants in `render_captions.py`)
| User says | Change |
|---|---|
| hook text bigger / smaller | `ns = 0.2 * zw` in `build_hook_fill()` (corner layout: `R1, R2, KBIG, KSMALL`) |
| hook bolder / less bold | `d['stroke']` in `build_hook_fill()` (0.022; the corner layout used 0.029; 0.034 starts merging letters) |
| more / fewer words per hook screen | the `4` in `fill_groups()` |
| letters closer / words closer | `tracking` and `gapk` in `wd()` |
| hook words longer on screen | `VIS` / `LAG` in `schedule_hook()` (trade-off: later = less on the beat) |
| smoother / snappier animation | `ANIM`, `XFADE`, `FOUT` in `schedule_hook()`; `anim` in `build_post()` |
| captions higher / lower | `post_y` in the config (default 0.451 = just above the middle); wide shots: `post_wide` |
| fewer / more words per caption | the `3.0` weight limit and `weight()` in `build_post()` |
| key word look | colours `GREEN`, `GOLD`, `YELLOW`; `key_words` / `emphasis` in the config |

More detail and the reasoning behind each number: `references/style-guide.md`.
