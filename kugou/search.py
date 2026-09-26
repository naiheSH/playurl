"""Search Kugou songs and print file hashes. No login or cookie."""
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

URL = "https://songsearch.kugou.com/song_search_v2"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"
TAG = re.compile(r"</?em>", re.I)
SPLIT = re.compile(r"[\s,，、/|]+")
NOISE = re.compile(r"[\s\-—_()（）【】\[\]·.。,，、/|]+")
LIVE = re.compile(r"live|现场|演唱会|cover|翻唱|伴奏|纯音乐|dj|remix", re.I)


def clean(value):
    return TAG.sub("", str(value or "")).strip()


def norm(value):
    return NOISE.sub("", clean(value)).casefold()


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
    limit = max(1, min(int(limit or 10), 20))
    offset = max(0, int(offset or 0))
    fetch = min(20, offset + limit)
    query = urlencode({
        "keyword": keywords,
        "page": "1",
        "pagesize": str(fetch),
        "userid": "-1",
        "clientver": "2000",
        "platform": "WebFilter",
        "tag": "em",
        "filter": "2",
        "iscorrection": "1",
        "privilege_filter": "0",
        "filter_ver": "2",
        "appid": "1014",
        "token": "",
        "mid": "0",
    })
    req = Request(URL + "?" + query, headers={"User-Agent": UA, "Referer": "https://www.kugou.com/"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("kugou search failed: %s" % exc) from exc
    if int(payload.get("status") or 0) != 1:
        raise RuntimeError("kugou search unavailable")
    items = ((payload.get("data") or {}).get("lists") or [])
    out = []
    for item in items:
        if not isinstance(item, dict) or not item.get("FileHash"):
            continue
        mix = item.get("MixSongID")
        if mix is None:
            mix = item.get("mixsongid") or ""
        out.append({
            "provider": "kugou",
            "id": item.get("FileHash"),
            "album_id": "" if item.get("AlbumID") is None else str(item.get("AlbumID")),
            "album_audio_id": str(mix),
            "name": clean(item.get("SongName") or item.get("FileName") or ""),
            "artist": clean(item.get("SingerName") or ""),
            "album": clean(item.get("AlbumName") or ""),
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
        print(json.dumps({"provider": "kugou", "error": str(exc), "songs": []}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"provider": "kugou", "songs": songs}, ensure_ascii=False, indent=2))
    return 0 if songs else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
