---
name: playurl-qishui
description: 搜索汽水音乐歌曲和歌单、读取个人歌单、解析 track_id 播放地址并检查 Cookie。用户提到汽水音乐、track_id、我的喜欢、最近播放或播放 URL 时使用。
---

# 汽水音乐搜索与播放地址

使用 `scripts/runtime.py`，通过 stdin 输入一个 JSON 对象并解析 stdout 的唯一 JSON 对象。

| 需求 | `action` | 必需输入 |
| --- | --- | --- |
| 搜歌曲 | `search` | `query` |
| 搜公开歌单 | `playlist_search` | `query` |
| 列歌单曲目 | `playlist_tracks` | `id` |
| 列我的歌单 | `playlist_mine` | KV Cookie |
| 解析播放地址 | `playurl` | `id`（数字 track_id） |
| 检查 Cookie | `check` | KV Cookie |

个人能力需要汽水 Cookie。先用 `gf-service-kv-get` 读取 `qishui-cookie`；用户明确提供或更新时用 `gf-service-kv-set` 保存，再调用 `check`。Cookie 通过请求的 `cookie` 字段注入 Code，不在输出、错误或回复中展示。KV 只由 Agent Runtime 注入。

正常流程只需 `get`/`set`；仅在检查当前 Agent 已保存的 key 时用 `gf-service-kv-query`，只有用户明确要求清除凭据时才用 `gf-service-kv-delete` 删除 `qishui-cookie`。

公开搜索、公开歌单和免费歌曲通常不需要 Cookie。`liked`、`recent` 只能作为歌单 ID；不能传给播放入口。歌曲搜索只稳定覆盖首批约 30 条。

默认排除 FLAC，在允许的 M4A/MP3 中按码率选择。返回 `httpHeaders` 时播放器必须原样携带。`trial`、会员流或推荐歌曲不能冒充完整目标歌曲；`playable: false` 时如实返回限制。
