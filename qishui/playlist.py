#!/usr/bin/env python3
"""List Qishui account playlists and their tracks. Standard library only."""
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
BASE = "https://api.qishui.com"
UA = "LunaPC/3.3.0(359450208)"
SEARCH_UA = "LunaPC/3.0.0(290101097)"
LIKED_ID = "liked"
RECENT_ID = "recent"


def load_cookie():
    path = HERE / "cookie"
    if not path.is_file():
        return ""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return "; ".join(line for line in lines if line and not line.startswith("#"))


def parse_cookie(cookie):
    values = {}
    for part in str(cookie or "").split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip():
                values[key.strip()] = value.strip()
    return values


def core_session_cookie(cookie):
    values = parse_cookie(cookie)
    token = values.get("sessionid") or values.get("sessionid_ss") or values.get("sid_tt") or ""
    return "sessionid=" + token if token else ""


def logged_in(cookie):
    return bool(core_session_cookie(cookie))


def pc_params(extra=None):
    now = str(int(time.time() * 1000))
    params = {
        "aid": "386088", "app_name": "luna_pc", "region": "cn", "geo_region": "cn",
        "os_region": "cn", "sim_region": "", "device_id": now, "cdid": "",
        "iid": str(int(now) + 1), "version_name": "3.3.0", "version_code": "30030000",
        "channel": "official", "build_mode": "master", "network_carrier": "", "ac": "wifi",
        "tz_name": "Asia/Shanghai", "resolution": "", "device_platform": "windows",
        "device_type": "Windows", "os_version": "Windows 11", "fp": now,
    }
    params.update(extra or {})
    return params


def headers(cookie):
    result = {
        "Accept": "application/json,text/plain,*/*", "User-Agent": UA,
        "Referer": "https://www.qishui.com/",
        "x-luna-background-type": "foreground", "x-luna-is-background-req": "0",
        "x-luna-is-local-user": "1",
    }
    if cookie:
        result["Cookie"] = cookie
    return result


