"""Open a local QR login page and save Kugou credentials beside this file."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import secrets
import string
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
COOKIE_FILE = HERE / "cookie"
BASE = "https://login-user.kugou.com"
WEB_SALT = "NVPh5oo715z5DIWAeQlhMDsWXXQV4hwt"
state = {"status": "正在创建酷狗二维码…", "done": False, "error": False}
qr_image = b""


def md5(text):
    return hashlib.md5(text.encode()).hexdigest()


def request_json(path, params, mid):
    merged = {
        "dfid": "-",
        "mid": mid,
        "uuid": "-",
        "appid": 1005,
        "clientver": 20489,
        "clienttime": int(time.time()),
        **params,
    }
    joined = "".join(f"{key}={merged[key]}" for key in sorted(merged))
    merged["signature"] = md5(WEB_SALT + joined + WEB_SALT)
    headers = {
        "User-Agent": "Android15-1070-11083-46-0-DiscoveryDRADProtocol-wifi",
        "dfid": "-",
        "mid": mid,
        "clienttime": str(merged["clienttime"]),
    }
    with urlopen(Request(BASE + path + "?" + urlencode(merged), headers=headers), timeout=15) as response:
        return json.load(response)


def save_cookie(userid, token, mid, dev, dfid="-", guid=""):
    if not userid or not token:
        raise RuntimeError("登录成功但没有返回 userid / token")
    fields = {
        "userid": userid,
        "token": token,
        "kg_mid": mid,
        "kg_dfid": dfid,
        "dfid": dfid,
        "KUGOU_API_MID": mid,
        "KUGOU_API_DEV": dev,
    }
    if guid:
        fields["KUGOU_API_GUID"] = guid
    text = "; ".join(f"{key}={value}" for key, value in fields.items()) + "\n"
    fd, name = tempfile.mkstemp(prefix=".cookie-", dir=HERE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(name, 0o600)
        os.replace(name, COOKIE_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def show_terminal_qr(image):
    try:
        from terminal_qrcode import draw
        draw(image).print(end="\n")
    except ImportError as exc:
        raise RuntimeError("缺少终端二维码依赖，请先运行：python3 -m pip install -r requirements.txt") from exc


def register_device(userid, token, mid, guid):
    path = HERE / "device.py"
    spec = importlib.util.spec_from_file_location("playurl_kugou_device", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载酷狗设备注册模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.register_device(userid, token, mid, guid)


PAGE = """<!doctype html><meta charset=utf-8><title>酷狗音乐登录</title>
<style>body{font:16px system-ui;margin:0;background:#f5f5f7;color:#222}main{max-width:440px;margin:8vh auto;background:white;padding:32px;border-radius:20px;text-align:center;box-shadow:0 12px 40px #0001}img{width:300px;max-width:90%}#s{margin-top:18px}small{color:#666}</style>
<main><h2>酷狗音乐扫码登录</h2><img src=/qr.png><div id=s>等待扫码…</div><p><small>请使用酷狗音乐 App 扫码并确认。凭据只保存到本目录 cookie。</small></p></main>
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
    parser = argparse.ArgumentParser(description="酷狗音乐独立扫码登录")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--timeout", type=int, default=180, help="等待秒数，默认 180")
    args = parser.parse_args()
    guid = md5(str(uuid.uuid4()))
    mid = str(int(md5(guid), 16))
    dev = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10))
    created = request_json(
        "/v2/qrcode",
        {
            "appid": 1001,
            "type": 1,
            "plat": 4,
            "qrcode_txt": "https://h5.kugou.com/apps/loginQRCode/html/index.html?appid=1005&",
            "srcappid": 2919,
        },
        mid,
    )
    data = created.get("data") or {}
    key = data.get("qrcode", "")
    image_uri = data.get("qrcode_img", "")
    if not key or "," not in image_uri:
        raise RuntimeError("酷狗没有返回有效二维码")
    qr_image = base64.b64decode(image_uri.split(",", 1)[1])
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    local_url = f"http://127.0.0.1:{server.server_port}/"
    print("请使用酷狗音乐 App 扫描下面的二维码：")
    show_terminal_qr(qr_image)
    print("浏览器备用地址：")
    print(local_url)
    if not args.no_open:
        webbrowser.open(local_url)
    deadline = time.time() + max(10, args.timeout)
    try:
        while time.time() < deadline:
            result = request_json(
                "/v2/get_userinfo_qrcode",
                {"plat": 4, "appid": 1005, "srcappid": 2919, "qrcode": key, "dev": dev},
                mid,
            )
            data = result.get("data") or {}
            status = int(data.get("status", result.get("status", -1)) or 0)
            if status == 4:
                userid = str(data.get("userid", ""))
                token = str(data.get("token", ""))
                dfid = register_device(userid, token, mid, guid)
                save_cookie(userid, token, mid, dev, dfid, guid)
                state.update(status="登录成功，cookie 已安全保存，可以关闭此页面。", done=True)
                time.sleep(2)
                return
            if status == 2:
                state["status"] = "已扫码，请在酷狗音乐 App 中确认。"
            elif status == 1:
                state["status"] = "等待酷狗音乐 App 扫码…"
            elif status == 0:
                raise RuntimeError("二维码已过期，请重新运行")
            else:
                state["status"] = f"等待登录（状态 {status}）…"
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
