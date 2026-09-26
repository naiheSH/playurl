---
name: playurl-kugou
description: 用 playurl/kugou 的独立脚本搜索酷狗歌曲和歌单，并把文件 hash 换成短期 MP3 或可选 FLAC 地址。用户提到酷狗、specialid、collection_、album_audio_id、音质或试听时使用。
---

# playurl 酷狗

只用 `playurl/kugou/` 里的独立脚本。需要 Python 3.10+。不要导入本目录外代码，不要请求常驻本地服务，不要把歌名当成 hash。登录和首次设备注册需要同目录 `requirements.txt`；终端二维码使用可选的 `requirements-terminal.txt`，缺少时继续使用 PNG 和 `127.0.0.1` 页面。

在要求 JSON stdin/stdout 的 Agent Runtime / Code 环境中，调用 `runtime.py`，输入一个含 `action` 的 JSON 对象并解析唯一的 stdout JSON。可用 action：`search`、`playlist_search`、`playlist_tracks`、`playlist_mine`、`playurl`、`check`。播放时保留 `albumId` 和 `albumAudioId`。不要在 Runtime 中调用 argv CLI；`ok: true` 后仍要检查 `data.playable` 和 `data.restriction`。

## 按用户原话选脚本

| 用户要的 | 用这个 | 不要用 |
| --- | --- | --- |
| 歌名、歌手、找一首歌 | `search.py` | `playurl.py` |
| 公开歌单名称 | `playlist.py search` | `search.py` |
| 已有 specialid，要里面的歌 | `playlist.py tracks` | `playurl.py` |
| 我的歌单、默认收藏、我喜欢 | `playlist.py mine`，再用返回的 `collection_` ID 调 `tracks` | 把 `collection_` 当 specialid 搜索 |
| 没有 token、要酷狗 App 扫码 | `login.py` | 手工打印 cookie |
| 检查 token 是否过期 | `check.py` | 只看 userid/token 字段 |
| 已有 hash，要播放地址 | `playurl.py` | 再搜一次 |

歌曲 `id` 是 32 位文件 hash。公开歌单 ID 是数字 `specialid`。自己的歌单 ID 以 `collection_` 开头。三者不能互换。

## 命令

在仓库根目录运行。`limit` 和 `offset` 可省略。

```text
python3 -m pip install -r playurl/kugou/requirements.txt
# 可选终端二维码
python3 -m pip install -r playurl/kugou/requirements-terminal.txt
python3 playurl/kugou/login.py
python3 playurl/kugou/check.py
python3 playurl/kugou/search.py "歌名"
python3 playurl/kugou/search.py "歌名 歌手"
python3 playurl/kugou/search.py "歌手 歌名" 10 0
python3 playurl/kugou/playlist.py search "歌单关键词" 10 0
python3 playurl/kugou/playlist.py tracks <specialid> 50 0
python3 playurl/kugou/playlist.py tracks <collection_id> 50 0
python3 playurl/kugou/playlist.py mine 30 0
python3 playurl/kugou/playurl.py <hash> exhigh <album_id> <album_audio_id>
python3 playurl/kugou/playurl.py <hash> --json
python3 playurl/kugou/playurl.py <hash> standard <album_id> <album_audio_id>
```

歌单 `offset` 是曲目序号，从 0 开始，不是页号。公开 `tracks` 按每页 100 首取再切片，自己的歌单按每页 50 首。返回都有 `total`。

## 怎么读搜索结果

搜索和歌单成功时输出 JSON，退出码 0。空结果或接口失败退出码 1。参数错误退出码 2。

歌曲对象必须原样保留这五个字段，少一个就不要进入播放：

- `id`：32 位 hash，交给 `playurl.py` 的第一个参数。
- `name`：歌名。
- `artist`：歌手。
- `album_id`：交给播放命令的第三个参数。
- `album_audio_id`：交给播放命令的第四个参数，必须是数字。

只有用户给的歌名和歌手都精确对应时才取这组字段。只给歌名且唯一精确命中时可以使用。多条、同名、现场、翻唱或歌手对不上时，列出这五个字段后停止。不要猜 hash，不要只抄 `id` 丢掉两个专辑字段。

歌单对象只保留 `id`、`name`、`trackCount`。用户没指定歌单时列出后停止。`mine` 里以 `collection_` 开头的 ID 只能交给 `playlist.py tracks`，不能交给公开搜索，也不能交给 `playurl.py`。

`tracks` 成功时读取 `songs` 和 `total`。公开歌单的 `total` 来自 `data.total`，自己的歌单来自 `data.count`。它是整张歌单的歌曲数。每首歌保留上面五个字段。公开歌单继续取时 `offset` 按 100 递增，自己的歌单按 50 递增。

