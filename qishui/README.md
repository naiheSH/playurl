# 汽水音乐

独立目录。不引用本目录以外的代码。播放、搜索、歌单和解密脚本只使用 Python 标准库；终端二维码显示使用同目录 `requirements.txt`。

## 文件

- `search.py`：公开搜歌。不读 cookie。
- `playlist.py`：读取登录账号的歌单、我的喜欢、最近播放和歌单曲目。
- `playurl.py`：用 `track_id` 请求播放地址，并可解密带 `#auth=` 的音频。
- `login.py`：默认打开独立 Chrome/Edge 官方登录窗口，扫码后从同一浏览器会话写入 cookie；保留实验性纯 HTTP 二维码模式。
- `requirements.txt`：仅 `login.py` 需要。
- `cookie`：登录凭据。已被 gitignore，不要提交。

## 命令

```text
python3 -m pip install -r playurl/qishui/requirements.txt
python3 playurl/qishui/login.py
python3 playurl/qishui/search.py <歌名|歌名 歌手|歌手 歌名> [limit] [offset]
python3 playurl/qishui/playlist.py search <关键词> [limit] [offset]
python3 playurl/qishui/playlist.py mine [limit] [offset]
python3 playurl/qishui/playlist.py tracks <歌单 id|liked|recent> [limit] [offset]
python3 playurl/qishui/playurl.py <track_id> [--decrypt output.m4a] [--json]
```

`login.py` 默认启动系统已有的 Chrome、Edge 或 Chromium，并打开汽水官方页面。浏览器使用一次性临时配置目录；扫码成功后脚本从同一浏览器上下文收集汽水会话 Cookie，原子写入同目录 `cookie` 并设置权限 `0600`，随后删除临时配置。凭据不会输出到终端。

纯 HTTP 二维码流程保留用于诊断：`python3 playurl/qishui/login.py --direct-qr`。该模式会在终端画二维码并提供随机 `127.0.0.1` 备用页面；`--no-open` 可关闭备用页面。当前上游会按设备身份限流，并可能在手机确认后仍不给纯 HTTP 会话返回登录 Cookie，因此不要把它作为默认登录方式，也不要连续刷新二维码。

二维码必须由上游返回的 `qrcode_index_url` 原样生成。不要改写成其他跳转链接，也不要直接复用响应附带的二维码图片；这两种做法可能在 App 中显示“无法访问”或让确认状态一直停在 `scanned`。

直接可播时标准输出只有一行 URL。集成播放器时使用 `--json`，结果里的 `httpHeaders` 必须随音频请求发送；汽水 CDN 会拒绝缺少这些请求头的裸请求。使用 `--decrypt` 或返回的是带 `#auth=` 的加密流时也输出 JSON。失败时输出 JSON。

搜索 ID 是 `item_id`，交给 `playurl.py`。没有音质位置参数；多余参数会作为参数错误退出。脚本只取返回流里码率最高的一条。

公开歌曲搜索接口只稳定提供首批最多约 30 条候选；歌曲搜索的 `offset` 是在这批候选中切片，达到 30 后会返回空列表。公开歌单搜索支持继续按记录序号翻页，不受这个限制。

公开歌单搜索和公开歌单 `tracks` 不需要 Cookie。搜索使用汽水 PC 歌单搜索协议，`offset` 是记录序号；`tracks` 返回的歌曲 `id` 可逐首交给 `playurl.py`。`mine`、`liked` 和 `recent` 读取同目录 Cookie；`liked` 会自动映射到账号真实的“我喜欢的音乐”歌单。

## 播放限制

配置位于本目录 `playurl.py` 顶部：

```python
ENABLE_FLAC = False
```

汽水没有命令行音质档。默认排除 FLAC 和可能解密为 FLAC 的加密流，然后在可用 M4A/MP3 中按码率从高到低选择；最高码率不可用或受会员限制时，会选择响应中下一条允许的 M4A/MP3。改为 `True` 后，FLAC 和加密无损流也恢复进码率排序。

非会员可完整播放的歌曲可以不放 Cookie，脚本会从目标歌曲公开详情直接选取最高可用码率。同目录 `cookie` 中的登录字段用于尝试 PC 账号接口和个人歌单；脚本会发送完整 Cookie，不再裁成单个 `sessionid`。`/luna/pc/track_v2` 返回空正文时也会回退公开详情。解析严格限定在目标 `seo_track.track_player`，不会误取推荐歌曲。

脚本不接受额外的客户端请求配置。PC 接口不可用时直接回退公开详情；公开详情中标记 `only_vip_playable` 或音质要求会员/购买时不会返回该地址，试听和推荐歌曲也不会冒充目标歌曲的完整流。

## 解密

`--decrypt` 使用本文件里的标准库 AES-CTR。脚本会先写临时文件再原子替换。实际结果为 FLAC 时自动把输出后缀改为 `.flac`，JSON 的 `decryptedFile` 是最终路径。

cookie 不要写入命令、日志、JSON 或文档。播放地址短期有效，不要长期缓存。
