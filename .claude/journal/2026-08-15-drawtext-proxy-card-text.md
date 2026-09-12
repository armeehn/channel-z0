# 2026-08-15 — drawtext ate punctuation on proxy placeholder cards

## Task
CHZ0-1 / "Stop drawtext eating apostrophes and colons in card text", pointing at
armeehn/channel-z0 **#15**.

## Outcome
Done. #15 turned out to be an already-**merged PR** (2026-08-13, merge commit
`e97bbbc`), not an open issue — `gh issue view 15` happily resolves a PR number,
which is what made it look open. The residual bug was in the one file #15 did not
touch. Fix is branch `agent/proxy-card-text-safety`, commit `9719f29`, PR
**#31**. Worktree: `/home/user/wt-z0-proxytext` in LXC 111. Not merged.

## Traps
- **`gh issue view <n>` silently resolves pull requests.** It printed
  `state: MERGED` for what the ticket called an issue. Check `gh pr view` before
  concluding there is work to do — or before concluding there isn't.
- **A fix that lands in `z0-lib.sh` is not a fix everywhere.** #15 added
  `z0_text()` (writes text to a file, emits `textfile='...':expansion=none`) and
  wired six `make-*.sh` generators to it. `tools/make-proxies.sh` sources the
  same library and was left on its own local `dt_escape()`. Grep every
  `drawtext` call site, not just the ones the PR listed.
- **The mangling was upstream of the escaping.** `placeholder_label()` ran the
  title through `tr -cd 'A-Za-z0-9 ._-'`, so apostrophes and colons were gone
  before ffmpeg saw them. Exit 0, card present, correct duration, wrong words.
  `Kelowna's Own: LAB HOUR` rendered as `KELOWNAS OWN LAB HOUR`. Nothing in the
  output hints at it — the only way to see it is to extract a frame.
- **`dt_escape()` was wrong in a way the flattening hid.** It emitted `\'` for an
  apostrophe. Inside a single-quoted ffmpeg filtergraph token backslash escapes
  do not apply at all; the correct form is `'\''`. It also never covered `,`
  `[` `]` or newline. Had anyone "fixed" the charset filter without touching
  `dt_escape`, the render would have started dying instead.
- **A second `trap ... EXIT` replaces the first, it does not add to it.**
  `z0-lib.sh` installs `trap 'rm -rf "$Z0_TEXT_DIR"' EXIT` at *source* time;
  `make-proxies.sh` line ~160 installs its own for its temp lists and silently
  dropped the library's. Every run leaked a `/tmp/z0-text.XXXXXX`. Measured: 1
  per run on main, 0 after. `tools/test-generators.sh` already had a comment
  about this footgun and still nobody checked the other sourcing script.
- **Checked and cleared, so don't re-check:** bash does *not* inherit an EXIT
  trap into a `&` background subshell (verified empirically), so `make_proxy`
  running in the job pool cannot delete the scratch dir out from under a sibling
  encode. This matters because `z0_text` is called from inside `$( )` inside a
  backgrounded function.

## Decisions
- **`textfile=` over repairing `dt_escape()`** — an escaping function must be
  correct across three nested parsers (filtergraph option split, quote layer,
  drawtext `%` expansion) and will be wrong again for the next character class.
  A file has no escaping layer.
- **Kept the newline/tab strip and the 30-char truncation.** Those are layout
  decisions for a 320px card, not escaping. Truncation moved from `cut -c1-30`
  (byte-based) to `${s:0:30}` (character-based) now that non-ASCII titles can
  survive that far.
- **Test asserts on rendered frame hashes, never on the command string.** For
  each hostile title it also builds a source named with the punctuation stripped
  and asserts the two frames *differ*. A card that renders "fine" with the wrong
  words is exactly the failure mode, so comparing to a blank reference would not
  have caught it.

## Verified / unverified
- Verified: reproduced on `main` — two clips differing only in filename produced
  the identical frame hash `b916989d…`; extracted the PNG and read
  `KELOWNAS OWN LAB HOUR` off it. After the fix the hashes differ and the card
  reads `KELOWNA'S OWN: LAB HOUR`.
- Verified: new test **fails 6 / passes 33** with `tools/make-proxies.sh`
  stashed back to main, **fails 0 / passes 39** with the fix. ffmpeg n8.1.2.
- Verified: no GitHub Actions run fires on this PR (`.github/workflows/` holds
  only `deploy-pages.yml`). The Cloudflare Workers build for the site ran and
  passed — unrelated to these files.
- Unverified: nothing was run against a real media library; all sources were
  synthetic 2–7 s clips. The default (non-placeholder) transcode path is
  untouched and uses no `drawtext`, so it was not re-tested.
- Unverified: `shellcheck` is not installed in LXC 111, so only `bash -n` ran.

## Open
- The remaining inline `text=` values across the generators are static station
  furniture (`CHANNEL Z0`, `DESIG RL-Z0`, `SIGN-ON AT 06\:00`). Left alone
  deliberately — moving them to `textfile=` would mean one scratch file per line
  for no gain.
- `docs/archive-fetch.md` was the only doc asserting the old flattening
  behaviour; it is updated in the same commit. Nothing else in `docs/` describes
  `dt_escape`.
