#!/usr/bin/env python3
"""Resolve a NetEase Cloud Music playback URL.

Cookie file (same directory, gitignored): cookie
  Paste the raw MUSIC_U value, or a Cookie header containing MUSIC_U=...
  Environment overrides: NETEASE_MUSIC_U, MUSIC_U
"""
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AES_KEY = b"e82ckenh8dichen8"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"
HERE = Path(__file__).resolve().parent
# 默认高音质 MP3；改为 True 后默认优先 FLAC，并继续向 MP3 降级。
ENABLE_FLAC = False
LEVELS = (("lossless", "exhigh", "standard") if ENABLE_FLAC else ("exhigh", "standard"))
QUALITY = "lossless" if ENABLE_FLAC else "exhigh"
BR = {"jymaster": 1999000, "hires": 1999000, "lossless": 1411000, "exhigh": 999000, "standard": 128000}

SBOX = [
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
]
RCON = [0, 1, 2, 4, 8, 16, 32, 64, 128, 27, 54]


class PlayUrlError(Exception):
    def __init__(self, message, **extra):
        super().__init__(message)
        self.extra = extra


def _xor(a, b):
    return [x ^ y for x, y in zip(a, b)]


def _expand(key):
    words = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    for i in range(4, 44):
        temp = words[i - 1][:]
        if i % 4 == 0:
            temp = [SBOX[x] for x in temp[1:] + temp[:1]]
            temp[0] ^= RCON[i // 4]
        words.append(_xor(words[i - 4], temp))
    return [sum(words[i:i + 4], []) for i in range(0, 44, 4)]


def _gm(a, b):
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        a = ((a << 1) ^ 0x11B) if a & 128 else a << 1
        b >>= 1
    return result & 255


def aes_ecb_encrypt(data, key=AES_KEY):
    pad = 16 - len(data) % 16
    data += bytes([pad]) * pad
    rounds = _expand(key)
    out = []
    for offset in range(0, len(data), 16):
        state = _xor(list(data[offset:offset + 16]), rounds[0])
        for rnd in range(1, 11):
            state = [SBOX[x] for x in state]
            state = [state[i] for i in (0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6, 11)]
            if rnd != 10:
                mixed = []
                for col in range(4):
                    a = state[col * 4:col * 4 + 4]
                    mixed.extend([
                        _gm(a[0], 2) ^ _gm(a[1], 3) ^ a[2] ^ a[3],
                        a[0] ^ _gm(a[1], 2) ^ _gm(a[2], 3) ^ a[3],
                        a[0] ^ a[1] ^ _gm(a[2], 2) ^ _gm(a[3], 3),
                        _gm(a[0], 3) ^ a[1] ^ a[2] ^ _gm(a[3], 2),
                    ])
                state = mixed
            state = _xor(state, rounds[rnd])
        out.extend(state)
    return bytes(out)


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


def http_json(url, data, timeout=15):
    pairs = {"os": "pc", "appver": "8.9.75", "osver": "", "deviceId": "pyncm!"}
    token = music_u()
    if token:
        pairs["MUSIC_U"] = token
    body = urlencode(data).encode() if data is not None else None
    req = Request(url, data=body, method="POST" if body is not None else "GET", headers={
        "User-Agent": UA,
        "Referer": "https://music.163.com/",
        "Cookie": "; ".join("%s=%s" % item for item in pairs.items()),
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise PlayUrlError("netease request failed: %s" % exc) from exc
    if not isinstance(payload, dict):
        raise PlayUrlError("netease returned a non-object")
    return payload


def eapi_url(song_id, level, timeout):
    path = "/api/song/enhance/player/url/v1"
    header = {
        "os": "pc", "appver": "8.9.75", "osver": "", "deviceId": "pyncm!",
        "requestId": str(random.randrange(20000000, 30000000)),
    }
    payload = {
        "ids": [int(song_id)],
        "level": level,
        "encodeType": "flac" if level == "lossless" else "mp3",
        "header": json.dumps(header, separators=(",", ":")),
    }
    raw = json.dumps(payload, separators=(",", ":"))
    digest = hashlib.md5(("nobody" + path + "use" + raw + "md5forencrypt").encode()).hexdigest()
    text = path + "-36cd479b6b5-" + raw + "-36cd479b6b5-" + digest
    encrypted = aes_ecb_encrypt(text.encode()).hex().upper()
    body = http_json(
        "https://interface.music.163.com/eapi/song/enhance/player/url/v1",
        {"params": encrypted},
        timeout,
    )
    data = body.get("data") or []
    item = data[0] if data and isinstance(data[0], dict) else {}
    url = str(item.get("url") or "")
    return {
        "url": url,
        "level": item.get("level") or "",
        "trial": bool(item.get("freeTrialInfo")),
        "fee": item.get("fee"),
        "code": item.get("code"),
        "expi": item.get("expi"),
        "type": item.get("type"),
    }


def weapi_url(song_id, level, timeout):
    body = http_json(
        "https://interface.music.163.com/api/song/enhance/player/url",
        {"ids": "[%s]" % int(song_id), "br": BR.get(level, 128000)},
        timeout,
    )
    data = body.get("data") or []
    item = data[0] if data and isinstance(data[0], dict) else {}
    return {
        "url": str(item.get("url") or ""),
        "level": item.get("level") or level,
        "trial": bool(item.get("freeTrialInfo")),
        "fee": item.get("fee"),
        "code": item.get("code"),
        "expi": item.get("expi"),
        "type": item.get("type"),
    }


def resolve(song_id, quality=QUALITY, timeout=15):
    quality = quality if quality in LEVELS else QUALITY
    chain = LEVELS[LEVELS.index(quality):]
    logged_in = bool(music_u())
    last = {}
    for level in chain:
        for fetch in (eapi_url, weapi_url):
            try:
                last = fetch(song_id, level, timeout)
            except PlayUrlError:
                continue
            if last.get("url"):
                return {
                    "provider": "netease",
                    "id": int(song_id),
                    "url": last["url"],
                    "requested": quality,
                    "level": last.get("level") or level,
                    "expi": last.get("expi"),
                    "type": last.get("type"),
                    "trial": bool(last.get("trial")),
                    "playable": True,
                    "loggedIn": logged_in,
                    "restriction": None,
                }
    return {
        "provider": "netease",
        "id": int(song_id),
        "url": "",
        "requested": quality,
        "level": "",
        "expi": last.get("expi"),
        "type": last.get("type"),
        "trial": False,
        "playable": False,
        "loggedIn": logged_in,
        "restriction": {
            "category": "url_unavailable",
            "message": "网易云没有返回可播放地址，可能需要会员或版权受限",
            "code": last.get("code"),
        },
    }


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: playurl.py <song_id> [quality] [--json]", file=sys.stderr)
        print("quality: " + " | ".join(LEVELS), file=sys.stderr)
        return 2
    as_json = "--json" in argv[2:]
    if any(item.startswith("--") and item != "--json" for item in argv[2:]) or argv[2:].count("--json") > 1:
        print("playurl.py: unknown or repeated option", file=sys.stderr)
        return 2
    args = [item for item in argv[1:] if item != "--json"]
    if not 1 <= len(args) <= 2 or not args[0].isdigit():
        print("playurl.py: expected a numeric song_id and optional quality", file=sys.stderr)
        return 2
    try:
        result = resolve(args[0], args[1] if len(args) > 1 else QUALITY)
    except ValueError as exc:
        print("playurl.py: %s" % exc, file=sys.stderr)
        return 2
    except PlayUrlError as exc:
        print(json.dumps({"provider": "netease", "playable": False, "url": "", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    if as_json or not result.get("url"):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["url"])
    return 0 if result.get("playable") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
