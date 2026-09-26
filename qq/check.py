#!/usr/bin/env python3
"""Validate the local QQ Music cookie without printing account secrets."""

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"


def parse_cookie(text):
    values = {}
    for part in str(text or "").split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip():
                values[key.strip()] = value.strip()
    return values


def load_cookie():
    path = HERE / "cookie"
    if not path.is_file():
        return ""
    return "; ".join(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def uin_of(values):
    wechat = bool(values.get("wxopenid")) or values.get("login_type") == "2"
    raw = values.get("wxuin" if wechat else "uin") or values.get("qqmusic_uin") or values.get("p_uin") or ""
    digits = "".join(character for character in str(raw) if character.isdigit()).lstrip("0")
    return digits or "0"


def playback_key(values):
    return next((values[name] for name in ("qm_keyst", "qqmusic_key", "music_key", "wxskey") if values.get(name)), "")


def result(status, valid, reason):
    return {
        "provider": "qq",
        "credential": "cookie",
        "status": status,
        "valid": valid,
        "reason": reason,
    }


def check(timeout=12, opener=urlopen):
    cookie = load_cookie()
    if not cookie:
        return result("missing", False, "未找到 cookie 文件"), 1
    values = parse_cookie(cookie)
    uin = uin_of(values)
    key = playback_key(values)
    if uin == "0" or not key:
        return result("invalid", False, "Cookie 缺少 uin/wxuin 或播放密钥"), 1
    body = json.dumps({
        "comm": {"ct": 24, "cv": 0, "uin": uin, "qq": uin, "authst": key},
        "req_0": {
            "module": "music.srfDissInfo.DissInfo",
            "method": "CgiGetDiss",
            "param": {
                "disstid": 0, "dirid": 201, "tag": 1, "song_begin": 0,
                "song_num": 1, "userinfo": 1, "orderlist": 1,
            },
        },
    }, separators=(",", ":")).encode()
    request = Request(URL, data=body, method="POST", headers={
        "User-Agent": UA,
        "Referer": "https://y.qq.com/",
        "Content-Type": "application/json",
        "Cookie": cookie,
    })
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            return result("expired", False, "QQ 音乐登录已过期"), 1
        return result("unknown", None, f"QQ 音乐接口 HTTP {exc.code}"), 2
    except (URLError, OSError, ValueError) as exc:
        return result("unknown", None, f"无法确认：{exc}"), 2
    block = (payload.get("req_0") or {}) if isinstance(payload, dict) else {}
    root_code = int(payload.get("code") or 0) if isinstance(payload, dict) else -1
    block_code = int(block.get("code") or 0) if isinstance(block, dict) else -1
    if root_code == 0 and block_code == 0 and isinstance(block.get("data"), dict):
        return result("valid", True, "QQ 音乐登录有效"), 0
    code = block_code or root_code
    return result("expired", False, f"QQ 音乐登录已过期或被拒绝（code={code}）"), 1


def main(argv):
    if len(argv) > 1:
        print("usage: check.py", file=sys.stderr)
        return 2
    body, exit_code = check()
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
