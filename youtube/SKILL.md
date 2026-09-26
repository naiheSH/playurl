---
name: playurl-youtube
description: 用 playurl/youtube 的 yt-dlp 包装脚本搜索 YouTube 音频和歌单，并解析短期 M4A、MP3 或可选 FLAC URL。用户提到 YouTube、video ID、playlist ID、PO Token、cookies.txt、音质或播放 URL 时使用。
---

# playurl YouTube

只使用 `playurl/youtube/` 中的独立脚本和当前版本 `yt-dlp`。不要把 YouTube 冒充 Spotify，也不要长期缓存播放 URL。

## 路由

- 搜歌曲：`search.py <关键词> [limit] [offset]`。
- 搜公开歌单：`playlist.py search <关键词> [limit] [offset]`。
- 读取歌单：`playlist.py tracks <playlist_id|url> [limit] [offset]`。
- 解析播放地址：`playurl.py <video_id|url> [high|standard] [--json]`。

歌曲 ID 是 11 位 video ID；歌单 ID 必须是实际 playlist ID。不要用频道 ID 冒充歌单，不模拟“我的歌单”。

## 播放与格式

配置只改本目录 `playurl.py` 顶部：

```python
ENABLE_FLAC = False
QUALITY = "high"
```

默认只接受 M4A/MP3：`high` 选择允许格式中的高音质流，`standard` 限制到约 160kbps；没有 M4A 时尝试 MP3，两种都没有则失败，不返回 WebM。把 `ENABLE_FLAC` 改为 `True` 后才把 FLAC 放到候选首位。

成功时默认只输出一行短期 URL；`--json`、限制和错误结果使用两空格缩进的多行 JSON。JSON 中的 `httpHeaders` 必须随媒体请求发送。接近 `expi`、过期或收到 401/403 时，用同一 video ID 重新解析。

## Cookie 与 Token

公开内容通常不需要登录。受限内容使用同目录、已 gitignore 的 Netscape `cookies.txt`。PO Token 逐行放入同目录 `token`；不要输出或提交 Cookie、Token，也不要把浏览器原始 `Cookie:` 请求头当成 Netscape 文件。

解析失败且提示 challenge、PO Token 或 403 时，先更新 `yt-dlp`，再按当前官方要求更新 Token；不要在脚本中固化临时签名或复制 YouTube 解密逻辑。
