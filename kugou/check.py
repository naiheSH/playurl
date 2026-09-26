#!/usr/bin/env python3
"""Validate the local Kugou cookie against a read-only account endpoint."""

import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
URL = "https://gateway.kugou.com/v7/get_all_list"
APPID = 1005
CLIENTVER = 20489
SALT = "OIlwieks28dk2k092lksi2UIkp"
UA = "Android15-1070-11083-46-0-DiscoveryDRADProtocol-wifi"


def md5(value):
    return hashlib.md5(str(value).encode()).hexdigest()


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


def auth_from(cookie):
    values = parse_cookie(cookie)
    embedded = values.get("KuGoo") or values.get("kugou") or values.get("Kugou") or ""
    try:
        embedded = unquote(embedded)
    except ValueError:
        pass
    kugoo = parse_cookie(embedded.replace("&", ";"))
    userid = "".join(character for character in str(
        values.get("userid") or values.get("KugooID") or kugoo.get("KugooID") or kugoo.get("userid") or ""
    ) if character.isdigit())
    token = str(values.get("token") or values.get("t") or kugoo.get("t") or kugoo.get("token") or "").strip()
    mid = str(values.get("kg_mid") or values.get("KUGOU_API_MID") or values.get("mid") or md5("playurl-kugou:" + (userid or "guest")))
    dfid = str(values.get("kg_dfid") or values.get("dfid") or "-")
    return userid, token, mid, dfid


def result(status, valid, reason):
    return {
        "provider": "kugou",
        "credential": "cookie",
        "status": status,
        "valid": valid,
        "reason": reason,
    }


def check(timeout=12, opener=urlopen):
    cookie = load_cookie()
    if not cookie:
        return result("missing", False, "未找到 cookie 文件"), 1
    userid, token, mid, dfid = auth_from(cookie)
    if not userid or not token:
        return result("invalid", False, "Cookie 缺少 userid 或 token"), 1
    now = int(time.time())
    params = {
        "clientver": CLIENTVER, "clienttime": now, "mid": mid, "uuid": "-",
        "dfid": dfid, "appid": APPID, "token": token, "userid": int(userid), "plat": 1,
    }
    body_text = json.dumps({
        "userid": int(userid), "token": token, "total_ver": 979,
        "type": 2, "page": 1, "pagesize": 1,
    }, separators=(",", ":"))
    params["signature"] = md5(
        SALT + "".join(f"{key}={params[key]}" for key in sorted(params)) + body_text + SALT
    )
    request = Request(URL + "?" + urlencode(params), data=body_text.encode(), method="POST", headers={
        "User-Agent": UA, "Content-Type": "application/json",
        "x-router": "cloudlist.service.kugou.com", "dfid": dfid, "mid": mid,
        "clienttime": str(now), "kg-rc": "1", "kg-thash": "5d816a0",
        "kg-rec": "1", "kg-rf": "B9EDA08A64250DEFFBCADDEE00F8F25F", "Cookie": cookie,
    })
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            return result("expired", False, "酷狗登录已过期"), 1
        return result("unknown", None, f"酷狗接口 HTTP {exc.code}"), 2
    except (URLError, OSError, ValueError) as exc:
        return result("unknown", None, f"无法确认：{exc}"), 2
    status = int(payload.get("status") or 0) if isinstance(payload, dict) else 0
    code = (
        payload.get("error_code") or payload.get("errcode") or payload.get("code")
    ) if isinstance(payload, dict) else None
    if status == 1:
        return result("valid", True, "酷狗登录有效"), 0
    if str(code) == "20017":
        return result("expired", False, "酷狗 Token 已过期（20017）"), 1
    return result("invalid", False, f"酷狗拒绝凭据（code={code or status or 'unknown'}）"), 1


def main(argv):
    if len(argv) > 1:
        print("usage: check.py", file=sys.stderr)
        return 2
    body, exit_code = check()
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
