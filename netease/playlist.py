"""Search public NetEase playlists and list the logged-in user's playlists.

Songs from `tracks` are numeric IDs for playurl.py. Public search needs no cookie.
`mine` reads the same-directory cookie (MUSIC_U) and does not print it.
"""
import base64
import json
import os
import random
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WEAPI_KEY = b"0CoJUm6Qyw8W8jud"
WEAPI_IV = b"0102030405060708"
WEAPI_PUBLIC = "010001"
WEAPI_MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7"
    "b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280"
    "104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932"
    "575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b"
    "3ece0462db0a22b8e7"
)


def _xtime(value):
    return ((value << 1) ^ (0x1B if value & 0x80 else 0)) & 0xFF


def _mul(a, b):
    result = 0
    while b:
        if b & 1:
            result ^= a
        a = _xtime(a)
        b >>= 1
    return result


def _sbox_value(value):
    inverse = 0
    if value:
        inverse = next(candidate for candidate in range(1, 256) if _mul(value, candidate) == 1)
    rotated = inverse
    result = inverse
    for _ in range(4):
        rotated = ((rotated << 1) | (rotated >> 7)) & 0xFF
        result ^= rotated
    return result ^ 0x63


SBOX = tuple(_sbox_value(index) for index in range(256))


def _sub_shift_mix(state, mix):
    columns = [bytearray(state[column * 4:(column + 1) * 4]) for column in range(4)]
    for column in columns:
        for row in range(4):
            column[row] = SBOX[column[row]]
    for row in range(1, 4):
        row_bytes = [columns[column][row] for column in range(4)]
        row_bytes = row_bytes[row:] + row_bytes[:row]
        for column in range(4):
            columns[column][row] = row_bytes[column]
    if mix:
        for column in columns:
            a, b, c, d = column
            column[0] = _xtime(a) ^ _xtime(b) ^ b ^ c ^ d
            column[1] = a ^ _xtime(b) ^ _xtime(c) ^ c ^ d
            column[2] = a ^ b ^ _xtime(c) ^ _xtime(d) ^ d
            column[3] = _xtime(a) ^ a ^ b ^ c ^ _xtime(d)
    out = bytearray(16)
    for column in range(4):
        out[column * 4:(column + 1) * 4] = columns[column]
    return out


def _expand_key(key):
    columns = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    while len(columns) < 44:
        temp = columns[-1][:]
        if len(columns) % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [SBOX[item] for item in temp]
            temp[0] ^= rcon
            rcon = _xtime(rcon)
        prev = columns[-4]
        columns.append([prev[i] ^ temp[i] for i in range(4)])
    keys = []
    for index in range(11):
        block = bytearray(16)
        for column, word in enumerate(columns[index * 4:(index + 1) * 4]):
            for row, item in enumerate(word):
                block[column * 4 + row] = item
        keys.append(bytes(block))
    return keys


def _encrypt_block(block, round_keys):
    state = bytearray(block[i] ^ round_keys[0][i] for i in range(16))
    for round_key in round_keys[1:-1]:
        state = _sub_shift_mix(state, True)
        state = bytearray(state[i] ^ round_key[i] for i in range(16))
    state = _sub_shift_mix(state, False)
    last = round_keys[-1]
    return bytes(state[i] ^ last[i] for i in range(16))


def aes_cbc(data, key, iv):
    pad = 16 - len(data) % 16
    data += bytes([pad]) * pad
    keys = _expand_key(key)
    prev = iv
    out = bytearray()
    for offset in range(0, len(data), 16):
        block = bytes(data[offset + i] ^ prev[i] for i in range(16))
        prev = _encrypt_block(block, keys)
        out += prev
    return bytes(out)


def weapi(data):
    text = json.dumps(data, separators=(",", ":")).encode()
    secret = "".join(random.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(16)).encode()
    first = base64.b64encode(aes_cbc(text, WEAPI_KEY, WEAPI_IV))
    params = base64.b64encode(aes_cbc(first, secret, WEAPI_IV)).decode()
    number = int(secret[::-1].hex(), 16)
    enc_sec_key = format(pow(number, int(WEAPI_PUBLIC, 16), int(WEAPI_MODULUS, 16)), "x").rjust(256, "0")
    return {"params": params, "encSecKey": enc_sec_key}


HERE = Path(__file__).resolve().parent
SEARCH_URL = "https://music.163.com/api/search/get/web"
DETAIL_URL = "https://music.163.com/api/v6/playlist/detail"
USER_URL = "https://music.163.com/weapi/user/playlist"
LOGIN_URL = "https://music.163.com/weapi/w/nuser/account/get"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"


def parse_cookie(text):
    out = {}
    for part in str(text or "").replace("\n", ";").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key, value = key.strip(), value.strip()
        if key:
            out[key] = value
    return out


