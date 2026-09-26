#!/usr/bin/env python3
"""Resolve a Qishui playback URL. This folder is standalone.

Free public tracks do not require a cookie. For account-only PC requests,
put the SodaMusic PC Cookie header in the same-directory ``cookie`` file.

A returned URL containing #auth= is encrypted. Pass --decrypt to download
and decrypt it with the Python decryptor in this same folder.
"""
import base64
import json
import os
import struct
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent


BASE = "https://api.qishui.com"
SEO_TRACK_URL = "https://beta-luna.douyin.com/luna/h5/seo_track"
UA = "LunaPC/3.3.0(359450208)"
# 默认只返回可直接播放的 M4A/MP3。改为 True 才允许 FLAC 及可能
# 解密为 FLAC 的加密流进入候选。
ENABLE_FLAC = False
PLAYBACK_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.qishui.com/",
}


class QishuiError(RuntimeError):
    def __init__(self, message, category="source_unavailable"):
        super().__init__(message)
        self.category = category



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


def logged_in(cookie):
    return bool(core_session_cookie(cookie))


def core_session_cookie(cookie):
    values = parse_cookie(cookie)
    token = values.get("sessionid") or values.get("sessionid_ss") or values.get("sid_tt") or ""
    return "sessionid=" + token if token else ""


def session_cookie(cookie):
    return cookie


def pc_params(extra=None):
    now = str(int(time.time() * 1000))
    params = {
        "aid": "386088", "app_name": "luna_pc", "region": "cn", "geo_region": "cn",
        "os_region": "cn", "sim_region": "", "device_id": now, "cdid": "",
        "iid": str(int(now) + 1), "version_name": "3.3.0", "version_code": "30030000",
        "channel": "official", "build_mode": "master", "network_carrier": "",
        "ac": "wifi", "tz_name": "Asia/Shanghai", "resolution": "",
        "device_platform": "windows", "device_type": "Windows", "os_version": "Windows 11",
        "fp": now,
    }
    params.update(extra or {})
    return params


def request_headers(cookie, content_type=False):
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "User-Agent": UA,
        "Referer": "https://www.qishui.com/",
        "x-luna-background-type": "foreground",
        "x-luna-is-background-req": "0",
        "x-luna-is-local-user": "1",
    }
    if cookie:
        headers["Cookie"] = session_cookie(cookie)
    if content_type:
        headers["Content-Type"] = "application/json; charset=utf-8"
    return headers


def request_json(method, params, cookie, body=None, timeout=12, url=""):
    url = url or (BASE + "/luna/pc/track_v2?" + urlencode(params))
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method, headers=request_headers(cookie, data is not None))
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if not raw.strip():
        raise QishuiError("汽水接口返回空正文。", "empty_response")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise QishuiError("汽水接口返回了无效 JSON。") from exc
    if not isinstance(payload, dict):
        raise QishuiError("汽水接口返回了非对象 JSON。")
    return payload


def request_json_with_session_fallback(method, params, cookie, body=None, timeout=12, url=""):
    """Retry a rejected full cookie jar with its core sessionid only."""
    core = core_session_cookie(cookie)
    try:
        payload = request_json(method, params, cookie, body, timeout, url)
    except (HTTPError, URLError, OSError, ValueError, QishuiError):
        if not core or core == cookie:
            raise
        return request_json(method, params, core, body, timeout, url)
    code = payload.get("status_code", payload.get("error_code", 0))
    if code not in (0, "0", None) and core and core != cookie:
        return request_json(method, params, core, body, timeout, url)
    return payload


