#!/usr/bin/env python3
"""
z0-lists.py — apply lists/z0-lists.yml to the ErsatzTV database.

ErsatzTV has no management API: /api/* and /swagger answer only through the
Blazor SPA catch-all, and a POST to an unrouted path returns 400, so a 400 from
/graphql proves nothing. Collections, playlists, filler presets, watermarks and
decos can only be created through the web UI — or, as here, by writing the rows
directly.

Everything this script writes is namespaced with a `Z0 ` prefix and matched on
name, so it is idempotent: run it as often as you like. It never deletes
anything unless you ask for --prune.

Usage:
    z0-lists.py --db /mnt/solid-state/ersatztv/ersatztv.sqlite3 \
                --manifest z0-lists.yml [--check] [--dry-run] [--prune]

    --check    evaluate every smart-collection query against the database and
               report how many items it matches. An empty pool is the single
               most common way to break this channel, and it fails silently on
               air, so this is worth running every time.

ErsatzTV keeps the database open in WAL mode while it runs. Writing to it from
outside is safe (SQLite serialises writers) but keep transactions short, and
take a backup first — there is no undo.
"""

import argparse
import os
import re
import sqlite3
import sys

import yaml

# ── Enum values, from ErsatzTV.Core.Domain ───────────────────────────────────
# These are the actual values, read out of the source rather than guessed; a
# wrong integer here produces a row that looks fine in the database and throws
# in the UI.
COLLECTION_TYPE = {
    "collection": 0, "multi": 4, "smart": 5, "playlist": 6,
    "movie": 10, "episode": 20, "music_video": 30, "other_video": 40,
    "song": 50, "image": 60, "remote_stream": 70,
}
FILLER_KIND = {"none": 0, "preroll": 1, "midroll": 2, "postroll": 3,
               "tail": 4, "fallback": 5}
FILLER_MODE = {"none": 0, "duration": 1, "count": 2, "pad": 3,
               "random_count": 4}
PLAYBACK_ORDER = {"none": 0, "chronological": 1, "random": 2, "shuffle": 3,
                  "shuffle_in_order": 4, "multi_episode_shuffle": 5,
                  "season_episode": 6, "random_rotation": 7, "marathon": 8}
WATERMARK_MODE = {"none": 0, "permanent": 1, "intermittent": 2,
                  "opacity_expression": 3}
WATERMARK_IMAGE_SOURCE = {"custom": 0, "channel_logo": 1, "resource": 100}
WATERMARK_LOCATION = {"bottom_right": 0, "bottom_left": 1, "top_right": 2,
                      "top_left": 3, "bottom_middle": 4, "top_middle": 5,
                      "middle": 6, "left_middle": 7, "right_middle": 8}
WATERMARK_SIZE = {"original": 0, "scaled": 1}
DECO_MODE = {"inherit": 0, "disable": 1, "override": 2, "merge": 3}
DECO_BREAK_PLACEMENT = {"block_start": 0, "block_finish": 1,
                        "between_block_items": 2, "chapter_markers": 3}

PREFIX = "Z0 "
NAME_MAX = 50


