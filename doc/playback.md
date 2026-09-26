# 播放、音质和失败

播放脚本返回的是短期签名地址。只长期保存歌曲 ID、歌单 ID 和曲目序号。开始播放、重试、收到 401/403，或接近网易云、QQ 的 `expi` 时重新请求。不要把播放地址称作 token，也不要长期缓存。

## 音质字段

`requested` 是本次请求档，`level` 是实际拿到的档。两者不是跨平台通用枚举，调用方不要把一个平台的 `level` 原样传给另一个平台。

没有单独的音质字段时，格式看 URL 后缀或平台附加字段。网易云用 `type`，QQ 用 `quality` 和 `filename`，汽水用 `format` 与 `bitrate`，YouTube 用 `format`。

| 平台 | 命令行可传 | 默认 `requested` | `level` 含义 |
| --- | --- | --- | --- |
| 网易云 | `lossless`、`exhigh`、`standard` | `exhigh` | 与请求档同一套名字；实际格式见 `type` |
| QQ | `lossless`、`exhigh`、`standard`、`aac`，以及下表别名 | `exhigh` | 与请求档同一套名字；展示名在 `quality` |
| 酷狗 | `lossless`、`exhigh`、`standard` | `exhigh` | 与请求档同一套名字 |
| 汽水 | 不接受命令行音质 | 无 `requested` | 上游原始 quality 字符串，不是上面三档 |
| YouTube | `high`、`standard` | `high` | yt-dlp 的 `format_id`，不是音质档名 |
| Spotify | 不接受 | 无 | 无音频档位 |

网易云、QQ、酷狗的 `ENABLE_FLAC = False` 时，`lossless` 不在可选档里。此时传入 `flac`、`lossless`、`hires` 会回落到该平台默认档，不会返回 FLAC。开启后默认档变成 `lossless`，并继续向更低档降级。命令行参数只覆盖当次请求。

QQ 另有别名：`flac`、`sq`、`hires`、`hi-res`、`highres`、`master`、`jymaster` 都映射到 `lossless`；`320`、`320k`、`hq` 映射到 `exhigh`；`128`、`128k` 映射到 `standard`。未识别的值回落到默认档。

## 各档对应什么

| 平台 | `lossless` | `exhigh` | `standard` | 更低档 |
| --- | --- | --- | --- | --- |
| 网易云 | FLAC，eapi `level=lossless` | MP3，eapi `level=exhigh` | MP3，eapi `level=standard` | 无 |
| QQ | `F000` FLAC；模板里的 `RS01` Hi-Res 不在默认降级链 | `M800` 320k MP3 | `M500` 128k MP3 | `aac`：`C400` M4A |
| 酷狗 | 请求 `flac`；命中后 `level` 仍写 `lossless` | 请求 `320`；命中后写 `exhigh` | 请求 `128`；命中后写 `standard` | 无 |
| YouTube | 不使用这个名字 | 不使用这个名字 | `standard` 只是 `abr<=160` 的 M4A/MP3 | `high` 是不限码率的最佳 M4A/MP3 |

汽水没有这三档。它把上游返回的可用流按 `bitrate` 从高到低选。默认只保留非加密的 M4A/MP3；`ENABLE_FLAC = True` 后，FLAC 和带 `play_auth` 的流才进入排序。因此汽水的 `level` 可能是上游 quality 名，不能把它当成 `exhigh`。

YouTube 的 `high` 选择 `bestaudio[ext=m4a]`，其次 MP3。`standard` 使用同样的后缀顺序，但限制 `abr<=160`。开启 FLAC 后，两种档位都先尝试 FLAC。返回的 `level` 是具体 `format_id`，比较音质应看 `format`、`bitrate`，不要比较 `level` 字符串。

实际档低于请求档，或 `trial` 为真，是曲目、账号或版权限制，不是分页错误。Spotify 不返回音频直链，所以没有音质档。

## 失败类别

播放失败仍输出 JSON，`playable` 为假，`url` 为空。`restriction.category` 目前使用：

| 类别 | 含义 | 调用方动作 |
| --- | --- | --- |
| `login_required` | 当前凭据不足，会员曲或个人内容无法继续 | 先运行对应 `login.py`，不要换一个猜测的歌曲 ID |
| `vip_required` | 汽水明确标记该曲需要会员 | 不把试听或推荐流当作完整版本 |
| `url_unavailable` | 上游没有给出可用的完整地址 | 可换音质或稍后重试，不缓存空结果 |
| `provider_limited` | Spotify 官方能力边界 | 使用官方 Embed 或 Web Playback SDK |
| `source_unavailable` | 上游或 `yt-dlp` 请求失败 | 保留错误信息，按网络或上游故障处理 |

试听流不会被伪装成完整播放。汽水还会拒绝与目标曲目 ID 不一致的公开详情，以及会员、购买或推荐来源的冒充流。

## 平台播放差异

- 网易云先请求 eapi，再回退旧的播放 URL 接口。两条都没有 URL 才失败。
- QQ 会先补 `media_mid`，再换 `purl`，并用 `Range: bytes=0-1` 探测候选 CDN。探测不是播放，只确认 200 或 206。
- 酷狗按 tracker、gateway、网页接口、网页重试、移动页的顺序尝试。JSON 里的 `source` 表示命中哪一条。
- 汽水未登录或登录接口空正文时回退公开详情。请求返回的 URL 时必须带 `httpHeaders`。带 `#auth=` 的结果先用同目录 `playurl.py <id> --decrypt <输出文件>` 解密。个人内容用 `qishui/login.py` 或 `qishui/login.cjs` 纯 HTTP 扫码；不要默认打开浏览器，也不要把 `login.cjs` 用于播放。
- YouTube 的格式选择和有效期由 `yt-dlp` 给出。公开内容通常不需要 cookie；受限内容才读取同目录凭据文件。
- Spotify 固定返回官方 URI、网页和 Embed 地址。不要把预览片段改写成通用音频 URL。

## 重试边界

可以重试的是同目录、同一歌曲 ID 的一次新请求。不应该做的是：

- 用另一个平台的 cookie 或脚本补救失败。
- 在脚本之间互相导入。
- 请求本机 `127.0.0.1:3000` 或常驻代理服务。
- 把 401、403、空正文或试听结果缓存成成功。
- 因为搜索排序第一就自动换一首同名曲继续播放。
