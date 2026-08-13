#!/usr/bin/env python3
"""
z0-nfo.py — give every file in the Channel Z0 library real metadata.

Channel Z0's library is one "Other Videos" library path. ErsatzTV gives an
Other Video *no* metadata beyond the file name: Year, Genre, Studio, Director
and Plot are all empty, and the on-screen title is the raw file stem, brackets
and archive.org identifiers included. The programme guide therefore reads

    Betty Boop Barnacle Bill (1930) [BettyBoopBarnacleBill1930]

and no query can ask for "a 1930s cartoon" because nothing knows what year it
is.

ErsatzTV *does* read an NFO sidecar for Other Videos (OtherVideoNfoReader), so
this script writes one `<file>.nfo` next to every media file, carrying a clean
title, a year, genres, studios, tags and a short factual outline.

  ── THE TRAP THIS SCRIPT EXISTS TO AVOID ───────────────────────────────────
  Folder tags and NFO tags are the SAME FIELD, and the NFO wins.

  With no sidecar, ErsatzTV tags an Other Video with the folder names above it
  (`movies/noir/x.mp4` -> tags `media`, `movies`, `noir`). The moment a sidecar
  appears, LocalMetadataProvider.ApplyMetadataUpdate calls
  UpdateMetadataCollections, which *removes every existing tag that the
  incoming metadata does not list* before adding the new ones. RefreshFallback
  Metadata — the thing that derives tags from folders — is only called when
  there is NO nfo file at all.

  So an NFO that forgets `<tag>noir</tag>` silently deletes the tag the whole
  schedule is built on. `tag:noir` then matches nothing, the pool is empty, and
  an empty pool is skipped in silence — a hole in the playout, not an error.

  This script therefore reads the CURRENT tags out of the ErsatzTV database and
  re-emits every one of them verbatim, then adds its own on top. Never write
  these files by hand, and never add a tag rule without running --verify after
  the rescan.
  ───────────────────────────────────────────────────────────────────────────

Usage:
    z0-nfo.py --inventory inventory.json --media-root /mnt/main-data/channelz0 \
              [--dry-run] [--report report.csv] [--clean]

`--media-root` is where the files live as seen from THIS machine; the paths in
the inventory are container paths (/media/...) and are rewritten onto it.
"""

import argparse
import csv
import json
import os
import re
import sys
from xml.sax.saxutils import escape

# ── Year ──────────────────────────────────────────────────────────────────────
# Prefer a parenthesised year: it is the convention in this library and it beats
# the false positives ("Chapter 10", "DVD-6605", "#5530"). Only fall back to a
# bare token when it is a plausible film year, and never accept one that is part
# of a longer number.
YEAR_PAREN = re.compile(r"\((1[89]\d{2}|20[0-2]\d)\)")
YEAR_BARE = re.compile(r"(?<![\d#-])(1[89]\d{2}|20[0-2]\d)(?![\d])")


# A handful of files carry no year at all. These are the ones whose date is not
# in dispute; everything else is left blank rather than guessed, because a wrong
# year on screen is worse than no year.
YEAR_OVERRIDES = {
    "a bucket of blood": 1959,
    "the day of the triffids": 1963,
    "the giant gila monster": 1959,
    "little nemo": 1911,
    "moonlight for two": 1931,
    "hittin the trail for hallelujah land": 1931,
    "the green hornet chapter 10": 1940,
    "prehistoric women": 1950,
}


def extract_year(stem):
    m = YEAR_PAREN.findall(stem)
    if m:
        # "Lilac Time (1928) (1928)" — identical repeats are common; take the first
        return int(m[0])
    m = YEAR_BARE.findall(stem)
    if m:
        return int(m[0])
    return None


# ── Title ─────────────────────────────────────────────────────────────────────
BRACKET_ID = re.compile(r"\s*\[[^\]]*\]\s*")
PAREN_YEAR = re.compile(r"\s*\((1[89]\d{2}|20[0-2]\d)\)\s*")
MULTISPACE = re.compile(r"\s{2,}")


