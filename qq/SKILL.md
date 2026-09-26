---
name: playurl-qq
description: 用 playurl/qq 的独立标准库脚本搜索 QQ 音乐歌曲和歌单，并把 songmid 换成短期 MP3、M4A 或可选 FLAC 地址。用户提到 QQ 音乐、songmid、media_mid、qm_keyst、我的喜欢或音质时使用。
---

# playurl QQ 音乐

只用 `playurl/qq/` 里的独立脚本。需要 Python 3.10+。搜索、歌单和播放只使用 Python 标准库；登录使用同目录 `requirements.txt` 的手机客户端协议库，终端绘制另用可选的 `requirements-terminal.txt`。缺少终端组件时继续使用 `127.0.0.1` 二维码页，不要判定登录失败。不要导入仓库其他代码，不要请求常驻本地服务，不要把歌名当成 songmid。

在要求 JSON stdin/stdout 的 Agent Runtime / Code 环境中，调用 `runtime.py`，输入一个含 `action` 的 JSON 对象并解析唯一的 stdout JSON。可用 action：`search`、`playlist_search`、`playlist_tracks`、`playlist_mine`、`playurl`、`check`。播放输入可带 `mediaMid`。不要在 Runtime 中调用 argv CLI；`ok: true` 后仍要检查业务字段。

## 按用户原话选脚本

| 用户要的 | 用这个 | 不要用 |
| --- | --- | --- |
| 歌名、歌手、找一首歌 | `search.py` | `playurl.py` |
| 公开歌单名称 | `playlist.py search` | `search.py` |
| 已有 disstid，要里面的歌 | `playlist.py tracks` | `playurl.py` |
| 我的歌单 | `playlist.py mine` | 公开搜索 |
| 我的喜欢、红心、收藏的歌 | `playlist.py tracks liked` | 把 `liked` 当 disstid 搜索 |
| 没有 qm_keyst、要 QQ 音乐 App 扫码 | `login.py` | QQ/微信网页登录二维码 |
| 检查 Cookie 是否过期 | `check.py` | 只看 uin/key 字段 |
| 已有 songmid，要播放地址 | `playurl.py` | 再搜一次 |

歌曲 ID 是 `songmid`，形如 `002uJqIq4fgN2F`。歌单 ID 是 `disstid`，通常是数字字符串。`liked` 只是「我的喜欢」的虚拟 ID。三者不能互换。

## 命令

在仓库根目录运行。`limit` 和 `offset` 可省略。

```text
python3 -m pip install -r playurl/qq/requirements.txt
# 可选终端二维码
python3 -m pip install -r playurl/qq/requirements-terminal.txt
python3 playurl/qq/login.py
python3 playurl/qq/check.py
python3 playurl/qq/search.py "歌名"
python3 playurl/qq/search.py "歌名 歌手"
python3 playurl/qq/search.py "歌手 歌名" 10
python3 playurl/qq/playlist.py search "歌单关键词" 10 0
python3 playurl/qq/playlist.py tracks <disstid> 50 0
python3 playurl/qq/playlist.py tracks liked 50 0
python3 playurl/qq/playlist.py mine 30 0
python3 playurl/qq/playurl.py <songmid>
python3 playurl/qq/playurl.py <songmid> --json
python3 playurl/qq/playurl.py <songmid> standard
python3 playurl/qq/playurl.py <songmid> exhigh <media_mid>
```

搜索没有 `offset`，smartbox 最多约 10 条。歌单 `offset` 是曲目序号，从 0 开始，不是页号。`tracks` 单次最多 200 首，返回有 `total`。

## 怎么读搜索结果

搜索和歌单成功时输出 JSON，退出码 0。空结果或接口失败退出码 1。参数错误退出码 2。

歌曲对象只用：

- `id`：songmid，交给 `playurl.py` 的第一个参数。
- `name`：歌名。歌单名里可能残留 `&#32;` 这类 HTML 实体，按字面比较，不要为此改 ID，也不要先解码再当成另一首歌。
- `artist`：歌手。

只有用户给的歌名和歌手都与某一条精确对应时才取 `id`。只给歌名且唯一精确命中时可以使用。多条、同名、现场、翻唱或歌手对不上时，列出 `id`、`name`、`artist` 后停止。不要猜 ID。

搜索结果没有 `media_mid`。不要用 `docid`、数字 `id` 或 songmid 编一个。没有可靠来源时留空，让 `playurl.py` 自己查。

歌单对象只保留 `id`、`name`。用户没指定歌单时列出后停止。`mine` 的第一项固定是 `liked` / 「我的喜欢」，dirid 为 `201`。它不是公开 disstid，不能传给 `playlist.py search`。

`tracks` 成功时读取 `songs` 和 `total`。`total` 是整张歌单的歌曲数。本页歌曲只保留上面三个字段。要继续取时，`offset` 按本次实际返回条数增加，单次不要超过 200。

