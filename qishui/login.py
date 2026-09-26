"""Qishui QR login CLI built on the reusable browser-free auth module."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
COOKIE_FILE = HERE / "cookie"
QR_FILE = HERE / "login-qr.png"
SESSION_NAMES = {"sessionid", "sessionid_ss", "sid_guard", "sid_tt"}

try:
    from .auth import QishuiAuthClient, QishuiAuthError
except ImportError:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    from auth import QishuiAuthClient, QishuiAuthError


def sessionid(jar: http.cookiejar.CookieJar) -> str:
    return next(
        (
            item.value
            for item in jar
            if item.name.lower() in SESSION_NAMES and item.value
        ),
        "",
    )


def _atomic_save_cookie(text: str, target: Path | None = None) -> Path:
    target = COOKIE_FILE if target is None else Path(target)
    values = {}
    for pair in text.strip().split(";"):
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        if name.strip() and value.strip():
            values[name.strip()] = value.strip()
    if not any(values.get(name) for name in SESSION_NAMES):
        raise RuntimeError("登录成功响应中没有汽水会话 Cookie")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("; ".join(f"{key}={value}" for key, value in values.items()) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def save_cookie(jar: http.cookiejar.CookieJar) -> Path:
    """Compatibility helper retained for tests and browser-cookie callers."""

    if not sessionid(jar):
        raise RuntimeError("登录成功响应中没有 sessionid")
    return _atomic_save_cookie(
        "; ".join(f"{item.name}={item.value}" for item in jar if item.name and item.value)
    )


def save_browser_cookies(cookies: list[dict]) -> Path:
    values = {}
    for item in cookies:
        name, value = str(item.get("name", "")), str(item.get("value", ""))
        if name and value:
            values[name] = value
    return _atomic_save_cookie(
        "; ".join(f"{key}={value}" for key, value in values.items())
    )


def chrome_executable() -> str:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for command in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "msedge",
    ):
        found = shutil.which(command)
        if found:
            candidates.append(found)
    return next((path for path in candidates if os.path.isfile(path)), "")


def browser_login(args: argparse.Namespace) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "缺少浏览器兜底依赖，请在虚拟环境中安装 requirements.txt"
        ) from exc
    executable = chrome_executable()
    if not executable:
        raise RuntimeError("没有找到 Google Chrome、Microsoft Edge 或 Chromium")
    deadline = time.time() + max(30, args.timeout)
    with tempfile.TemporaryDirectory(prefix="qishui-login-") as profile:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                profile,
                executable_path=executable,
                headless=False,
                viewport={"width": 1120, "height": 820},
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(
                    "https://music.douyin.com/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                print("已打开汽水官方页面，请在浏览器页面完成扫码登录。", flush=True)
                while time.time() < deadline:
                    cookies = context.cookies()
                    if any(
                        item.get("name", "").lower() in SESSION_NAMES
                        and item.get("value")
                        for item in cookies
                    ):
                        save_browser_cookies(cookies)
                        print(f"登录成功，凭据已保存到 {COOKIE_FILE}", flush=True)
                        return
                    if not context.pages:
                        raise RuntimeError("登录窗口已关闭")
                    time.sleep(1)
                raise RuntimeError("等待浏览器登录超时，请重新运行")
            finally:
                context.close()


def _show_terminal_qr(url: str) -> bool:
    try:
        from terminal_qrcode import generate
    except ImportError:
        return False
    generate(url).print(end="\n")
    return True


def _safe_status(result: dict) -> dict:
    return {
        key: value
        for key, value in result.items()
        if key not in {"cookie", "session"}
    }


def _print_status(result: dict, as_json: bool) -> None:
    safe = _safe_status(result)
    if as_json:
        print(json.dumps(safe, ensure_ascii=False, indent=2), flush=True)
    else:
        message = str(safe.get("message") or safe.get("status") or "等待扫码")
        retry = safe.get("retryAfterSec")
        if retry:
            message += f"（约 {retry} 秒后继续）"
        print(message, flush=True)


def direct_login(args: argparse.Namespace) -> None:
    qr_path = Path(args.qr_file).expanduser().resolve()
    cookie_path = Path(args.cookie_file).expanduser().resolve()
    client = QishuiAuthClient(timeout=args.request_timeout)
    login = client.create_qr_login()
    if not login.qr_png:
        raise RuntimeError("上游未返回可保存的二维码 PNG；可改用 login.cjs")
    qr_path.parent.mkdir(parents=True, exist_ok=True)
    qr_path.write_bytes(login.qr_png)
    os.chmod(qr_path, 0o600)

    if not args.no_terminal:
        shown = _show_terminal_qr(login.scan_url)
        if not shown and not args.json:
            print("未安装可选的 terminal-qrcode，跳过终端绘制。", flush=True)
    if args.json:
        print(
            json.dumps(
                {
                    "status": "waiting",
                    "message": "等待扫码",
                    "qrFile": str(qr_path),
                    "expireTime": login.expire_time or None,
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
    else:
        print(f"二维码图片：{qr_path}", flush=True)
        print("请使用汽水音乐 App 扫码并在手机确认。", flush=True)

    deadline = time.monotonic() + max(30, args.timeout)
    last_message = ""
    try:
        while time.monotonic() < deadline:
            result = login.poll()
            message = str(result.get("message") or result.get("status") or "")
            if message != last_message or result.get("status") in {"expired", "failed"}:
                _print_status(result, args.json)
                last_message = message

            status = result.get("status")
            if status == "confirmed":
                login.save_cookie(cookie_path)
                final = {
                    "status": "confirmed",
                    "message": "登录成功",
                    "cookieFile": str(cookie_path),
                }
                _print_status(final, args.json)
                return
            if status in {"expired", "failed"}:
                raise RuntimeError(message or "二维码登录失败")

            mfa = result.get("mfa") or {}
            if mfa.get("needSms"):
                sent = login.send_mfa_sms()
                _print_status(sent, args.json)
                if not sent.get("ok"):
                    raise RuntimeError(sent.get("message") or "短信验证码发送失败")
                for _ in range(3):
                    code = input("请输入短信验证码：").strip()
                    verified = login.validate_mfa_sms(code)
                    _print_status(verified, args.json)
                    if verified.get("ok"):
                        login.save_cookie(cookie_path)
                        if not args.json:
                            print(f"凭据已保存到 {cookie_path}", flush=True)
                        return
                raise RuntimeError("短信验证码连续验证失败，请重新登录")

            retry = float(result.get("retryAfterSec") or 0)
            default_wait = 6.5 if status == "scanned" else 8.0
            time.sleep(max(default_wait, retry))
        raise RuntimeError("等待扫码超时，请重新运行")
    finally:
        if not args.keep_qr:
            try:
                qr_path.unlink()
            except FileNotFoundError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="汽水音乐独立扫码登录（默认纯 HTTP，不打开浏览器）"
    )
    parser.add_argument("--browser", action="store_true", help="改用 Playwright 浏览器兜底")
    parser.add_argument(
        "--direct-qr",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--no-terminal", action="store_true", help="不尝试在终端绘制二维码")
    parser.add_argument("--timeout", type=int, default=600, help="等待登录秒数，默认 600")
    parser.add_argument(
        "--request-timeout", type=float, default=30, help="单次网络请求秒数，默认 30"
    )
    parser.add_argument("--qr-file", default=str(QR_FILE), help="二维码 PNG 保存路径")
    parser.add_argument("--cookie-file", default=str(COOKIE_FILE), help="Cookie 保存路径")
    parser.add_argument("--keep-qr", action="store_true", help="流程结束后保留二维码图片")
    parser.add_argument("--json", action="store_true", help="用格式化 JSON 输出状态，不输出 Cookie")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.browser:
        browser_login(args)
    else:
        direct_login(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("已取消登录。", file=sys.stderr)
        raise SystemExit(130)
    except (QishuiAuthError, RuntimeError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
