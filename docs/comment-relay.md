# The comment relay

The storefront's chat panel reads the tower directly. It does **not** write to
it directly, and the reason is the whole design of this piece: writing needs a
token that can post, and a token in a public page belongs to everyone who views
it. So the page asks a Worker on its own origin, and that Worker holds the
token, applies the house rules, and speaks to Owncast itself.

```
  viewer  ──POST /api/comment──▶  Worker (ch0.ripostelabs.xyz)
                                    │  1. shape        worker/screen.js    free
                                    │  2. allowance    worker/gate.js      a DO
                                    │  3. house rules  worker/moderate.js  a model
                                    ▼
                                  Owncast  /api/integrations/chat/send
                                    │
  viewer  ◀──websocket, like everyone else's message──┘
```

Nothing is echoed into the log optimistically. A relayed comment comes back
down the same websocket as everybody else's, which is also the proof it landed.

## The order is the design

1. **Shape** (`worker/screen.js`) — length, line count, link count, character
   floods, shouting. Free, and it turns away most of what a public comment box
   receives.
2. **Allowance** (`worker/gate.js`) — checked *before* the model so a flood
   cannot run up a bill, and *after* the shape checks so obvious rubbish does
   not consume a viewer's quota. A refused comment still spends its allowance;
   otherwise a spammer gets unlimited free attempts at finding a phrasing that
   passes.
3. **House rules** (`worker/moderate.js`) — one model call, one structured
   verdict. The only step that costs money.
4. **Post** — the only step the room can see.

## Rate limits

| Limit | Default | Answers |
|---|---|---|
| `RELAY_BURST_SECONDS` | 15 | is one person hammering the button? |
| `RELAY_VIEWER_PER_HOUR` | 8 | is one person here all night? |
| `RELAY_CHANNEL_PER_HOUR` | 200 | is the whole room running up the bill? |

Held in one Durable Object for the channel. **Not KV**: rate limiting is
read-modify-write, and KV is eventually consistent, so a KV limiter is one that
can be beaten by sending faster. The check and the spend happen in a single
trip to the object for the same reason — asking and then spending is a race.

A viewer is keyed on **both** their chat id and their address, so clearing
`localStorage` does not hand anyone a fresh allowance.

## The moderator

`MODERATION_PROVIDER` picks one:

- **`anthropic`** (default) — Claude Haiku 4.5 over the Messages API, with a
  single forced tool so the answer is a typed object and never prose to be
  regex'd. Needs `ANTHROPIC_API_KEY`.
- **`workers-ai`** — Cloudflare's own inference, no API key to hold. Cruder:
  one word out, and anything that is not exactly `ALLOW` is a refusal. Needs an
  `ai` binding in `wrangler.jsonc`.
- **`off`** — no model. The deterministic checks still run, and `GET
  /api/comment` reports `moderated: false` so the page can say so out loud
  rather than implying a moderator that is not there.

The comment reaches the model as **data**, wrapped in a `<comment>` delimiter,
with a system prompt that says everything inside it is text to be judged and
never an instruction. A comment that tries to instruct the moderator is itself
a refusal, category `prompt_injection` — that is the first thing a public
comment box receives.

**Failure is closed.** A timeout, a 500, a malformed answer, a safety stop —
anything that is not an explicit allow refuses the comment, and the viewer is
told the moderator is offline rather than that they were rejected. An open
failure mode on a moderation path means the one moment the moderator is down is
the moment anything at all can be said in the room, which is exactly backwards.

## What the room sees

Every relayed comment is posted by the token's own user, so the room sees one
author — **Z0 STOREFRONT**, flagged by Owncast as a bot — with the sender's
name in the line:

```
Z0 STOREFRONT   **bob** · a well-known short (1949) — 50% grain
```

That name is **decoration, not identity.** It is whatever the sender typed, cleaned
to letters, digits, spaces and `._-` and cut to 24 characters. Nobody is
authenticated; a relayed comment proves only that it came through this relay.
The bot badge is what tells the room where the line came from.

The body is markdown-escaped on the way in. Owncast renders what it is handed,
so an unescaped image from a stranger is a picture on everyone's screen and a
markdown link is a URL wearing whatever text the sender likes. A backslash
escape renders as the literal character, so ordinary prose is unchanged —
verified against the live tower: `a well-known short (1949) — 50% grain, no
re_touch. love it!` arrives with zero stray backslashes.

## Setting it up

Two secrets, neither in the repo:

```bash
# 1. An Owncast token that may post, and nothing else.
#    Admin → Integrations → Access tokens → scope CAN_SEND_MESSAGES.
#    Its NAME becomes the author the room sees, so name it for the station.
wrangler secret put OWNCAST_TOKEN

# 2. The moderator (skip for MODERATION_PROVIDER=workers-ai or off).
wrangler secret put ANTHROPIC_API_KEY
```

Then `npx wrangler deploy`, or let the Git integration do it.

Until both are set the relay reports itself closed, the comment box never
appears, and the panel keeps the link to the tower it has always had. **A
storefront deployed without them looks exactly as it did before this feature
existed** — that is deliberate.

To close the box again without redeploying the site, set the `RELAY_ENABLED`
var to `"false"`.

### Local

```bash
cp .dev.vars.example .dev.vars     # gitignored
npx wrangler dev
```

## Testing

```bash
node tools/test-comment-relay.mjs   # the Worker, no browser, no network
node tools/test-chat-composer.mjs   # the box in a real browser, relay stubbed
```

`test-comment-relay.mjs` drives `worker/index.js` directly with fake bindings —
a real `CommentGate` over a `Map`, and a `fetch` standing in for both the model
and the tower. That is what makes the interesting cases reachable: the
moderator returning 500, a comment addressed to the moderator, the tower
refusing, the clock moved forward an hour. Against the real thing only the
happy path is easy to produce.

## Known limits

- One Durable Object serialises every comment for the channel. Right for a
  station with a handful of viewers; wrong for a million.
- The rate limiter is per address and per chat id. It does not stop somebody
  with a lot of addresses.
- The relay cannot delete or edit anything it has posted; moderation after the
  fact is Owncast's own admin.
