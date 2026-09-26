---
name: playurl-netease
description: 搜索网易云音乐歌曲和歌单、读取歌单曲目、解析短期播放地址并检查 MUSIC_U。用户提到网易云、歌曲数字 ID、歌单或播放 URL 时使用。
---

# 网易云音乐搜索与播放地址

使用 `scripts/runtime.py`，通过 stdin 输入一个 JSON 对象并解析 stdout 的唯一 JSON 对象。

| 需求 | `action` | 必需输入 |
| --- | --- | --- |
| 搜歌曲 | `search` | `query` |
| 搜公开歌单 | `playlist_search` | `query` |
| 列歌单曲目 | `playlist_tracks` | `id` |
| 列我的歌单 | `playlist_mine` | KV Cookie |
| 解析播放地址 | `playurl` | `id`（数字歌曲 ID） |
| 检查凭据 | `check` | KV Cookie |

个人能力需要 `MUSIC_U`。先用 `gf-service-kv-get` 读取 `netease-cookie`；用户明确提供或更新时用 `gf-service-kv-set` 保存，再调用 `check`。KV 由当前 Agent 隔离，只能使用 Agent Runtime 注入的工具，不通过 MCP 传 Agent ID。Cookie 写入 Code 请求的 `cookie` 字段，不在回复或日志中展示。

正常流程只需 `get`/`set`；仅在检查当前 Agent 已保存的 key 时用 `gf-service-kv-query`，只有用户明确要求清除凭据时才用 `gf-service-kv-delete` 删除 `netease-cookie`。

搜索和公开歌单不需要 Cookie。歌曲 ID 与歌单 ID 都是数字但不能互换。只有歌名和歌手精确匹配时才选择歌曲；同名、现场、翻唱或多个候选时先让用户确认。

退出码 `0` 且 `ok: true` 只表示调用完成；继续检查 `data.playable`、`data.trial`、`data.restriction` 和结果数组。默认音质 `exhigh`，不可用时降级到 `standard`。播放 URL 短期有效，发生 401/403 或开始新播放时用同一歌曲 ID 重新解析。