def clean_title(stem):
    t = BRACKET_ID.sub(" ", stem)
    t = PAREN_YEAR.sub(" ", t)
    t = MULTISPACE.sub(" ", t).strip(" -_.")
    # "Arctic Giant, The" -> "The Arctic Giant"; the guide sorts on sort_title,
    # so the display title should read the way a person would say it.
    m = re.match(r"^(.*), (The|A|An)$", t)
    if m:
        t = f"{m.group(2)} {m.group(1)}"
    return t or stem


ARTICLE = re.compile(r"^(the|a|an)\s+", re.I)


def sort_title(title, chapter=None, series=None):
    """Sort title drives `order: chronological`. For serials we bury a
    zero-padded chapter number in it so a serial plays in story order rather
    than alphabetically ("Chapter 10" before "Chapter 3")."""
    if series and chapter is not None:
        return f"{series.lower()} {chapter:03d}"
    return ARTICLE.sub("", title).lower()


# ── Series recognition ────────────────────────────────────────────────────────
# (regex, series name, slug, studio-or-None, extra genres, extra tags)
# A studio is asserted ONLY where the file name states it or the attribution is
# unambiguous for the whole run of the series. Where a series changed hands
# mid-run (Popeye and Superman both moved from Fleischer to Famous Studios in
# 1942) no studio is claimed at all — a wrong credit on screen is worse than a
# missing one.
SERIES_RULES = [
    (r"betty\s*boop", "Betty Boop", "betty-boop", "Fleischer Studios",
     ["Animation", "Comedy"], ["fleischer"]),
    (r"\bbosko\b", "Bosko", "bosko", "Harman-Ising Productions",
     ["Animation", "Comedy"], ["harman-ising"]),
    (r"felix\s+(the\s+cat|in\b|goes)", "Felix the Cat", "felix-the-cat", None,
     ["Animation", "Comedy"], []),
    (r"\bpopeye\b|spooky\s+swabs", "Popeye", "popeye", None,
     ["Animation", "Comedy"], []),
    (r"superman|arctic\s+giant|japoteurs|jungle\s+drums|mechanical\s+monsters|terror\s+on\s+the\s+midway",
     "Superman", "superman", None, ["Animation", "Adventure"], []),
    (r"merrie\s+melodies|bugs\s+bunny|wabbit|corny\s+concerto",
     "Merrie Melodies", "merrie-melodies", "Warner Bros.",
     ["Animation", "Comedy"], []),
    (r"private\s+snafu|pvt\.?\s*snafu", "Private Snafu", "private-snafu",
     "U.S. Army Signal Corps", ["Animation", "Propaganda"], ["wwii"]),
    (r"ub\s+iwerks|toby\s+the\s+pup|soup\s+song|little\s+orphan\s+willie",
     "Ub Iwerks", "ub-iwerks", "Ub Iwerks Studio", ["Animation"], []),
    (r"tom\s+and\s+jerry", "Van Beuren Tom and Jerry", "van-beuren-tom-jerry",
     None, ["Animation", "Comedy"], []),
    (r"why\s+we\s+fight", "Why We Fight", "why-we-fight", None,
     ["Documentary", "Propaganda"], ["wwii"]),
    (r"rin\s+tin\s+tin", "Rin Tin Tin", "rin-tin-tin", None,
     ["Serial", "Adventure"], []),
    (r"soundie", "Soundies", "soundies", None, ["Musical Short"], ["music"]),
    (r"snader\s+telescription", "Snader Telescriptions", "snader", None,
     ["Musical Short"], ["music"]),
    (r"march\s+of\s+time", "The March of Time", "march-of-time", None,
     ["Newsreel", "Documentary"], ["newsreel"]),
    (r"movietone", "Movietone News", "movietone", None,
     ["Newsreel"], ["newsreel"]),
    (r"industry\s+on\s+parade", "Industry on Parade", "industry-on-parade",
     None, ["Industrial", "Documentary"], []),
    (r"stillman\s+fires", "Stillman Fires Collection", "stillman-fires", None,
     ["Industrial"], []),
    (r"oldsmobile\s+playlets|olds\s+minute\s+movies", "Oldsmobile Playlets",
     "oldsmobile-playlets", None, ["Advertising"], []),
]

