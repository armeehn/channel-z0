# Forking this station

Everything here runs one 24/7 channel from a house. Nothing in it needs to be
Channel Z0. This is the checklist from fork to first sign-on.

## 1. Fork and clone

Fork on GitHub (or import into your own Gitea), clone it, and work on `main`.
Nothing in the tree phones home: no telemetry, no upstream URLs at runtime
except the ones you set below.

## 2. Give it a name

Every name, domain, mailbox, show title and place the tree carries is listed
in [`station.env`](station.env), with the upstream value beside a one-line
description. Edit it, then:

```sh
python3 tools/rebrand.py --dry-run   # what would change
python3 tools/rebrand.py             # do it
```

The tool rewrites whole tokens only, longest first, so `Channel Z0` never
bites into `channel-z0`, and it renames the schedule files that carry the
slug. It records what it applied in `.station.applied`, so you can change
your mind and run it again. `python3 tools/test_rebrand.py` proves the round
trip on a scratch copy; CI runs it on every push.

What it does **not** do, and where to go instead:

| Left as upstream | Where it lives |
|---|---|
| Colours, type, the checker mark | the `:root` block and `.mark` rules at the top of `site/index.html` |
| The GROUND ZERO lockup (glyph-drawn) | `tools/z0-gz-open/gzlogo.py`; the opener is rebuilt by `tools/z0-gz-open/build.sh` |
| Committed PDFs in `docs/pdf/` | typeset from `docs/*.tex`, which need the upstream's private LaTeX class; the Markdown and the PDFs are what you get |
| Internal ids: `z0-ersatztv`, the `z0-*` graphics elements, `Z0_*` env vars, tool file names | harmless; rename by hand if you must |
| Coordinates on the flagship card | `playout/cards/ground-zero.html` |
| Sign-on 06:00, sign-off 00:00, flagship at 19:00 | `tools/z0-build-schedule.py` |

## 3. Decide what airs

The broadcast week is yours to write. Start from these, in this order:

- [`playout/_content.yml`](playout/_content.yml): the blocks and what feeds them.
- [`lists/z0-lists.yml`](lists/z0-lists.yml): every ErsatzTV collection by
  name. The upstream pools are Prelinger, Fleischer and Canadian archive
  material because the station is in British Columbia.
- [`tools/z0-nfo.py`](tools/z0-nfo.py) and the notes in `lists/`: the
  rights reasoning is written for Canadian law (Crown copyright, s.12 and
  s.23 terms). It is a worked example, not legal advice for your country.
- `tools/z0-build-schedule.py` turns the week into the schedule YAML that
  `tools/z0-validate-schedule.py` checks.

Anything you air has to be yours to air. See `docs/pdf/docs-ad-standards.pdf`.

## 4. Set the secrets

None are in the repository. Copy [`.env.example`](.env.example) to `.env`
on the playout machine and fill the stream key. For the storefront Worker:

```sh
npx wrangler secret put OWNCAST_TOKEN        # scope CAN_SEND_MESSAGES
npx wrangler secret put ANTHROPIC_API_KEY    # only for MODERATION_PROVIDER=anthropic
```

`WATCH_HOST` in `wrangler.jsonc` is required; the Worker has no fallback host.

## 5. Put it on the air

Follow `docs/pdf/docs-build-guide.pdf`, Phase 0 to Phase 4. In short: a VPS
running `vps/` (Owncast behind Caddy, TLS from your `WATCH_DOMAIN`), a
playout machine running `playout/` (ErsatzTV in Docker, the uplink service),
and a Cloudflare Worker for `site/` (connect the repo in the dashboard, add
your `SITE_DOMAIN` as a custom domain; every push to `main` deploys).

## 6. Continuous integration

- `.github/workflows/verify.yml` validates the schedules, the relay and the
  generators. It needs no secrets and runs anywhere.
- `.gitea/workflows/mirror-to-github.yml` pushes a Gitea repo to a GitHub
  twin. It is inert until the `MIRROR_REMOTE` repository variable and the
  `MIRROR_SSH_KEY` secret exist. Delete it if you only use GitHub.

## 7. Scripts that only run at the upstream

These carry the upstream's own hosts and paths and are kept as worked
examples of operating a running station. Read them; do not expect them to
run unchanged:

`tools/z0-intervals.sh`, `tools/z0-gz-open/build.sh`,
`tools/z0-day-align.py`, `tools/z0-lead-guard.py`,
`tools/z0-presignon-reset.sh`, `tools/z0-media-sync.sh`,
`tools/z0-generative.py` (needs a private glitch engine),
`tools/z0-lsys/` (needs FFglitch), `playout/cards/make-long-cards.sh`.

## 8. Licence

Code and configuration are MIT. The upstream names and marks are not part of
the grant; `station.env` is how you avoid using them.
