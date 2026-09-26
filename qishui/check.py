#!/usr/bin/env python3
"""Validate the local Qishui login cookie without exposing it."""

import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
URL = "https://api.qishui.com/luna/pc/me"
UA = "LunaPC/3.5.2(412998333)"
SESSION_NAMES = ("sessionid", "sessionid_ss", "sid_tt")


def load_cookie():
    path = HERE / "cookie"
    if not path.is_file():
        return ""
    return "; ".join(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


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
    token = next((values.get(name) for name in SESSION_NAMES if values.get(name)), "")
    return "sessionid=" + token if token else ""


def result(status, valid, reason, mode=None):
    body = {
        "provider": "qishui",
        "credential": "cookie",
        "status": status,
        "valid": valid,
        "reason": reason,
    }
    if mode:
        body["sessionMode"] = mode
    return body


def probe(cookie, query, timeout, opener):
    request = Request(URL + "?" + query, headers={
        "Accept": "application/json,text/plain,*/*",
        "User-Agent": UA,
        "Referer": "https://www.qishui.com/",
        "Cookie": cookie,
        "x-luna-is-local-user": "1",
    })
    with opener(request, timeout=timeout) as response:
        raw = response.read()
    payload = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    code = payload.get("status_code", payload.get("error_code", 0)) if isinstance(payload, dict) else None
    user_id = str(((payload.get("my_info") or {}).get("id") or "")) if isinstance(payload, dict) else ""
    return code, user_id


def check(timeout=12, opener=urlopen):
    cookie = load_cookie()
    if not cookie:
        return result("missing", False, "未找到 cookie 文件"), 1
    core = core_session_cookie(cookie)
    if not core:
        return result("invalid", False, "Cookie 缺少 sessionid 会话字段"), 1
    now = str(int(time.time() * 1000))
    query = urlencode({
        "aid": "386088", "app_name": "luna_pc", "region": "cn", "geo_region": "cn",
        "os_region": "cn", "device_id": now, "iid": str(int(now) + 1),
        "version_name": "3.5.2", "version_code": "30050002", "channel": "official",
        "ac": "wifi", "tz_name": "Asia/Shanghai", "device_platform": "windows",
        "device_type": "Windows", "os_version": "Windows 11", "fp": now,
    })
    tried_core = False
    try:
        code, user_id = probe(cookie, query, timeout, opener)
    except HTTPError as exc:
        if exc.code in (401, 403) and core != cookie:
            try:
                tried_core = True
                code, user_id = probe(core, query, timeout, opener)
            except HTTPError as core_exc:
                if core_exc.code in (401, 403):
                    return result("expired", False, "汽水 sessionid 已失效", "sessionid"), 1
                return result("unknown", None, f"汽水接口 HTTP {core_exc.code}"), 2
            except (URLError, OSError, ValueError) as core_exc:
                return result("unknown", None, f"无法确认：{core_exc}"), 2
            if code in (0, "0", None) and user_id:
                return result("valid_sessionid_only", True, "完整 Cookie 被拒绝，但核心 sessionid 仍有效", "sessionid"), 0
        elif exc.code in (401, 403):
            return result("expired", False, "汽水 sessionid 已失效", "sessionid"), 1
        else:
            return result("unknown", None, f"汽水接口 HTTP {exc.code}"), 2
    except (URLError, OSError, ValueError) as exc:
        return result("unknown", None, f"无法确认：{exc}"), 2
    if code in (0, "0", None) and user_id:
        return result("valid", True, "汽水登录有效", "full_cookie"), 0
    if core != cookie and not tried_core:
        try:
            core_code, core_user_id = probe(core, query, timeout, opener)
        except HTTPError as exc:
            if exc.code in (401, 403):
                return result("expired", False, "汽水 sessionid 已失效", "sessionid"), 1
            return result("unknown", None, f"汽水接口 HTTP {exc.code}"), 2
        except (URLError, OSError, ValueError) as exc:
            return result("unknown", None, f"无法确认：{exc}"), 2
        if core_code in (0, "0", None) and core_user_id:
            return result("valid_sessionid_only", True, "辅助 Cookie 已失效，核心 sessionid 仍有效", "sessionid"), 0
        code = core_code
        user_id = core_user_id
    if code in (401, 403, 10002, "401", "403", "10002") or not user_id:
        return result("expired", False, f"汽水 sessionid 已失效（code={code}）", "sessionid"), 1
    return result("invalid", False, f"汽水拒绝凭据（code={code}）"), 1


def main(argv):
    if len(argv) > 1:
        print("usage: check.py", file=sys.stderr)
        return 2
    body, exit_code = check()
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