# ── Serial chapters ───────────────────────────────────────────────────────────
# Serial chapter numbers live in the title; pulling them out lets a serial run in
# story order and lets the guide say "Chapter 8" instead of the whole file name.
CHAPTER_PATTERNS = [
    re.compile(r"\bchapter\s+(\d+)\b", re.I),
    re.compile(r"\bpart\s+(\d+)\b", re.I),
    re.compile(r"\bep(?:isode)?\s*(\d+)\b", re.I),
]
SERIAL_TITLES = [
    (r"green\s+archer", "The Green Archer", "green-archer"),
    (r"green\s+hornet", "The Green Hornet", "green-hornet"),
    (r"holt\s+of\s+the\s+secret\s+service", "Holt of the Secret Service", "holt"),
    (r"junior\s+g-?men", "Junior G-Men", "junior-g-men"),
    (r"mystery\s+squadron", "Mystery Squadron", "mystery-squadron"),
    (r"phantom\s+empire", "The Phantom Empire", "phantom-empire"),
    (r"radar\s+men", "Radar Men From the Moon", "radar-men"),
    (r"robinson\s+crusoe\s+of\s+clipper\s+island", "Robinson Crusoe of Clipper Island", "clipper-island"),
    (r"shadow\s+of\s+chinatown", "Shadow of Chinatown", "shadow-of-chinatown"),
    (r"fighting\s+marines", "The Fighting Marines", "fighting-marines"),
    (r"whispering\s+shadow", "The Whispering Shadow", "whispering-shadow"),
    (r"lightning\s+warrior", "The Lightning Warrior", "lightning-warrior"),
    (r"lone\s+defender", "The Lone Defender", "lone-defender"),
]

# ── Content rating ────────────────────────────────────────────────────────────
# Z0 has no ratings board; `mpaa` is used purely as a daypart gate so the
# schedule can say "nothing rated Z0-LATE before 11pm" in one clause instead of
# blacklisting titles one at a time.
#
# These four burlesque reels and the exploitation ("square-up") features were
# airing inside daytime SHORT SUBJECTS and afternoon feature blocks, because the
# only thing the schedule knew about them was the folder they sat in.
LATE_PATTERNS = [
    r"^stripper", r"betty\s+rowland", r"georgia\s+sothern", r"red-?headed\s+riot",
    r"sex\s+madness", r"slaves\s+in\s+bondage", r"test\s+tube\s+babies",
    r"confessions\s+of\s+a\s+vice\s+baron", r"maniac", r"blonde\s+captive",
    r"prehistoric\s+women", r"werewolf\s+in\s+a\s+girls",
]

# Modern fan animation (MAP / PMV "Warrior Cats" edits and friends) that arrived
# in a bulk download. Not public domain, not vintage, and not what this channel
# is. Tagged rather than deleted so the decision stays the operator's, but every
# curated pool excludes `review-nonpd`.
NONPD_PATTERNS = [
    r"warrior\s*cats", r"\bmap\b\s*(\[|complete|$)", r"complete\s+map", r"\bpmv\b",
    r"\bmep\b", r"mistystar", r"feathertail", r"nightcloud", r"scourge",
    r"hollyleaf", r"firestar", r"thistleclaw", r"snowfur", r"yellowfang",
    r"mapleshade", r"brightheart", r"teen\s+titans", r"world\s+of\s+warcraft",
    r"shipping\s+map", r"seventeen\s*\[?\]?\s*complete", r"viva\s+la\s+vida",
    r"skinny\s+love", r"ghost\s+city\s+tokyo", r"battle\s+cry",
    r"on\s+the\s+run", r"labyrinth\s+map", r"silent\s+night.*mini\s+map",
    r"ebenezer\s+scourge", r"^burn\b", r"young\s+folks",
    # Not fan-edits, but modern amateur uploads of unknown provenance that
    # arrived in the same bulk download. Z0-REVIEW means "an operator should
    # look at this", not "delete it" — but an unattended channel should not be
    # airing anything whose licence nobody has established.
    r"^wow tv", r"pirates and ninjas", r"^cat$", r"^rounnd$",
]

