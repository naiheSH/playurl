#!/usr/bin/env python3
"""Resolve a Kugou playback URL.

Cookie file (same directory, gitignored): cookie
  Paste the kugou.com Cookie header. Logged-in playback needs KuGoo
  (or userid + token) and works better with kg_mid / kg_dfid.
"""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
GATEWAY = "https://gateway.kugou.com"
WEB = "https://wwwapi.kugou.com/play/songinfo"
WEB_RETRY = "https://wwwapiretry.kugou.com/play/songinfo"
MOBILE = "https://m.kugou.com/app/i/getSongInfo.php"
APPID = 1005
WEB_APPID = 1014
CLIENTVER = 20489
ANDROID_SALT = "OIlwieks28dk2k092lksi2UIkp"
H5_SALT = "NVPh5oo715z5DIWAeQlhMDsWXXQV4hwt"
H5_SRC_APPID = "2919"
H5_CLIENTVER = "20000"
SIGN_KEY_SALT = "57ae12eb6890223e355ccfcb74edf70d"
V6_KEY_SALT = "185672dd44712f60bb1736df5a377e82"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"
GATEWAY_UA = "Android15-1070-11083-46-0-DiscoveryDRADProtocol-wifi"
# 默认高音质 MP3；改为 True 后默认优先 FLAC，并继续向 MP3 降级。
ENABLE_FLAC = False
LEVELS = (("lossless", "exhigh", "standard") if ENABLE_FLAC else ("exhigh", "standard"))
QUALITY = "lossless" if ENABLE_FLAC else "exhigh"

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
        text = json.loads('"%s"' % text) if False else text
    except ValueError:
        pass
    from urllib.parse import unquote
    try:
        text = unquote(text)
    except ValueError:
        pass
    return parse_cookie(text.replace("&", ";"))


def auth_from(cookie):
    obj = parse_cookie(cookie)
    kugoo = compound(obj.get("KuGoo") or obj.get("kugou") or obj.get("Kugou") or "")
    userid = "".join(ch for ch in str(
        obj.get("userid") or obj.get("KugooID") or kugoo.get("KugooID") or kugoo.get("userid") or ""
    ) if ch.isdigit())
    token = str(obj.get("token") or obj.get("t") or kugoo.get("t") or kugoo.get("token") or "").strip()
    mid = str(obj.get("kg_mid") or obj.get("mid") or md5("playurl-kugou:" + (userid or token or "guest")))
    dfid = str(obj.get("kg_dfid") or obj.get("dfid") or "-")
    return {"userid": userid, "token": token, "mid": mid, "dfid": dfid, "ready": bool(userid and token)}


def request_cookie(cookie, auth):
    obj = parse_cookie(cookie)
    if cookie:
        obj.setdefault("kg_mid", auth["mid"])
        obj.setdefault("kg_dfid", auth["dfid"])
    else:
        obj = {"kg_mid": auth["mid"], "kg_dfid": auth["dfid"]}
    return "; ".join("%s=%s" % item for item in obj.items())


