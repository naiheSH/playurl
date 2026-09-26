"""Search the public Qishui catalog and print track IDs. No login or cookie."""
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

URL = "https://api-vehicle.volcengine.com/v2/search/type"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"


SPLIT = re.compile(r"[\s,，、/|]+")
NOISE = re.compile(r"[\s\-—_()（）【】\[\]·.。,，、/|]+")
LIVE = re.compile(r"live|现场|演唱会|cover|翻唱|伴奏|纯音乐|dj|remix", re.I)


def norm(value):
    return NOISE.sub("", str(value or "")).casefold()


def tokens(keywords):
    return [item for item in SPLIT.split(str(keywords or "").strip()) if item]


def rank(song, keywords):
    norms = [norm(item) for item in tokens(keywords)]
    name = norm(song.get("name"))
    artist = norm(song.get("artist"))
    score = 0
    if len(norms) == 1:
        score += 300 if name == norms[0] else 180 if norms[0] in name else 0
        score += 80 if norms[0] in artist else 0
    else:
        for item in norms:
            if item == name:
                score += 220
            elif item in name:
                score += 120
            if item and item in artist:
                score += 160
        if all(item in name or item in artist for item in norms):
            score += 80
    if LIVE.search(song.get("name") or "") or LIVE.search(song.get("artist") or ""):
        score -= 40
    return score


def order(songs, keywords):
    return [song for _, song in sorted(enumerate(songs), key=lambda pair: (-rank(pair[1], keywords), pair[0]))]


def search(keywords, limit=10, offset=0, timeout=12):
    keywords = str(keywords or "").strip()
    if not keywords:
        raise ValueError("missing keywords")
    limit = max(1, min(int(limit or 10), 30))
    offset = max(0, int(offset or 0))
    query = urlencode({
        "keyword": keywords,
        "search_type": "music",
        "limit": min(30, offset + limit),
        "real_offset": "0",
        "search_source": "qishui",
    })
    req = Request(URL + "?" + query, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("qishui search failed: %s" % exc) from exc
    items = ((payload.get("data") or {}).get("list") or [])
    out = []
    for item in items:
        if not isinstance(item, dict) or not item.get("item_id"):
            continue
        author = item.get("author_info") or {}
        out.append({
            "provider": "qishui",
            "id": item.get("item_id"),
            "name": item.get("title") or item.get("name") or "",
            "artist": author.get("name") if isinstance(author, dict) else "",
            "album": item.get("collection_name") or "",
        })
    return order(out, keywords)[offset:offset + limit]


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: search.py <keywords> [limit] [offset]", file=sys.stderr)
        return 2
    if len(argv) > 4:
        print("search.py: too many arguments", file=sys.stderr)
        return 2
    try:
        songs = search(argv[1], argv[2] if len(argv) > 2 else 10, argv[3] if len(argv) > 3 else 0)
    except ValueError as exc:
        print("search.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "qishui", "error": str(exc), "songs": []}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"provider": "qishui", "songs": songs}, ensure_ascii=False, indent=2))
    return 0 if songs else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