# Subject tags — these are what turn a flat folder into a schedule you can
# actually programme against ("a railway film", "something about aviation").
SUBJECT_RULES = [
    (r"train|railroad|railway|locomotive|clipper", "subject-rail"),
    (r"helicopter|aviation|lockheed|squadron|flight|rocket|moon", "subject-flight"),
    (r"nazi|war\s+comes|battle\s+of|bataan|tojo|japoteurs|snafu|why\s+we\s+fight|prisoners\s+return|torpedoed|star-spangled",
     "subject-wwii"),
    (r"atom|science|laboratory|triffids|unknown\s+world|things\s+to\s+come", "subject-science"),
    (r"golden\s+gate|san\s+francisco|new\s+york|story\s+of\s+a\s+city|desert\s+empire|golden\s+gate\s+city",
     "subject-cities"),
    (r"school|classroom|responsibility|courtesy|playing\s+together|social\s+class|leap\s+frog",
     "subject-schoolroom"),
    (r"christmas|snowman|silent\s+night|santa", "seasonal-christmas"),
    (r"ghost|spook|monster|zombie|vampire|werewolf|gila|gorgon|frankenstein|devil|haunt|witch|blood|maniac|castle\s+of\s+freaks|arctic\s+giant",
     "seasonal-halloween"),
]

# The music library is filed "Artist - Track". Pulling the artist out gives the
# guide a sensible title and gives the schedule an `artist-*` tag to build a
# music strand from — Other Videos have no artist field of their own.
MUSIC_SPLIT = re.compile(r"^(.{2,60}?)\s+-\s+(.+)$")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


FOLDER_GENRES = {
    "cartoons": ["Animation"],
    "prelinger": ["Educational", "Short"],
    "psas": ["Short"],
    "noir": ["Film Noir", "Crime", "Feature"],
    "scifi": ["Science Fiction", "Horror", "Feature"],
    "docs": ["Documentary", "Feature"],
    "serials": ["Serial", "Adventure"],
    "classics": ["Classic", "Feature"],
    "cult": ["Cult", "Exploitation", "Feature"],
    "slowtv": ["Feature"],
    "interstitials": ["Station"],
    "bumpers": ["Station"],
    "weather": ["Station", "Weather"],
    "bc": ["Regional", "Documentary"],
    "music": ["Music"],
}

