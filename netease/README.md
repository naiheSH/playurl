# 网易云

独立目录。不引用本目录以外的代码，也不需要先打开桌面客户端。播放、搜索和歌单脚本只使用 Python 标准库；扫码登录额外使用同目录 `requirements.txt` 中的轻量二维码库。

## 文件

- `search.py`：公开搜歌。不读 cookie。
- `playlist.py`：公开搜歌单、按曲目偏移列歌、读取已登录账号的歌单。
- `playurl.py`：用歌曲数字 ID 换短期播放地址。
- `runtime.py`：Agent Runtime 的 JSON stdin/stdout 入口。
- `login.py`：打开本机浏览器二维码页，用网易云音乐 App 扫码后写入 cookie。
- `check.py`：请求只读账号接口，判断 `MUSIC_U` 是否真实有效或已过期。
- `requirements.txt`：`login.py` 生成二维码 PNG 所需的跨平台依赖。
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

python -m pip install -r playurl/netease/requirements.txt
# 可选：在终端直接绘制二维码
python -m pip install -r playurl/netease/requirements-terminal.txt
python playurl/netease/login.py
python3 playurl/netease/check.py
python3 playurl/netease/search.py <歌名|歌名 歌手|歌手 歌名> [limit] [offset]
python3 playurl/netease/playlist.py search <关键词> [limit] [offset]
python3 playurl/netease/playlist.py tracks <歌单 id> [limit] [offset]
python3 playurl/netease/playlist.py mine [limit] [offset]
python3 playurl/netease/playurl.py <歌曲数字 id> [quality] [--json]
```

Agent Runtime 示例：`{"action":"playurl","id":"347230","quality":"exhigh"}` 通过 stdin 传给 `python3 playurl/netease/runtime.py`。stdout 始终是 `{"ok":...,"data":...}` 或结构化错误；协议见 [`../doc/runtime.md`](../doc/runtime.md)。旧命令行输出不变。

需要 Python 3.10+。`login.py` 始终提供并默认打开只监听 `127.0.0.1` 的二维码页面；安装可选的 `requirements-terminal.txt` 后还会直接在终端绘制二维码。缺少终端组件不会中断登录。传 `--no-open` 可关闭自动打开浏览器。登录成功后原子写入同目录 `cookie`；macOS/Linux 权限设为 `0600`，终端和页面状态接口都不会返回凭据。

二维码内容包含网易网页端要求的 `codekey` 和一次性 `chainId`；不要删掉 `chainId` 后自行重画，否则部分网易云音乐 App 版本无法识别或无法完成确认。

播放成功时标准输出只有一行 URL。加 `--json` 才输出完整字段。失败时输出 JSON。

`tracks` 先取完整 `trackIds`，再按 `offset` 取歌名。`offset` 是曲目序号，不是页号。单次最多 100 首。返回含 `total`。

`mine` 只读同目录 `cookie`，使用 weapi。没有登录时失败，不会回退到本地服务。

## 音质

配置位于本目录 `playurl.py` 顶部：

```python
ENABLE_FLAC = False
QUALITY = "lossless" if ENABLE_FLAC else "exhigh"
```

默认关闭 FLAC，按 `exhigh 高音质 MP3 → standard MP3` 降级；高音质没有可用地址时会自动尝试标准 MP3。把 `ENABLE_FLAC` 改为 `True` 后，顺序变为 `lossless FLAC → exhigh MP3 → standard MP3`。命令行第二个参数可临时覆盖，非法值回到 `QUALITY`。

返回里 `requested` 是请求档，`level` 是实际拿到的档。另有 `expi`（秒）和 `type`。

## cookie

按顺序读取 `NETEASE_MUSIC_U`、`MUSIC_U`、同目录 `cookie` 里的 `MUSIC_U=`。不要把值写入命令、日志、JSON 或文档。

播放地址短期有效。过期、401 或 403 时重新请求，不要长期缓存，也不要把它当成 token。
