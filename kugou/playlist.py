"""Search public Kugou playlists and list the logged-in user's playlists.

Songs from `tracks` include hash, album_id, and album_audio_id for playurl.py.
Public search needs no cookie. `mine` reads the same-directory cookie and does not print it.
"""
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
SEARCH_URL = "http://mobilecdn.kugou.com/api/v3/search/special"
TRACKS_URL = "http://mobilecdn.kugou.com/api/v3/special/song"
GATEWAY = "https://gateway.kugou.com"
ANDROID_APPID = 1005
ANDROID_CLIENTVER = 20489
ANDROID_SALT = "OIlwieks28dk2k092lksi2UIkp"
ANDROID_UA = "Android15-1070-11083-46-0-DiscoveryDRADProtocol-wifi"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"


def md5(text):
    return hashlib.md5(str(text).encode()).hexdigest()


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


def compound(raw):
    text = str(raw or "")
    try:
        text = unquote(text)
    except ValueError:
        pass
    return parse_cookie(text.replace("&", ";"))


def auth_from(cookie):
    obj = parse_cookie(cookie)
    kugoo = compound(obj.get("KuGoo") or obj.get("kugou") or "")
    userid = "".join(ch for ch in str(
        obj.get("userid") or obj.get("KugooID") or kugoo.get("KugooID") or kugoo.get("userid") or ""
    ) if ch.isdigit())
    token = str(obj.get("token") or obj.get("t") or kugoo.get("t") or kugoo.get("token") or "").strip()
    mid = str(obj.get("kg_mid") or obj.get("mid") or md5("playurl-kugou:" + (userid or "guest")))
    dfid = str(obj.get("kg_dfid") or obj.get("dfid") or "-")
    return {"userid": userid, "token": token, "mid": mid, "dfid": dfid, "ready": bool(userid and token)}


