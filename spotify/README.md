# Spotify

独立目录，只使用 Python 标准库。搜索和歌单读取走官方 Web API；播放入口只返回官方播放模式，不返回音频直链。

需要 Python 3.10+。Windows 可把下方命令中的 `python3` 替换为 `py -3.10` 或已激活虚拟环境中的 `python`。

## 文件

- `search.py`：搜索歌曲元数据。
- `playlist.py`：搜索公开歌单、列歌和读取当前用户歌单。
- `playurl.py`：明确返回不可作为通用音频 URL 播放，同时提供 Spotify URI、网页和 Embed URL。
- `check.py`：验证用户 access token；没有用户 token 时验证 Client Credentials。
- `credentials`：可选 OAuth 配置 JSON，已被 gitignore，不要提交。

## 命令

```text
python3 playurl/spotify/search.py <关键词> [limit] [offset]
python3 playurl/spotify/playlist.py search <关键词> [limit] [offset]
python3 playurl/spotify/playlist.py tracks <playlist_id> [limit] [offset]
python3 playurl/spotify/playlist.py mine [limit] [offset]
python3 playurl/spotify/playurl.py <spotify_track_id> [--json]
python3 playurl/spotify/check.py
```

## OAuth 配置

优先读取环境变量 `SPOTIFY_CLIENT_ID`、`SPOTIFY_CLIENT_SECRET`、`SPOTIFY_ACCESS_TOKEN`、`SPOTIFY_MARKET`。也可以写同目录 `credentials`：

```json
{
  "client_id": "本机应用 Client ID",
  "client_secret": "本机应用 Client Secret",
  "access_token": "可选的用户 access token",
  "market": "US"
}
```

搜索元数据可使用 Client Credentials，每次最多返回 10 条。`mine` 和 `tracks` 必须使用带相应 scope 的用户 access token；当前 Web API 只允许读取该用户拥有或参与协作的歌单内容，不能再把任意公开歌单当作可列曲目的公开资源。Spotify Development Mode 当前要求开发者账号为 Premium。脚本不读取 Spotify 网页 cookie，也不打印凭据。

## 播放边界

官方 Web API 不提供可直接交给 `<audio>`、MPV 或下载器的完整音频 URL。`playurl.py` 固定输出 JSON、退出码 1、`playable: false`、`restriction.category: provider_limited`，另提供：

- `spotifyUri`
- `spotifyUrl`
- `embedUrl`
- `supportedPlayback`: `spotify_embed`、`spotify_web_playback_sdk`

这些是官方受控播放入口，不是音频直链。Web API 的预览字段可能为空且不能冒充完整歌曲。

## GitHub 客户端边界

- `librespot`、`go-librespot`：完整的 Spotify Connect 客户端，只支持 Premium；音频在客户端会话内解密和解码，不返回可复用的 CDN 音频直链。
- `spotDL`、`Spotube`：主要使用 Spotify 元数据匹配 YouTube 等第三方音源，不是 Spotify 原始音频。
- 下载并解密 Spotify 原始媒体的项目不接入本目录。它们不符合官方禁止下载和 stream ripping 的政策，也无法维持“仅标准库、返回合法直链”的约束。
