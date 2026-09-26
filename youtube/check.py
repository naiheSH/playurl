#!/usr/bin/env python3
"""Check YouTube cookie/PO-token configuration without exposing values."""

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def result(status, valid, reason, credential, usable=None):
    body = {
        "provider": "youtube",
        "credential": credential,
        "status": status,
        "valid": valid,
        "reason": reason,
    }
    if usable is not None:
        body["publicUsable"] = usable
    return body


def netscape_cookies():
    cookie_file = HERE / "cookies.txt"
    if not cookie_file.is_file():
        return {}, False
    values = {}
    expired = False
    now = int(time.time())
    for line in cookie_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _, _, _, expires, name, value = parts[:7]
        if "youtube.com" not in domain and "google.com" not in domain:
            continue
        try:
            if int(expires or 0) and int(expires) <= now:
                expired = True
                continue
        except ValueError:
            pass
        if name and value:
            values[name] = value
    return values, expired


def token_values():
    token_file = HERE / "token"
    if not token_file.is_file():
        return []
    return [
        line.strip()
        for line in token_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def yt_dlp_command():
    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    return []


def check(timeout=35, opener=urlopen):
    cookies, had_expired = netscape_cookies()
    tokens = token_values()
    if cookies:
        request = Request("https://www.youtube.com/feed/history", headers={
            "User-Agent": UA,
            "Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items()),
        })
        try:
            with opener(request, timeout=min(timeout, 15)) as response:
                html = response.read().decode("utf-8", "replace")
        except HTTPError as exc:
            if exc.code in (401, 403):
                return result("expired", False, "YouTube Cookie 已过期或被拒绝", "cookies.txt"), 1
            return result("unknown", None, f"YouTube HTTP {exc.code}", "cookies.txt"), 2
        except (URLError, OSError) as exc:
            return result("unknown", None, f"无法确认：{exc}", "cookies.txt"), 2
        compact = html.replace(" ", "")
        if '"LOGGED_IN":true' in compact:
            return result("valid", True, "YouTube Cookie 登录有效", "cookies.txt"), 0
        return result("expired", False, "YouTube 页面未识别登录状态", "cookies.txt"), 1
    if (HERE / "cookies.txt").is_file() and had_expired and not tokens:
        return result("expired", False, "cookies.txt 中的 YouTube Cookie 已过期", "cookies.txt"), 1
    if tokens:
        command = yt_dlp_command()
        if not command:
            return result("unknown", None, "已配置 PO Token，但缺少 yt-dlp，无法联机验证", "token"), 2
        normalized = [value if "." in value.split("+", 1)[0] else "mweb.gvs+" + value for value in tokens]
        args = command + [
            "--ignore-config", "--no-warnings", "--no-playlist", "--skip-download",
            "--dump-single-json", "--extractor-args",
            "youtube:player-client=default,mweb;po_token=" + ",".join(normalized),
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        ]
        try:
            completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return result("unknown", None, f"无法确认：{exc}", "token"), 2
        if completed.returncode == 0:
            return result("valid", True, "PO Token 可用于测试视频解析", "token"), 0
        return result("invalid", False, "PO Token 测试解析失败，可能已过期或与会话不匹配", "token"), 1
    return result("not_configured", None, "未配置 Cookie/PO Token；公开视频仍可使用", "none", True), 0


def main(argv):
    if len(argv) > 1:
        print("usage: check.py", file=sys.stderr)
        return 2
    body, exit_code = check()
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
