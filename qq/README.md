# QQ 音乐

独立目录。不引用本目录以外的代码，也不需要先打开桌面客户端。播放、搜索和歌单脚本只使用 Python 标准库；QQ 音乐 App 扫码登录使用同目录 `requirements.txt` 中的客户端协议库。

## 文件

- `search.py`：公开搜歌。不读 cookie。
- `playlist.py`：公开搜歌单、按曲目偏移列歌、读取已登录账号的歌单。
- `playurl.py`：用 songmid 换短期播放地址。
- `login.py`：模拟 QQ 音乐手机客户端，打开本机浏览器二维码页并写入 cookie。
- `check.py`：请求“我的喜欢”只读接口，判断 Cookie 是否真实有效或已过期。
- `requirements.txt`：`login.py` 使用的 QQ 音乐客户端协议库。
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

python -m pip install -r playurl/qq/requirements.txt
# 可选：在终端直接绘制二维码
python -m pip install -r playurl/qq/requirements-terminal.txt
python playurl/qq/login.py
python3 playurl/qq/check.py
python3 playurl/qq/search.py <歌名|歌名 歌手|歌手 歌名> [limit] [offset]
python3 playurl/qq/playlist.py search <关键词> [limit] [offset]
python3 playurl/qq/playlist.py tracks <歌单 id> [limit] [offset]
python3 playurl/qq/playlist.py mine [limit] [offset]
python3 playurl/qq/playurl.py <songmid> [quality] [media_mid] [--json]
```

需要 Python 3.10+。`login.py` 使用的是 QQ 音乐 App 自己的二维码协议：请用手机 QQ 音乐 App 扫码，不需要打开 QQ 或微信。脚本始终提供并默认打开只监听 `127.0.0.1` 的二维码页面；安装可选的 `requirements-terminal.txt` 后还会直接在终端绘制二维码。缺少终端组件不会中断登录。传 `--no-open` 可关闭自动打开浏览器。登录成功后原子写入同目录 `cookie`；macOS/Linux 权限设为 `0600`，不会在终端或页面状态接口返回 token。

播放成功时标准输出只有一行 URL。加 `--json` 才输出完整字段。失败时输出 JSON。未传 `media_mid` 时，脚本会按 songmid 查询文件 ID；两者不同时不能只用 songmid 拼文件名。

公开歌单用 `disstid`。`tracks` 的 `offset` 是曲目序号，接口参数是 `song_begin` / `song_num`，单次最多 200 首。返回含 `total`。

`liked` 是虚拟歌单，对应 dirid `201`，只在 `mine` 和已登录的 `tracks liked` 里使用。

## 音质

配置位于本目录 `playurl.py` 顶部：

```python
ENABLE_FLAC = False
QUALITY = "lossless" if ENABLE_FLAC else "exhigh"
```

默认关闭 FLAC，按 `M800 320k MP3 → M500 标准 MP3 → C400 M4A/AAC` 降级。把 `ENABLE_FLAC` 改为 `True` 后，顺序变为 `F000 FLAC → M800 → M500 → C400`。前一档没有可用地址时会自动尝试下一档。关闭 FLAC 时，`flac`、`lossless`、`hires` 会回落到 `exhigh`，不会返回 FLAC。`320k`、`hq` 等同 `exhigh`，`128k` 等同 `standard`。

返回里 `requested` 是请求档，`level` 来自命中的模板。`expi` 来自接口的 `expiration`，单位秒。

## cookie

QQ 登录需要 `uin`，以及 `qm_keyst`、`qqmusic_key` 或 `music_key`。微信登录使用 `wxuin` 和 `wxskey`。只放同目录 `cookie`。不要把值写入命令、日志、JSON 或文档。

播放地址短期有效。过期、401 或 403 时重新请求，不要长期缓存。