def first(obj, keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if obj.get(key) not in (None, ""):
            return obj.get(key)
    return None


def number(value):
    try:
        return int(float(str(value or "0").lower().replace("kbps", "").replace("k", "").strip()))
    except ValueError:
        return 0


def first_url(value):
    if isinstance(value, str) and value.startswith("http"):
        return value
    if isinstance(value, list):
        for item in value:
            found = first_url(item)
            if found:
                return found
    if isinstance(value, dict):
        for key in ("url", "main_url", "main_play_url", "backup_url", "backup_play_url"):
            found = first_url(value.get(key))
            if found:
                return found
    return ""


def walk_streams(node, found, inherited_auth=""):
    if isinstance(node, str) and node.lstrip().startswith(("{", "[", '"')):
        try:
            parsed = json.loads(node)
        except ValueError:
            parsed = None
        if parsed is not None and parsed != node:
            walk_streams(parsed, found, inherited_auth)
        return
    if isinstance(node, list):
        for item in node:
            walk_streams(item, found, inherited_auth)
        return
    if not isinstance(node, dict):
        return
    encrypt_info = first(node, ("encrypt_info", "EncryptInfo", "encryptInfo"))
    own_auth = first(node, ("play_auth", "PlayAuth", "spade_a", "SpadeA")) or first(
        encrypt_info, ("play_auth", "PlayAuth", "spade_a", "SpadeA")
    ) or inherited_auth
    video_meta = first(node, ("video_meta", "VideoMeta", "videoMeta"))
    if not isinstance(video_meta, dict):
        video_meta = {}
    url = first(node, (
        "main_play_url", "MainPlayUrl", "main_url", "MainUrl", "url", "URL",
        "play_url", "PlayUrl", "playable_url", "PlayableUrl", "backup_play_url",
        "BackupPlayUrl", "backup_url", "BackupUrl",
    ))
    url = first_url(url) or first_url(first(node, ("url_list", "UrlList", "backup_urls", "BackupUrls")))
    if url:
        found.append({
            "url": url,
            "auth": own_auth,
            "quality": first(node, ("quality", "Quality", "definition", "Definition")) or
                       first(video_meta, ("quality", "Quality", "definition", "Definition")) or "",
            "bitrate": number(first(node, ("bitrate", "Bitrate", "real_bitrate", "RealBitrate", "br")) or
                              first(video_meta, ("bitrate", "Bitrate", "real_bitrate", "RealBitrate", "br"))),
            "size": number(first(node, ("size", "Size", "file_size", "FileSize")) or
                           first(video_meta, ("size", "Size", "file_size", "FileSize"))),
            "format": first(node, ("format", "Format", "vtype", "VType")) or
                      first(video_meta, ("format", "Format", "vtype", "VType")) or "",
            "duration": number(first(node, ("duration", "Duration", "duration_ms"))),
            "trial": first(node, ("is_free_part", "isFreePart", "trial", "is_trial", "isTrial")) in (1, "1", True, "true"),
        })
    for value in node.values():
        if isinstance(value, (dict, list)) or (isinstance(value, str) and value.lstrip().startswith(("{", "[", '"'))):
            walk_streams(value, found, own_auth)


def find_values(node, keys, found=None):
    found = [] if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            if key in keys and value not in (None, ""):
                found.append(value)
            if isinstance(value, (dict, list)):
                find_values(value, keys, found)
    elif isinstance(node, list):
        for value in node:
            find_values(value, keys, found)
    return found


def _fetch_track_with_cookie(track_id, cookie, timeout):
    body = {
        "track_id": track_id,
        "media_type": "track",
        "queue_type": "favorite_track_playlist",
        "scene_name": "library",
    }
    try:
        return request_json("POST", pc_params(), cookie, body, timeout)
    except (HTTPError, URLError, OSError, ValueError, QishuiError) as post_error:
        try:
            return request_json(
                "GET", pc_params({"track_id": track_id, "media_type": "track"}),
                cookie, timeout=timeout,
            )
        except (HTTPError, URLError, OSError, ValueError, QishuiError) as get_error:
            if isinstance(get_error, QishuiError):
                raise get_error
            raise QishuiError("汽水播放信息请求失败：%s" % get_error) from post_error


def fetch_track(track_id, cookie, timeout):
    core = core_session_cookie(cookie)
    try:
        payload = _fetch_track_with_cookie(track_id, cookie, timeout)
    except (HTTPError, URLError, OSError, ValueError, QishuiError):
        if not core or core == cookie:
            raise
        return _fetch_track_with_cookie(track_id, core, timeout)
    code = payload.get("status_code", payload.get("error_code", 0))
    if code not in (0, "0", None) and core and core != cookie:
        return _fetch_track_with_cookie(track_id, core, timeout)
    return payload


def fetch_public_track(track_id, timeout=12):
    """Fetch the public detail for exactly one requested track."""
    url = SEO_TRACK_URL + "?" + urlencode({
        "track_id": track_id,
        "device_platform": "web",
    })
    return request_json("GET", {}, "", timeout=timeout, url=url)


def public_track_parts(payload, track_id):
    seo = payload.get("seo_track") if isinstance(payload, dict) else None
    if not isinstance(seo, dict):
        raise QishuiError("汽水公开详情缺少 seo_track。", "url_unavailable")
    track = seo.get("track")
    # Current public responses keep track_player beside seo_track, while older
    # captures may nest it inside seo_track.  In both shapes the validated
    # seo_track.track id above is the binding to the requested song.
    player = seo.get("track_player") or payload.get("track_player")
    if not isinstance(track, dict) or str(track.get("id") or "") != str(track_id):
        raise QishuiError("汽水公开详情与目标歌曲不匹配。", "url_unavailable")
    if not isinstance(player, dict):
        raise QishuiError("汽水公开详情没有目标歌曲播放信息。", "url_unavailable")
    return track, player


def stream_allowed_for_free_account(track, stream):
    label = track.get("label_info") if isinstance(track, dict) else {}
    label = label if isinstance(label, dict) else {}
    if label.get("only_vip_playable") in (1, "1", True, "true"):
        return False
    quality_map = label.get("quality_map")
    quality_map = quality_map if isinstance(quality_map, dict) else {}
    quality = str(stream.get("quality") or "")
    detail = quality_map.get(quality)
    detail = detail if isinstance(detail, dict) else {}
    play = detail.get("play_detail")
    play = play if isinstance(play, dict) else {}
    return play.get("need_vip") not in (1, "1", True, "true") and \
        play.get("need_purchase") not in (1, "1", True, "true")


def stream_allowed_format(stream):
    if ENABLE_FLAC:
        return True
    value = " ".join((
        str(stream.get("format") or ""),
        str(stream.get("quality") or ""),
        str(stream.get("url") or ""),
    )).lower()
    if any(marker in value for marker in ("flac", "lossless", "hires", "hi-res")):
        return False
    # 汽水带 play_auth/spade_a 的流需要先解密，解密结果可能是 FLAC。
    # 默认格式策略下不自动选择这种流。
    return not bool(stream.get("auth"))


def resolve_public_track(track_id, timeout=12, logged_in_state=False):
    payload = fetch_public_track(track_id, timeout)
    track, player = public_track_parts(payload, track_id)
    label = track.get("label_info") if isinstance(track.get("label_info"), dict) else {}
    if label.get("only_vip_playable") in (1, "1", True, "true"):
        return {
            "provider": "qishui", "id": track_id, "url": "", "playable": False,
            "loggedIn": bool(logged_in_state), "source": "qishui-public-seo",
            "restriction": {"category": "vip_required", "message": "该汽水歌曲需要会员权益。"},
        }
    streams = []
    walk_streams(player, streams)
    streams = [item for item in streams
               if stream_allowed_for_free_account(track, item) and stream_allowed_format(item)]
    if not streams:
        raise QishuiError("汽水公开详情没有非会员可用的完整播放地址。", "url_unavailable")
    streams.sort(key=lambda item: number(item.get("bitrate")), reverse=True)
    best = streams[0]
    auth = str(best.get("auth") or "")
    url = best["url"] + (("#auth=" + quote(auth, safe="")) if auth and "#auth=" not in best["url"] else "")
    return {
        "provider": "qishui", "id": track_id, "url": url,
        "level": best.get("quality") or "", "bitrate": number(best.get("bitrate")),
        "size": number(best.get("size")), "format": best.get("format") or "",
        "duration": number(best.get("duration")) or number(track.get("duration")),
        "trial": False, "playable": True, "encrypted": bool(auth),
        "directPlayable": not bool(auth), "loggedIn": bool(logged_in_state),
        "httpHeaders": dict(PLAYBACK_HEADERS),
        "source": "qishui-public-seo",
        "restriction": None,
    }


def resolve(track_id, timeout=12):
    track_id = str(track_id or "").strip()
    cookie = load_cookie()
    if not track_id:
        raise ValueError("missing qishui track id")
    has_login = logged_in(cookie)
    if not has_login:
        try:
            return resolve_public_track(track_id, timeout, False)
        except (HTTPError, URLError, OSError, ValueError, QishuiError):
            return {
                "provider": "qishui", "id": track_id, "url": "", "playable": False,
                "loggedIn": False, "restriction": {
                    "category": "login_required",
                    "message": "公开详情没有非会员可用的完整流；登录后可继续尝试。",
                },
            }
    try:
        payload = fetch_track(track_id, cookie, timeout)
    except QishuiError as exc:
        try:
            return resolve_public_track(track_id, timeout, True)
        except (HTTPError, URLError, OSError, ValueError, QishuiError):
            return {
                "provider": "qishui", "id": track_id, "url": "", "playable": False,
                "loggedIn": True,
                "restriction": {"category": exc.category, "message": str(exc)},
            }
    code = payload.get("status_code", payload.get("error_code", 0))
    if code not in (0, None, "0"):
        return {
            "provider": "qishui", "id": track_id, "url": "", "playable": False, "loggedIn": True,
            "restriction": {"category": "source_unavailable", "message": "汽水接口返回错误 %s" % code},
        }
    streams = []
    walk_streams(payload, streams)
    player_urls = find_values(payload, {"url_player_info", "URLPlayerInfo", "urlPlayerInfo"})
    for player_url in player_urls:
        if not isinstance(player_url, str) or not player_url.startswith("http"):
            continue
        try:
            player = request_json_with_session_fallback(
                "GET", {}, cookie, timeout=timeout, url=player_url
            )
            walk_streams(player, streams)
        except (HTTPError, URLError, OSError, ValueError, QishuiError):
            continue
    streams = [item for item in streams if stream_allowed_format(item)]
    if not streams:
        return {
            "provider": "qishui", "id": track_id, "url": "", "playable": False, "loggedIn": True,
            "restriction": {"category": "url_unavailable", "message": "汽水没有返回播放地址。"},
        }
    streams.sort(key=lambda item: number(item.get("bitrate")), reverse=True)
    best = streams[0]
    auth = str(best.get("auth") or "")
    url = best["url"] + (("#auth=" + quote(auth, safe="")) if auth and "#auth=" not in best["url"] else "")
    return {
        "provider": "qishui",
        "id": track_id,
        "url": url,
        "level": best.get("quality") or "",
        "trial": bool(best.get("trial")),
        "playable": True,
        "encrypted": bool(auth),
        "directPlayable": not bool(auth),
        "httpHeaders": dict(PLAYBACK_HEADERS),
        "loggedIn": True,
        "restriction": None,
    }


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
    value = inverse
    result = value
    rotated = value
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


def _aes_encrypt_block(block, round_keys):
    state = bytearray(block[i] ^ round_keys[0][i] for i in range(16))
    for round_key in round_keys[1:-1]:
        state = _sub_shift_mix(state, True)
        state = bytearray(state[i] ^ round_key[i] for i in range(16))
    state = _sub_shift_mix(state, False)
    last = round_keys[-1]
    return bytes(state[i] ^ last[i] for i in range(16))


def _expand_key(key):
    size = len(key)
    if size not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24, or 32 bytes")
    rounds = {16: 10, 24: 12, 32: 14}[size]
    columns = [list(key[i:i + 4]) for i in range(0, size, 4)]
    rcon = 1
    while len(columns) < 4 * (rounds + 1):
        temp = columns[-1][:]
        if len(columns) % (size // 4) == 0:
            temp = temp[1:] + temp[:1]
            temp = [SBOX[item] for item in temp]
            temp[0] ^= rcon
            rcon = _xtime(rcon)
        elif size == 32 and len(columns) % 8 == 4:
            temp = [SBOX[item] for item in temp]
        prev = columns[-size // 4]
        columns.append([prev[i] ^ temp[i] for i in range(4)])
    keys = []
    for index in range(rounds + 1):
        block = bytearray(16)
        for column, word in enumerate(columns[index * 4:(index + 1) * 4]):
            for row, item in enumerate(word):
                block[column * 4 + row] = item
        keys.append(bytes(block))
    return keys


def _aes_ctr(data, key, iv):
    counter = int.from_bytes(iv[:16].ljust(16, b"\x00"), "big")
    keys = _expand_key(key)
    out = bytearray()
    for offset in range(0, len(data), 16):
        stream = _aes_encrypt_block(counter.to_bytes(16, "big"), keys)
        block = data[offset:offset + 16]
        out.extend(block[i] ^ stream[i] for i in range(len(block)))
        counter = (counter + 1) & ((1 << 128) - 1)
    return bytes(out)


def _u32(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def _bit_count(value):
    value &= 0xFFFFFFFF
    value = value - ((value >> 1) & 0x55555555)
    value = (value & 0x33333333) + ((value >> 2) & 0x33333333)
    return (((value + (value >> 4)) & 0x0F0F0F0F) * 0x01010101) >> 24


def _decrypt_spade_a(spade_a):
    try:
        raw = base64.b64decode(spade_a)
    except (ValueError, TypeError):
        return ""
    if len(raw) < 3:
        return ""
    padding = (raw[0] ^ raw[1] ^ raw[2]) - 48
    if padding < 0 or len(raw) < padding + 2:
        return ""
    inner = raw[1:len(raw) - padding]
    working = bytes((0xFA, 0x55)) + inner
    out = bytearray(len(inner))
    for index, item in enumerate(inner):
        value = (item ^ working[index]) - _bit_count(index) - 21
        while value < 0:
            value += 0xFF
        out[index] = value & 0xFF
    if not out:
        return ""
    first = out[0]
    skip = first - 48 if 48 <= first <= 57 else (first - 87 if 97 <= first <= 122 else 0xFF)
    end = 1 + (len(raw) - padding - 2) - skip
    if skip == 0xFF or end > len(out) or end < 1:
        return ""
    return out[1:end].decode("utf-8", "replace")


def _find_box(data, box_type, start=0, end=None):
    end = len(data) if end is None else end
    position = start
    wanted = box_type.encode("ascii")
    while position + 8 <= end:
        size = _u32(data, position)
        header_size = 8
        if size == 1:
            if position + 16 > end:
                break
            size = struct.unpack_from(">Q", data, position + 8)[0]
            header_size = 16
        elif size == 0:
            size = end - position
        if size < header_size or position + size > end:
            break
        if data[position + 4:position + 8] == wanted:
            return position, size, data[position + header_size:position + size]
        position += size
    return None


def _find_box_recursive(data, box_type, start=0, end=None, depth=0):
    end = len(data) if end is None else end
    direct = _find_box(data, box_type, start, end)
    if direct or depth >= 8:
        return direct
    containers = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"moof", b"traf", b"schi"}
    position = start
    while position + 8 <= end:
        size = _u32(data, position)
        header_size = 8
        if size == 1:
            if position + 16 > end:
                break
            size = struct.unpack_from(">Q", data, position + 8)[0]
            header_size = 16
        elif size == 0:
            size = end - position
        if size < header_size or position + size > end:
            break
        if data[position + 4:position + 8] in containers:
            found = _find_box_recursive(data, box_type, position + header_size, position + size, depth + 1)
            if found:
                return found
        position += size
    return None


def _box_payload_start(box):
    return box[0] + box[1] - len(box[2])


def decrypt_bytes(encrypted, spade_a):
    key_hex = spade_a if all(ch in "0123456789abcdefABCDEF" for ch in spade_a) else _decrypt_spade_a(spade_a)
    if not key_hex or len(key_hex) % 2:
        raise RuntimeError("failed to resolve qishui decryption key")
    key = bytes.fromhex(key_hex)
    moov = _find_box(encrypted, "moov")
    if not moov:
        raise RuntimeError("moov atom not found")
    moov_off, moov_size, _ = moov
    trak = _find_box(encrypted, "trak", _box_payload_start(moov), moov_off + moov_size)
    if not trak:
        raise RuntimeError("trak atom not found")
    mdia = _find_box(encrypted, "mdia", _box_payload_start(trak), trak[0] + trak[1])
    if not mdia:
        raise RuntimeError("mdia atom not found")
    minf = _find_box(encrypted, "minf", _box_payload_start(mdia), mdia[0] + mdia[1])
    if not minf:
        raise RuntimeError("minf atom not found")
    stbl = _find_box(encrypted, "stbl", _box_payload_start(minf), minf[0] + minf[1])
    if not stbl:
        raise RuntimeError("stbl atom not found")
    stsd = _find_box(encrypted, "stsd", _box_payload_start(stbl), stbl[0] + stbl[1])
    stsz = _find_box(encrypted, "stsz", _box_payload_start(stbl), stbl[0] + stbl[1])
    senc = _find_box_recursive(encrypted, "senc", _box_payload_start(moov), moov_off + moov_size)
    mdat = _find_box(encrypted, "mdat")
    if not all((stsd, stsz, senc, mdat)):
        raise RuntimeError("required mp4 atoms are missing")
    sample_size, count = _u32(stsz[2], 4), _u32(stsz[2], 8)
    if count > 10000000:
        raise RuntimeError("unreasonable mp4 sample count")
    if not sample_size and len(stsz[2]) < 12 + count * 4:
        raise RuntimeError("truncated stsz atom")
    sizes = [sample_size] * count if sample_size else [_u32(stsz[2], 12 + i * 4) for i in range(count)]
    ivs = []
    pos = 8
    for _ in range(count):
        if pos + 8 > len(senc[2]):
            raise RuntimeError("truncated senc atom")
        ivs.append(senc[2][pos:pos + 8] + b"\x00" * 8)
        pos += 8
    if len(sizes) != len(ivs):
        raise RuntimeError("sample count does not match iv count")
    marker = b"dfLa"
    marker_at = stsd[2].find(marker)
    flac = b""
    if marker_at >= 4:
        box_size = _u32(stsd[2], marker_at - 4)
        flac = stsd[2][marker_at + 4:min(marker_at - 4 + box_size, len(stsd[2]))]
    samples = []
    offset = _box_payload_start(mdat)
    for size, iv in zip(sizes, ivs):
        samples.append(_aes_ctr(encrypted[offset:offset + size], key, iv))
        offset += size
    if flac:
        return b"fLaC" + (flac[4:] if len(flac) > 4 else flac) + b"".join(samples), ".flac"
    output = bytearray(encrypted)
    write_at = _box_payload_start(mdat)
    for sample in samples:
        output[write_at:write_at + len(sample)] = sample
        write_at += len(sample)
    start, end = stsd[0], stsd[0] + stsd[1]
    found = output.find(b"enca", start, end)
    if found >= 0:
        output[found:found + 4] = b"mp4a"
    return bytes(output), ".m4a"


def decrypt_to(result, output):
    auth = ""
    url = result["url"]
    if "#auth=" in url:
        url, auth = url.split("#auth=", 1)
        auth = unquote(auth)
    if not auth:
        raise RuntimeError("url has no #auth= fragment to decrypt")
    req = Request(url, headers=PLAYBACK_HEADERS)
    with urlopen(req, timeout=30) as resp:
        encrypted = resp.read()
    data, extension = decrypt_bytes(encrypted, auth)
    target = Path(output)
    if target.suffix.lower() != extension:
        target = target.with_suffix(extension)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(prefix=target.name + ".", suffix=".tmp", dir=target.parent, delete=False) as handle:
            temp_name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return {"decryptedFile": str(target), "bytes": len(data), "extension": extension}




def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: playurl.py <track_id> [--decrypt output.m4a] [--json]", file=sys.stderr)
        return 2
    if not str(argv[1]).isdigit():
        print("playurl.py: track_id must be numeric", file=sys.stderr)
        return 2
    as_json = False
    decrypt = False
    output = ""
    index = 2
    while index < len(argv):
        item = argv[index]
        if item == "--json" and not as_json:
            as_json = True
            index += 1
        elif item == "--decrypt" and not decrypt:
            decrypt = True
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                print("playurl.py: --decrypt requires an output path", file=sys.stderr)
                return 2
            output = argv[index + 1]
            index += 2
        else:
            print("playurl.py: unknown or repeated argument %s" % item, file=sys.stderr)
            return 2
    try:
        result = resolve(argv[1])
        if decrypt:
            if not result.get("playable"):
                raise RuntimeError(result.get("restriction", {}).get("message") or "no url")
            result.update(decrypt_to(result, output))
            result["directPlayable"] = True
            result["encrypted"] = False
    except (HTTPError, URLError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"provider": "qishui", "playable": False, "url": "", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    if as_json or decrypt or not result.get("url") or not result.get("directPlayable", True):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["url"])
    return 0 if result.get("playable") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