def music_u():
    for key in ("NETEASE_MUSIC_U", "MUSIC_U"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    path = HERE / "cookie"
    if not path.is_file():
        return ""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw or raw.startswith("#"):
        return ""
    parsed = parse_cookie(raw)
    return parsed.get("MUSIC_U") or ("" if "=" in raw else raw)


def get_json(url, data=None, timeout=12, login=False):
    headers = {"User-Agent": UA, "Referer": "https://music.163.com/"}
    token = music_u() if login else ""
    if token:
        headers["Cookie"] = "MUSIC_U=" + token
    body = urlencode(weapi(data) if login else data).encode() if data is not None else None
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(url, data=body, method="POST" if body is not None else "GET", headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("netease playlist failed: %s" % exc) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("netease playlist returned a non-object")
    return payload


def playlist_row(item, source):
    if not isinstance(item, dict) or not item.get("id"):
        return None
    creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
    return {
        "provider": "netease",
        "id": item.get("id"),
        "name": item.get("name") or "",
        "trackCount": item.get("trackCount") or item.get("track_count") or 0,
        "creator": creator.get("nickname") or "",
        "source": source,
    }


def search(keywords, limit=10, offset=0, timeout=12):
    keywords = str(keywords or "").strip()
    if not keywords:
        raise ValueError("missing keywords")
    limit = max(1, min(int(limit or 10), 30))
    offset = max(0, int(offset or 0))
    payload = get_json(SEARCH_URL, {
        "s": keywords, "type": "1000", "limit": limit, "offset": offset,
    }, timeout=timeout)
    rows = ((payload.get("result") or {}).get("playlists") or [])
    return [row for row in (playlist_row(item, "search") for item in rows) if row]


def tracks(playlist_id, limit=50, offset=0, timeout=12):
    playlist_id = str(playlist_id or "").strip()
    if not playlist_id.isdigit():
        raise ValueError("missing playlist id")
    limit = max(1, min(int(limit or 50), 100))
    offset = max(0, int(offset or 0))
    payload = get_json(DETAIL_URL, {"id": playlist_id, "n": 0}, timeout=timeout)
    playlist = payload.get("playlist") or {}
    ids = []
    for item in playlist.get("trackIds") or []:
        song_id = item.get("id") if isinstance(item, dict) else item
        if song_id:
            ids.append(song_id)
    page = ids[offset:offset + limit]
    songs = []
    for start in range(0, len(page), 100):
        chunk = page[start:start + 100]
        body = json.dumps([{"id": int(song_id)} for song_id in chunk], separators=(",", ":"))
        detail = get_json("https://music.163.com/api/v3/song/detail", {"c": body}, timeout=timeout)
        for song in detail.get("songs") or []:
            if not isinstance(song, dict) or not song.get("id"):
                continue
            artists = song.get("ar") or []
            names = [item.get("name") for item in artists if isinstance(item, dict) and item.get("name")]
            songs.append({
                "provider": "netease",
                "id": song.get("id"),
                "name": song.get("name") or "",
                "artist": " / ".join(names),
            })
    return {
        "playlist": playlist_row(playlist, "detail"),
        "songs": songs,
        "total": playlist.get("trackCount") or len(ids),
    }


def mine(limit=30, offset=0, timeout=12):
    if not music_u():
        raise RuntimeError("netease cookie missing")
    account = get_json(LOGIN_URL, {}, timeout=timeout, login=True)
    profile = ((account.get("account") or {}).get("id")) or ((account.get("profile") or {}).get("userId"))
    if not profile:
        raise RuntimeError("netease login unavailable")
    limit = max(1, min(int(limit or 30), 50))
    offset = max(0, int(offset or 0))
    payload = get_json(USER_URL, {
        "uid": profile, "limit": limit, "offset": offset,
    }, timeout=timeout, login=True)
    rows = payload.get("playlist") or []
    return [row for row in (playlist_row(item, "mine") for item in rows) if row]


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
            body = {"provider": "netease", "playlists": search(argv[2], argv[3] if len(argv) > 3 else 10, argv[4] if len(argv) > 4 else 0)}
        elif command == "tracks":
            body = {"provider": "netease"}
            body.update(tracks(argv[2] if len(argv) > 2 else "", argv[3] if len(argv) > 3 else 50, argv[4] if len(argv) > 4 else 0))
        elif command == "mine":
            body = {"provider": "netease", "playlists": mine(argv[2] if len(argv) > 2 else 30, argv[3] if len(argv) > 3 else 0)}
    except ValueError as exc:
        print("playlist.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "netease", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(body, ensure_ascii=False, indent=2))
    rows = body.get("playlists") or body.get("songs") or []
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