# Curated one-liners for titles worth introducing properly. Everything not
# listed here gets a formula line built from what the file itself states — a
# guide entry that is honestly generic beats one that is confidently wrong.
OUTLINES = {
    "detour": "Edgar G. Ulmer's hitchhiking noir, shot fast and cheap and never bettered.",
    "things to come": "H. G. Wells adapts his own future history; designed and directed by William Cameron Menzies.",
    "white zombie": "Bela Lugosi as 'Murder' Legendre in the first feature-length zombie picture.",
    "a bucket of blood": "Roger Corman's beatnik horror comedy about a busboy who becomes a sculptor.",
    "the day of the triffids": "John Wyndham's walking plants, adapted for the screen.",
    "he walked by night": "Semi-documentary police procedural whose radio-car cadence became Dragnet.",
    "the great flamarion": "Anthony Mann directs Erich von Stroheim as a vaudeville marksman.",
    "the suspect": "Charles Laughton in a quiet Edwardian murder story directed by Robert Siodmak.",
    "ministry of fear": "Fritz Lang's wartime thriller, from the Graham Greene novel. Portuguese subtitles.",
    "the mad magician": "Vincent Price in stage-magic horror, shot for 3-D. Portuguese subtitles.",
    "inner sanctum": "Small-town suspense spun off the radio anthology of the same name.",
    "trapped": "Counterfeiting procedural, restored.",
    "oliver twist": "The Dickens novel, in an early sound version.",
    "becky sharp": "The first feature shot in three-strip Technicolor.",
    "when a man loves": "John Barrymore and Dolores Costello in a late silent from Warner Bros.",
    "lilac time": "Late-silent aviation romance. The print is interlaced and upscaled; it is the roughest picture on the channel.",
    "the nazi plan": "Evidence film assembled for the Nuremberg prosecution from German footage.",
    "war comes to america": "The last of Frank Capra's Why We Fight series.",
    "chang a drama of the wilderness": "Cooper and Schoedsack in Siam, four years before they made King Kong.",
    "africa speaks": "An expedition travelogue of its period, narration and attitudes included.",
    "the american west of john ford": "Ford talks about his own westerns, with Fonda, Stewart and Wayne.",
    "design for dreaming": "The 1956 Motorama dream: a kitchen of the future, sung.",
    "a is for atom": "General Electric explains the atom to the public, cheerfully.",
    "the phantom empire": "Gene Autry sings, rides, and descends into the underground city of Murania.",
    "the johnny cash show": "The ABC variety hour, as broadcast 4 November 1970.",
    "timetable": "Insurance-investigator noir with a train robbery at its centre.",
    "big trains rolling": "Steam and early diesel on the American main line.",
    "this is my railroad": "Southern Pacific shows off its own network.",
    "the lawless train": "Silent melodrama with Wallace Beery and Louise Brooks.",
}


def match_first(patterns, text):
    for p in patterns:
        if re.search(p, text, re.I):
            return True
    return False


def decade_tag(year):
    if not year:
        return None
    return f"era-{year // 10 * 10}s"


