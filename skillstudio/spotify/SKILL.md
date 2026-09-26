---
name: playurl-spotify
description: 使用 Spotify 官方 Web API 搜索歌曲和歌单、读取账号歌单、检查 OAuth 凭据并返回官方播放方式。用户提到 Spotify、track ID、playlist ID 或官方播放器时使用。
---

# Spotify 元数据与官方播放

使用 `scripts/runtime.py`，通过 stdin 输入一个 JSON 对象并解析 stdout 的唯一 JSON 对象。

| 需求 | `action` | 必需输入 |
| --- | --- | --- |
| 搜歌曲 | `search` | `query`、KV 凭据 |
| 搜歌单 | `playlist_search` | `query`、KV 凭据 |
| 列歌单曲目 | `playlist_tracks` | `id`、用户 access token |
| 列我的歌单 | `playlist_mine` | 用户 access token |
| 返回官方播放方式 | `playurl` | `id`（22 位 track ID） |
| 检查凭据 | `check` | KV 凭据 |

用 `gf-service-kv-get` 读取 `spotify-credentials`。值是 JSON 对象，可含 `client_id`、`client_secret`、`access_token`、`market`；用户明确提供或更新时用 `gf-service-kv-set` 保存并调用 `check`。把对象放进 Code 请求的 `credentials` 字段，不展示任何 token 或 secret。KV 只由 Agent Runtime 注入。

正常流程只需 `get`/`set`；仅在检查当前 Agent 已保存的 key 时用 `gf-service-kv-query`，只有用户明确要求清除凭据时才用 `gf-service-kv-delete` 删除 `spotify-credentials`。

搜索可使用 Client Credentials；`playlist_mine` 和 `playlist_tracks` 需要用户 access token。Spotify 官方 API 不提供通用音频直链。`playurl` 返回 `provider_limited`、Spotify URI、网页和 Embed URL；这是正常业务结果，不能改写成音频 URL，也不使用其他平台补播。