def get_json(url, timeout=12):
    req = Request(url, headers={"User-Agent": UA, "Referer": "https://www.kugou.com/"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("kugou playlist failed: %s" % exc) from exc
    if not isinstance(payload, dict) or int(payload.get("status") or 0) != 1:
        raise RuntimeError("kugou playlist unavailable")
    return payload


def playlist_row(item, source):
    if not isinstance(item, dict):
        return None
    playlist_id = item.get("specialid") or item.get("global_collection_id") or item.get("listid")
    if not playlist_id:
        return None
    return {
        "provider": "kugou",
        "id": str(playlist_id),
        "name": item.get("specialname") or item.get("name") or item.get("listname") or "",
        "trackCount": item.get("songcount") or item.get("song_count") or item.get("count") or 0,
        "creator": item.get("nickname") or item.get("username") or "",
        "source": source,
    }


def search(keywords, limit=10, offset=0, timeout=12):
    keywords = str(keywords or "").strip()
    if not keywords:
        raise ValueError("missing keywords")
    limit = max(1, min(int(limit or 10), 20))
    offset = max(0, int(offset or 0))
    page_size = 20
    first = offset // page_size + 1
    last = (offset + limit - 1) // page_size + 1
    rows = []
    for page in range(first, last + 1):
        query = urlencode({"keyword": keywords, "page": page, "pagesize": page_size, "platform": "WebFilter"})
        payload = get_json(SEARCH_URL + "?" + query, timeout=timeout)
        rows.extend(((payload.get("data") or {}).get("info") or []))
    start = offset - (first - 1) * page_size
    selected = rows[start:start + limit]
    return [row for row in (playlist_row(item, "search") for item in selected) if row]


def song_row(item):
    if not isinstance(item, dict):
        return None
    file_hash = item.get("hash") or item.get("FileHash") or ""
    if not file_hash:
        return None
    filename = str(item.get("filename") or item.get("name") or "")
    artist, _, name = filename.partition(" - ")
    if not name:
        artist, name = "", filename
    album_id = item.get("album_id")
    if album_id is None:
        album_id = item.get("AlbumID") or ""
    mix = item.get("album_audio_id")
    if mix is None:
        mix = item.get("MixSongID") or item.get("mixsongid") or ""
    return {
        "provider": "kugou",
        "id": file_hash,
        "album_id": str(album_id),
        "album_audio_id": str(mix),
        "name": name,
        "artist": artist,
    }


def tracks(playlist_id, limit=50, offset=0, timeout=12):
    playlist_id = str(playlist_id or "").strip()
    if not playlist_id:
        raise ValueError("missing playlist id")
    if playlist_id.startswith("collection_"):
        return mine_tracks(playlist_id, limit, offset, timeout)
    limit = max(1, min(int(limit or 50), 100))
    offset = max(0, int(offset or 0))
    page_size = 100
    first = offset // page_size + 1
    last = (offset + limit - 1) // page_size + 1
    rows = []
    total = None
    for page in range(first, last + 1):
        query = urlencode({"specialid": playlist_id, "page": page, "pagesize": page_size, "platform": "WebFilter"})
        payload = get_json(TRACKS_URL + "?" + query, timeout=timeout)
        data = payload.get("data") or {}
        if total is None:
            total = data.get("total")
        rows.extend(data.get("info") or [])
    start = offset - (first - 1) * page_size
    songs = [row for row in (song_row(item) for item in rows[start:start + limit]) if row]
    return {
        "provider": "kugou",
        "playlist": {"id": playlist_id, "source": "search"},
        "songs": songs,
        "total": total if total is not None else len(songs),
    }


def gateway(path, body, timeout=12):
    cookie = load_cookie()
    auth = auth_from(cookie)
    if not auth["ready"]:
        raise RuntimeError("kugou cookie missing")
    now = int(time.time())
    params = {
        "clientver": ANDROID_CLIENTVER,
        "clienttime": now,
        "mid": auth["mid"],
        "uuid": "-",
        "dfid": auth["dfid"],
        "appid": ANDROID_APPID,
        "token": auth["token"],
        "userid": int(auth["userid"]),
        "plat": 1,
    }
    body_text = json.dumps(body, separators=(",", ":"))
    parts = ["%s=%s" % item for item in sorted(params.items())]
    parts.append(body_text)
    params["signature"] = md5(ANDROID_SALT + "".join(parts) + ANDROID_SALT)
    req = Request(GATEWAY + path + "?" + urlencode(params), data=body_text.encode(), method="POST", headers={
        "User-Agent": ANDROID_UA,
        "Content-Type": "application/json",
        "x-router": "cloudlist.service.kugou.com",
        "dfid": auth["dfid"],
        "mid": auth["mid"],
        "clienttime": str(now),
        "kg-rc": "1",
        "kg-thash": "5d816a0",
        "kg-rec": "1",
        "kg-rf": "B9EDA08A64250DEFFBCADDEE00F8F25F",
        "Cookie": cookie,
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("kugou playlist failed: %s" % exc) from exc
    if int(payload.get("status") or 0) != 1:
        code = payload.get("error_code") or payload.get("errcode") or payload.get("code") or payload.get("status")
        message = payload.get("error_msg") or payload.get("errmsg") or payload.get("message") or "unavailable"
        raise RuntimeError("kugou playlist unavailable: %s (%s)" % (message, code))
    return payload.get("data") or {}


def list_id(playlist_id):
    parts = str(playlist_id or "").split("_")
    if len(parts) >= 5 and parts[0] == "collection" and parts[3].isdigit():
        return parts[3]
    return playlist_id if str(playlist_id).isdigit() else ""


def mine(limit=30, offset=0, timeout=12):
    auth = auth_from(load_cookie())
    limit = max(1, min(int(limit or 30), 50))
    offset = max(0, int(offset or 0))
    page_size = 50
    first = offset // page_size + 1
    last = (offset + limit - 1) // page_size + 1
    rows = []
    for page in range(first, last + 1):
        data = gateway("/v7/get_all_list", {
            "userid": int(auth["userid"]),
            "token": auth["token"],
            "total_ver": 979,
            "type": 2,
            "page": page,
            "pagesize": page_size,
        }, timeout=timeout)
        info = data.get("info") if isinstance(data.get("info"), dict) else data
        page_rows = []
        for key in ("list", "collect", "love", "self"):
            page_rows.extend(info.get(key) or [])
        if not page_rows and isinstance(data.get("info"), list):
            page_rows = data.get("info")
        rows.extend(page_rows)
    start = offset - (first - 1) * page_size
    rows = rows[start:start + limit]
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        playlist_id = item.get("global_collection_id") or item.get("listid") or item.get("list_id")
        if not playlist_id:
            continue
        out.append({
            "provider": "kugou",
            "id": str(playlist_id),
            "name": item.get("name") or item.get("listname") or "",
            "trackCount": item.get("count") or item.get("song_count") or 0,
            "source": "mine",
        })
    return out


def mine_tracks(playlist_id, limit, offset, timeout):
    auth = auth_from(load_cookie())
    parsed = list_id(playlist_id)
    if not parsed:
        raise ValueError("missing playlist id")
    limit = max(1, min(int(limit or 50), 50))
    offset = max(0, int(offset or 0))
    page_size = 50
    first = offset // page_size + 1
    last = (offset + limit - 1) // page_size + 1
    rows = []
    total = None
    for page in range(first, last + 1):
        data = gateway("/v4/get_list_all_file", {
            "listid": int(parsed),
            "userid": int(auth["userid"]),
            "area_code": 1,
            "show_relate_goods": 0,
            "pagesize": page_size,
            "allplatform": 1,
            "show_cover": 1,
            "type": 0,
            "token": auth["token"],
            "page": page,
        }, timeout=timeout)
        if total is None:
            total = data.get("count")
        rows.extend(data.get("info") or data.get("songs") or [])
    start = offset - (first - 1) * page_size
    songs = [row for row in (song_row(item) for item in rows[start:start + limit]) if row]
    return {
        "provider": "kugou",
        "playlist": {"id": playlist_id, "source": "mine"},
        "songs": songs,
        "total": total if total is not None else len(songs),
    }


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
            body = {"provider": "kugou", "playlists": search(argv[2], argv[3] if len(argv) > 3 else 10, argv[4] if len(argv) > 4 else 0)}
        elif command == "tracks":
            body = tracks(argv[2] if len(argv) > 2 else "", argv[3] if len(argv) > 3 else 50, argv[4] if len(argv) > 4 else 0)
        elif command == "mine":
            body = {"provider": "kugou", "playlists": mine(argv[2] if len(argv) > 2 else 30, argv[3] if len(argv) > 3 else 0)}
    except ValueError as exc:
        print("playlist.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "kugou", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(body, ensure_ascii=False, indent=2))
    rows = body.get("playlists") or body.get("songs") or []
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
