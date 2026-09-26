"""Search public QQ playlists and list the logged-in user's playlists.

Songs from `tracks` are songmids for playurl.py. Public search needs no cookie.
`mine` reads the same-directory cookie and does not print it.
"""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
SEARCH_URL = "https://c.y.qq.com/soso/fcgi-bin/client_music_search_songlist"
DETAIL_URL = "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"
CREATED_URL = "https://c.y.qq.com/rsc/fcgi-bin/fcg_user_created_diss"
COLLECT_URL = "https://c.y.qq.com/fav/fcgi-bin/fcg_get_profile_order_asset.fcg"
MUSIC_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"
LIKED_ID = "liked"
LIKED_DIRID = 201


def parse_cookie(text):
    out = {}
    for part in str(text or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key, value = key.strip(), value.strip()
        if key:
            out[key] = value
    return out


def load_cookie():
    path = HERE / "cookie"
    if not path.is_file():
        return ""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return "; ".join(line for line in lines if line and not line.startswith("#"))


def uin_of(obj):
    wechat = bool(obj.get("wxopenid")) or obj.get("login_type") == "2"
    raw = obj.get("wxuin" if wechat else "uin") or obj.get("qqmusic_uin") or obj.get("p_uin") or ""
    digits = "".join(ch for ch in raw if ch.isdigit()).lstrip("0")
    return digits or "0"


def playback_key(obj):
    for key in ("qm_keyst", "qqmusic_key", "music_key", "wxskey"):
        if obj.get(key):
            return obj[key]
    return ""


def get_json(url, query, timeout=12, login=False):
    headers = {"User-Agent": UA, "Referer": "https://y.qq.com/"}
    cookie = load_cookie() if login else ""
    if cookie:
        headers["Cookie"] = cookie
    req = Request(url + "?" + urlencode(query), headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", "replace")
            payload = json.loads(text)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("qq playlist failed: %s" % exc) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("qq playlist returned a non-object")
    return payload


def playlist_row(item, source):
    if not isinstance(item, dict):
        return None
    playlist_id = item.get("dissid") or item.get("tid") or item.get("diss_id") or item.get("id")
    if not playlist_id:
        return None
    return {
        "provider": "qq",
        "id": str(playlist_id),
        "name": item.get("dissname") or item.get("diss_name") or item.get("name") or "",
        "trackCount": item.get("songnum") or item.get("song_cnt") or item.get("song_count") or 0,
        "creator": item.get("creator") or item.get("nickname") or item.get("hostname") or "",
        "source": source,
    }


def search(keywords, limit=10, offset=0, timeout=12):
    keywords = str(keywords or "").strip()
    if not keywords:
        raise ValueError("missing keywords")
    limit = max(1, min(int(limit or 10), 30))
    offset = max(0, int(offset or 0))
    page_size = 30
    first = offset // page_size + 1
    last = (offset + limit - 1) // page_size + 1
    rows = []
    for page in range(first, last + 1):
        payload = get_json(SEARCH_URL, {
            "page_no": page,
            "num_per_page": page_size,
            "format": "json",
            "query": keywords,
            "remoteplace": "txt.yqq.playlist",
        }, timeout=timeout)
        rows.extend(((payload.get("data") or {}).get("list") or []))
    start = offset - (first - 1) * page_size
    selected = rows[start:start + limit]
    return [row for row in (playlist_row(item, "search") for item in selected) if row]


def song_row(item):
    if not isinstance(item, dict):
        return None
    mid = item.get("songmid") or item.get("mid") or ""
    if not mid:
        return None
    singers = item.get("singer") or []
    names = [singer.get("name") for singer in singers if isinstance(singer, dict) and singer.get("name")]
    return {
        "provider": "qq",
        "id": mid,
        "name": item.get("songname") or item.get("name") or "",
        "artist": " / ".join(names) or item.get("singername") or "",
    }


def tracks(playlist_id, limit=50, offset=0, timeout=12):
    playlist_id = str(playlist_id or "").strip()
    if not playlist_id:
        raise ValueError("missing playlist id")
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    if playlist_id == LIKED_ID:
        return liked_tracks(limit, offset, timeout)
    payload = get_json(DETAIL_URL, {
        "type": 1,
        "utf8": 1,
        "disstid": playlist_id,
        "song_begin": offset,
        "song_num": limit,
        "format": "json",
        "inCharset": "utf8",
        "outCharset": "utf-8",
        "notice": 0,
        "platform": "yqq.json",
        "needNewCode": 0,
    }, timeout=timeout, login=bool(load_cookie()))
    cd = ((payload.get("cdlist") or [None])[0] or {})
    songs = [row for row in (song_row(item) for item in (cd.get("songlist") or [])) if row]
    playlist = playlist_row(cd, "detail")
    if playlist:
        playlist["id"] = playlist_id
    return {
        "playlist": playlist,
        "songs": songs,
        "total": cd.get("total_song_num") or cd.get("songnum") or len(songs),
    }


def musicu(module, method, param, timeout=12):
    cookie = load_cookie()
    obj = parse_cookie(cookie)
    body = {
        "comm": {"ct": 24, "cv": 0, "uin": uin_of(obj), "qq": uin_of(obj), "authst": playback_key(obj)},
        "req_0": {"module": module, "method": method, "param": param},
    }
    req = Request(MUSIC_URL, data=json.dumps(body).encode(), method="POST", headers={
        "User-Agent": UA,
        "Referer": "https://y.qq.com/",
        "Content-Type": "application/json",
        "Cookie": cookie,
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("qq playlist failed: %s" % exc) from exc
    block = payload.get("req_0") or {}
    if int(payload.get("code") or 0) or int(block.get("code") or 0):
        raise RuntimeError("qq login unavailable")
    return block.get("data") or {}


def liked_tracks(limit, offset, timeout):
    obj = parse_cookie(load_cookie())
    if not playback_key(obj):
        raise RuntimeError("qq cookie missing playback key")
    data = musicu("music.srfDissInfo.DissInfo", "CgiGetDiss", {
        "disstid": 0,
        "dirid": LIKED_DIRID,
        "tag": 1,
        "song_begin": offset,
        "song_num": limit,
        "userinfo": 1,
        "orderlist": 1,
    }, timeout=timeout)
    songs = [row for row in (song_row(item) for item in (data.get("songlist") or [])) if row]
    return {
        "playlist": {"provider": "qq", "id": LIKED_ID, "name": "我的喜欢", "source": "mine"},
        "songs": songs,
        "total": data.get("total_song_num") or len(songs),
    }


def mine(limit=30, offset=0, timeout=12):
    cookie = load_cookie()
    obj = parse_cookie(cookie)
    uin = uin_of(obj)
    if uin == "0":
        raise RuntimeError("qq cookie missing")
    limit = max(1, min(int(limit or 30), 50))
    offset = max(0, int(offset or 0))
    fetch_size = offset + limit
    created = get_json(CREATED_URL, {
        "hostUin": 0, "hostuin": uin, "sin": 0, "size": fetch_size,
        "g_tk": 5381, "loginUin": uin, "format": "json",
        "inCharset": "utf8", "outCharset": "utf-8", "notice": 0,
        "platform": "yqq.json", "needNewCode": 0,
    }, timeout=timeout, login=True)
    collected = get_json(COLLECT_URL, {
        "ct": 20, "cid": 205360956, "userid": uin, "reqtype": 3,
        "sin": 0, "ein": fetch_size - 1,
    }, timeout=timeout, login=True)
    rows = [{"provider": "qq", "id": LIKED_ID, "name": "我的喜欢", "source": "mine"}]
    created_rows = ((created.get("data") or {}).get("disslist") or [])
    collect_rows = ((collected.get("data") or {}).get("cdlist") or [])
    rows.extend(row for row in (playlist_row(item, "mine") for item in created_rows) if row)
    rows.extend(row for row in (playlist_row(item, "collect") for item in collect_rows) if row)
    seen = set()
    out = []
    for row in rows:
        if row["id"] in seen or row["id"] == "0":
            continue
        seen.add(row["id"])
        out.append(row)
    return out[offset:offset + limit]


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: playlist.py search <keywords> [limit] [offset]", file=sys.stderr)
        print("       playlist.py tracks <playlist_id> [limit] [offset]", file=sys.stderr)
        print("       playlist.py mine [limit] [offset]", file=sys.stderr)
        return 2
    command = argv[1]
    expected = {"search": (3, 5), "tracks": (3, 5), "mine": (2, 4)}
    if command not in expected:
        print("playlist.py: unknown command", file=sys.stderr)
        return 2
    minimum, maximum = expected[command]
    if not minimum <= len(argv) <= maximum:
        print("playlist.py: invalid arguments for %s" % command, file=sys.stderr)
        return 2
    try:
        if command == "search":
            if len(argv) < 3:
                raise ValueError("missing keywords")
            body = {"provider": "qq", "playlists": search(argv[2], argv[3] if len(argv) > 3 else 10, argv[4] if len(argv) > 4 else 0)}
        elif command == "tracks":
            body = {"provider": "qq"}
            body.update(tracks(argv[2] if len(argv) > 2 else "", argv[3] if len(argv) > 3 else 50, argv[4] if len(argv) > 4 else 0))
        elif command == "mine":
            body = {"provider": "qq", "playlists": mine(argv[2] if len(argv) > 2 else 30, argv[3] if len(argv) > 3 else 0)}
    except ValueError as exc:
        print("playlist.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "qq", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(body, ensure_ascii=False, indent=2))
    rows = body.get("playlists") or body.get("songs") or []
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
