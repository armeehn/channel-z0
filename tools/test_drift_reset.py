#!/usr/bin/env python3
"""z0-drift-reset.py must name itself to the tower.

Cloudflare in front of watch.ch0 started answering the default
`Python-urllib/3.x` agent with 403 on 2026-09-16 01:45Z. The drift monitor
logged "status unreachable" every 15 minutes and measured nothing, while
curl (and the sentinel) still saw 200. The other tower clients already send
a User-Agent; this pins the one that did not.

    python3 tools/test_drift_reset.py
"""
import importlib.util
import io
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("drift", os.path.join(HERE, "z0-drift-reset.py"))
drift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drift)

seen = {}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    seen["url"] = req.full_url if hasattr(req, "full_url") else req
    seen["ua"] = req.get_header("User-agent") if hasattr(req, "get_header") else None
    return _Resp(b'{"online": true}')


urllib.request.urlopen = fake_urlopen
body = drift.fetch("/api/status")
fails = []
if body != '{"online": true}':
    fails.append("fetch did not return the body")
if seen.get("url") != drift.TOWER + "/api/status":
    fails.append("fetch hit %r" % seen.get("url"))
if not seen.get("ua") or seen["ua"].startswith("Python-urllib"):
    fails.append("fetch sends User-Agent %r; Cloudflare 403s the urllib default" % seen.get("ua"))
# the variant is wherever the master says: absolute on the CDN since the R2
# offload, relative on the tower before it, never a fixed path
master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nhttps://hls.example/hls/0/stream.m3u8\n"
if drift.variant_url(master) != "https://hls.example/hls/0/stream.m3u8":
    fails.append("absolute variant not followed: %r" % drift.variant_url(master))
if drift.variant_url("#EXTM3U\n0/stream.m3u8\n") != drift.TOWER + "/0/stream.m3u8":
    fails.append("relative variant not resolved against the tower")
try:
    drift.variant_url("#EXTM3U\n")
    fails.append("empty master accepted")
except ValueError:
    pass
seen.clear()
drift.fetch("https://hls.example/x.m3u8")
if seen.get("url") != "https://hls.example/x.m3u8":
    fails.append("absolute fetch was rewritten to %r" % seen.get("url"))
for f in fails:
    print("FAIL", f)
print("drift-reset: %s" % ("all green" if not fails else "%d failed" % len(fails)))
sys.exit(1 if fails else 0)