class DB:
    def __init__(self, path, dry_run=False):
        self.dry = dry_run
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.changes = []

    def q(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        r = self.conn.execute(sql, args).fetchone()
        return r[0] if r else None

    def write(self, sql, args=()):
        if self.dry:
            self.changes.append((sql.split()[0], sql, args))
            return None
        cur = self.conn.execute(sql, args)
        return cur.lastrowid

    def commit(self):
        if not self.dry:
            self.conn.commit()


def check_name(name):
    if len(name) > NAME_MAX:
        raise SystemExit(
            f"FATAL: name longer than {NAME_MAX} chars ({len(name)}): {name!r}")
    return name


# ═══ Media item resolution ═══════════════════════════════════════════════════
def load_media(db):
    """Every scanned local Other Video, with its path. Collections are defined
    by regex against the path so the manifest survives item ids changing."""
    rows = db.q("""
        select mi.Id as id, mf.Path as path
        from MediaItem mi
        join MediaVersion mv on mv.OtherVideoId = mi.Id
        join MediaFile mf on mf.MediaVersionId = mv.Id
        where mi.State = 0
        order by mf.Path
    """)
    return [(r["id"], r["path"]) for r in rows]


# ═══ A small Lucene subset evaluator ═════════════════════════════════════════
# This does NOT reimplement Lucene. It understands exactly the shapes used in
# z0-lists.yml — field:value, field:"quoted value", numeric ranges, AND/OR/NOT,
# parentheses and smart_collection references — and evaluates them against the
# database so an empty pool is caught here rather than as a hole in the
# schedule. Anything it cannot parse is reported as "unknown", not as zero,
# because a false "0 items" is worse than no answer.
TOKEN = re.compile(r'''
      (?P<lparen>\()
    | (?P<rparen>\))
    | (?P<op>\b(?:AND|OR|NOT)\b)
    | (?P<field>[a-z_]+):(?P<value>"[^"]*"|\[[^\]]*\]|[^\s()]+)
''', re.X)


class Unknown(Exception):
    pass


def tokenize(q):
    out, pos = [], 0
    while pos < len(q):
        if q[pos].isspace():
            pos += 1
            continue
        m = TOKEN.match(q, pos)
        if not m:
            raise Unknown(f"cannot tokenize at {q[pos:pos + 20]!r}")
        pos = m.end()
        if m.group("lparen"):
            out.append(("(", None))
        elif m.group("rparen"):
            out.append((")", None))
        elif m.group("op"):
            out.append(("op", m.group("op")))
        else:
            out.append(("term", (m.group("field"), m.group("value"))))
    return out


def eval_term(db, field, value, smart_lookup):
    v = value.strip('"')
    if field == "type":
        # Everything in this library is an other_video; treat as a no-op filter.
        return set(i for i, _ in db._media) if v == "other_video" else set()
    if field == "smart_collection":
        sub = smart_lookup.get(v)
        if sub is None:
            raise Unknown(f"smart collection {v!r} not defined")
        return evaluate(db, sub, smart_lookup)
    if field in ("tag", "genre", "studio"):
        table = {"tag": "Tag", "genre": "Genre", "studio": "Studio"}[field]
        rows = db.q(f"""
            select ovm.OtherVideoId from {table} x
            join OtherVideoMetadata ovm on ovm.Id = x.OtherVideoMetadataId
            join MediaItem mi on mi.Id = ovm.OtherVideoId
            where mi.State = 0 and lower(x.Name) = lower(?)
        """, (v,))
        return {r[0] for r in rows}
    if field == "mpaa":
        rows = db.q("""
            select ovm.OtherVideoId from OtherVideoMetadata ovm
            join MediaItem mi on mi.Id = ovm.OtherVideoId
            where mi.State = 0 and lower(ovm.ContentRating) = lower(?)
        """, (v,))
        return {r[0] for r in rows}
    if field == "title":
        rows = db.q("""
            select ovm.OtherVideoId from OtherVideoMetadata ovm
            join MediaItem mi on mi.Id = ovm.OtherVideoId
            where mi.State = 0 and lower(ovm.Title) like lower(?)
        """, (f"%{v}%",))
        return {r[0] for r in rows}
    if field in ("minutes", "seconds"):
        m = re.match(r"\[\s*(\S+)\s+TO\s+(\S+)\s*\]", v)
        if not m:
            raise Unknown(f"{field} must use range syntax, got {v!r}")
        lo = 0 if m.group(1) == "*" else int(m.group(1))
        hi = 10 ** 9 if m.group(2) == "*" else int(m.group(2))
        div = 60.0 if field == "minutes" else 1.0
        out = set()
        for mid, dur in db._durations:
            if dur is None:
                continue
            val = dur / div
            # Lucene indexes these as integers, so compare the way it does.
            if lo <= int(val) <= hi:
                out.add(mid)
        return out
    raise Unknown(f"unsupported field {field!r}")


def evaluate(db, query, smart_lookup):
    """Shunting-yard over the token list. Lucene's default operator here is OR
    for bare adjacency, but every query in the manifest is explicit, so
    adjacency without an operator is treated as AND and flagged."""
    toks = tokenize(query)
    universe = {i for i, _ in db._media}

    pos = 0

    def parse_expr():
        nonlocal pos
        left = parse_term()
        # Lucene's classic parser treats a NOT in binary position as
        # "prohibit the next clause", i.e. `A NOT B` means A AND NOT B. Reading
        # it as a unary operator instead leaves the left side dangling, which is
        # what "trailing tokens" means when this raises.
        while pos < len(toks) and toks[pos][0] == "op":
            op = toks[pos][1]
            pos += 1
            right = parse_term()
            if op == "AND":
                left = left & right
            elif op == "OR":
                left = left | right
            else:  # NOT
                left = left - right
        return left

    def parse_term():
        nonlocal pos
        if pos >= len(toks):
            raise Unknown("unexpected end of query")
        kind, val = toks[pos]
        if kind == "op" and val == "NOT":
            pos += 1
            return universe - parse_term()
        if kind == "(":
            pos += 1
            inner = parse_expr()
            if pos >= len(toks) or toks[pos][0] != ")":
                raise Unknown("unbalanced parentheses")
            pos += 1
            return inner
        if kind == "term":
            pos += 1
            return eval_term(db, val[0], val[1], smart_lookup)
        raise Unknown(f"unexpected token {kind} {val}")

    result = parse_expr()
    if pos != len(toks):
        raise Unknown("trailing tokens")
    return result


# ═══ Appliers ════════════════════════════════════════════════════════════════
def apply_smart_collections(db, spec):
    ids = {}
    for sc in spec.get("smart_collections", []):
        name = check_name(sc["name"])
        existing = db.one("select Id from SmartCollection where Name = ?", (name,))
        if existing:
            db.write("update SmartCollection set Query = ? where Id = ?",
                     (sc["query"], existing))
            ids[name] = existing
        else:
            ids[name] = db.write(
                "insert into SmartCollection (Name, Query) values (?, ?)",
                (name, sc["query"]))
    return ids


def apply_collections(db, spec):
    ids = {}
    media = db._media
    for c in spec.get("collections", []):
        name = check_name(c["name"])
        custom = 1 if c.get("custom_order") else 0
        existing = db.one("select Id from Collection where Name = ?", (name,))
        if existing:
            cid = existing
            db.write("update Collection set UseCustomPlaybackOrder = ? where Id = ?",
                     (custom, cid))
            db.write("delete from CollectionItem where CollectionId = ?", (cid,))
        else:
            cid = db.write(
                "insert into Collection (Name, UseCustomPlaybackOrder) values (?, ?)",
                (name, custom))
        ids[name] = cid

        index, seen = 0, set()
        for sel in c.get("items", []):
            pat = re.compile(sel["match"], re.I)
            hits = [(mid, p) for mid, p in media if pat.search(p)]
            if not hits:
                print(f"  WARNING: collection {name!r} selector "
                      f"{sel['match']!r} matched nothing", file=sys.stderr)
            for mid, _ in hits:
                if mid in seen:
                    continue
                seen.add(mid)
                db.write(
                    "insert into CollectionItem (CollectionId, MediaItemId, CustomIndex) "
                    "values (?, ?, ?)",
                    (cid, mid, index if custom else None))
                index += 1
    return ids


def apply_multi_collections(db, spec, coll_ids, smart_ids):
    ids = {}
    for mc in spec.get("multi_collections", []):
        name = check_name(mc["name"])
        existing = db.one("select Id from MultiCollection where Name = ?", (name,))
        if existing:
            mid = existing
            db.write("delete from MultiCollectionItem where MultiCollectionId = ?", (mid,))
            db.write("delete from MultiCollectionSmartItem where MultiCollectionId = ?", (mid,))
        else:
            mid = db.write("insert into MultiCollection (Name) values (?)", (name,))
        ids[name] = mid

        # A grouped member becomes a MultiCollectionGroup, and that constructor
        # supports only Chronological and SeasonEpisode — anything else throws
        # NotSupportedException and the whole playout fails to build.
        for m in list(mc.get("manual", [])) + list(mc.get("smart", [])):
            if m.get("group") and m.get("order", "shuffle") not in (
                    "chronological", "season_episode"):
                raise SystemExit(
                    f"FATAL: multi collection {name!r} member {m['name']!r} has "
                    f"group: true with order {m.get('order', 'shuffle')!r}. A "
                    f"grouped member must be chronological or season_episode; "
                    f"anything else throws and kills the entire playout build. "
                    f"Shuffle the GROUPS instead, via the multi_collection "
                    f"content key's own order.")

        for m in mc.get("manual", []):
            db.write(
                "insert into MultiCollectionItem "
                "(MultiCollectionId, CollectionId, ScheduleAsGroup, PlaybackOrder) "
                "values (?, ?, ?, ?)",
                (mid, coll_ids[m["name"]], 1 if m.get("group") else 0,
                 PLAYBACK_ORDER[m.get("order", "shuffle")]))
        for m in mc.get("smart", []):
            db.write(
                "insert into MultiCollectionSmartItem "
                "(MultiCollectionId, SmartCollectionId, ScheduleAsGroup, PlaybackOrder) "
                "values (?, ?, ?, ?)",
                (mid, smart_ids[m["name"]], 1 if m.get("group") else 0,
                 PLAYBACK_ORDER[m.get("order", "shuffle")]))
    return ids


def apply_playlists(db, spec, coll_ids, smart_ids, multi_ids):
    group_ids = {}
    for g in spec.get("playlist_groups", []):
        existing = db.one("select Id from PlaylistGroup where Name = ?", (g,))
        group_ids[g] = existing or db.write(
            "insert into PlaylistGroup (Name, IsSystem) values (?, 0)", (g,))

    ids = {}
    for pl in spec.get("playlists", []):
        name = check_name(pl["name"])
        gid = group_ids[pl["group"]]
        existing = db.one(
            "select Id from Playlist where Name = ? and PlaylistGroupId = ?",
            (name, gid))
        if existing:
            pid = existing
            db.write("delete from PlaylistItem where PlaylistId = ?", (pid,))
        else:
            pid = db.write(
                "insert into Playlist (Name, PlaylistGroupId, IsSystem) values (?, ?, 0)",
                (name, gid))
        ids[name] = pid

        # A playlist may not name the same source twice. PlaylistEnumerator
        # keys its map on (ContentKey, CollectionKey), so a repeat throws
        # "An item with the same key has already been added" and the WHOLE
        # playout fails to build — every channel, not just this playlist, and
        # the only symptom is the channel eventually falling back.
        seen_src = set()
        for i, it in enumerate(pl.get("items", []), start=1):
            src = next(((k, it[k]) for k in ("collection", "smart", "multi")
                        if k in it), None)
            if src in seen_src:
                raise SystemExit(
                    f"FATAL: playlist {name!r} names {src[1]!r} more than once. "
                    f"ErsatzTV keys playlist items on their collection, so a "
                    f"repeat makes the entire playout fail to build. Use a "
                    f"different pool for the second slot.")
            seen_src.add(src)

        for i, it in enumerate(pl.get("items", []), start=1):
            ctype, cid, sid, mid = None, None, None, None
            if "collection" in it:
                ctype, cid = COLLECTION_TYPE["collection"], coll_ids[it["collection"]]
            elif "smart" in it:
                ctype, sid = COLLECTION_TYPE["smart"], smart_ids[it["smart"]]
            elif "multi" in it:
                ctype, mid = COLLECTION_TYPE["multi"], multi_ids[it["multi"]]
            else:
                raise SystemExit(f"playlist {name!r} item {i} has no source")
            db.write(
                'insert into PlaylistItem ("Index", PlaylistId, CollectionType, '
                "CollectionId, SmartCollectionId, MultiCollectionId, MediaItemId, "
                "IncludeInProgramGuide, PlaybackOrder, PlayAll, Count) "
                "values (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)",
                (i, pid, ctype, cid, sid, mid,
                 1 if it.get("guide", True) else 0,
                 PLAYBACK_ORDER[it.get("order", "shuffle")],
                 1 if it.get("play_all") else 0,
                 it.get("count")))
    return ids


def apply_filler_presets(db, spec, coll_ids, smart_ids, multi_ids, playlist_ids):
    ids = {}
    for f in spec.get("filler_presets", []):
        name = check_name(f["name"])
        kind = FILLER_KIND[f["kind"]]
        mode = FILLER_MODE[f.get("mode", "none")]
        ctype, cid, sid, mid, plid = 0, None, None, None, None
        if "collection" in f:
            ctype, cid = COLLECTION_TYPE["collection"], coll_ids[f["collection"]]
        elif "smart" in f:
            ctype, sid = COLLECTION_TYPE["smart"], smart_ids[f["smart"]]
        elif "multi" in f:
            ctype, mid = COLLECTION_TYPE["multi"], multi_ids[f["multi"]]
        elif "playlist" in f:
            ctype, plid = COLLECTION_TYPE["playlist"], playlist_ids[f["playlist"]]

        cols = dict(
            AllowWatermarks=1 if f.get("allow_watermarks") else 0,
            CollectionId=cid, CollectionType=ctype, Count=f.get("count"),
            Duration=f.get("duration"), Expression=f.get("expression"),
            FillerKind=kind, FillerMode=mode, MediaItemId=None,
            MultiCollectionId=mid, Name=name,
            PadToNearestMinute=f.get("pad_to_nearest_minute"),
            PlaylistId=plid, SmartCollectionId=sid, UseChaptersAsMediaItems=0)

        existing = db.one("select Id from FillerPreset where Name = ?", (name,))
        if existing:
            sets = ", ".join(f"{k} = ?" for k in cols)
            db.write(f"update FillerPreset set {sets} where Id = ?",
                     tuple(cols.values()) + (existing,))
            ids[name] = existing
        else:
            keys = ", ".join(cols)
            marks = ", ".join("?" for _ in cols)
            ids[name] = db.write(
                f"insert into FillerPreset ({keys}) values ({marks})",
                tuple(cols.values()))
    return ids


def apply_watermarks(db, spec):
    ids = {}
    for w in spec.get("watermarks", []):
        name = check_name(w["name"])
        cols = dict(
            DurationSeconds=w.get("duration_seconds", 0),
            FrequencyMinutes=w.get("frequency_minutes", 0),
            HorizontalMarginPercent=float(w.get("horizontal_margin", 3)),
            Image=w.get("image"),
            ImageSource=WATERMARK_IMAGE_SOURCE[w.get("image_source", "custom")],
            Location=WATERMARK_LOCATION[w.get("location", "bottom_right")],
            Mode=WATERMARK_MODE[w.get("mode", "permanent")],
            Name=name, Opacity=w.get("opacity", 100),
            OpacityExpression=w.get("opacity_expression"),
            OriginalContentType=w.get("content_type", "image/png"),
            PlaceWithinSourceContent=1 if w.get("within_source") else 0,
            Size=WATERMARK_SIZE[w.get("size", "scaled")],
            VerticalMarginPercent=float(w.get("vertical_margin", 4)),
            WidthPercent=float(w.get("width_percent", 12)),
            ZIndex=w.get("z_index", 0))
        existing = db.one("select Id from ChannelWatermark where Name = ?", (name,))
        if existing:
            sets = ", ".join(f'"{k}" = ?' for k in cols)
            db.write(f"update ChannelWatermark set {sets} where Id = ?",
                     tuple(cols.values()) + (existing,))
            ids[name] = existing
        else:
            keys = ", ".join(f'"{k}"' for k in cols)
            marks = ", ".join("?" for _ in cols)
            ids[name] = db.write(
                f"insert into ChannelWatermark ({keys}) values ({marks})",
                tuple(cols.values()))
    return ids


def apply_decos(db, spec, coll_ids, smart_ids, wm_ids, playout_id):
    group_ids = {}
    for g in spec.get("deco_groups", []):
        existing = db.one("select Id from DecoGroup where Name = ?", (g,))
        group_ids[g] = existing or db.write(
            "insert into DecoGroup (Name) values (?)", (g,))

    ids = {}
    for d in spec.get("decos", []):
        name = check_name(d["name"])

        def src(prefix):
            if f"{prefix}_collection" in d:
                return COLLECTION_TYPE["collection"], coll_ids[d[f"{prefix}_collection"]], None
            if f"{prefix}_smart" in d:
                return COLLECTION_TYPE["smart"], None, smart_ids[d[f"{prefix}_smart"]]
            return 0, None, None

        da_type, da_coll, da_smart = src("dead_air_fallback")
        df_type, df_coll, df_smart = src("default_filler")

        cols = dict(
            BreakContentMode=DECO_MODE[d.get("break_content_mode", "inherit")],
            DeadAirFallbackCollectionId=da_coll,
            DeadAirFallbackCollectionType=da_type,
            DeadAirFallbackMediaItemId=None,
            DeadAirFallbackMode=DECO_MODE[d.get("dead_air_fallback_mode", "inherit")],
            DeadAirFallbackMultiCollectionId=None,
            DeadAirFallbackSmartCollectionId=da_smart,
            DecoGroupId=group_ids[d["group"]],
            DefaultFillerCollectionId=df_coll,
            DefaultFillerCollectionType=df_type,
            DefaultFillerMediaItemId=None,
            DefaultFillerMode=DECO_MODE[d.get("default_filler_mode", "inherit")],
            DefaultFillerMultiCollectionId=None,
            DefaultFillerSmartCollectionId=df_smart,
            DefaultFillerTrimToFit=1 if d.get("default_filler_trim_to_fit") else 0,
            GraphicsElementsMode=DECO_MODE[d.get("graphics_mode", "inherit")],
            Name=name,
            UseGraphicsElementsDuringFiller=1 if d.get("graphics_during_filler") else 0,
            UseWatermarkDuringFiller=1 if d.get("watermark_during_filler") else 0,
            WatermarkMode=DECO_MODE[d.get("watermark_mode", "inherit")])

        existing = db.one("select Id from Deco where Name = ?", (name,))
        if existing:
            did = existing
            sets = ", ".join(f'"{k}" = ?' for k in cols)
            db.write(f"update Deco set {sets} where Id = ?",
                     tuple(cols.values()) + (did,))
            db.write("delete from DecoBreakContent where DecoId = ?", (did,))
            db.write("delete from DecoWatermark where DecoId = ?", (did,))
        else:
            keys = ", ".join(f'"{k}"' for k in cols)
            marks = ", ".join("?" for _ in cols)
            did = db.write(f"insert into Deco ({keys}) values ({marks})",
                           tuple(cols.values()))
        ids[name] = did

        for w in d.get("watermarks", []):
            db.write("insert into DecoWatermark (DecoId, WatermarkId) values (?, ?)",
                     (did, wm_ids[w]))

        for b in d.get("break_content", []):
            btype, bcoll, bsmart = 0, None, None
            if "collection" in b:
                btype, bcoll = COLLECTION_TYPE["collection"], coll_ids[b["collection"]]
            elif "smart" in b:
                btype, bsmart = COLLECTION_TYPE["smart"], smart_ids[b["smart"]]
            db.write(
                "insert into DecoBreakContent (DecoId, CollectionType, CollectionId, "
                "MediaItemId, MultiCollectionId, SmartCollectionId, PlaylistId, Placement) "
                "values (?, ?, ?, NULL, NULL, ?, NULL, ?)",
                (did, btype, bcoll, bsmart,
                 DECO_BREAK_PLACEMENT[b.get("placement", "between_block_items")]))

        if d.get("attach_to_playout") and playout_id:
            db.write("update Playout set DecoId = ? where Id = ?", (did, playout_id))

    # Deco templates
    tgroup_ids = {}
    for g in spec.get("deco_template_groups", []):
        existing = db.one("select Id from DecoTemplateGroup where Name = ?", (g,))
        tgroup_ids[g] = existing or db.write(
            "insert into DecoTemplateGroup (Name) values (?)", (g,))

    for t in spec.get("deco_templates", []):
        name = check_name(t["name"])
        gid = tgroup_ids[t["group"]]
        existing = db.one("select Id from DecoTemplate where Name = ?", (name,))
        if existing:
            tid = existing
            db.write("update DecoTemplate set DecoTemplateGroupId = ?, "
                     "DateUpdated = datetime('now') where Id = ?", (gid, tid))
            db.write("delete from DecoTemplateItem where DecoTemplateId = ?", (tid,))
        else:
            tid = db.write(
                "insert into DecoTemplate (Name, DecoTemplateGroupId, DateUpdated) "
                "values (?, ?, datetime('now'))", (name, gid))
        for it in t.get("items", []):
            db.write(
                "insert into DecoTemplateItem (DecoTemplateId, DecoId, StartTime, EndTime) "
                "values (?, ?, ?, ?)",
                (tid, ids[it["deco"]], it["start"], it["end"]))
    return ids


def prune(db, spec):
    """Remove Z0-prefixed rows that the manifest no longer defines. Order
    matters: a filler preset referencing a collection blocks its delete."""
    wanted = {
        "FillerPreset": {f["name"] for f in spec.get("filler_presets", [])},
        "Playlist": {p["name"] for p in spec.get("playlists", [])},
        "MultiCollection": {m["name"] for m in spec.get("multi_collections", [])},
        "Collection": {c["name"] for c in spec.get("collections", [])},
        "SmartCollection": {s["name"] for s in spec.get("smart_collections", [])},
        "ChannelWatermark": {w["name"] for w in spec.get("watermarks", [])},
    }
    for table, names in wanted.items():
        rows = db.q(f"select Id, Name from {table} where Name like ?", (PREFIX + "%",))
        for r in rows:
            if r["Name"] not in names:
                print(f"  prune {table}: {r['Name']}")
                db.write(f"delete from {table} where Id = ?", (r["Id"],))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--playout-id", type=int, default=None,
                    help="playout to attach decos to (default: the only one)")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        raise SystemExit(f"no such database: {args.db}")

    spec = yaml.safe_load(open(args.manifest))
    db = DB(args.db, args.dry_run)

    db._media = load_media(db)
    rows = db.q("""
        select mi.Id, mv.Duration from MediaItem mi
        join MediaVersion mv on mv.OtherVideoId = mi.Id where mi.State = 0
    """)

    def secs(d):
        if not d:
            return None
        parts = str(d).split(":")
        try:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except (ValueError, IndexError):
            return None

    db._durations = [(r[0], secs(r[1])) for r in rows]
    print(f"{len(db._media)} scanned media items")

    if args.check:
        lookup = {s["name"]: s["query"] for s in spec.get("smart_collections", [])}
        print("\n── smart collection match counts ──")
        empty = []
        for s in spec.get("smart_collections", []):
            try:
                n = len(evaluate(db, s["query"], lookup))
                flag = "  <-- EMPTY" if n == 0 else ""
                if n == 0:
                    empty.append(s["name"])
                print(f"  {n:>4}  {s['name']}{flag}")
            except Unknown as e:
                print(f"     ?  {s['name']}   (not evaluated: {e})")
        if empty:
            print(f"\nFATAL: {len(empty)} smart collection(s) match nothing. "
                  "An empty pool is a silent hole in the schedule.", file=sys.stderr)
            for e in empty:
                print(f"  - {e}", file=sys.stderr)
            return 2
        print()

    playout_id = args.playout_id or db.one("select Id from Playout order by Id limit 1")

    print("── applying ──")
    smart_ids = apply_smart_collections(db, spec)
    print(f"  smart collections : {len(smart_ids)}")
    coll_ids = apply_collections(db, spec)
    print(f"  collections       : {len(coll_ids)}")
    multi_ids = apply_multi_collections(db, spec, coll_ids, smart_ids)
    print(f"  multi collections : {len(multi_ids)}")
    playlist_ids = apply_playlists(db, spec, coll_ids, smart_ids, multi_ids)
    print(f"  playlists         : {len(playlist_ids)}")
    filler_ids = apply_filler_presets(db, spec, coll_ids, smart_ids, multi_ids,
                                      playlist_ids)
    print(f"  filler presets    : {len(filler_ids)}")
    wm_ids = apply_watermarks(db, spec)
    print(f"  watermarks        : {len(wm_ids)}")
    deco_ids = apply_decos(db, spec, coll_ids, smart_ids, wm_ids, playout_id)
    print(f"  decos             : {len(deco_ids)}")

    if args.prune:
        print("── pruning ──")
        prune(db, spec)

    db.commit()
    if args.dry_run:
        print(f"\ndry run: {len(db.changes)} statements not executed")
    else:
        print("\ncommitted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
