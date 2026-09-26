# 酷狗

独立目录。不引用本目录以外的代码，也不需要先打开桌面客户端。搜索和歌单脚本只使用 Python 标准库；扫码登录和首次设备注册使用同目录 `requirements.txt`。

## 文件

- `search.py`：公开搜歌。不读 cookie。
- `playlist.py`：公开搜歌单、按曲目偏移列歌、读取已登录账号的歌单。
- `playurl.py`：用文件 hash 换短期播放地址。
- `runtime.py`：Agent Runtime 的 JSON stdin/stdout 入口。
- `login.py`：保存并展示二维码，用酷狗音乐 App 扫码后写入 cookie；终端二维码依赖缺失时仍可正常登录。
- `check.py`：请求只读个人歌单接口，识别有效 Token 和 `20017` 过期状态。
- `device.py`：注册酷狗设备并获取播放接口要求的 `dfid`。
- `requirements.txt`：`login.py` 和首次设备注册需要。
- `requirements-terminal.txt`：可选的终端二维码渲染依赖。
- `cookie`：登录凭据。已被 gitignore，不要提交。

## 命令

```text
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows PowerShell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r playurl/kugou/requirements.txt
# 可选：在终端直接绘制二维码
python -m pip install -r playurl/kugou/requirements-terminal.txt
python playurl/kugou/login.py
python3 playurl/kugou/check.py
python3 playurl/kugou/search.py <歌名|歌名 歌手|歌手 歌名> [limit] [offset]
python3 playurl/kugou/playlist.py search <关键词> [limit] [offset]
python3 playurl/kugou/playlist.py tracks <specialid 或 collection_id> [limit] [offset]
python3 playurl/kugou/playlist.py mine [limit] [offset]
python3 playurl/kugou/playurl.py <hash> [quality] [album_id] [album_audio_id] [--json]
```

Agent Runtime 示例：`{"action":"playurl","id":"hash","albumId":"...","albumAudioId":123}` 通过 stdin 传给 `python3 playurl/kugou/runtime.py`。stdout 始终是 JSON；协议见 [`../doc/runtime.md`](../doc/runtime.md)。旧命令行输出不变。

需要 Python 3.10+。`login.py` 会把官方二维码保存为同目录 `login-qr.png`，并打印、默认打开只监听 `127.0.0.1` 的备用浏览器页面。安装可选的 `requirements-terminal.txt` 后还会在终端绘制二维码；没有安装只跳过终端绘制，不会让本地页面退出。传 `--no-open` 可关闭自动打开浏览器，`--keep-qr` 可在流程结束后保留图片。扫码成功后还会注册播放接口要求的设备 `dfid`，再原子写入同目录 `cookie`；macOS/Linux 权限设为 `0600`。旧 cookie 没有有效 `dfid` 时，`playurl.py` 会在已安装依赖的虚拟环境中自动注册一次并安全更新 cookie。终端和浏览器状态接口都不会返回凭据。

播放成功时标准输出只有一行 URL。加 `--json` 才输出完整字段。失败时输出 JSON。

公开歌单 ID 是 `specialid`。`collection_` 开头的是自己的云歌单，不能当公开 `specialid`。

`tracks` 的 `offset` 是曲目序号，不是页号。公开接口按 100 首取页后切片；自己的歌单按 50 首取页后切片。两边都返回 `total`。公开总数来自 `data.total`，自己的歌单总数来自 `data.count`。

歌曲行里的 `id` 是文件 hash。交给 `playurl.py` 时带上 `album_id` 和 `album_audio_id`。

## 音质

配置位于本目录 `playurl.py` 顶部：

```python
ENABLE_FLAC = False
QUALITY = "lossless" if ENABLE_FLAC else "exhigh"
```

默认关闭 FLAC，按 `320k MP3 → 128k MP3` 降级；320k 没有可用地址时会自动尝试 128k。把 `ENABLE_FLAC` 改为 `True` 后，顺序变为 `FLAC → 320k MP3 → 128k MP3`。每一档都优先使用已注册设备的 v6 播放接口，再尝试旧网关、网页和移动接口。

返回里 `requested` 是请求档，`level` 是实际拿到的档。酷狗响应没有 `expi`。`trial` 为真时只是试听地址。

## cookie

`mine` 和登录播放需要 `KuGoo`，或 `userid` + `token`，以及 `kg_mid`、有效的 `dfid`/`kg_dfid`。只放同目录 `cookie`。不要把值写入命令、日志、JSON 或文档。

播放地址短期有效。过期、401 或 403 时重新请求，不要长期缓存。
