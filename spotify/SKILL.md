---
name: playurl-spotify
description: 用 playurl/spotify 的独立标准库脚本查询 Spotify 歌曲和歌单元数据，并说明官方 Embed/Web Playback SDK 与音频直链的边界。用户提到 Spotify、track id、playlist id、access token 或官方播放器时使用。
---

# playurl Spotify

只使用 `playurl/spotify/` 内的脚本和官方 Spotify API。不要调用下载器、网页抓流、YouTube 或其他平台补一首“同名可播”。

## 路由

| 用户要的 | 使用 | 不要用 |
| --- | --- | --- |
| 搜歌曲 | `search.py` | `playurl.py` |
| 搜歌单 | `playlist.py search` | `search.py` |
| 已有 playlist id，要列歌 | `playlist.py tracks` | `playurl.py` |
| 我的歌单 | `playlist.py mine` | Client Credentials |
| 已有 track id，要播放方式 | `playurl.py` | 任何音频下载器 |
| 要在应用内官方播放 | 返回的 Embed URL 或应用层 Web Playback SDK | 把 URI 改成音频 URL |

track id 和 playlist id 都是 22 位字母数字。二者不能互换，也不能把 Spotify URL 的其他路径段当成 ID。

## 命令

在仓库根目录运行。搜索每次最多 10 条，`offset` 最大 1000。

```text
python3 playurl/spotify/search.py "歌名 歌手" 10 0
python3 playurl/spotify/playlist.py search "歌单关键词" 10 0
python3 playurl/spotify/playlist.py tracks <playlist_id> 50 0
python3 playurl/spotify/playlist.py mine 30 0
python3 playurl/spotify/playurl.py <track_id>
```

`playurl.py` 不访问网络。它不接受音质参数。

## 凭据

公开搜索和歌单搜索使用 `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET`，或同目录已忽略的 `credentials` JSON。可选 `SPOTIFY_MARKET`。

`mine` 和 `tracks` 必须有用户 `SPOTIFY_ACCESS_TOKEN` 或 `credentials.access_token`。Client Credentials 不够。当前官方接口只允许读取该用户拥有或协作的歌单内容。

不要读取网页 cookie，不要打印或提交 OAuth 值。缺 token 时停止并说明缺哪一类，不要用客户端密钥冒充用户 token。

## 怎么读结果

搜索和歌单成功时输出两空格缩进 JSON，退出码 0。空结果、OAuth 或接口失败退出码 1。参数或 ID 格式错误退出码 2。

歌曲对象标记 `playable: false`、`playbackMode: spotify_official_player`。这表示元数据可用，不是播放失败，也不能把 Web API 当音频 CDN。只有歌名和歌手精确对应才采用 ID；多条或不确定时列出后停止。

歌单对象保留 `id`、`name`。用户没指定歌单时不要自动列歌。`tracks` 的 `total` 是总数，`offset` 是曲目序号。

`playurl.py` 固定返回：

- `playable: false`
- `url: ""`
- `spotifyUri`
- `spotifyUrl`
- `embedUrl`
- `supportedPlayback`
- `restriction.category: provider_limited`

这些字段只能交给 Spotify 官方播放器。不得改写成音频 URL，也不得拿预览片段冒充完整音频。退出码 1 在这里是能力边界，不是需要重试的网络错误。

## 失败时怎么停

| 看到什么 | 怎么处理 |
| --- | --- |
| 退出码 2 | ID 不是 22 位或命令错误。不要截取 URL 猜测 |
| 缺 client id/secret | 只影响公开元数据。不要改用网页 cookie |
| 缺 access token | 只影响 `mine` 和 `tracks`。不要反复搜索同一歌单 |
| `provider_limited` | 停止寻求直链，改说明官方播放方式 |
| 空 `songs` 或 `playlists` | 停止。不要换 YouTube 自动补播 |

## 不要做

- 不调用 `yt-dlp`、浏览器抓流或其他平台脚本补救。
- 不把 `spotifyUrl`、`embedUrl` 或 URI 称为播放地址。
- 不打印、缓存或提交 token、client secret。
- 不在脚本之间互相 import。