def build(item, media_root):
    path = item["path"]
    rel = path[len("/media/"):] if path.startswith("/media/") else path.lstrip("/")
    stem = os.path.splitext(os.path.basename(path))[0]
    folders = os.path.dirname(rel).split("/") if os.path.dirname(rel) else []

    # Some files use underscores where the rest of the library uses spaces
    # ("The_Green_Hornet_-_Chapter_10"). Match against a normalised form or
    # every series and chapter rule below silently misses them.
    stem = re.sub(r"_+", " ", stem)

    existing_tags = [t for t in (item.get("tags") or "").split("\x1f") if t]

    year = extract_year(stem)
    title = clean_title(stem)
    low = stem.lower()
    if year is None:
        for k, v in YEAR_OVERRIDES.items():
            if k in title.lower():
                year = v
                break

    genres, studios, tags, directors = [], [], list(existing_tags), []
    series = series_slug = None

    # Series
    for pat, name, slug, studio, g, extra in SERIES_RULES:
        if re.search(pat, low, re.I):
            series, series_slug = name, slug
            if studio:
                studios.append(studio)
            genres += g
            tags += extra
            tags.append(f"series-{slug}")
            break

    # The file names for the Harman-Ising and Iwerks shorts carry their own
    # credits; use them rather than guessing.
    if re.search(r"hugh\s+harman", low):
        directors.append("Hugh Harman")
    if re.search(r"rudol[fp]\s+ising", low):
        directors.append("Rudolf Ising")
    if re.search(r"ub\s+iwerks", low):
        directors.append("Ub Iwerks")
    # Roughly half the Harman-Ising shorts here are not named "Bosko" ("Box Car
    # Blues", "Yodeling Yokels", "Hold Anything"), so the series rule misses
    # them — but every one of them names its directors in the file name. Credit
    # the studio off the directors rather than off the title.
    if {"Hugh Harman", "Rudolf Ising"} & set(directors):
        studios.append("Harman-Ising Productions")
        tags.append("harman-ising")
        genres += ["Animation", "Comedy"]
    if "Ub Iwerks" in directors:
        studios.append("Ub Iwerks Studio")
        genres += ["Animation"]

    # Serial chapter
    chapter = None
    serial_name = serial_slug = None
    for pat, name, slug in SERIAL_TITLES:
        if re.search(pat, low, re.I):
            serial_name, serial_slug = name, slug
            break
    if serial_slug:
        for cp in CHAPTER_PATTERNS:
            m = cp.search(stem)
            if m:
                chapter = int(m.group(1))
                break
        tags.append(f"serial-{serial_slug}")
        if chapter is not None:
            tags.append(f"chapter-{chapter:02d}")

    # Folder genres
    for f in folders:
        genres += FOLDER_GENRES.get(f, [])

    # ── The two folders nobody has ever put on air ────────────────────────────
    # Both arrived in the library without metadata and without a slot in the
    # schedule, so the channel has never played a frame of either.
    artist = None
    if "music" in folders:
        m = MUSIC_SPLIT.match(title)
        if m:
            artist = m.group(1).strip()
            tags.append(f"artist-{slugify(artist)}")
        genres += ["Music", "Folk"]
        tags.append("canada")
        if re.search(r"\bpolka\b", low):
            genres.append("Polka")
            tags.append("polka")
        if re.search(r"\bwaltz\b", low):
            genres.append("Waltz")
            tags.append("waltz")
        if re.search(r"\breel\b|breakdown|fiddle", low):
            tags.append("fiddle")

    # ── Contested copyright: the NFB shorts ──────────────────────────────────
    # As a federal agency the NFB's pre-1976 output should be public domain in
    # Canada under Crown copyright (s.12, 50 years). No court has ruled, and the
    # NFB actively asserts and licenses this exact catalogue. The question is
    # open with the user, so anything filed under an `nfb` folder is tagged and
    # rated for review — which keeps it out of every curated pool by default,
    # independently of whether someone remembers to write `NOT tag:nfb`.
    if "nfb" in folders:
        tags.append("nfb")

    if "canada" in folders or "bc" in folders:
        genres += ["Regional", "Archival"]
        tags.append("canada")

    if "bc" in folders:
        tags.append("bc")
        if "vancouver" in folders:
            studios.append("City of Vancouver Archives")
            tags.append("vancouver")
        # Kenneth J. Bishop's Central Films made twelve "quota quickie"
        # features for Columbia at Willows Park, Victoria, 1935-37. Three are
        # here, and they are the only BC-MADE narrative features in the
        # library — everything else Canadian is archive or documentary footage.
        if "features" in folders:
            studios.append("Central Films")
            genres += ["Feature"]
            tags.append("bc-made")
        for pat, tag in [(r"stanley\s+park", "subject-stanley-park"),
                         (r"parade|grey\s+cup|pne", "subject-parade"),
                         (r"empire\s+games|polo|swimming", "subject-sport"),
                         (r"royal\s+visit|king\s+george|jubilee", "subject-ceremony")]:
            if re.search(pat, low, re.I):
                tags.append(tag)

    # Era
    dt = decade_tag(year)
    if dt:
        tags.append(dt)

    # Subjects
    for pat, tag in SUBJECT_RULES:
        if re.search(pat, low, re.I):
            tags.append(tag)

    # Daypart gate
    nonpd = match_first(NONPD_PATTERNS, low) or "nfb" in folders
    late = match_first(LATE_PATTERNS, low)
    if nonpd:
        tags.append("review-nonpd")
        rating = "Z0-REVIEW"
    elif late:
        tags.append("daypart-late")
        rating = "Z0-LATE"
    else:
        rating = "Z0-GENERAL"

    # Station furniture is never "programming"; mark it so pools can exclude it.
    if any(f in ("bumpers", "interstitials", "weather") for f in folders):
        tags.append("station-furniture")
        rating = "Z0-STATION"

    if re.search(r"noaudio|no\s+audio", low):
        tags.append("no-audio")

    # Outline
    key = title.lower()
    outline = None
    for k, v in OUTLINES.items():
        if k in key:
            outline = v
            break
    if not outline:
        if serial_name and chapter is not None:
            outline = f"Chapter {chapter} of the serial {serial_name}."
        elif series:
            outline = f"A {series} short." if not year else f"A {series} short from {year}."
        elif "music" in folders:
            outline = f"{artist} performs." if artist else "Prairie dance-band recording."
        elif "bc" in folders:
            outline = "Vancouver on film, from the City of Vancouver Archives."
            if year:
                outline = f"Vancouver on film, {year}, from the City of Vancouver Archives."
        elif "prelinger" in folders:
            outline = "Sponsored, educational or industrial short film."
            if year:
                outline = f"Sponsored, educational or industrial short film, {year}."
        elif "psas" in folders:
            outline = "Vintage advertising, newsreel or short subject."
            if year:
                outline = f"Vintage advertising, newsreel or short subject, {year}."
        elif "cartoons" in folders:
            outline = "Vintage animated short." if not year else f"Vintage animated short, {year}."
        elif year:
            outline = f"Feature presentation, {year}."
        else:
            outline = "Feature presentation."

    # Dedupe, preserving order
    def uniq(seq):
        seen, out = set(), []
        for x in seq:
            if x and x.lower() not in seen:
                seen.add(x.lower())
                out.append(x)
        return out

    return {
        "id": item["id"],
        "rel": rel,
        "nfo": os.path.join(media_root, os.path.splitext(rel)[0] + ".nfo"),
        "title": title,
        "year": year,
        "sorttitle": sort_title(title, chapter, serial_slug),
        "genres": uniq(genres),
        "studios": uniq(studios),
        "directors": uniq(directors),
        "tags": uniq(tags),
        "rating": rating,
        "outline": outline,
        "series": series or serial_name or "",
        "chapter": chapter,
        "existing_tags": existing_tags,
    }


