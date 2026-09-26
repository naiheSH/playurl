---
name: playurl-spotify
description: 用 playurl/spotify 的独立标准库脚本查询 Spotify 歌曲和歌单元数据，并说明官方 Embed/Web Playback SDK 与音频直链的边界。
---

# playurl Spotify

只使用 `playurl/spotify/` 内的脚本和官方 Spotify API。不要调用下载器、网页抓流或非官方音源。

| 用户要的 | 使用方式 |
| --- | --- |
| 搜歌曲 | `search.py` |
| 搜公开歌单 | `playlist.py search` |
| 已有 playlist id，要列歌 | `playlist.py tracks` |
| 我的歌单 | `playlist.py mine`，必须有用户 access token |
| 已有 track id，要音频直链 | `playurl.py`，按 JSON 说明官方接口不提供直链 |
| 要在应用内官方播放 | 使用返回的 Embed URL，或在应用层接 Web Playback SDK |

## 凭据

公开元数据使用 `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET`，或同目录 `credentials`。用户歌单使用 `SPOTIFY_ACCESS_TOKEN` 或 `credentials.access_token`。不要读取网页 cookie，不要打印或提交 OAuth 值。

## 结果边界

搜索和歌单返回的曲目都标记 `playable: false`、`playbackMode: spotify_official_player`。这表示元数据可用，但不能把 Web API 当音频 CDN。

`playurl.py` 固定返回 `playable: false` 和空 `url`，退出码 1，同时给出 `spotifyUri`、`spotifyUrl`、`embedUrl` 与 `supportedPlayback`。这些字段只能用于 Spotify 官方播放器，不得改写成音频 URL。

所有命令行 JSON 使用两空格缩进的多行格式；这是显示格式变化，字段结构和 JSON 解析方式不变。

参数或 ID 格式错误退出码 2。接口、OAuth 或空结果错误退出码 1。
