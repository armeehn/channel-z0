#!/usr/bin/env python3
"""Channel Z0 — the weather desk.

Fetches the forecast, then writes every text asset the on-air graphics need:
drawtext payloads for the corner card and the full-screen segment, and the
scrolling crawl. It renders nothing itself; z0-weather.sh drives ffmpeg over
the filter scripts written here.

Splitting it this way is deliberate. Everything that comes off the network or
out of the guide is user data as far as ffmpeg is concerned, and drawtext's
escaping rules (colons, backslashes, quotes, percent) are a minefield. So no
dynamic string is ever inlined into a filtergraph: each one goes to its own
file and drawtext reads it with textfile=. There is then no such thing as a
forecast that happens to contain a character which breaks the render.
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

LAT = os.environ.get("Z0_WX_LAT", "49.88307")
LON = os.environ.get("Z0_WX_LON", "-119.48568")
CITY = os.environ.get("Z0_WX_CITY", "KELOWNA")
REGION = os.environ.get("Z0_WX_REGION", "BC")
TZNAME = os.environ.get("Z0_WX_TZ", "America/Vancouver")
XMLTV = os.environ.get("Z0_XMLTV_URL", "http://127.0.0.1:8409/iptv/xmltv.xml")

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/z0wx"
STATE = sys.argv[2] if len(sys.argv) > 2 else "/tmp/z0wx-state"

INK = "0x141414"
PAPER = "0xF2F0E9"
RED = "0xE02A1B"
GREY = "0x8A8A8A"
# Bottom information strip. CRAWL_Y is the top edge of the text box; the bug
# sits above it (vertical_margin_percent 8 in z0-bug.yml) and must stay clear.
MARGIN_X = 48
CRAWL_Y = 1012
DWELL = 9.0  # seconds a page holds before the next one replaces it

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

    A failed fetch must never blank the card. An overlay that vanishes reads as
    a broken channel, whereas a forecast that is an hour stale reads as a
    forecast — and the card carries its own "AS OF" stamp, so a viewer can tell.
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


def get_upcoming(limit=4):
    """Next programmes from ErsatzTV's own XMLTV guide, for the crawl."""
    try:
        req = urllib.request.Request(XMLTV, headers={"User-Agent": "channel-z0/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            tree = ET.parse(r)
    except Exception as e:  # noqa: BLE001
        log(f"guide unavailable: {e}")
        return []

    now = datetime.now(timezone.utc)
    out = []
    for prog in tree.getroot().findall("programme"):
        raw = prog.get("start", "")
        try:
            # XMLTV: YYYYMMDDHHMMSS +ZZZZ
            start = datetime.strptime(raw, "%Y%m%d%H%M%S %z")
        except ValueError:
            continue
        if start <= now:
            continue
        title_el = prog.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            continue
        out.append((start, title))
    out.sort(key=lambda x: x[0])
    return out[:limit]


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


def build_card(wx, tx, live):
    """The persistent corner card: 920x300, composited at ~24% of frame width."""
    cur = wx["current"]
    code = int(cur["weather_code"])
    cond = WMO.get(code, "—")
    temp = c(cur["temperature_2m"])
    feels = c(cur["apparent_temperature"])
    wind = c(cur["wind_speed_10m"])
    wdir = COMPASS[int((cur["wind_direction_10m"] % 360) / 22.5 + 0.5) % 16]
    hum = int(cur["relative_humidity_2m"])
    stamp = hhmm(local_now())

    f = [
        # Ink panel, then the station's red spine down the left edge.
        #
        # replace=1 is load-bearing on a transparent canvas. drawbox's default
        # is to blend, which mixes the colour into RGB but leaves the source
        # alpha at zero — the panel renders and is then composited away to
        # nothing, and all you see is floating text.
        f"drawbox=x=0:y=0:w=920:h=300:color={INK}@0.72:t=fill:replace=1",
        f"drawbox=x=0:y=0:w=12:h=300:color={RED}:t=fill:replace=1",
        tx.draw(f"{CITY}, {REGION}", x=48, y=30, size=44, color=PAPER),
        tx.draw(f"{temp}°", x=48, y=88, size=150, color=PAPER),
        tx.draw(cond, x=340, y=110, size=46, color=PAPER),
        tx.draw(f"FEELS {feels}°", x=340, y=170, size=34, color=GREY),
        tx.draw(f"WIND {wind} KM/H {wdir}  ·  HUM {hum}%",
                x=48, y=245, size=32, color=GREY),
    ]
    if live:
        f.append(tx.draw(f"AS OF {stamp}", x=620, y=30, size=30, color=GREY))
    else:
        # Say so on air rather than pretending the number is current.
        f.append(tx.draw(f"LAST GOOD {stamp}", x=560, y=30, size=30, color=RED))
    return ",".join(f)


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
    f = slide_base(tx, "THE NEXT SIX HOURS")
    idx = [i for i, t in enumerate(hourly["time"])
           if datetime.fromisoformat(t) > now.replace(tzinfo=None)][:6]
    # Six evenly spaced columns; 1920/6 = 320, so each column is centred at
    # 160 + 320n and the text is drawn centred inside it.
    for col, i in enumerate(idx):
        cx = 160 + 320 * col
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
    for col in range(5):
        cx = 192 + 384 * col
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
    f += [
        tx.draw("SUNRISE", x=480 - 0, y=330, size=40, color=GREY),
        tx.draw(hhmm(sr), x=430, y=400, size=88, color=PAPER),
        tx.draw("SUNSET", x=1200, y=330, size=40, color=GREY),
        tx.draw(hhmm(ss), x=1150, y=400, size=88, color=PAPER),
        tx.draw(f"{daylen.seconds // 3600}H {(daylen.seconds % 3600) // 60}M OF DAYLIGHT",
                x="(w-tw)/2", y=600, size=48, color=PAPER),
        tx.draw("ONE SIGNAL, ALWAYS ON", x="(w-tw)/2", y=760, size=42, color=RED),
        tx.draw("FORECAST DATA: OPEN-METEO", x="(w-tw)/2", y=850, size=26,
                color=GREY, font=FONT_R),
    ]
    slides.append(",".join(f))
    return slides


def ass_escape(s):
    """ASS is line-oriented; a literal newline or brace would end the event or
    open an override block."""
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_crawl(wx, upcoming, path):
    """The bottom-of-screen information strip, as a libass subtitle track.

    Timing is relative to the start of whatever programme is on, because that
    is the only clock a subtitle element has. Events are laid down for six
    hours so a long feature never runs out.

    This element is EXPENSIVE and it has taken the channel off air. ErsatzTV
    composites graphics in-process and pipes one full-frame RGBA stream to
    ffmpeg; image and text elements are rasterised once and reused, but a
    subtitle element is re-rendered every single frame whether or not anything
    changed. On vile that costs ~4x realtime at 1080p, so items carrying this
    strip transcoded at 0.25x, and ErsatzTV logs [FTL] "not fast enough to
    support playback", abandons the item and cuts to fallback colour bars —
    which carry no graphics at all.

    Measured, so it is not guesswork: it is not libass (ffmpeg renders this
    exact file at 635 fps) and it is not the box (12 cores at load 2.2, no CPU
    limit). It is also NOT animation — rewriting a scrolling \\move crawl into
    the static paged form below changed nothing, still 0.254x. There is no
    static-content fast path in ErsatzTV to exploit.

    What made it affordable is the channel dropping to 854x480: the per-frame
    cost is proportional to pixel count. Paging is kept because it reads far
    better than a scroll at SD, not because it is cheaper.

    If the channel ever goes back to 720p/1080p, this strip has to be removed.
    """
    cur = wx["current"]
    bits = [
        f"CHANNEL Z0",
        f"{CITY} {c(cur['temperature_2m'])}° "
        f"{WMO.get(int(cur['weather_code']), '')}",
        f"WIND {c(cur['wind_speed_10m'])} KM/H",
        f"HUMIDITY {int(cur['relative_humidity_2m'])}%",
    ]
    for start, title in upcoming:
        try:
            from zoneinfo import ZoneInfo
            local = start.astimezone(ZoneInfo(TZNAME))
        except Exception:  # noqa: BLE001
            local = start
        bits.append(f"{local.strftime('%-I:%M %p').upper()}  {title.upper()}")
    bits.append("ONE SIGNAL, ALWAYS ON")

    bits = [ass_escape(b) for b in bits]

    # Monospace makes the run width computable: NotoSansMono advances 0.6 em,
    # so a 34px face is ~20.4px per glyph. Pack bits into pages that fit the
    # frame with the left margin, rather than one bit per page (too sparse).
    size = 34
    sep = "   ·   "
    max_chars = int((1920 - 2 * MARGIN_X) / (size * 0.6))

    pages, cur_page = [], []
    for b in bits:
        trial = sep.join(cur_page + [b])
        if cur_page and len(trial) > max_chars:
            pages.append(sep.join(cur_page))
            cur_page = [b]
        else:
            cur_page.append(b)
    if cur_page:
        pages.append(sep.join(cur_page))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Crawl,Noto Sans Mono,{size},&H00E9F0F2,&H00E9F0F2,&H00141414,&HB4141414,-1,0,0,0,100,100,0,0,3,6,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def ts(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h:d}:{m:02d}:{s:05.2f}"

    lines = []
    t = 8.0  # let the programme breathe before the first page
    limit = 6 * 3600
    i = 0
    while t < limit:
        end = min(t + DWELL, limit)
        lines.append(
            f"Dialogue: 0,{ts(t)},{ts(end)},Crawl,,0,0,0,,"
            f"{{\\pos({MARGIN_X},{CRAWL_Y})}}{pages[i % len(pages)]}"
        )
        # A short blank beat between pages so a changed page is noticeable
        # and never looks like a smear.
        t = end + 0.5
        i += 1
    body = "\n".join(lines) + "\n"

    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(header + body)
    os.replace(tmp, path)
    return len(lines)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(STATE, exist_ok=True)

    wx, live = get_weather()
    if wx is None:
        log("no forecast available and no cache — leaving existing assets alone")
        return 2

    tx = Text(OUT)
    with open(os.path.join(OUT, "card.vf"), "w") as f:
        f.write(build_card(wx, tx, live))
    for i, s in enumerate(build_slides(wx, tx), start=1):
        with open(os.path.join(OUT, f"slide{i}.vf"), "w") as f:
            f.write(s)

    upcoming = get_upcoming()
    n = build_crawl(wx, upcoming, os.path.join(OUT, "z0-crawl.ass"))

    log(f"forecast {'live' if live else 'CACHED'}; "
        f"{len(upcoming)} guide entries; {n} strip pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
