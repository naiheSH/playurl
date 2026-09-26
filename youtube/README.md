# YouTube

独立的 YouTube 音频地址解析目录。Python 脚本只使用标准库，但必须另外安装当前版本的 `yt-dlp`；解析逻辑不复制到本仓库，因为 YouTube 播放协议、JavaScript challenge 和 PO Token 要求会持续变化。

需要 Python 3.10+。Windows 可把下方命令中的 `python3` 替换为 `py -3.10` 或已激活虚拟环境中的 `python`。

## 命令

`runtime.py` 是 Agent Runtime 的 JSON stdin/stdout 入口，与下面的传统 argv 命令并存。

```text
python3 playurl/youtube/search.py <歌名|歌名 歌手> [limit] [offset]
python3 playurl/youtube/playlist.py search <关键词> [limit] [offset]
python3 playurl/youtube/playlist.py tracks <playlist_id|url> [limit] [offset]
python3 playurl/youtube/playurl.py <video_id|url> [high|standard] [--json]
python3 playurl/youtube/check.py
```

Agent Runtime 示例：`{"action":"playurl","id":"video_id或URL","quality":"high"}` 通过 stdin 传给 `python3 playurl/youtube/runtime.py`。YouTube 不支持 `playlist_mine`；完整协议见 [`../doc/runtime.md`](../doc/runtime.md)。旧命令行输出不变。

歌曲搜索结果和歌单曲目的 `id` 是 11 位 YouTube video ID，可直接交给 `playurl.py`。歌单搜索使用 YouTube 的 Playlist 类型筛选，只保留真实 playlist ID；已有播放列表 ID/URL 使用 `playlist.py tracks`。不模拟“我的歌单”。

格式与音质配置位于本目录 `playurl.py` 顶部：

```python
ENABLE_FLAC = False
QUALITY = "high"
```

默认格式选择器只接受 M4A/MP3。`high` 选择允许格式中的高音质流；命令行传 `standard` 时限制到约 160kbps。没有 M4A 时会尝试 MP3；两种格式都没有则明确失败，不会偷偷返回 WebM。把 `ENABLE_FLAC` 改为 `True` 后才把 FLAC 放到格式候选首位。

默认标准输出只有短期音频 URL；`--json` 还返回格式、编码、码率、有效期和可能需要的 `httpHeaders`。URL 到期、发生 403 或开始新一次播放时应重新解析，不能长期缓存。

## 依赖和 Cookie

安装 `yt-dlp` 后，脚本会优先使用 PATH 中的 `yt-dlp`，也支持当前 Python 环境中的 `yt_dlp` 模块。缺失时返回结构化错误。

```text
python3 -m pip install -U -r playurl/youtube/requirements.txt
```

公开内容通常不需要登录。年龄限制、私人内容或账号可见内容可以把 Netscape 格式 Cookie 文件放在：

```text
playurl/youtube/cookies.txt
```

不要放原始 `Cookie:` 请求头；`yt-dlp --cookies` 要求 Netscape Cookie 文件。该文件已被 gitignore，不应打印或提交。Cookie 不能替代 YouTube 当前可能要求的 PO Token；遇到 PO Token/403 时应更新 `yt-dlp` 并按其官方 Wiki 配置 provider，而不是把临时 Token 写进脚本。

`check.py` 在存在 `cookies.txt` 时访问账号历史页确认网页是否识别登录；只有 PO Token 时用一个公开测试视频验证当前 `yt-dlp` 解析通路。未配置凭据时返回 `not_configured`，但 `publicUsable: true`，因为公开内容不要求登录。

如果需要手工保存 PO Token，放在同目录、已 gitignore 的 `token` 文件。每行一个，空行和 `#` 注释会被忽略：

```text
mweb.gvs+实际的_GVS_PO_TOKEN
mweb.player+实际的_PLAYER_PO_TOKEN
```

如果文件中只写裸 Token，脚本默认按 `mweb.gvs` 处理。三支脚本都会自动把文件转换为 `yt-dlp --extractor-args`，不会打印 Token。PO Token 可能绑定账号会话、Visitor ID 或具体视频，过期或换视频后仍可能需要更新；自动 provider 通常比长期保存文件可靠。

只解析用户有权访问的非 DRM 内容。播放地址来自 YouTube，不是 Spotify 原始音频。
