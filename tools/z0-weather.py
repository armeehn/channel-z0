#!/usr/bin/env python3
"""Channel Z0 — the weather desk and the on-air rails.

Fetches the forecast, then writes every text asset the on-air graphics need:
drawtext payloads for the two side rails and for the full-screen segment. It
renders nothing itself; z0-weather.sh drives ffmpeg over the filter scripts
written here.

Splitting it this way is deliberate. Everything that comes off the network or
out of the guide is user data as far as ffmpeg is concerned, and drawtext's
escaping rules (colons, backslashes, quotes, percent) are a minefield. So no
dynamic string is ever inlined into a filtergraph: each one goes to its own
file and drawtext reads it with textfile=. There is then no such thing as a
forecast that happens to contain a character which breaks the render.

── The rails ───────────────────────────────────────────────────────────────

The channel is 854x480 and every frame of programming is 4:3, so ffmpeg
pillarboxes 640x480 of picture into the middle and leaves a 107px black bar
down each side. All of the station's furniture lives in those bars now, so
nothing is ever composited over the picture. See docs/graphics.md.
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

LAT = os.environ.get("Z0_WX_LAT", "49.88307")
LON = os.environ.get("Z0_WX_LON", "-119.48568")
CITY = os.environ.get("Z0_WX_CITY", "KELOWNA")
REGION = os.environ.get("Z0_WX_REGION", "BC")
TZNAME = os.environ.get("Z0_WX_TZ", "America/Vancouver")

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/z0wx"
STATE = sys.argv[2] if len(sys.argv) > 2 else "/tmp/z0wx-state"

INK = "0x141414"
PAPER = "0xF2F0E9"
RED = "0xE02A1B"
GREY = "0x8A8A8A"

# ── Frame geometry ──────────────────────────────────────────────────────────
#
# RAIL_W is derived, never typed twice: it is exactly half of what is left
# over when 4:3 picture is pillarboxed into the channel's frame. Change the
# channel resolution and this follows, which is the whole reason it is
# computed rather than written down. The three numbers below are the only
# place the geometry lives; the element YAMLs quote RAIL_W as a percentage of
# frame width and docs/graphics.md shows the arithmetic.
FRAME_W = int(os.environ.get("Z0_FRAME_W", "854"))
FRAME_H = int(os.environ.get("Z0_FRAME_H", "480"))
CONTENT_W = int(os.environ.get("Z0_CONTENT_W", "640"))
RAIL_W = (FRAME_W - CONTENT_W) // 2          # 107

# The right rail is one column split into two blocks that abut exactly, so the
# red spine down its inner edge is unbroken from top to bottom. They are two
# elements rather than one because the bug must never depend on a cron job:
# the weather block is rewritten every 15 minutes, the bug is rendered once.
WX_H = 340                                   # right rail, top: the weather
BUG_H = FRAME_H - WX_H                       # right rail, bottom: the bug

SPINE = 3       # the red rule down each rail's INNER edge, framing the picture
PAD = 8         # text inset from the rail's outer edge

# Usable text column, identical in both rails.
COL_W = RAIL_W - SPINE - PAD - PAD           # 88

# Mono advance is 0.6 em, which is what makes a fixed-width column predictable:
# characters-per-line is (column / (0.6 * size)) and never needs measuring.
ADVANCE = 0.6

# The full-screen weather segment is 4:3 as well, so the picture window never
# changes size when it comes on. 1440x1080 is 4:3 at a comfortable working
# size; ErsatzTV scales it into the 640x480 content area like everything else.
SLIDE_W = 1440
SLIDE_H = 1080

FONT = "/usr/share/fonts/truetype/noto/NotoSansMono-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf"

# WMO weather codes. Short forms, because these are set in a monospace face at
# display sizes and anything longer than about 18 characters overruns the card.
WMO = {
    0: "CLEAR", 1: "MAINLY CLEAR", 2: "PARTLY CLOUDY", 3: "OVERCAST",
    45: "FOG", 48: "FREEZING FOG",
    51: "LIGHT DRIZZLE", 53: "DRIZZLE", 55: "HEAVY DRIZZLE",
    56: "FREEZING DRIZZLE", 57: "FREEZING DRIZZLE",
    61: "LIGHT RAIN", 63: "RAIN", 65: "HEAVY RAIN",
    66: "FREEZING RAIN", 67: "FREEZING RAIN",
    71: "LIGHT SNOW", 73: "SNOW", 75: "HEAVY SNOW", 77: "SNOW GRAINS",
    80: "RAIN SHOWERS", 81: "RAIN SHOWERS", 82: "HEAVY SHOWERS",
    85: "SNOW SHOWERS", 86: "SNOW SHOWERS",
    95: "THUNDERSTORM", 96: "THUNDERSTORM", 99: "THUNDERSTORM",
}

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def log(msg):
    print(f"z0-weather: {msg}", file=sys.stderr)


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "channel-z0/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def get_weather():
    """Fetch the forecast, falling back to the last good copy.

    A failed fetch must never blank the rail. An overlay that vanishes reads as
    a broken channel, whereas a forecast that is an hour stale reads as a
    forecast — and the rail carries its own "AS OF" stamp, so a viewer can tell.
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        "is_day,weather_code,wind_speed_10m,wind_direction_10m"
        "&hourly=temperature_2m,weather_code,precipitation_probability"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,sunrise,sunset"
        f"&timezone={urllib.parse.quote(TZNAME)}&forecast_days=6"
    )
    cache = os.path.join(STATE, "weather.json")
    for attempt in (1, 2, 3):
        try:
            data = fetch_json(url)
            data["_fetched"] = datetime.now(timezone.utc).isoformat()
            tmp = cache + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, cache)
            return data, True
        except Exception as e:  # noqa: BLE001 - any failure falls back to cache
            log(f"fetch attempt {attempt} failed: {e}")
    try:
        with open(cache) as f:
            log("using cached forecast")
            return json.load(f), False
    except Exception as e:  # noqa: BLE001
        log(f"no cached forecast either: {e}")
        return None, False