def get_json(path, params, cookie, timeout=12, user_agent=UA):
    url = BASE + path + "?" + urlencode(pc_params(params))
    request_headers = headers(cookie)
    request_headers["User-Agent"] = user_agent
    req = Request(url, headers=request_headers)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
        if not raw.strip():
            raise RuntimeError("汽水歌单接口返回空正文")
        payload = json.loads(raw.decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError("qishui playlist failed: %s" % exc) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("qishui playlist returned a non-object")
    code = payload.get("status_code", payload.get("error_code", 0))
    if code not in (0, "0", None):
        raise RuntimeError("qishui playlist returned error %s" % code)
    return payload


def authenticated_get_json(path, params, cookie, timeout=12, user_agent=UA):
    """Use the full jar first, then retry with the long-lived sessionid only."""
    core = core_session_cookie(cookie)
    try:
        return get_json(path, params, cookie, timeout, user_agent)
    except RuntimeError:
        if not core or core == cookie:
            raise
        return get_json(path, params, core, timeout, user_agent)


def first_url(value):
    if isinstance(value, str) and value.startswith("http"):
        return value
    if isinstance(value, list):
        for item in value:
            found = first_url(item)
            if found:
                return found
    if isinstance(value, dict):
        urls = value.get("urls")
        uri = str(value.get("uri") or "")
        if isinstance(urls, list) and urls and isinstance(urls[0], str):
            return urls[0] + uri
        for key in ("url", "urls", "main_url", "cover_url", "medium_url"):
            found = first_url(value.get(key))
            if found:
                return found
    return ""


def playlist_row(item, source="mine"):
    if not isinstance(item, dict):
        return None
    playlist_id = item.get("id") or item.get("playlist_id")
    if not playlist_id:
        return None
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    resources = item.get("resource_cnt") if isinstance(item.get("resource_cnt"), dict) else {}
    return {
        "provider": "qishui", "id": str(playlist_id),
        "name": item.get("title") or item.get("public_title") or item.get("name") or "汽水歌单",
        "trackCount": item.get("count_tracks") or resources.get("track_cnt") or item.get("track_count") or 0,
        "creator": owner.get("nickname") or owner.get("public_name") or "",
        "cover": first_url(item.get("url_cover") or item.get("cover")), "source": source,
    }


def track_from(value):
    if not isinstance(value, dict):
        return None
    entity = value.get("entity") if isinstance(value.get("entity"), dict) else {}
    wrapper = entity.get("track_wrapper") if isinstance(entity.get("track_wrapper"), dict) else {}
    track = wrapper.get("track") if isinstance(wrapper.get("track"), dict) else None
    if track is None and isinstance(value.get("track_wrapper"), dict):
        track = value["track_wrapper"].get("track")
    if track is None and value.get("media_type") == "track":
        track = value
    if not isinstance(track, dict) or not track.get("id"):
        return None
    artists = track.get("artists") if isinstance(track.get("artists"), list) else []
    album = track.get("album") if isinstance(track.get("album"), dict) else {}
    return {
        "provider": "qishui", "id": str(track["id"]), "name": track.get("name") or "",
        "artist": " / ".join(str(item.get("name")) for item in artists if isinstance(item, dict) and item.get("name")),
        "album": album.get("name") or "", "duration": track.get("duration") or 0,
    }


def extract_tracks(payload):
    rows = []
    seen = set()

    def visit(node, depth=0):
        if depth > 8:
            return
        if isinstance(node, list):
            for item in node:
                visit(item, depth + 1)
            return
        if not isinstance(node, dict):
            return
        row = track_from(node)
        if row and row["id"] not in seen:
            seen.add(row["id"])
            rows.append(row)
            return
        for value in node.values():
            if isinstance(value, (dict, list)):
                visit(value, depth + 1)

    visit(payload)
    return rows


def require_session():
    cookie = load_cookie()
    if not logged_in(cookie):
        raise RuntimeError("qishui cookie missing login session")
    return cookie


def created_playlists(cookie, timeout):
    core = core_session_cookie(cookie)
    active_cookie = cookie
    try:
        me = get_json("/luna/pc/me", {}, active_cookie, timeout)
    except RuntimeError:
        if not core or core == active_cookie:
            raise
        active_cookie = core
        me = get_json("/luna/pc/me", {}, active_cookie, timeout)
    user_id = str((me.get("my_info") or {}).get("id") or "")
    if not user_id and core and core != active_cookie:
        active_cookie = core
        me = get_json("/luna/pc/me", {}, active_cookie, timeout)
        user_id = str((me.get("my_info") or {}).get("id") or "")
    if not user_id:
        raise RuntimeError("qishui account did not return a user id")
    return authenticated_get_json("/luna/pc/user/playlist", {
        "user_id": user_id, "cursor": "", "count": 100,
    }, active_cookie, timeout).get("playlists") or []


def is_primary_liked_playlist(item):
    name = str((item or {}).get("title") or (item or {}).get("public_title") or "")
    return "喜欢" in name and "抖音" not in name and "收藏" not in name


def search(keywords, limit=10, offset=0, timeout=12):
    keywords = str(keywords or "").strip()
    if not keywords:
        raise ValueError("missing keywords")
    limit = max(1, min(int(limit or 10), 30))
    offset = max(0, int(offset or 0))
    cookie = ""
    rows = []
    cursor = offset
    while len(rows) < limit:
        payload = get_json("/luna/pc/search/playlist", {
            "version_name": "3.0.0", "version_code": "30000000",
            "q": keywords, "cursor": cursor, "search_id": "",
            "search_method": "input", "debug_params": "",
            "from_search_id": "", "search_scene": "",
        }, cookie, timeout, user_agent=SEARCH_UA)
        groups = payload.get("result_groups") or []
        page_items = []
        has_more = False
        next_cursor = ""
        for group in groups:
            if not isinstance(group, dict):
                continue
            page_items.extend(group.get("data") or [])
            has_more = has_more or bool(group.get("has_more"))
            if group.get("next_cursor") not in (None, ""):
                next_cursor = str(group.get("next_cursor"))
        page_rows = []
        for item in page_items:
            entity = item.get("entity") if isinstance(item, dict) and isinstance(item.get("entity"), dict) else {}
            row = playlist_row(entity.get("playlist") or (item.get("playlist") if isinstance(item, dict) else None), "search")
            if row:
                page_rows.append(row)
        known = {row["id"] for row in rows}
        rows.extend(row for row in page_rows if row["id"] not in known)
        if len(rows) >= limit or not page_rows or not has_more or not next_cursor:
            break
        try:
            next_value = int(next_cursor)
        except ValueError:
            break
        if next_value <= cursor:
            break
        cursor = next_value
    return rows[:limit]


def mine(limit=30, offset=0, timeout=12):
    limit = max(1, min(int(limit or 30), 100))
    offset = max(0, int(offset or 0))
    cookie = require_session()
    created = created_playlists(cookie, timeout)
    rows = [
        {"provider": "qishui", "id": LIKED_ID, "name": "我的喜欢", "source": "mine"},
        {"provider": "qishui", "id": RECENT_ID, "name": "最近播放", "source": "mine"},
    ]
    rows.extend(row for row in (playlist_row(item) for item in created if not is_primary_liked_playlist(item)) if row)
    return rows[offset:offset + limit]


def virtual_tracks(playlist_id, limit, offset, cookie, timeout):
    if playlist_id == LIKED_ID:
        liked = next((item for item in created_playlists(cookie, timeout) if is_primary_liked_playlist(item)), None)
        liked_id = str((liked or {}).get("id") or "")
        if liked_id:
            result = tracks(liked_id, limit, offset, timeout)
            result["playlist"] = dict(result.get("playlist") or {}, id=LIKED_ID, name="我的喜欢", source="mine")
            return result
        path = "/luna/pc/me/collection/mixed"
    else:
        path = "/luna/pc/me/recently-played-media"
    wanted = offset + limit
    cursor = ""
    all_rows = []
    total = 0
    seen_cursors = set()
    while len(all_rows) < wanted:
        payload = authenticated_get_json(
            path,
            {"cursor": cursor, "count": min(100, max(1, wanted - len(all_rows)))},
            cookie,
            timeout,
        )
        page = extract_tracks(payload)
        known = {row["id"] for row in all_rows}
        all_rows.extend(row for row in page if row["id"] not in known)
        total = payload.get("total_num") or total
        next_cursor = str(payload.get("next_cursor") or "")
        if not page or not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return {
        "playlist": {"provider": "qishui", "id": playlist_id,
                     "name": "我的喜欢" if playlist_id == LIKED_ID else "最近播放", "source": "mine"},
        "songs": all_rows[offset:offset + limit],
        "total": total or len(all_rows),
    }


def tracks(playlist_id, limit=50, offset=0, timeout=12):
    playlist_id = str(playlist_id or "").strip()
    if not playlist_id:
        raise ValueError("missing playlist id")
    limit = max(1, min(int(limit or 50), 100))
    offset = max(0, int(offset or 0))
    if playlist_id in (LIKED_ID, RECENT_ID):
        cookie = require_session()
        return virtual_tracks(playlist_id, limit, offset, cookie, timeout)
    cookie = ""
    wanted = offset + limit
    cursor = ""
    all_rows = []
    meta = None
    seen_cursors = set()
    while len(all_rows) < wanted:
        params = {"playlist_id": playlist_id, "cursor": cursor,
                  "count": min(100, max(1, wanted - len(all_rows)))}
        try:
            payload = get_json("/luna/pc/playlist/detail", params, cookie, timeout)
        except RuntimeError:
            login_cookie = load_cookie()
            if cookie or not logged_in(login_cookie):
                raise
            cookie = login_cookie
            payload = authenticated_get_json("/luna/pc/playlist/detail", params, cookie, timeout)
        meta = payload.get("playlist") if isinstance(payload.get("playlist"), dict) else meta
        page = extract_tracks(payload.get("media_resources") or [])
        known = {row["id"] for row in all_rows}
        all_rows.extend(row for row in page if row["id"] not in known)
        next_cursor = str(payload.get("next_cursor") or "")
        if not page or not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    playlist = playlist_row(meta or {"id": playlist_id}, "detail")
    total = 0
    if isinstance(meta, dict):
        resources = meta.get("resource_cnt") if isinstance(meta.get("resource_cnt"), dict) else {}
        total = meta.get("count_tracks") or resources.get("track_cnt") or 0
    return {"playlist": playlist, "songs": all_rows[offset:offset + limit], "total": total or len(all_rows)}


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print("usage: playlist.py search <keywords> [limit] [offset] | mine [limit] [offset] | tracks <playlist_id|liked|recent> [limit] [offset]", file=sys.stderr)
        return 2
    command = argv[1]
    try:
        if command == "search" and 3 <= len(argv) <= 5:
            result = {"provider": "qishui", "playlists": search(argv[2], argv[3] if len(argv) > 3 else 10, argv[4] if len(argv) > 4 else 0)}
        elif command == "mine" and len(argv) <= 4:
            result = {"provider": "qishui", "playlists": mine(argv[2] if len(argv) > 2 else 30, argv[3] if len(argv) > 3 else 0)}
        elif command == "tracks" and 3 <= len(argv) <= 5:
            result = tracks(argv[2], argv[3] if len(argv) > 3 else 50, argv[4] if len(argv) > 4 else 0)
            result["provider"] = "qishui"
        else:
            print("playlist.py: invalid command or arguments", file=sys.stderr)
            return 2
    except ValueError as exc:
        print("playlist.py: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"provider": "qishui", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
