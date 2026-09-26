---
name: playurl-kugou
description: 搜索酷狗歌曲和歌单、读取歌单曲目、解析短期播放地址并检查酷狗 Cookie。用户提到酷狗、specialid、collection_、歌曲 hash、音质或试听时使用。
---

# 酷狗搜索与播放地址

使用 `scripts/runtime.py`。Code 入口从 stdin 读取一个 JSON 对象，只向 stdout 写入一个 JSON 对象。不要调用本地服务，也不要把歌名当作歌曲 hash。

## 能力路由

| 需求 | `action` | 必需输入 |
| --- | --- | --- |
| 搜歌曲 | `search` | `query` |
| 搜公开歌单 | `playlist_search` | `query` |
| 列歌单曲目 | `playlist_tracks` | `id`，个人 `collection_` 歌单还需 Cookie |
| 列我的歌单 | `playlist_mine` | Cookie |
| 解析播放地址 | `playurl` | `id`（歌曲 hash） |
| 检查 Cookie | `check` | Cookie |

歌曲 `id` 是文件 hash，公开歌单 ID 是数字 `specialid`，个人歌单 ID 以 `collection_` 开头。三者不能互换。播放时从搜索或歌单结果原样保留 `album_id` 和 `album_audio_id`。

## Cookie 与 KV

公开搜索、公开歌单及免费歌曲通常不需要 Cookie。个人歌单、账号检查和部分播放请求需要完整酷狗 Cookie。

当前调用没有 Cookie 时，先用 `gf-service-kv-get` 读取 key `kugou-cookie`。读取不到时，只说明需要用户提供 Cookie；不要用空值调用个人能力。用户明确提供或更新 Cookie 时，先用 `gf-service-kv-set` 写入同一个 key，再调用 `check` 验证，验证通过后才用于个人歌单或登录播放。把读取值放入 Code 请求的 `cookie` 字段。不要在回复、日志、错误或工具说明中展示 Cookie，也不要在验证失败时反复写入相同值。

KV 数据由当前 Agent 隔离，四个工具都必须来自 Agent Runtime 上下文，不能用普通 MCP 调用，也不要传入或推测 Agent ID。正常流程只需 `get` 和 `set`；仅在需要检查当前 Agent 已保存的 key 时使用 `gf-service-kv-query`，分页参数 `page_num`、`page_size`，其中 `page_size` 为 1～20；只有用户明确要求清除酷狗凭据时才使用 `gf-service-kv-delete` 删除 `kugou-cookie`，不要因一次网络错误自动删除。

需要账号能力时，KV 中的 Cookie 应包含 `userid`、`token`、`kg_mid` 和现有 `kg_dfid`/`dfid`。缺少部分字段时如实返回平台结果，不伪造凭据。

## 调用与结果

示例输入：

```json
{
  "action": "playurl",
  "id": "歌曲hash",
  "albumId": "数字专辑ID",
  "albumAudioId": 123,
  "quality": "exhigh",
  "cookie": "从KV读取的值"
}
```

公开免费曲验证可先搜索 `安和桥 宋冬野`，再把精确匹配结果的 `id`、`album_id`、`album_audio_id` 交给 `playurl`。公开结果不需要传 Cookie。

退出码 `0` 且 `ok: true` 表示 Code 已完成，不等于歌曲一定可播放。继续检查 `data.playable`、`data.trial`、`data.restriction` 和结果数组。输入错误为 `invalid_input`、退出码 `2`；网络或上游执行异常为 `execution_failed`、退出码 `1`。

默认关闭 FLAC，音质按 `320k MP3 → 128k MP3` 降级。`trial: true` 是试听；`level` 是实际档位。`playable: false` 时不要用网页链接、试听或其他歌曲冒充完整播放地址。

歌单 `offset` 是曲目序号。公开歌单单次最多 100 首；继续读取时按实际返回数增加 offset，直到达到 `total`。

播放 URL 是短期地址。发生 401/403 或开始新的播放时，用同一组 hash、`album_id` 和 `album_audio_id` 重新解析。
