"""Search NetEase songs and print numeric IDs. No login or cookie."""
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

URL = "https://music.163.com/api/search/get/web"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"


SPLIT = re.compile(r"[\s,，、/|]+")
NOISE = re.compile(r"[\s\-—_()（）【】\[\]·.。,，、/|]+")
LIVE = re.compile(r"live|现场|演唱会|cover|翻唱|伴奏|纯音乐|dj|remix", re.I)


def norm(value):
    return NOISE.sub("", str(value or "")).casefold()


def tokens(keywords):
    return [item for item in SPLIT.split(str(keywords or "").strip()) if item]


def rank(song, keywords):
    parts = tokens(keywords)
    norms = [norm(item) for item in parts]
    name = norm(song.get("name"))
    artist = norm(song.get("artist"))
    title = name
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
    fetch = min(30, offset + limit)
    body = urlencode({"s": keywords, "type": "1", "limit": fetch, "offset": 0}).encode()
    req = Request(URL, data=body, method="POST", headers={
        "User-Agent": UA,
        "Referer": "https://music.163.com/",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("netease search failed: %s" % exc) from exc
    songs = ((payload.get("result") or {}).get("songs") or [])
    out = []
    for song in songs:
        if not isinstance(song, dict) or not song.get("id"):
            continue
        artists = song.get("artists") or song.get("ar") or []
        names = [item.get("name") for item in artists if isinstance(item, dict) and item.get("name")]
        album = song.get("album") or song.get("al") or {}
        out.append({
            "provider": "netease",
            "id": song.get("id"),
            "name": song.get("name") or "",
            "artist": " / ".join(names),
            "album": album.get("name") if isinstance(album, dict) else "",
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
        print(json.dumps({"provider": "netease", "error": str(exc), "songs": []}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"provider": "netease", "songs": songs}, ensure_ascii=False, indent=2))
    return 0 if songs else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
