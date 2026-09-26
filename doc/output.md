# 输出字段

所有命令行 JSON 都使用两空格缩进，并保留中文字符。播放成功且没有 `--json` 时，标准输出只有一行 URL，不输出这些字段。

## 搜索

歌曲搜索成功时：

```json
{
  "provider": "netease",
  "songs": []
}
```

每首至少有 `provider`、`id`、`name`、`artist`。平台差异：

| 平台 | `id` | 额外字段 |
| --- | --- | --- |
| 网易云 | 数字歌曲 ID | `album` |
| QQ | `songmid` | 无 |
| 酷狗 | 文件 hash | `album_id`、`album_audio_id` |
| 汽水 | `item_id` | 无 |
| Spotify | 22 位 track id | 由官方 track 对象映射 |
| YouTube | 11 位 video ID | `duration`、`webpageUrl` |

搜索结果经过本地排序。只有歌名和歌手都精确对应时才使用 `id`，同名、翻唱和现场版本不能靠排序第一自动选中。

## 歌单

`playlist.py search` 和 `playlist.py mine` 返回 `playlists`。每条至少有 `provider`、`id`、`name`、`source`。有总数时带 `trackCount`，有创建者时带 `creator`。

`playlist.py tracks` 返回：

| 字段 | 含义 |
| --- | --- |
| `playlist` | 当前歌单元信息；公开接口没有元信息时至少保留 `id` |
| `songs` | 当前这一窗的曲目，字段与歌曲搜索相同 |
| `total` | 歌单曲目总数；上游没给时使用本次已见数量 |

`offset` 是曲目序号，不是页号。歌单没有一条总播放地址，曲目 `id` 还要逐首交给同目录 `playurl.py`。

虚拟歌单 ID：

| 平台 | ID | 含义 |
| --- | --- | --- |
| QQ | `liked` | 我的喜欢，dirid `201` |
| 汽水 | `liked` | 我的喜欢 |
| 汽水 | `recent` | 最近播放 |

酷狗云歌单 ID 以 `collection_` 开头，不是公开 `specialid`。

## 播放

可播放平台加 `--json` 时共有：

| 字段 | 含义 |
| --- | --- |
| `provider` | 平台目录名 |
| `id` | 请求使用的歌曲 ID |
| `url` | 短期播放地址；失败时为空字符串 |
| `requested` | 本次请求档。网易云、QQ、酷狗是 `lossless` / `exhigh` / `standard`；YouTube 是 `high` / `standard`。汽水没有这个字段 |
| `level` | 实际档。前三个平台与 `requested` 使用同一套名字；汽水是上游 quality 字符串；YouTube 是 `format_id`，不是音质档名 |
| `trial` | 是否试听或片段 |
| `playable` | 是否可以交给通用播放器 |
| `loggedIn` | 这次是否读到登录凭据 |
| `restriction` | 成功时为 `null`；失败时含 `category` 和 `message` |

平台附加字段：

| 平台 | 字段 |
| --- | --- |
| 网易云 | `type`、`expi` |
| QQ | `quality`、`filename`、`expi` |
| 酷狗 | `source`，表示命中了哪条播放回退链 |
| 汽水 | `bitrate`、`size`、`format`、`duration`、`encrypted`、`directPlayable`、`httpHeaders`、`source` |
| YouTube | `format`、`codec`、`bitrate`、`duration`、`title`、`webpageUrl`、`httpHeaders`、`expiresAt`、`expi`、`source` |
| Spotify | `spotifyUri`、`spotifyUrl`、`embedUrl`、`supportedPlayback` |

`expi` 单位是秒。YouTube 的 `expiresAt` 是 Unix 秒，`expi` 是距离到期的剩余秒数。酷狗播放结果没有到期字段。汽水请求 CDN 时必须原样带上 `httpHeaders`，否则可能 403。`encrypted: true` 或 URL 含 `#auth=` 时，不能把 URL 直接交给普通播放器。

Spotify 永远是 `playable: false` 和空 `url`。`spotifyUrl` 与 `embedUrl` 不是音频直链。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 成功，且播放结果 `playable` 为真或列表非空 |
| 1 | 上游失败、空结果、版权或登录限制 |
| 2 | 参数、命令或 ID 格式错误 |

退出码 2 的说明写到标准错误。退出码 1 通常仍输出 JSON，便于调用方读取 `error` 或 `restriction`，不要把 Python traceback 当成正常结果。