def local_now():
    """Wall clock at the station, without depending on a tz database package."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(TZNAME))
    except Exception:  # noqa: BLE001
        return datetime.now()


def hhmm(dt):
    return dt.strftime("%-I:%M %p").upper()


def c(v):
    return f"{round(v):d}"


def fit_size(text, want, column=COL_W):
    """Largest size at or below `want` that keeps `text` inside `column`.

    A rail is 88 pixels wide and the temperature is the one string whose length
    is not known in advance: "3°" and "-14°" differ by two characters, which at
    display size is the difference between centred and clipped. Rather than
    pick a size small enough for the worst case all winter, size to the string.
    """
    if not text:
        return want
    return max(8, min(want, int(column / (ADVANCE * len(text)))))


def wrap(text, size, column=COL_W):
    """Break on spaces to fit a fixed-width column. Over-long words are kept
    whole and allowed to overhang rather than hyphenated — a broken word reads
    as a rendering fault, an overhanging one reads as a long word."""
    limit = max(1, int(column / (ADVANCE * size)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and len(trial) > limit:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


class Text:
    """Collects every dynamic string as a numbered file, and hands back the
    drawtext fragment that reads it. Nothing dynamic is ever inlined."""

    def __init__(self, outdir):
        self.outdir = outdir
        self.n = 0

    def draw(self, s, *, x, y, size, color, font=FONT, alpha=None):
        self.n += 1
        path = os.path.join(self.outdir, f"t{self.n:03d}.txt")
        with open(path, "w") as f:
            f.write(s)
        col = color if alpha is None else f"{color}@{alpha}"
        # expansion=none: these strings are data, not templates. Without it a
        # humidity of "22%" makes drawtext try to expand a strftime escape and
        # warn "Stray %"; a forecast containing "%T" would silently become a
        # timestamp.
        return (
            f"drawtext=fontfile='{font}':textfile='{path}':expansion=none"
            f":fontcolor={col}:fontsize={size}:x={x}:y={y}"
        )


class Rail:
    """A rail is a fixed-width column filled top-down.

    Everything in a rail is centred in the same 88px text column and stacked by
    a running cursor, so adding or removing a line never means re-deriving a
    dozen y coordinates by hand — which is exactly the edit that used to put a
    graphic on top of another one with nothing to warn about it.

    `side` places the red spine: "left" means the rail is on the left of the
    frame, so its inner edge — the one facing the picture — is its right side.
    """

    def __init__(self, tx, side, height):
        self.tx = tx
        self.side = side
        self.height = height
        self.y = 0
        self.f = []
        spine_x = RAIL_W - SPINE if side == "left" else 0
        # replace=1 is load-bearing on a transparent canvas. drawbox's default
        # is to blend, which mixes the colour into RGB but leaves the source
        # alpha at zero — the rule renders and is then composited away to
        # nothing, and all you see is floating text.
        self.f.append(
            f"drawbox=x={spine_x}:y=0:w={SPINE}:h={height}"
            f":color={RED}:t=fill:replace=1")
        # Text starts clear of the spine on whichever side it is.
        self.x0 = PAD if side == "left" else SPINE + PAD

    def cx(self):
        """Centre within the text column, not within the rail — otherwise the
        spine pushes everything half its width off-centre."""
        return f"{self.x0}+({COL_W}-tw)/2"

    def gap(self, n):
        self.y += n
        return self

    def line(self, s, size, color, font=FONT, alpha=None, lead=1.25):
        self.f.append(self.tx.draw(s, x=self.cx(), y=self.y, size=size,
                                   color=color, font=font, alpha=alpha))
        self.y += int(size * lead)
        return self

    def block(self, s, size, color, font=FONT, alpha=None):
        for ln in wrap(s, size):
            self.line(ln, size, color, font=font, alpha=alpha)
        return self

    def rule(self, color=PAPER, alpha=0.25, thick=1):
        self.f.append(
            f"drawbox=x={self.x0}:y={self.y}:w={COL_W}:h={thick}"
            f":color={color}@{alpha}:t=fill:replace=1")
        self.y += thick
        return self

    def render(self):
        return ",".join(self.f)


def build_weather_rail(wx, tx, live):
    """The right rail's top block: conditions, stacked in a 107px column.

    This replaces the 920x300 landscape card, which could not survive being
    squeezed into a gutter — the redesign is what makes the move possible, not
    a side effect of it.
    """
    cur = wx["current"]
    daily = wx["daily"]
    code = int(cur["weather_code"])
    temp = f"{c(cur['temperature_2m'])}°"
    wdir = COMPASS[int((cur["wind_direction_10m"] % 360) / 22.5 + 0.5) % 16]

    r = Rail(tx, "right", WX_H)
    r.gap(12)
    r.line(CITY, 15, PAPER)
    r.line(REGION, 11, GREY)
    r.gap(10)
    # Sized to the string: see fit_size. A winter "-14°" is four characters.
    r.line(temp, fit_size(temp, 54), PAPER, lead=1.15)
    r.gap(6)
    r.block(WMO.get(code, "—"), 12, PAPER)
    r.gap(12)
    r.rule()
    r.gap(10)
    r.line(f"FEELS {c(cur['apparent_temperature'])}°", 11, GREY)
    r.gap(4)
    # Wind is set as two deliberate lines rather than one wrapped string.
    # Wrapping "WIND 2 KM/H WSW" leaves the bearing stranded on a line of its
    # own, and where it breaks changes with the speed — "WIND 100 KM/H" fills
    # the column exactly while "WIND 2 KM/H" does not. Two fixed lines always
    # fit and always break in the same place.
    r.line(f"WIND {wdir}", 11, GREY)
    r.gap(2)
    r.line(f"{c(cur['wind_speed_10m'])} KM/H", 11, GREY)
    r.gap(4)
    r.line(f"HUM {int(cur['relative_humidity_2m'])}%", 11, GREY)
    r.gap(4)
    # "PRECIP", not "RAIN": this is Open-Meteo's daily probability of
    # precipitation, and in Kelowna half the year that precipitation is snow.
    r.line(f"PRECIP {int(daily['precipitation_probability_max'][0])}%", 11, GREY)
    r.gap(12)
    r.rule()
    r.gap(8)
    # Say so on air rather than pretending a cached number is current. The
    # element is re-read once per programme, not per frame, so even a live
    # fetch is only as fresh as the last programme boundary.
    if live:
        r.line("AS OF", 10, GREY, font=FONT_R)
        r.line(hhmm(local_now()), 11, GREY)
    else:
        r.line("LAST GOOD", 10, RED, font=FONT_R)
        r.line(hhmm(local_now()), 11, RED)
    return r.render()


def build_listings_rail(tx):
    """The left rail: the frame around the live UP NEXT text element.

    The listings themselves are NOT baked in here. They come from ErsatzTV's
    own EPG through text/z0-upnext.yml, which is re-rendered for every playout
    item and therefore cannot disagree with the guide — where a PNG written on
    a 15-minute cron would go stale between programmes. This file supplies only
    what does not change: the spine, the header, and the station line.

    The middle of the rail is deliberately empty. That void is where the text
    element lands, and its extent is the one thing the two files have to agree
    about — z0-upnext.yml quotes the same numbers.
    """
    r = Rail(tx, "left", FRAME_H)
    r.gap(12)
    r.line("UP NEXT", 11, RED)
    r.gap(2)
    r.rule(color=RED, alpha=0.55, thick=2)

    # ── the void: y from here to the station block belongs to z0-upnext.yml ──
    r.y = FRAME_H - 124
    r.rule()
    r.gap(10)
    now = local_now()
    r.line(now.strftime("%a").upper(), 14, PAPER)
    r.line(now.strftime("%b %-d").upper(), 11, GREY)
    r.gap(14)
    r.block("ONE SIGNAL, ALWAYS ON", 11, RED)
    return r.render()


def slide_base(tx, title):
    """Every full-screen slide shares the slate furniture from make-slate.sh."""
    return [
        f"drawbox=x=0:y=120:w=iw:h=10:color={RED}:t=fill",
        f"drawbox=x=0:y=950:w=iw:h=10:color={RED}:t=fill",
        tx.draw("CHANNEL Z0 · THE WEATHER DESK", x="(w-tw)/2", y=52,
                size=34, color=GREY),
        tx.draw(title, x="(w-tw)/2", y=170, size=56, color=RED),
        tx.draw(f"{CITY}, {REGION}", x=60, y=1000, size=28, color=GREY, font=FONT_R),
    ]


def build_slides(wx, tx):
    cur = wx["current"]
    daily = wx["daily"]
    hourly = wx["hourly"]
    now = local_now()
    slides = []

    # ── 1. Current conditions ────────────────────────────────────────────────
    f = slide_base(tx, "CURRENT CONDITIONS")
    f += [
        tx.draw(f"{c(cur['temperature_2m'])}°", x="(w-tw)/2", y=300,
                size=260, color=PAPER),
        tx.draw(WMO.get(int(cur["weather_code"]), "—"), x="(w-tw)/2", y=600,
                size=72, color=PAPER),
        tx.draw(f"FEELS LIKE {c(cur['apparent_temperature'])}°", x="(w-tw)/2",
                y=706, size=40, color=GREY),
        tx.draw(
            f"WIND {c(cur['wind_speed_10m'])} KM/H "
            f"{COMPASS[int((cur['wind_direction_10m'] % 360) / 22.5 + 0.5) % 16]}"
            f"   ·   HUMIDITY {int(cur['relative_humidity_2m'])}%",
            x="(w-tw)/2", y=790, size=40, color=GREY),
        tx.draw(f"AS OF {hhmm(now)}", x="(w-tw)/2", y=872, size=32, color=GREY),
    ]
    slides.append(",".join(f))

    # ── 2. Next six hours ────────────────────────────────────────────────────
    #
    # Six evenly spaced columns. The divisor is SLIDE_W, not a literal — the
    # canvas went 16:9 -> 4:3 so the picture window never changes size, and a
    # hard-coded 1920/6 would have left every column a third too far right with
    # the last one off the canvas entirely.
    f = slide_base(tx, "THE NEXT SIX HOURS")
    idx = [i for i, t in enumerate(hourly["time"])
           if datetime.fromisoformat(t) > now.replace(tzinfo=None)][:6]
    step = SLIDE_W // 6
    for col, i in enumerate(idx):
        cx = step // 2 + step * col
        t = datetime.fromisoformat(hourly["time"][i])
        temp = c(hourly["temperature_2m"][i])
        pop = hourly["precipitation_probability"][i]
        cond = WMO.get(int(hourly["weather_code"][i]), "—")
        short = cond if len(cond) <= 14 else cond.split()[0]
        f += [
            tx.draw(t.strftime("%-I%p"), x=f"{cx}-tw/2", y=330, size=44, color=GREY),
            tx.draw(f"{temp}°", x=f"{cx}-tw/2", y=410, size=92, color=PAPER),
            tx.draw(short, x=f"{cx}-tw/2", y=540, size=24, color=PAPER, font=FONT_R),
            tx.draw(f"{pop}%", x=f"{cx}-tw/2", y=600, size=32, color=GREY),
        ]
    f.append(tx.draw("PRECIPITATION PROBABILITY BELOW EACH HOUR",
                     x="(w-tw)/2", y=830, size=28, color=GREY, font=FONT_R))
    slides.append(",".join(f))

    # ── 3. Five-day outlook ──────────────────────────────────────────────────
    f = slide_base(tx, "FIVE-DAY OUTLOOK")
    step = SLIDE_W // 5
    for col in range(5):
        cx = step // 2 + step * col
        d = datetime.fromisoformat(daily["time"][col])
        hi = c(daily["temperature_2m_max"][col])
        lo = c(daily["temperature_2m_min"][col])
        cond = WMO.get(int(daily["weather_code"][col]), "—")
        short = cond if len(cond) <= 13 else cond.split()[0]
        label = "TODAY" if col == 0 else d.strftime("%a").upper()
        f += [
            tx.draw(label, x=f"{cx}-tw/2", y=320, size=46, color=RED),
            tx.draw(f"{hi}°", x=f"{cx}-tw/2", y=400, size=96, color=PAPER),
            tx.draw(f"{lo}°", x=f"{cx}-tw/2", y=530, size=56, color=GREY),
            tx.draw(short, x=f"{cx}-tw/2", y=630, size=24, color=PAPER, font=FONT_R),
            tx.draw(f"{daily['precipitation_probability_max'][col]}%",
                    x=f"{cx}-tw/2", y=690, size=30, color=GREY),
        ]
    f.append(tx.draw("HIGH / LOW · CHANCE OF PRECIPITATION",
                     x="(w-tw)/2", y=830, size=28, color=GREY, font=FONT_R))
    slides.append(",".join(f))

    # ── 4. Sun, and the sign-out ─────────────────────────────────────────────
    f = slide_base(tx, "SUN & SKY")
    sr = datetime.fromisoformat(daily["sunrise"][0])
    ss = datetime.fromisoformat(daily["sunset"][0])
    daylen = ss - sr
    left, right = SLIDE_W // 4, SLIDE_W * 3 // 4
    f += [
        tx.draw("SUNRISE", x=f"{left}-tw/2", y=330, size=40, color=GREY),
        tx.draw(hhmm(sr), x=f"{left}-tw/2", y=400, size=88, color=PAPER),
        tx.draw("SUNSET", x=f"{right}-tw/2", y=330, size=40, color=GREY),
        tx.draw(hhmm(ss), x=f"{right}-tw/2", y=400, size=88, color=PAPER),
        tx.draw(f"{daylen.seconds // 3600}H {(daylen.seconds % 3600) // 60}M OF DAYLIGHT",
                x="(w-tw)/2", y=600, size=48, color=PAPER),
        tx.draw("ONE SIGNAL, ALWAYS ON", x="(w-tw)/2", y=760, size=42, color=RED),
        tx.draw("FORECAST DATA: OPEN-METEO", x="(w-tw)/2", y=850, size=26,
                color=GREY, font=FONT_R),
    ]
    slides.append(",".join(f))
    return slides


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(STATE, exist_ok=True)

    wx, live = get_weather()
    if wx is None:
        log("no forecast available and no cache — leaving existing assets alone")
        return 2

    tx = Text(OUT)
    with open(os.path.join(OUT, "wx-rail.vf"), "w") as f:
        f.write(build_weather_rail(wx, tx, live))
    with open(os.path.join(OUT, "listings-rail.vf"), "w") as f:
        f.write(build_listings_rail(tx))
    for i, s in enumerate(build_slides(wx, tx), start=1):
        with open(os.path.join(OUT, f"slide{i}.vf"), "w") as f:
            f.write(s)

    log(f"forecast {'live' if live else 'CACHED'}; "
        f"rails {RAIL_W}x{WX_H} and {RAIL_W}x{FRAME_H}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