def to_xml(rec):
    L = ['<?xml version="1.0" encoding="utf-8" standalone="yes"?>', "<movie>"]
    L.append(f"  <title>{escape(rec['title'])}</title>")
    L.append(f"  <sorttitle>{escape(rec['sorttitle'])}</sorttitle>")
    if rec["year"]:
        L.append(f"  <year>{rec['year']}</year>")
    L.append(f"  <mpaa>{escape(rec['rating'])}</mpaa>")
    if rec["outline"]:
        L.append(f"  <outline>{escape(rec['outline'])}</outline>")
        L.append(f"  <plot>{escape(rec['outline'])}</plot>")
    for g in rec["genres"]:
        L.append(f"  <genre>{escape(g)}</genre>")
    for s in rec["studios"]:
        L.append(f"  <studio>{escape(s)}</studio>")
    for d in rec["directors"]:
        L.append(f"  <director>{escape(d)}</director>")
    for t in rec["tags"]:
        L.append(f"  <tag>{escape(t)}</tag>")
    L.append("</movie>")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory",
                    help="JSON export of the ErsatzTV library (id, path, tags). "
                         "Preferred: it is the only way to know the tags a file "
                         "already carries in the database.")
    ap.add_argument("--scan-fs", action="store_true",
                    help="walk --media-root instead of reading an inventory. "
                         "Tags are derived from the folder chain, exactly as "
                         "ErsatzTV's own fallback provider derives them, so new "
                         "files that have never been scanned are handled "
                         "correctly. Use this from cron after a download run.")
    ap.add_argument("--media-root", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report")
    ap.add_argument("--clean", action="store_true",
                    help="delete generated .nfo files instead of writing them")
    args = ap.parse_args()

    if not args.inventory and not args.scan_fs:
        raise SystemExit("need --inventory or --scan-fs")

    items = json.load(open(args.inventory)) if args.inventory else []
    if args.scan_fs:
        # ErsatzTV tags an Other Video with the folder names above it, relative
        # to the library path's PARENT — so /media/movies/noir/x.mp4 carries
        # "media", "movies", "noir". Reproduce that exactly for files the
        # inventory does not know about yet.
        known = {i["path"] for i in items}
        exts = {".mp4", ".mkv", ".avi", ".mpg", ".mpeg", ".m4v", ".webm", ".mov", ".ts"}
        for dirpath, _, files in os.walk(args.media_root):
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() not in exts:
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, args.media_root)
                if rel.startswith("."):
                    continue
                cpath = "/media/" + rel.replace(os.sep, "/")
                if cpath in known:
                    continue
                chain = ["media"] + os.path.dirname(rel).split(os.sep) if os.path.dirname(rel) else ["media"]
                items.append({
                    "id": None, "path": cpath, "duration": None,
                    "title": os.path.splitext(fn)[0],
                    "tags": "\x1f".join([c for c in chain if c]),
                })

    recs = [build(i, args.media_root) for i in items]

    # The inventory is a snapshot of the DATABASE, which still lists items whose
    # files have been deleted (the scanner only flags them missing on its next
    # pass). Writing a sidecar for one of those would resurrect metadata for a
    # file that is deliberately gone — and, worse, leave an orphan .nfo that
    # looks authoritative. Only ever write beside media that is actually there.
    missing = [r for r in recs
               if not os.path.exists(os.path.join(
                   args.media_root, r["rel"]))]
    if missing:
        print(f"skipping {len(missing)} record(s) whose media file no longer "
              f"exists:")
        for r in missing[:10]:
            print(f"  {r['rel']}")
    recs = [r for r in recs
            if os.path.exists(os.path.join(args.media_root, r["rel"]))]

    # Guard: every tag the database currently holds must survive into the NFO.
    # A dropped tag is a silently empty content pool, so this is fatal, not a
    # warning.
    lost = [(r["rel"], set(r["existing_tags"]) - set(r["tags"])) for r in recs]
    lost = [(p, t) for p, t in lost if t]
    if lost:
        print("FATAL: these files would lose tags:", file=sys.stderr)
        for p, t in lost[:20]:
            print(f"  {p}: {sorted(t)}", file=sys.stderr)
        return 2

    if args.report:
        with open(args.report, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["rel", "title", "year", "series", "chapter", "rating",
                        "genres", "studios", "directors", "tags"])
            for r in recs:
                w.writerow([r["rel"], r["title"], r["year"] or "", r["series"],
                            r["chapter"] if r["chapter"] is not None else "",
                            r["rating"], "|".join(r["genres"]),
                            "|".join(r["studios"]), "|".join(r["directors"]),
                            "|".join(r["tags"])])

    written = removed = 0
    for r in recs:
        if args.clean:
            if os.path.exists(r["nfo"]):
                if not args.dry_run:
                    os.remove(r["nfo"])
                removed += 1
            continue
        xml = to_xml(r)
        if args.dry_run:
            written += 1
            continue
        # Write-temp + rename: ErsatzTV's scanner may be reading this directory,
        # and a torn read is a file it treats as invalid metadata.
        tmp = r["nfo"] + ".tmp"
        os.makedirs(os.path.dirname(r["nfo"]), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(xml)
        os.replace(tmp, r["nfo"])
        written += 1

    if args.clean:
        print(f"removed {removed} nfo files{' (dry run)' if args.dry_run else ''}")
    else:
        years = sum(1 for r in recs if r["year"])
        print(f"{'would write' if args.dry_run else 'wrote'} {written} nfo files")
        print(f"  years resolved : {years}/{len(recs)}")
        print(f"  rated LATE     : {sum(1 for r in recs if r['rating'] == 'Z0-LATE')}")
        print(f"  flagged REVIEW : {sum(1 for r in recs if r['rating'] == 'Z0-REVIEW')}")
        print(f"  with a series  : {sum(1 for r in recs if r['series'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
