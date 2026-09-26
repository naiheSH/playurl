---
name: playurl-qq
description: 搜索 QQ 音乐歌曲和歌单、读取个人或公开歌单、把 songmid 解析为短期播放地址并检查 Cookie。用户提到 QQ 音乐、songmid、disstid 或我的喜欢时使用。
---

# QQ 音乐搜索与播放地址

使用 `scripts/runtime.py`，通过 stdin 输入一个 JSON 对象并解析 stdout 的唯一 JSON 对象。

| 需求 | `action` | 必需输入 |
| --- | --- | --- |
| 搜歌曲 | `search` | `query` |
| 搜公开歌单 | `playlist_search` | `query` |
| 列歌单曲目 | `playlist_tracks` | `id`（disstid 或 `liked`） |
| 列我的歌单 | `playlist_mine` | KV Cookie |
| 解析播放地址 | `playurl` | `id`（songmid） |
| 检查 Cookie | `check` | KV Cookie |

个人能力需要 QQ 音乐 Cookie。先用 `gf-service-kv-get` 读取 `qqmusic-cookie`；用户明确提供或更新时用 `gf-service-kv-set` 保存，再调用 `check`。Cookie 通过请求的 `cookie` 字段注入 Code，不回显。KV 工具只来自 Agent Runtime 上下文。

正常流程只需 `get`/`set`；仅在检查当前 Agent 已保存的 key 时用 `gf-service-kv-query`，只有用户明确要求清除凭据时才用 `gf-service-kv-delete` 删除 `qqmusic-cookie`。

搜索和公开歌单不需要 Cookie。播放时保留搜索结果中的 `media_mid`，有值时作为 `mediaMid` 传入；songmid、media_mid 和歌单 disstid 不能互换。搜索没有翻页，`offset` 必须为 0。

默认按 320k MP3、标准 MP3、M4A/AAC 降级。`trial: true` 是试听；`playable: false` 时不要把网页地址或非空但未探测通过的 purl 当作播放地址。短期 URL 发生 401/403 时用同一 songmid 重新解析。