def ensure_device(cookie, auth):
    if auth.get("dfid") and auth["dfid"] != "-":
        return cookie, auth
    if not auth.get("ready"):
        return cookie, auth
    path = HERE / "device.py"
    spec = importlib.util.spec_from_file_location("playurl_kugou_device", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载酷狗设备注册模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    guid = md5(str(uuid.uuid4()))
    mid = str(int(md5(guid), 16))
    dfid = module.register_device(auth["userid"], auth["token"], mid, guid)
    obj = parse_cookie(cookie)
    obj.update({
        "kg_mid": mid,
        "kg_dfid": dfid,
        "dfid": dfid,
        "KUGOU_API_MID": mid,
        "KUGOU_API_GUID": guid,
    })
    text = "; ".join("%s=%s" % item for item in obj.items()) + "\n"
    fd, name = tempfile.mkstemp(prefix=".cookie-", dir=HERE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(name, 0o600)
        os.replace(name, HERE / "cookie")
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return text.strip(), auth_from(text)


def signature_h5(params):
    parts = ["%s=%s" % item for item in sorted(params.items())]
    return md5(H5_SALT + "".join(parts) + H5_SALT)


def signature_android(params):
    parts = ["%s=%s" % item for item in sorted(params.items())]
    return md5(ANDROID_SALT + "".join(parts) + ANDROID_SALT)


def h5_params(auth, extra):
    now = int(time.time() * 1000)
    params = {
        "srcappid": H5_SRC_APPID,
        "clientver": H5_CLIENTVER,
        "clienttime": now,
        "mid": auth["mid"],
        "uuid": now,
        "dfid": auth["dfid"],
        "appid": WEB_APPID,
        "token": auth["token"],
        "userid": int(auth["userid"] or 0),
    }
    params.update(extra or {})
    return params


def get_json(url, cookie, timeout, headers=None):
    req = Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.kugou.com/",
        **({"Cookie": cookie} if cookie else {}),
        **(headers or {}),
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError):
        return None


def post_json(url, params, body, cookie, timeout, headers=None):
    body_text = json.dumps(body, separators=(",", ":"))
    signed = dict(params)
    signed["signature"] = md5(
        ANDROID_SALT
        + "".join("%s=%s" % item for item in sorted(params.items()))
        + body_text
        + ANDROID_SALT
    )
    req = Request(url + "?" + urlencode(signed), data=body_text.encode(), method="POST", headers={
        "User-Agent": GATEWAY_UA,
        "Content-Type": "application/json",
        **({"Cookie": cookie} if cookie else {}),
        **(headers or {}),
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError):
        return None


def pick_url(payload):
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for source in (payload, data):
        for key in ("url", "play_url", "backupUrl", "backup_url", "play_backup_url"):
            value = source.get(key)
            values = value if isinstance(value, list) else [value]
            for item in values:
                text = str(item or "").replace("\\/", "/").strip()
                if text.startswith("http://") or text.startswith("https://"):
                    return text
    return ""


def trial(payload):
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else {}
    for source in (payload or {}, data):
        if not isinstance(source, dict):
            continue
        for key in ("is_free_part", "isFreePart", "trial", "is_trial", "isTrial"):
            if source.get(key) in (1, "1", True, "true"):
                return True
    return False


def quality_param(level):
    return {"jymaster": "viper_tape", "hires": "hires", "lossless": "flac", "exhigh": 320}.get(level, 128)


def via_v6(file_hash, album_audio_id, cookie, auth, level, timeout):
    now_ms = int(time.time() * 1000)
    body = {
        "area_code": "1",
        "behavior": "play",
        "qualities": ["128", "320", "flac", "high", "multitrack", "viper_atmos", "viper_tape", "viper_clear", "super"],
        "resource": {
            "album_audio_id": str(album_audio_id or 0),
            "collect_list_id": "3",
            "collect_time": now_ms,
            "hash": file_hash,
            "id": 0,
            "page_id": 1,
            "type": "audio",
        },
        "token": auth["token"],
        "tracker_param": {
            "all_m": 1,
            "auth": "",
            "is_free_part": 0,
            "key": md5("%s%s%s%s%s" % (file_hash, V6_KEY_SALT, APPID, auth["mid"], auth["userid"] or 0)),
            "module_id": 0,
            "need_climax": 1,
            "need_xcdn": 1,
            "open_time": "",
            "pid": "411",
            "pidversion": "3001",
            "priv_vip_type": "6",
            "viptoken": "",
        },
        "userid": str(auth["userid"]),
        "vip": 0,
    }
    now = int(time.time())
    params = {
        "dfid": auth["dfid"],
        "mid": auth["mid"],
        "uuid": "-",
        "appid": APPID,
        "clientver": CLIENTVER,
        "clienttime": now,
        "token": auth["token"],
        "userid": auth["userid"],
    }
    payload = post_json("http://tracker.kugou.com/v6/priv_url", params, body, request_cookie(cookie, auth), timeout, {
        "dfid": auth["dfid"],
        "mid": auth["mid"],
        "clienttime": str(now),
        "kg-rc": "1",
        "kg-thash": "5d816a0",
        "kg-rec": "1",
        "kg-rf": "B9EDA08A64250DEFFBCADDEE00F8F25F",
    })
    rows = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), list) else []
    wanted = {
        "lossless": ("flac", "320", "128"),
        "exhigh": ("320", "128"),
        "standard": ("128",),
    }[level]
    for quality in wanted:
        for item in rows:
            if not isinstance(item, dict) or str(item.get("quality")) != quality:
                continue
            info = item.get("info") if isinstance(item.get("info"), dict) else {}
            urls = info.get("tracker_url") or []
            if isinstance(urls, str):
                urls = [urls]
            url = next((str(value).replace("\\/", "/") for value in urls if str(value).startswith(("http://", "https://"))), "")
            if not url:
                continue
            trial_value = info.get("tracker_type") == "part"
            return {
                "url": url,
                "level": "lossless" if quality == "flac" else ("exhigh" if quality == "320" else "standard"),
                "trial": trial_value,
                "source": "v6",
            }
    return None


