---
name: playurl-youtube
description: 用 playurl/youtube 的 yt-dlp 包装脚本搜索 YouTube 音频和歌单，并解析短期 M4A、MP3 或可选 FLAC URL。用户提到 YouTube、video ID、playlist ID、PO Token、cookies.txt、音质或播放 URL 时使用。
---

# playurl YouTube

只使用 `playurl/youtube/` 中的独立脚本和当前版本 `yt-dlp`。需要 Python 3.10+；Windows 可用 `py -3.10` 或虚拟环境中的 `python`。不要把 YouTube 冒充 Spotify，也不要把 Spotify 失败改到这里自动补播。不要长期缓存播放 URL。

## 路由

| 用户要的 | 命令 | 不要用 |
| --- | --- | --- |
| 搜歌曲或视频 | `search.py <关键词> [limit] [offset]` | `playurl.py` |
| 搜公开播放列表 | `playlist.py search <关键词> [limit] [offset]` | 歌曲搜索结果冒充歌单 |
| 读取已知播放列表 | `playlist.py tracks <playlist_id或url> [limit] [offset]` | 频道 URL |
| 解析播放地址 | `playurl.py <video_id或url> [high或standard] [--json]` | 手工拼接 googlevideo 地址 |
| 检查 cookies.txt / PO Token | `check.py` | 只检查文件存在 |
| 我的歌单、稍后观看 | 不支持 | 不要编一个 `mine` 命令 |

歌曲 ID 是 11 位 video ID。歌单 ID 是实际 playlist ID。频道 ID、handle 和 playlist ID 不能互换。`youtu.be`、`watch?v=` 和 `/shorts/` 可由脚本规范化，其他站点 URL 不要传进来。

没有 `mine`。不要用登录 cookie 去枚举用户私有列表，除非用户明确给出 playlist URL。

## 命令

```text
python3 playurl/youtube/search.py "歌名 歌手" 10 0
python3 playurl/youtube/playlist.py search "歌单关键词" 10 0
python3 playurl/youtube/playlist.py tracks <playlist_id或url> 50 0
python3 playurl/youtube/playurl.py <video_id或url>
python3 playurl/youtube/playurl.py <video_id或url> standard --json
python3 playurl/youtube/check.py
```

搜索和歌单依赖本机 `yt-dlp`。优先使用 PATH 中的命令，否则使用当前 Python 的 `yt_dlp` 模块。缺失时报告安装 `youtube/requirements.txt`，不要在脚本里复制 YouTube 解密逻辑。

## 怎么读结果

成功输出两空格缩进 JSON，退出码 0。空结果或 `yt-dlp` 失败退出码 1。参数或 ID 错误退出码 2。

歌曲对象保留 `id`、`name`、`artist`、`duration`、`webpageUrl`。只有标题和频道或歌手都精确对应时才采用 ID。同名、翻唱、现场或多个候选时列出后停止，不要选第一条。

歌单对象保留 `id`、`name`、`creator`、`trackCount`、`webpageUrl`。用户没指定播放列表时不要自动 `tracks`。`offset` 是条目序号，不是页号。

## 播放与格式

配置只改本目录 `playurl.py` 顶部：

```python
ENABLE_FLAC = False
QUALITY = "high"
```

命令行只接受 `high` 和 `standard`。`high` 选择最佳 M4A，其次 MP3。`standard` 使用同样顺序，但限制 `abr<=160`。两种都没有则失败，不返回 WebM。把 `ENABLE_FLAC` 改为 `True` 后才把 FLAC 放到候选首位。

返回的 `level` 是 yt-dlp 的 `format_id`，不是 `high` 或 `exhigh`。比较音质看 `format`、`codec`、`bitrate`。

成功时默认只输出一行短期 URL。接入播放器或需要到期时间时加 `--json`，并原样发送 `httpHeaders`。`expiresAt` 是 Unix 秒，`expi` 是剩余秒数。接近到期、过期或收到 401/403 时，用同一 video ID 重新解析一次。

`url_unavailable` 表示没有可播放的音频格式。`source_unavailable` 表示 `yt-dlp` 或上游请求失败。两者都不要改视频 ID 重试。

## Cookie 与 Token

公开内容通常不需要登录。受限内容使用同目录、已 gitignore 的 Netscape `cookies.txt`。PO Token 逐行放入同目录 `token`；裸 token 会被当成 `mweb.gvs`。不要输出或提交 Cookie、Token，也不要把浏览器原始 `Cookie:` 请求头当成 Netscape 文件。

解析失败且提示 challenge、PO Token 或 403 时，先更新 `yt-dlp`，再按当前官方要求更新 Token。不要在脚本中固化临时签名。

配置过凭据时可运行 `check.py`：`cookies.txt` 检查网页是否识别登录，PO Token 用公开测试视频验证解析。`not_configured` 且 `publicUsable: true` 表示公开内容仍可用，不是登录有效。

## 不要做

- 不把频道 ID 当 playlist ID。
- 不模拟“我的歌单”。
- 不长期缓存 googlevideo URL。
- 不把 YouTube 结果回写成 Spotify 音频直链。
- 不在仓库里复制 YouTube player、签名或 challenge 求解代码。
