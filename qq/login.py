"""Open a local QR page for QQ Music App login and save the resulting credential."""
import argparse
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
COOKIE_FILE = HERE / "cookie"
state = {"status": "正在模拟 QQ 音乐手机客户端创建二维码…", "done": False, "error": False}
qr_image = b""


def atomic_write(path, text):
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_credential(credential):
    musicid = str(credential.musicid or credential.str_musicid or "")
    musickey = str(credential.musickey or "")
    if not musicid or not musickey:
        raise RuntimeError("登录成功但没有返回 musicid / musickey")
    atomic_write(
        COOKIE_FILE,
        f"uin={musicid}; qm_keyst={musickey}; qqmusic_key={musickey}; music_key={musickey}\n",
    )


def show_terminal_qr(image):
    try:
        from terminal_qrcode import draw
        draw(image).print(end="\n")
    except (ImportError, OSError, RuntimeError, ValueError):
        return False
    return True


PAGE = """<!doctype html><meta charset=utf-8><title>QQ 音乐登录</title>
<style>body{font:16px system-ui;margin:0;background:#f5f5f7;color:#222}main{max-width:460px;margin:8vh auto;background:white;padding:32px;border-radius:20px;text-align:center;box-shadow:0 12px 40px #0001}img{width:280px;max-width:90%}#s{margin-top:18px}small{color:#666}</style>
<main><h2>QQ 音乐 App 扫码登录</h2><img src=/qr.png><div id=s>等待扫码…</div><p><small>这是 QQ 音乐手机客户端协议，不需要打开手机 QQ 或微信。请使用 QQ 音乐 App 的扫码功能。</small></p></main>
<script>setInterval(async()=>{let r=await fetch('/status');let j=await r.json();s.textContent=j.status;if(j.done||j.error)document.querySelector('img').style.opacity='.35'},900)</script>"""


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


async def login(args):
    global qr_image
    try:
        from qqmusic_api import Client
        from qqmusic_api.models.login import QRCodeLoginEvents, QRLoginType
        from qqmusic_api.modules.login_utils import QRCodeLoginSession
    except ImportError as exc:
        raise RuntimeError("缺少依赖，请先运行：python3 -m pip install -r requirements.txt") from exc

    server = None
    async with Client() as client:
        session = QRCodeLoginSession(
            client.login,
            QRLoginType.MOBILE,
            interval=1.5,
            timeout_seconds=float(max(10, args.timeout)),
        )
        qr = await session.get_qrcode()
        qr_image = qr.data
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        local_url = f"http://127.0.0.1:{server.server_port}/"
        print("请使用 QQ 音乐 App 扫描下面的二维码：")
        if not show_terminal_qr(qr_image):
            print("未安装可选的 terminal-qrcode，跳过终端绘制。")
        print("浏览器备用地址：")
        print(local_url)
        if not args.no_open:
            webbrowser.open(local_url)
        try:
            async for result in session.iter_events():
                if result.event == QRCodeLoginEvents.SCAN:
                    state["status"] = "等待 QQ 音乐 App 扫码…"
                elif result.event == QRCodeLoginEvents.CONF:
                    state["status"] = "已扫码，请在 QQ 音乐 App 中确认。"
                elif result.event == QRCodeLoginEvents.DONE:
                    if result.credential is None:
                        raise RuntimeError("登录完成但没有返回凭据")
                    save_credential(result.credential)
                    state.update(status="登录成功，cookie 已安全保存，可以关闭此页面。", done=True)
                    await asyncio.sleep(2)
                    return
                elif result.event == QRCodeLoginEvents.REFUSE:
                    raise RuntimeError("你在手机上拒绝了登录")
                elif result.event == QRCodeLoginEvents.TIMEOUT:
                    raise RuntimeError("二维码已过期或等待超时，请重新运行")
        except Exception as exc:
            state.update(status=str(exc), error=True)
            await asyncio.sleep(2)
            raise
        finally:
            if server:
                server.shutdown()
                server.server_close()


def main():
    parser = argparse.ArgumentParser(description="QQ 音乐 App 独立扫码登录")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--timeout", type=int, default=180, help="等待秒数，默认 180")
    args = parser.parse_args()
    asyncio.run(login(args))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("已取消登录。", file=sys.stderr)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