def via_web(file_hash, album_id, album_audio_id, cookie, auth, level, timeout, retry=False):
    params = h5_params(auth, {
        "uuid": auth["mid"], "platid": 4, "hash": file_hash,
        "album_id": album_id or "0", "quality": quality_param(level),
    })
    if album_audio_id:
        params["album_audio_id"] = album_audio_id
    params["signature"] = signature_h5(params)
    payload = get_json((WEB_RETRY if retry else WEB) + "?" + urlencode(params), request_cookie(cookie, auth), timeout)
    url = pick_url(payload)
    if payload and int(payload.get("status") or 0) == 1 and url:
        bitrate = int((payload.get("data") or {}).get("bitrate") or 0)
        kbps = bitrate / 1000 if bitrate >= 10000 else bitrate
        actual = "lossless" if kbps >= 900 else ("exhigh" if kbps >= 300 else "standard")
        allowed = {
            "lossless": {"lossless", "exhigh", "standard"},
            "exhigh": {"exhigh", "standard"},
            "standard": {"standard"},
        }
        if actual not in allowed[level]:
            return None
        return {"url": url, "level": actual, "trial": trial(payload), "source": "web"}
    return None


def via_mobile(file_hash, album_id, cookie, auth, timeout):
    params = {
        "cmd": "playInfo", "hash": file_hash, "key": md5(file_hash + "kgcloud"),
        "album_id": album_id or "0", "pid": "1", "forceDown": "0", "vip": "65530",
    }
    if auth["userid"]:
        params["userid"] = auth["userid"]
    if auth["token"]:
        params["token"] = auth["token"]
    payload = get_json(MOBILE + "?" + urlencode(params), request_cookie(cookie, auth), timeout, {"Referer": "https://m.kugou.com/"})
    url = pick_url(payload)
    if payload and int(payload.get("status") or 0) == 1 and url:
        return {"url": url, "level": "standard", "trial": trial(payload), "source": "mobile"}
    return None


def via_gateway(file_hash, album_id, album_audio_id, cookie, auth, level, timeout, h5=True):
    if not auth["ready"]:
        return None
    quality = quality_param(level)
    if h5:
        params = h5_params(auth, {
            "album_id": int(album_id or 0), "area_code": 1, "hash": file_hash.lower(),
            "ssa_flag": "is_fromtrack", "version": 11430, "page_id": 151369488,
            "quality": quality,
            "album_audio_id": int(album_audio_id or 0), "behavior": "play", "pid": 2,
            "cmd": 26, "pidversion": 3001, "IsFreePart": 0,
            "ppage_id": "463467626,350369493,788954147", "cdnBackup": 1,
            "module": "", "clientver": 11430,
        })
        params["key"] = md5("%s%s%s%s%s" % (file_hash.lower(), SIGN_KEY_SALT, WEB_APPID, auth["mid"], auth["userid"] or 0))
        params["signature"] = signature_h5(params)
        headers = {"x-router": "trackercdn.kugou.com"}
    else:
        params = {
            "dfid": auth["dfid"], "mid": auth["mid"], "uuid": "-", "appid": APPID,
            "clientver": CLIENTVER, "clienttime": int(time.time()), "token": auth["token"],
            "userid": auth["userid"], "album_id": int(album_id or 0), "area_code": 1,
            "hash": file_hash.lower(), "ssa_flag": "is_fromtrack", "version": 11430,
            "page_id": 151369488, "quality": quality,
            "album_audio_id": int(album_audio_id or 0), "behavior": "play",
            "pid": 2, "cmd": 26, "pidversion": 3001, "IsFreePart": 0,
            "ppage_id": "463467626,350369493,788954147", "cdnBackup": 1,
            "module": "", "clientver": 11430,
        }
        params["key"] = md5("%s%s%s%s%s" % (params["hash"], SIGN_KEY_SALT, APPID, auth["mid"], auth["userid"] or 0))
        params["signature"] = signature_android(params)
        headers = {"User-Agent": GATEWAY_UA, "x-router": "trackercdn.kugou.com", "dfid": auth["dfid"], "mid": auth["mid"]}
    payload = get_json(GATEWAY + "/v5/url?" + urlencode(params, quote_via=quote), request_cookie(cookie, auth), timeout, headers)
    url = pick_url(payload)
    if payload and int(payload.get("status") or 0) == 1 and url:
        return {"url": url, "level": level, "trial": trial(payload), "source": "h5" if h5 else "gateway"}
    return None


