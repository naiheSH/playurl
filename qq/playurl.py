#!/usr/bin/env python3
"""Resolve a QQ Music playback URL.

Cookie file (same directory, gitignored): cookie
  Paste the y.qq.com Cookie header. Member tracks need uin plus
  qm_keyst / qqmusic_key / music_key.
"""
import json
import random
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"
TEMPLATES = (
    ("RS01", ".flac", "hires", "Hi-Res FLAC"),
    ("F000", ".flac", "lossless", "FLAC"),
    ("M800", ".mp3", "exhigh", "320k MP3"),
    ("M500", ".mp3", "standard", "128k MP3"),
    ("C400", ".m4a", "aac", "AAC"),
)
# 默认高音质 MP3/M4A；改为 True 后默认优先 FLAC，并继续向 MP3/M4A 降级。
ENABLE_FLAC = False
ORDER = (("lossless", "exhigh", "standard", "aac") if ENABLE_FLAC else ("exhigh", "standard", "aac"))
QUALITY = "lossless" if ENABLE_FLAC else "exhigh"


def reachable(url, timeout):
    if not url:
        return False
    req = Request(url, method="GET", headers={
        "User-Agent": UA,
        "Referer": "https://y.qq.com/",
        "Range": "bytes=0-1",
    })
    try:
        with urlopen(req, timeout=min(timeout, 8)) as resp:
            return resp.status in (200, 206)
    except HTTPError as exc:
        return exc.code in (200, 206)
    except (URLError, OSError, ValueError):
        return False



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
    lines = [line for line in lines if line and not line.startswith("#")]
    return "; ".join(lines)


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


def normalize_quality(value):
    raw = str(value or QUALITY).lower()
    aliases = {
        "jymaster": "lossless", "master": "lossless", "hires": "lossless", "hi-res": "lossless", "highres": "lossless",
        "flac": "lossless", "sq": "lossless", "lossless": "lossless", "320": "exhigh", "320k": "exhigh", "hq": "exhigh",
        "128": "standard", "128k": "standard",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in ORDER else QUALITY


def candidates(songmid, media_mid, quality):
    quality = normalize_quality(quality)
    templates = [item for item in TEMPLATES if ENABLE_FLAC or item[1] != ".flac"]
    start = next((i for i, item in enumerate(templates) if item[2] == quality), 0)
    media_ids = []
    for item in (media_mid, songmid):
        item = str(item or "").strip()
        if item and item not in media_ids:
            media_ids.append(item)
    out = []
    for media_id in media_ids:
        for prefix, ext, level, label in templates[start:]:
            out.append({
                "filename": prefix + media_id + ext,
                "level": level,
                "label": label,
            })
    return out


def media_mid_of(songmid, timeout):
    body = json.dumps({
        "comm": {"ct": 24, "cv": 0, "format": "json"},
        "req_0": {
            "module": "music.pf_song_detail_svr",
            "method": "get_song_detail_yqq",
            "param": {"song_mid": songmid},
        },
    }).encode()
    req = Request(URL, data=body, method="POST", headers={
        "User-Agent": UA,
        "Referer": "https://y.qq.com/",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError):
        return ""
    track = (((payload.get("req_0") or {}).get("data") or {}).get("track_info") or {})
    return str(((track.get("file") or {}).get("media_mid") or "")).strip()


def resolve(songmid, media_mid="", quality=QUALITY, timeout=15):
    songmid = str(songmid or "").strip()
    if not songmid:
        raise ValueError("missing QQ song mid")
    media_mid = str(media_mid or "").strip() or media_mid_of(songmid, timeout)
    cookie = load_cookie()
    obj = parse_cookie(cookie)
    uin = uin_of(obj)
    key = playback_key(obj)
    files = candidates(songmid, media_mid, quality)
    names = [item["filename"] for item in files]
    comm = {"uin": uin, "format": "json", "ct": 19 if key else 24, "cv": 0}
    if key:
        comm["authst"] = key
    param = {
        "guid": str(10000000 + random.randrange(90000000)),
        "songmid": [songmid] * len(names) if names else [songmid],
        "songtype": [0] * (len(names) or 1),
        "uin": uin,
        "loginflag": 1,
        "platform": "20",
    }
    if names:
        param["filename"] = names
    body = json.dumps({
        "comm": comm,
        "req_0": {"module": "vkey.GetVkeyServer", "method": "CgiGetVkey", "param": param},
    }).encode()
    req = Request(URL, data=body, method="POST", headers={
        "User-Agent": UA,
        "Referer": "https://y.qq.com/",
        "Content-Type": "application/json;charset=UTF-8",
        **({"Cookie": cookie} if cookie else {}),
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("qq request failed: %s" % exc) from exc
    data = ((payload.get("req_0") or {}).get("data") or {})
    infos = data.get("midurlinfo") or []
    sips = [item for item in (data.get("sip") or ["https://ws.stream.qqmusic.qq.com/"]) if item]
    for info in infos:
        info = info or {}
        purl = str(info.get("purl") or "")
        if not purl:
            continue
        meta = next((item for item in files if item["filename"] == info.get("filename")), {})
        url = ""
        for sip in sips:
            candidate = sip + purl
            if reachable(candidate, timeout):
                url = candidate
                break
        if not url:
            continue
        return {
            "provider": "qq",
            "id": songmid,
            "url": url,
            "requested": normalize_quality(quality),
            "level": meta.get("level") or info.get("filename") or "",
            "quality": meta.get("label") or "",
            "expi": data.get("expiration"),
            "trial": False,
            "playable": True,
            "loggedIn": bool(uin != "0" and key),
            "filename": info.get("filename") or "",
            "restriction": None,
        }
    return {
        "provider": "qq",
        "id": songmid,
        "url": "",
        "requested": normalize_quality(quality),
        "level": "",
        "expi": data.get("expiration"),
        "trial": False,
        "playable": False,
        "loggedIn": bool(uin != "0" and key),
        "restriction": {
            "category": "login_required" if not key else "url_unavailable",
            "message": "QQ 音乐没有返回播放地址。会员曲目需要 cookie 中的 uin 和 qm_keyst。",
        },
    }


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: playurl.py <songmid> [quality] [media_mid] [--json]", file=sys.stderr)
        return 2
    as_json = "--json" in argv[2:]
    if any(item.startswith("--") and item != "--json" for item in argv[2:]) or argv[2:].count("--json") > 1:
        print("playurl.py: unknown or repeated option", file=sys.stderr)
        return 2
    args = [item for item in argv[1:] if item != "--json"]
    if not 1 <= len(args) <= 3:
        print("playurl.py: invalid arguments", file=sys.stderr)
        return 2
    try:
        result = resolve(args[0], args[2] if len(args) > 2 else "", args[1] if len(args) > 1 else QUALITY)
    except ValueError as exc:
        print("playurl.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "qq", "playable": False, "url": "", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    if as_json or not result.get("url"):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["url"])
    return 0 if result.get("playable") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
