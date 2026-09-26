#!/usr/bin/env python3
"""Validate the local NetEase MUSIC_U without printing credential values."""

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
URL = "https://music.163.com/api/nuser/account/get"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrl/1.0"


def music_u():
    for name in ("NETEASE_MUSIC_U", "MUSIC_U"):
        value = os.environ.get(name, "").strip()
        if value:
            return value, "environment"
    path = HERE / "cookie"
    if not path.is_file():
        return "", "file"
    raw = path.read_text(encoding="utf-8").strip()
    if not raw or raw.startswith("#"):
        return "", "file"
    for part in raw.replace("\n", ";").split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip() == "MUSIC_U" and value.strip():
                return value.strip(), "file"
    return (raw, "file") if "=" not in raw else ("", "file")


def result(status, valid, reason, source="file"):
    return {
        "provider": "netease",
        "credential": "MUSIC_U",
        "status": status,
        "valid": valid,
        "source": source,
        "reason": reason,
    }


def check(timeout=12, opener=urlopen):
    token, source = music_u()
    if not token:
        return result("missing", False, "未找到 MUSIC_U", source), 1
    request = Request(URL, headers={
        "User-Agent": UA,
        "Referer": "https://music.163.com/",
        "Cookie": "MUSIC_U=" + token,
    })
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (301, 401, 403):
            return result("expired", False, "网易云登录已过期", source), 1
        return result("unknown", None, f"网易云接口 HTTP {exc.code}", source), 2
    except (URLError, OSError, ValueError) as exc:
        return result("unknown", None, f"无法确认：{exc}", source), 2
    code = int(payload.get("code") or 0) if isinstance(payload, dict) else 0
    account = payload.get("account") if isinstance(payload, dict) else None
    profile = payload.get("profile") if isinstance(payload, dict) else None
    if code == 200 and (account or profile):
        return result("valid", True, "网易云登录有效", source), 0
    if code in (301, 401, 403) or (code == 200 and not account and not profile):
        return result("expired", False, "网易云登录已过期", source), 1
    return result("invalid", False, f"网易云拒绝凭据（code={code or 'unknown'}）", source), 1


def main(argv):
    if len(argv) > 1:
        print("usage: check.py", file=sys.stderr)
        return 2
    body, exit_code = check()
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
