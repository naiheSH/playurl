"""Open a local QR login page and save Qishui credentials beside this file."""
import argparse
import http.cookiejar
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

HERE = Path(__file__).resolve().parent
COOKIE_FILE = HERE / "cookie"
BASE = "https://api.qishui.com"
FIXED = {
    "passport_jssdk_version": "2.4.13",
    "passport_jssdk_type": "normal",
    "is_from_ttaccountsdk": "1",
    "aid": "386088",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://music.douyin.com/"}
state = {"status": "正在创建汽水音乐二维码…", "done": False, "error": False}
qr_image = b""


def request_json(opener, path, query, body=None):
    url = BASE + path + "?" + urlencode(query)
    headers = dict(HEADERS)
    encoded = None
    if body is not None:
        encoded = urlencode(body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    with opener.open(Request(url, data=encoded, headers=headers), timeout=15) as response:
        return json.load(response)


SESSION_NAMES = {"sessionid", "sessionid_ss", "sid_guard", "sid_tt"}


def sessionid(jar):
    return next((item.value for item in jar if item.name.lower() in SESSION_NAMES), "")


def save_cookie(jar):
    if not sessionid(jar):
        raise RuntimeError("登录成功响应中没有 sessionid")
    text = "; ".join(f"{item.name}={item.value}" for item in jar) + "\n"
    fd, name = tempfile.mkstemp(prefix=".cookie-", dir=HERE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(name, 0o600)
        os.replace(name, COOKIE_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_browser_cookies(cookies):
    values = {}
    for item in cookies:
        name, value = str(item.get("name", "")), str(item.get("value", ""))
        if name and value:
            values[name] = value
    if not any(values.get(name) for name in SESSION_NAMES):
        raise RuntimeError("浏览器登录完成但没有取得汽水会话 Cookie")
    text = "; ".join(f"{key}={value}" for key, value in values.items()) + "\n"
    fd, name = tempfile.mkstemp(prefix=".cookie-", dir=HERE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(name, 0o600)
        os.replace(name, COOKIE_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def chrome_executable():
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for command in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge"):
        found = shutil.which(command)
        if found:
            candidates.append(found)
    return next((path for path in candidates if os.path.isfile(path)), "")


def browser_login(args):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("缺少浏览器登录依赖，请先运行：python3 -m pip install -r requirements.txt") from exc
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
                page.goto("https://music.douyin.com/", wait_until="domcontentloaded", timeout=60000)
                print("已打开汽水官方页面，请在浏览器页面完成扫码登录。", flush=True)
                while time.time() < deadline:
                    cookies = context.cookies()
                    if any(item.get("name", "").lower() in SESSION_NAMES and item.get("value") for item in cookies):
                        save_browser_cookies(cookies)
                        print("登录成功，cookie 已安全保存。", flush=True)
                        return
                    if not context.pages:
                        raise RuntimeError("登录窗口已关闭")
                    time.sleep(1)
                raise RuntimeError("等待浏览器登录超时，请重新运行")
            finally:
                context.close()


def show_terminal_qr(url):
    try:
        from terminal_qrcode import generate
        generate(url).print(end="\n")
    except ImportError as exc:
        raise RuntimeError("缺少终端二维码依赖，请先运行：python3 -m pip install -r requirements.txt") from exc


def render_scan_url(url):
    try:
        import qrcode
    except ImportError as exc:
        raise RuntimeError("缺少二维码依赖，请先运行：python3 -m pip install -r requirements.txt") from exc
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    qr.add_data(url)
    matrix = qr.get_matrix()
    size = len(matrix)
    cells = "".join(
        f'<rect x="{x}" y="{y}" width="1" height="1"/>'
        for y, row in enumerate(matrix)
        for x, dark in enumerate(row)
        if dark
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'shape-rendering="crispEdges"><rect width="100%" height="100%" fill="white"/>'
        f'<g fill="black">{cells}</g></svg>'
    ).encode()


PAGE = """<!doctype html><meta charset=utf-8><title>汽水音乐登录</title>
<style>body{font:16px system-ui;margin:0;background:#f5f5f7;color:#222}main{max-width:460px;margin:8vh auto;background:white;padding:32px;border-radius:20px;text-align:center;box-shadow:0 12px 40px #0001}img{width:280px;max-width:90%}#s{margin-top:18px}small{color:#666}</style>
<main><h2>汽水音乐扫码登录</h2><img src=/qr.png><div id=s>等待扫码…</div><p><small>当前汽水 PC 登录协议要求使用已登录账号的抖音 App 扫码验证。凭据只保存到本目录 cookie。</small></p></main>
<script>setInterval(async()=>{let r=await fetch('/status');let j=await r.json();s.textContent=j.status;if(j.done||j.error)document.querySelector('img').style.opacity='.35'},1200)</script>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/qr.png":
            body, mime = qr_image, "image/svg+xml"
        elif self.path == "/status":
            body, mime = json.dumps(state, ensure_ascii=False).encode(), "application/json; charset=utf-8"
        else:
            body, mime = PAGE.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def direct_qr_login(args):
    global qr_image
    jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    created = request_json(
        opener,
        "/passport/web/get_qrcode/",
        {
            **FIXED,
            "next": BASE,
            "need_logo": "false",
            "need_short_url": "false",
            "is_new_login": "1",
        },
    )
    data = created.get("data") or created
    token = data.get("token", "")
    scan_url = data.get("qrcode_index_url", "")
    if not token or not scan_url.startswith("https://bff-pc.qishui.com/"):
        raise RuntimeError("汽水音乐没有返回有效的官方扫码地址")
    # 上游附带的 qrcode PNG 可能不是可完成确认的最终内容。必须原样编码
    # qrcode_index_url；改写链接或直接使用附带图片可能无法打开或卡在 scanned。
    qr_image = render_scan_url(scan_url)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    local_url = f"http://127.0.0.1:{server.server_port}/"
    print("请使用已登录账号的抖音 App 扫描下面的二维码：")
    show_terminal_qr(scan_url)
    print("浏览器备用地址：")
    print(local_url)
    if not args.no_open:
        webbrowser.open(local_url)
    deadline = time.time() + max(10, args.timeout)
    try:
        while time.time() < deadline:
            result = request_json(
                opener,
                "/passport/web/check_qrconnect/",
                {**FIXED, "iid": "27960026095955"},
                {
                    "need_logo": "false",
                    "need_short_url": "false",
                    "is_frontier": "true",
                    "token": token,
                    "is_new_login": "1",
                    "next": BASE,
                },
            )
            if sessionid(jar):
                save_cookie(jar)
                state.update(status="登录成功，cookie 已安全保存，可以关闭此页面。", done=True)
                time.sleep(2)
                return
            data = result.get("data") or result
            status = str(data.get("status", "")).lower()
            if status in {"scanned", "scan", "confirmed", "confirm"}:
                state["status"] = "已扫码，请在抖音 App 中确认。"
            elif status in {"expired", "timeout", "cancel", "refuse"}:
                raise RuntimeError("二维码已过期或已取消，请重新运行")
            else:
                state["status"] = "等待抖音 App 扫码…"
            time.sleep(1.5)
        raise RuntimeError("等待扫码超时，请重新运行")
    except Exception as exc:
        state.update(status=str(exc), error=True)
        time.sleep(2)
        raise
    finally:
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="汽水音乐独立扫码登录")
    parser.add_argument("--direct-qr", action="store_true", help="使用实验性的纯 HTTP 二维码流程")
    parser.add_argument("--no-open", action="store_true", help="纯 HTTP 模式不自动打开备用页面")
    parser.add_argument("--timeout", type=int, default=180, help="等待秒数，默认 180")
    args = parser.parse_args()
    if args.direct_qr:
        direct_qr_login(args)
    else:
        browser_login(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("已取消登录。", file=sys.stderr)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
