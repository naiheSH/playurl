"""Open a local QR login page and save NetEase credentials beside this file."""
import argparse
import base64
import http.cookiejar
import importlib.util
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

HERE = Path(__file__).resolve().parent
COOKIE_FILE = HERE / "cookie"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 PlayUrlLogin/1.0"
state = {"status": "正在创建网易云音乐二维码…", "done": False, "error": False}
qr_image = b""


def request_json(opener, url, data):
    request = Request(
        url,
        data=urlencode(data).encode(),
        headers={"User-Agent": UA, "Referer": "https://music.163.com/"},
    )
    with opener.open(request, timeout=15) as response:
        return json.load(response)


def load_weapi():
    """Reuse the provider's tested WEAPI encoder without duplicating crypto code."""
    module_path = HERE / "playlist.py"
    spec = importlib.util.spec_from_file_location("playurl_netease_playlist_crypto", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载网易云 WEAPI 加密模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.weapi


def save_cookie(jar):
    values = [f"{item.name}={item.value}" for item in jar]
    if not any(item.name == "MUSIC_U" for item in jar):
        raise RuntimeError("登录成功响应中没有 MUSIC_U")
    text = "; ".join(values) + "\n"
    fd, name = tempfile.mkstemp(prefix=".cookie-", dir=HERE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(name, 0o600)
        os.replace(name, COOKIE_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def render_qr(content):
    try:
        import segno
    except ImportError as exc:
        raise RuntimeError("缺少依赖，请先运行：python3 -m pip install -r requirements.txt") from exc
    output = BytesIO()
    segno.make(content, error="m").save(output, kind="png", scale=7, border=3)
    return output.getvalue()


def show_terminal_qr(image):
    try:
        from terminal_qrcode import draw
        draw(image).print(end="\n")
    except (ImportError, OSError, RuntimeError, ValueError):
        return False
    return True


PAGE = """<!doctype html><meta charset=utf-8><title>网易云音乐登录</title>
<style>body{font:16px system-ui;margin:0;background:#f5f5f7;color:#222}main{max-width:440px;margin:8vh auto;background:white;padding:32px;border-radius:20px;text-align:center;box-shadow:0 12px 40px #0001}img{width:280px;max-width:90%}#s{margin-top:18px}small{color:#666}</style>
<main><h2>网易云音乐扫码登录</h2><img src=/qr.png><div id=s>等待扫码…</div><p><small>请使用网易云音乐 App 扫码并在手机上确认。凭据只保存到本目录 cookie。</small></p></main>
<script>setInterval(async()=>{let r=await fetch('/status');let j=await r.json();s.textContent=j.status;if(j.done||j.error)document.querySelector('img').style.opacity='.35'},1200)</script>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/qr.png":
            body, mime = qr_image, "image/png"
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


def main():
    global qr_image
    parser = argparse.ArgumentParser(description="网易云音乐独立扫码登录")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--timeout", type=int, default=180, help="等待秒数，默认 180")
    args = parser.parse_args()
    jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    weapi = load_weapi()
    created = request_json(
        opener,
        "https://music.163.com/weapi/login/qrcode/unikey",
        weapi({"type": 1, "csrf_token": ""}),
    )
    key = created.get("unikey", "")
    if not key:
        raise RuntimeError("网易云没有返回二维码 key")
    device_id = "".join(secrets.choice("0123456789ABCDEF") for _ in range(52))
    jar.set_cookie(http.cookiejar.Cookie(
        version=0, name="deviceId", value=device_id, port=None, port_specified=False,
        domain=".music.163.com", domain_specified=True, domain_initial_dot=True,
        path="/", path_specified=True, secure=True, expires=None, discard=True,
        comment=None, comment_url=None, rest={}, rfc2109=False,
    ))
    chain_id = f"v1_{device_id}_web_login_{int(time.time() * 1000)}"
    qr_image = render_qr("https://music.163.com/login?" + urlencode({"codekey": key, "chainId": chain_id}))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    local_url = f"http://127.0.0.1:{server.server_port}/"
    print("请使用网易云音乐 App 扫描下面的二维码：")
    if not show_terminal_qr(qr_image):
        print("未安装可选的 terminal-qrcode，跳过终端绘制。")
    print("浏览器备用地址：")
    print(local_url)
    if not args.no_open:
        webbrowser.open(local_url)
    deadline = time.time() + max(10, args.timeout)
    try:
        while time.time() < deadline:
            result = request_json(
                opener,
                "https://music.163.com/weapi/login/qrcode/client/login",
                weapi({"key": key, "type": 1, "csrf_token": ""}),
            )
            code = int(result.get("code", 0) or 0)
            if code == 803:
                save_cookie(jar)
                state.update(status="登录成功，cookie 已安全保存，可以关闭此页面。", done=True)
                time.sleep(2)
                return
            if code == 802:
                state["status"] = "已扫码，请在手机上确认登录。"
            elif code == 801:
                state["status"] = "等待网易云音乐 App 扫码…"
            elif code == 800:
                raise RuntimeError("二维码已过期或已取消，请重新运行")
            else:
                state["status"] = result.get("message") or f"未知状态 {code}"
            time.sleep(1.5)
        raise RuntimeError("等待扫码超时，请重新运行")
    except Exception as exc:
        state.update(status=str(exc), error=True)
        time.sleep(2)
        raise
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("已取消登录。", file=sys.stderr)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
