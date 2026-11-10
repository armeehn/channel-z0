#!/usr/bin/env python3
"""z0-promos.py must read the shop through the Storefront API.

Shopify's bot protection started answering `/products.json` with
`429 local_rate_limited` (retry-after 60) on 2026-11-08: unsigned automated
clients on storefront routes are rate limited on the first request, whatever
they call themselves. The weekly promo refresh died there. The Storefront
GraphQL API is the supported machine route and answers without a token.

    python3 tools/test_promos_fetch.py
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("promos", os.path.join(HERE, "z0-promos.py"))
promos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promos)

CDN = "https://cdn.shopify.com/s/files/1/0000/"
SECOND_PAGE_CURSOR = "cursor-page-2"
seen = []


def node(handle, title, low, high, image):
    images = [{"url": CDN + image + "?v=1"}] if image else []
    return {"handle": handle, "title": title,
            "priceRange": {"minVariantPrice": {"amount": low},
                           "maxVariantPrice": {"amount": high}},
            "images": {"nodes": images}}


PAGES = {
    None: {"pageInfo": {"hasNextPage": True, "endCursor": SECOND_PAGE_CURSOR},
           "nodes": [node("tee", "Z0 Tee", "28.0", "34.0", "tee.png"),
                     node("tote", "Z0 Tote", "18.0", "18.0", "tote.png")]},
    SECOND_PAGE_CURSOR: {"pageInfo": {"hasNextPage": False, "endCursor": None},
                         "nodes": [node("pin", "Z0 Pin", "4.5", "4.5", None)]},
}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    url = req.full_url
    seen.append((req.get_method(), url, req.get_header("User-agent")))

    if "/products.json" in url:
        raise AssertionError("fetch still reads /products.json, which Shopify rate limits")
    if url.startswith(promos.SHOP_URL + "/api/"):
        cursor = json.loads(req.data)["variables"].get("after")
        return _Resp(json.dumps({"data": {"products": PAGES[cursor]}}).encode())
    if url.startswith(promos.API_URL):
        return _Resp(b'{"projects": [], "software": []}')
    return _Resp(b"png")


urllib.request.urlopen = fake_urlopen
fails = []

with tempfile.TemporaryDirectory() as feed:
    try:
        promos.fetch(feed)
    except AssertionError as e:
        fails.append(str(e))
    else:
        products, _entries = promos.load_feed(feed)
        by_handle = {p["handle"]: p for p in products}

        if sorted(by_handle) != ["pin", "tee", "tote"]:
            fails.append("both pages were not read: got %r" % sorted(by_handle))
        if promos.price_of(by_handle.get("tee", {"variants": []})) != "from CA$28":
            fails.append("a price range must read 'from CA$28'")
        if promos.price_of(by_handle.get("tote", {"variants": []})) != "CA$18":
            fails.append("a single price must read 'CA$18'")
        if promos.price_of(by_handle.get("pin", {"variants": []})) != "CA$4.50":
            fails.append("a fractional price must keep its cents")
        if not os.path.exists(os.path.join(feed, "images", "tee.png")):
            fails.append("the product image was not mirrored")
        if os.path.exists(os.path.join(feed, "images", "pin.png")):
            fails.append("a product with no image got one")

posts = [s for s in seen if s[0] == "POST" and "/graphql.json" in s[1]]
if len(posts) != len(PAGES):
    fails.append("expected %d Storefront API calls, saw %d" % (len(PAGES), len(posts)))
if any((s[1] == CDN + "tee.png?v=1") for s in seen):
    fails.append("the image URL kept its ?v= query")
if any(not s[2] or s[2].startswith("Python-urllib") for s in seen):
    fails.append("a request went out without the tool's own User-Agent")

if fails:
    print("FAIL")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok: promos fetch reads the Storefront API, paginates, keeps the feed shape")