`error` 非空、退出码 1 或结果为空时停止。`error_code` 20010 不是未登录，见下方凭据。

## 播放

每首歌单独运行一次。参数顺序固定为：

```text
playurl.py <hash> [quality] [album_id] [album_audio_id] [--json]
```

`album_audio_id` 必须是数字。不要把 `album_id` 和 `album_audio_id` 对调。没有这两个值时仍可只传 hash，但能拿到就必须传。

成功时标准输出只有一行完整 URL，退出码 0。原样使用，不要截断。

需要判断音质时加 `--json`。命令行 JSON 使用两空格缩进的多行格式。酷狗没有 `expi`。看这些字段：

- `requested`：请求档。
- `level`：实际档。请求 `exhigh` 后得到 `standard` 不是脚本错误。
- `trial`：`true` 是试听地址，不是完整音质，也不是脚本失败。不要把它说成高音质。
- `playable: false` 且 `restriction.category` 为 `login_required`：未登录或 cookie 不完整。不要改 hash 重试。
- 其他 `playable: false`：停止，不要编一个网页链接代替。

地址仍是短期 URL。过期、401 或 403 时用同一组 hash、`album_id`、`album_audio_id` 重新请求。

## 音质

配置只改本目录 `playurl.py` 顶部的 `ENABLE_FLAC`。默认是 `False`，顺序为 `320k MP3 → 128k MP3`；320k 不可用时自动降级。改成 `True` 后默认顺序为 `FLAC → 320k MP3 → 128k MP3`。

命令行第二个参数只覆盖这一次。关闭 FLAC 时，`hires`、`lossless`、`jymaster` 会按默认 `exhigh` 处理，不得返回 FLAC。

## 凭据

搜歌和公开歌单不读 cookie。`mine`、`collection_` 歌单和登录播放才读同目录 `cookie`。

cookie 需要 `KuGoo`，或 `userid` + `token`，以及 `kg_mid`、有效的 `dfid`/`kg_dfid`。只报告字段是否存在，不打印值。不要写入命令、日志、测试、JSON 或提交。文件权限应为 `600`。

登录播放或个人歌单失败且字段齐全时，先运行 `check.py`。它会识别酷狗 `20017` 为 `expired`；此时重新扫码。`unknown` 是网络或平台异常，不要盲目换歌或更换 Cookie。

缺少登录凭据时运行 `login.py`。它打印并打开随机的 `127.0.0.1` 页面，使用酷狗音乐 App 扫码确认后注册设备 `dfid`，再原子写入同目录 `cookie`。旧 cookie 缺少有效 `dfid` 时 `playurl.py` 会自动注册一次。临时页面不是播放服务。

播放优先走 v6 接口。只从目标质量项的 `info.tracker_url` 取地址；`info.tracker_type == "part"` 必须返回 `trial: true`，不能把会员试听冒充完整歌曲。

自己的歌单网关请求体必须带 `show_relate_goods`、`allplatform`、`show_cover`。`error_code` 20010 是请求体或签名不匹配，不要把它说成未登录，也不要为此更换 cookie。

只长期保存 hash、`album_id`、`album_audio_id`、歌单 ID 和曲目序号。

## 失败时怎么停

| 看到什么 | 怎么处理 |
| --- | --- |
| 退出码 2 | hash、`album_id` 或 `album_audio_id` 格式错误。不要对调两个专辑字段后盲目重试 |
| 退出码 1 且 `error` 非空 | 停止并报告 `error` |
| `error_code` 20010 | 请求体或签名不匹配。不要说成未登录，也不要更换 cookie |
| `login_required` | 缺 `userid`/`token`。先运行 `login.py`，不改 hash |
| `trial: true` 或 `tracker_type=part` | 试听。不要说成完整音质 |
| 其他 `playable: false` | 停止。不要编网页链接代替 |
| 401 或 403 | 用同一组 hash、`album_id`、`album_audio_id` 重新请求一次 |

播放 JSON 的 `source` 只说明命中了哪条回退链，不是音质，也不是失败原因。酷狗没有 `expi`，不要向用户承诺剩余秒数。

## 不要做

- 不在脚本之间互相 import。
- 不调用本地接口补救失败请求。
- 不把试听地址说成完整音质。
- 不把 `collection_` ID 当成公开 specialid，也不把 hash 当成歌单 ID。
- 不增加第三方依赖。登录和设备注册依赖只留在同目录 `requirements.txt`。
