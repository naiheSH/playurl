---
name: playurl-youtube
description: 使用 yt-dlp 搜索 YouTube 视频和播放列表，并解析短期 M4A 或 MP3 音频地址。用户提到 YouTube、video ID、playlist ID、PO Token 或音频 URL 时使用。
---

# YouTube 音频与播放列表

使用 `scripts/runtime.py`，通过 stdin 输入一个 JSON 对象并解析 stdout 的唯一 JSON 对象。Code 环境必须提供当前版本 `yt-dlp`。

| 需求 | `action` | 必需输入 |
| --- | --- | --- |
| 搜视频 | `search` | `query` |
| 搜播放列表 | `playlist_search` | `query` |
| 列播放列表曲目 | `playlist_tracks` | `id` 或 URL |
| 解析音频地址 | `playurl` | `id`（video ID 或 URL） |
| 检查受限内容凭据 | `check` | 可选 KV 凭据 |

公开视频不需要凭据。受限内容可用 `gf-service-kv-get` 分别读取 `youtube-cookies`（Netscape Cookie 文本）和 `youtube-po-tokens`（逐行 Token），放入请求的 `cookies`、`poTokens` 字段。用户明确提供或更新时用 `gf-service-kv-set` 保存。凭据只通过 Agent Runtime 注入，不回显；Code 只创建本次调用的临时 Cookie 文件，结束即删除。

正常流程只需 `get`/`set`；仅在检查当前 Agent 已保存的 key 时用 `gf-service-kv-query`，只有用户明确要求清除凭据时才用 `gf-service-kv-delete` 删除对应的两个 key。

没有“我的歌单”能力。默认只选择 M4A/MP3；`quality` 为 `high` 或 `standard`。返回 `httpHeaders` 时播放器必须原样携带。URL、Cookie 与 PO Token 都可能过期；401/403 时更新凭据或用同一 video ID 重新解析，不长期缓存。
