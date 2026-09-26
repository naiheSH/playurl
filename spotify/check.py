#!/usr/bin/env python3
"""Validate Spotify OAuth credentials without printing tokens or client secrets."""

import base64
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
TOKEN_URL = "https://accounts.spotify.com/api/token"
ME_URL = "https://api.spotify.com/v1/me"
UA = "Mineradio-PlayUrl/1.0"


def config():
    stored = {}
    path = HERE / "credentials"
    if path.is_file():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    if not isinstance(stored, dict):
        return None
    return {
        "client_id": os.environ.get("SPOTIFY_CLIENT_ID") or stored.get("client_id") or "",
        "client_secret": os.environ.get("SPOTIFY_CLIENT_SECRET") or stored.get("client_secret") or "",
        "access_token": os.environ.get("SPOTIFY_ACCESS_TOKEN") or stored.get("access_token") or "",
    }


def result(status, valid, reason, credential="oauth"):
    return {
        "provider": "spotify",
        "credential": credential,
        "status": status,
        "valid": valid,
        "reason": reason,
    }


def check(timeout=12, opener=urlopen):
    settings = config()
    if settings is None:
        return result("invalid", False, "credentials 不是有效 JSON 对象"), 1
    access_token = settings["access_token"]
    if access_token:
        request = Request(ME_URL, headers={"Authorization": "Bearer " + access_token, "User-Agent": UA})
        try:
            with opener(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in (401, 403):
                return result("expired", False, "Spotify 用户 access token 已过期或权限不足", "access_token"), 1
            return result("unknown", None, f"Spotify API HTTP {exc.code}", "access_token"), 2
        except (URLError, OSError, ValueError) as exc:
            return result("unknown", None, f"无法确认：{exc}", "access_token"), 2
        if isinstance(payload, dict) and payload.get("id"):
            return result("valid", True, "Spotify 用户 access token 有效", "access_token"), 0
        return result("invalid", False, "Spotify 用户接口没有返回账号", "access_token"), 1

    client_id, client_secret = settings["client_id"], settings["client_secret"]
    if not client_id or not client_secret:
        return result("missing", False, "缺少 access_token 或 client_id/client_secret"), 1
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    request = Request(TOKEN_URL, data=b"grant_type=client_credentials", method="POST", headers={
        "Authorization": "Basic " + basic,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": UA,
    })
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (400, 401, 403):
            return result("invalid", False, "Spotify Client Credentials 无效", "client_credentials"), 1
        return result("unknown", None, f"Spotify token 接口 HTTP {exc.code}", "client_credentials"), 2
    except (URLError, OSError, ValueError) as exc:
        return result("unknown", None, f"无法确认：{exc}", "client_credentials"), 2
    if isinstance(payload, dict) and payload.get("access_token"):
        return result("valid", True, "Spotify Client Credentials 有效", "client_credentials"), 0
    return result("invalid", False, "Spotify token 接口没有返回 access token", "client_credentials"), 1


def main(argv):
    if len(argv) > 1:
        print("usage: check.py", file=sys.stderr)
        return 2
    body, exit_code = check()
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