`error` 非空、退出码 1 或结果为空时停止。不要换接口重试。

## 播放

每首歌单独运行一次 `playurl.py`。歌单没有一条总播放地址。

默认不传 `media_mid`。脚本会用 songmid 查询 `file.media_mid`，再用它拼文件名，然后探测 CDN。`songmid` 和 `media_mid` 经常不同。只用 songmid 拼出的文件名会 404，即使接口返回了非空 `purl`。

已有 `media_mid` 时放在音质后面，不要放在 songmid 的位置。

脚本对返回地址做 `Range: bytes=0-1` 探测。404 就跳过该音质并尝试下一个 CDN。这种 404 不是版权限制，也不要把本地接口没带 `mediaMid` 时的「版权或会员限制」当成结论。

成功时标准输出只有一行完整 URL，退出码 0。原样使用，不要截断。

需要判断档位时加 `--json`。命令行 JSON 使用两空格缩进的多行格式，仍可直接交给 JSON 解析器：

- `requested`：请求档。
- `level`：实际拿到的档。低于请求档不是脚本错误。
- `trial`：`true` 是试听，不要说成完整歌曲。
- `expi`：接口 `expiration`，单位秒。过期、401 或 403 时用同一个 songmid 重新请求。
- `playable: false` 且 `restriction.category` 为 `login_required`：QQ 登录 cookie 缺 `uin`/播放 key，或微信登录 cookie 缺 `wxuin`/`wxskey`。不要改 songmid 重试。
- `playable: false` 且 `url_unavailable`：探测后仍没有可访问文件。停止，不要把非空 `purl` 返回给用户。

## 音质

配置只改本目录 `playurl.py` 顶部的 `ENABLE_FLAC`。默认是 `False`，从 `exhigh` 只往下降：

1. `exhigh`：`M800` MP3。
2. `standard`：`M500` MP3。
3. `aac`：`C400` M4A/AAC。

前一档不可用时自动尝试下一档。把 `ENABLE_FLAC` 改为 `True` 后，默认顺序变成 `F000 lossless FLAC → M800 → M500 → C400`。关闭时 `lossless` 不在可选档里，`flac`、`hires`、`lossless`、`jymaster`、`master` 都会回落到默认 `exhigh`，不得返回 FLAC。`320`、`320k`、`hq` 映射到 `exhigh`；`128`、`128k` 映射到 `standard`。

## 凭据

搜歌和公开歌单不读 cookie。`mine`、`tracks liked` 和会员播放才读同目录 `cookie`。

登录播放或个人数据失败且本地字段齐全时，先运行 `check.py`。`expired` 才重新登录；`unknown` 是网络或平台异常。

QQ 登录 cookie 必须同时有 `uin`，以及 `qm_keyst`、`qqmusic_key`、`music_key` 三者之一；微信登录使用 `wxuin` 和 `wxskey`。检查时只报告字段是否存在，不打印值。不要写入命令、日志、测试、JSON 或提交。文件权限应为 `600`。

缺少 QQ 登录 cookie 时运行 `login.py`。它模拟 QQ 音乐手机客户端并通过 MQTT 等待扫码状态；二维码必须用 QQ 音乐 App 扫，不需要打开 QQ 或微信。随机的 `127.0.0.1` 页面只负责显示二维码和状态，不是常驻服务。成功后只写同目录 `cookie`。

只长期保存 songmid、disstid 和曲目序号。播放地址是短期签名 URL。

## 失败时怎么停

| 看到什么 | 怎么处理 |
| --- | --- |
| 退出码 2 | 参数、命令或 songmid 格式错误。修正后只运行一次 |
| 退出码 1 且 `error` 非空 | 停止并报告 `error` |
| `login_required` | cookie 缺 `uin`/播放 key，或微信登录缺 `wxuin`/`wxskey`。先登录，不改 songmid |
| `url_unavailable` | 探测后没有可访问文件。不要把非空 `purl` 交出去 |
| `trial: true` | 试听片段，不要说成完整歌曲 |
| CDN 404 | 当前候选音质不可达。让脚本继续降级，不要改成版权结论 |
| 401、403 或接近 `expi` | 用同一个 songmid 重新请求一次 |

搜索最多约 10 条，排序不能补回接口没返回的原曲。不要为了凑结果换平台。

## 不要做

- 不在脚本之间互相 import。
- 不调用本地接口补救失败请求。
- 不把非空 `purl` 直接当成可播放。必须是探测通过的地址。
- 不把 `media_mid` 写进仓库或当 cookie。
- 不把 `liked` 当公开 disstid，也不把 disstid 交给 `playurl.py`。
- 不给搜索、歌单或播放增加第三方依赖；登录依赖只放同目录。