def resolve(file_hash, album_id="", album_audio_id=0, quality=QUALITY, timeout=8):
    file_hash = str(file_hash or "").strip()
    if not file_hash:
        raise ValueError("missing kugou hash")
    quality = quality if quality in LEVELS else QUALITY
    chain = LEVELS[LEVELS.index(quality):]
    cookie = load_cookie()
    auth = auth_from(cookie)
    cookie, auth = ensure_device(cookie, auth)
    attempts = []
    for level in chain:
        attempts.append(lambda level=level: via_v6(file_hash, album_audio_id, cookie, auth, level, timeout))
        attempts.append(lambda level=level: via_gateway(file_hash, album_id, album_audio_id, cookie, auth, level, timeout, True))
        attempts.append(lambda level=level: via_gateway(file_hash, album_id, album_audio_id, cookie, auth, level, timeout, False))
        attempts.append(lambda level=level: via_web(file_hash, album_id, album_audio_id, cookie, auth, level, timeout, False))
        attempts.append(lambda level=level: via_web(file_hash, album_id, album_audio_id, cookie, auth, level, timeout, True))
        if level == "standard":
            attempts.append(lambda: via_mobile(file_hash, album_id, cookie, auth, timeout))
    for run in attempts:
        found = run()
        if found and found.get("url"):
            return {
                "provider": "kugou",
                "id": file_hash,
                "url": found["url"],
                "requested": quality,
                "level": found.get("level") or quality,
                "trial": bool(found.get("trial")),
                "playable": True,
                "loggedIn": auth["ready"],
                "source": found.get("source"),
                "restriction": None,
            }
    return {
        "provider": "kugou",
        "id": file_hash,
        "url": "",
        "requested": quality,
        "level": "",
        "trial": False,
        "playable": False,
        "loggedIn": auth["ready"],
        "restriction": {
            "category": "login_required" if not auth["ready"] else "url_unavailable",
            "message": "酷狗没有返回播放地址。会员曲目需要 cookie 中的 userid 和 token。",
        },
    }


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: playurl.py <hash> [quality] [album_id] [album_audio_id] [--json]", file=sys.stderr)
        return 2
    as_json = "--json" in argv[2:]
    if any(item.startswith("--") and item != "--json" for item in argv[2:]) or argv[2:].count("--json") > 1:
        print("playurl.py: unknown or repeated option", file=sys.stderr)
        return 2
    args = [item for item in argv[1:] if item != "--json"]
    if not 1 <= len(args) <= 4:
        print("playurl.py: invalid arguments", file=sys.stderr)
        return 2
    if len(args) > 2 and args[2] and not str(args[2]).isdigit():
        print("playurl.py: album_id must be numeric", file=sys.stderr)
        return 2
    if len(args) > 3 and args[3] and not str(args[3]).isdigit():
        print("playurl.py: album_audio_id must be numeric", file=sys.stderr)
        return 2
    try:
        result = resolve(
            args[0],
            args[2] if len(args) > 2 else "",
            int(args[3]) if len(args) > 3 and str(args[3]).isdigit() else 0,
            args[1] if len(args) > 1 else QUALITY,
        )
    except ValueError as exc:
        print("playurl.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "kugou", "playable": False, "url": "", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    if as_json or not result.get("url"):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["url"])
    return 0 if result.get("playable") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
