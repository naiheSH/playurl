# playurl

六个平台的播放地址查询。每个平台一个目录，Python 脚本不导入其他平台目录的代码，也不需要先打开桌面客户端或请求 `127.0.0.1:3000`。播放、搜索和歌单脚本除 YouTube 外只使用 Python 标准库；扫码登录的可选依赖放在各平台自己的目录中。

各平台命令细节在对应目录的 `README.md`。给代理用的流程在同目录 `SKILL.md`。跨平台接口、输出、凭据和播放说明在 `doc/`。

每个平台独立检查自己的凭据，不依赖根目录入口或其他平台脚本：

```text
python3 playurl/netease/check.py
python3 playurl/qq/check.py
python3 playurl/kugou/check.py
python3 playurl/qishui/check.py
python3 playurl/spotify/check.py
python3 playurl/youtube/check.py
```

平台目录可单独复制使用。

## 目录

| 目录 | 搜索 | 歌单 | 播放 | 歌曲 ID |
| --- | --- | --- | --- | --- |
| `netease` | 有 | 有 | 有 | 数字 ID |
| `qq` | 有 | 有 | 有 | songmid，可选 media_mid |
| `kugou` | 有 | 有 | 有 | 文件 hash，建议带 album_id、album_audio_id |
| `qishui` | 有 | 有 | 免费曲可直接播放；加密流可解密 | track_id / item_id |
| `spotify` | 有 | 有 | 无音频直链；支持官方播放器元数据 | Spotify track id |
| `youtube` | 有 | 有 | 有，依赖 `yt-dlp` | 11 位 video ID |

歌单没有一条总播放地址。先拿到曲目 ID，再逐首交给该目录的 `playurl.py`。

## 流程

1. 搜歌。查询可以是歌名、`歌名 歌手` 或 `歌手 歌名`。脚本会拉一页较宽的结果再本地排序，不依赖上游顺序。
2. 只有歌名和歌手都精确对应时才使用返回的 `id`。同名、翻唱或现场版本不确定时停下来确认，不要猜 ID。
3. 搜歌单用 `playlist.py search`。列歌用 `playlist.py tracks`。`offset` 是曲目序号，不是页号，返回里有 `total`。
4. 自己的歌单才用 `playlist.py mine`。网易云、QQ、酷狗读同目录 `cookie`；Spotify 使用用户 OAuth access token。
5. 用 `playurl.py` 换播放地址。成功时标准输出只有 URL。加 `--json` 才输出完整字段。

搜歌和公开歌单不读 cookie。`mine` 与登录播放才读 cookie。

```text
python3 playurl/<platform>/search.py <歌名|歌名 歌手|歌手 歌名> [limit] [offset]
python3 playurl/<platform>/playlist.py search <关键词> [limit] [offset]
python3 playurl/<platform>/playlist.py tracks <歌单 id> [limit] [offset]
python3 playurl/<platform>/playlist.py mine [limit] [offset]
python3 playurl/<platform>/playurl.py <id> [quality]
python3 playurl/<platform>/playurl.py <id> [quality] --json
```

国内平台扫码登录也是逐目录独立的，目录拆走后仍可单独使用：

```text
python3 playurl/netease/login.py   # 网易云音乐 App 扫码
python3 playurl/qq/login.py        # QQ 音乐 App 扫码，不用 QQ/微信
python3 playurl/kugou/login.py     # 酷狗音乐 App 扫码
python3 playurl/qishui/login.py    # 汽水 App 扫码，默认纯 HTTP、无需浏览器
node playurl/qishui/login.cjs      # 同一登录流程的 Node.js 18+ 单文件，不是播放入口
```

网易云、QQ 和酷狗首次扫码登录前分别安装其同目录 `requirements.txt`。它们会在终端绘制二维码，并提供随机 `127.0.0.1` 备用页面；传 `--no-open` 可只用终端。汽水默认登录只使用 Python 标准库，不打开浏览器；只有显式传入 `--browser` 时才需要安装 `qishui/requirements.txt`。

`<platform>` 只替换成上表里的目录名。QQ 搜歌不支持 `offset`。Spotify 的搜索和歌单命令需要官方 OAuth 配置，播放命令不会返回音频直链。YouTube 不支持 `mine`。

成功时退出码 0。参数或命令错误退出码 2。接口失败或空结果退出码 1。

搜索和歌单成功时输出 JSON。播放成功时默认只输出一行 URL。播放失败、播放命令带了 `--json`，或汽水返回需要解密的加密流时输出 JSON。不要把 Python traceback 当成正常输出。

所有命令行 JSON（包括成功、限制和错误结果）都使用两空格缩进的多行格式，并保留中文字符，不再压成一行。它仍是标准 JSON，可以直接交给 JSON 解析器。

## 播放结果

默认：

```text
https://...
```

`--json` 时，三个可播放平台都有：

- `provider`
- `id`
- `url`
- `requested`：请求的音质
- `level`：实际拿到的音质
- `trial`：是否试听
- `playable`
- `loggedIn`
- `restriction`

汽水可播放结果另有 `httpHeaders`。客户端请求汽水 `url` 时必须原样携带这些请求头，否则 CDN 可能返回 403。字段命名与 YouTube 播放结果一致。

网易云另有 `type`。网易云和 QQ 另有 `expi`，单位秒。酷狗没有到期字段。

播放地址是短期签名 URL。只长期保存歌曲 ID、歌单 ID 和曲目序号。开始播放、重试、收到 401/403，或接近 `expi` 时重新请求。不要把它叫 token，也不要长期缓存。

## 音质

默认只选择 M4A 或 MP3。配置在每个平台自己的 `playurl.py` 顶部，彼此独立：

| 平台 | 默认配置 | 高音质不可用时 | 开启 FLAC 后 |
| --- | --- | --- | --- |
| 网易云 | `ENABLE_FLAC = False`、`QUALITY = "exhigh"` | `exhigh MP3 → standard MP3` | `lossless FLAC → exhigh MP3 → standard MP3` |
| QQ | `ENABLE_FLAC = False`、`QUALITY = "exhigh"` | `320k MP3 → 标准 MP3 → M4A/AAC` | `FLAC → 320k MP3 → 标准 MP3 → M4A/AAC` |
| 酷狗 | `ENABLE_FLAC = False`、`QUALITY = "exhigh"` | `320k MP3 → 128k MP3` | `FLAC → 320k MP3 → 128k MP3` |
| 汽水 | `ENABLE_FLAC = False` | 在可用 M4A/MP3 中按码率从高到低选择 | FLAC 也加入码率排序 |
| YouTube | `ENABLE_FLAC = False`、`QUALITY = "high"` | 选择上游可用的 M4A，其次 MP3 | FLAC 也加入格式候选 |

开启某个平台的 FLAC，只修改该目录的 `playurl.py`：

```python
ENABLE_FLAC = True
```

网易云、QQ、酷狗会自动把默认 `QUALITY` 切成 `lossless`。关闭时即使传入 `flac`、`lossless` 或 `hires`，也会按该平台默认高音质档处理，不会返回 FLAC。命令行音质参数只覆盖当次请求。

Spotify 官方接口不提供音频直链，因此没有这里的格式和降级配置。

高音质取决于曲目、账号和版权。实际档低于请求档，或 `trial` 为真，不是脚本分页错误。

## 平台差异

### 网易云

`tracks` 先用 `n=0` 取完整 `trackIds`，再按 offset 分批请求歌曲详情。单次最多 100 首。`mine` 走 weapi，不使用未签名的普通 POST。

cookie 读取顺序：`NETEASE_MUSIC_U`、`MUSIC_U`、同目录 `cookie` 中的 `MUSIC_U=`。

### QQ

公开歌单 ID 是 `disstid`。`tracks` 使用 `song_begin` 和 `song_num`，单次最多 200 首。`liked` 是虚拟歌单「我的喜欢」，dirid 为 `201`，不是公开 ID。

QQ 账号登录需要 `uin` 和 `qm_keyst`、`qqmusic_key` 或 `music_key`；微信账号登录使用 `wxuin` 和 `wxskey`。搜索接口最多约 10 条，排序不能补回没有返回的原曲。

### 酷狗

公开歌单 ID 是 `specialid`。`collection_` 开头的是云歌单，只能在已登录时列歌。公开总数来自 `data.total`，自己的歌单总数来自 `data.count`。

`playurl.py` 的 ID 是 hash。能拿到时一并传入 `album_id` 和 `album_audio_id`。cookie 需要 `KuGoo` 或 `userid` + `token`，以及 `kg_mid`、`kg_dfid`。

### 汽水

搜索 ID 是 `item_id`。个人歌单和登录播放读取同目录 `cookie`，核心凭据是 `sessionid`；完整 Cookie 失败时自动使用核心会话重试，不按 `sid_guard` 日期提前判定过期。默认用 `login.py` 纯 HTTP 扫码，不打开浏览器。`/luna/pc/track_v2` 仍可能返回空正文。

公开歌曲搜索只稳定覆盖首批最多约 30 条候选，歌曲 `offset` 只在该批次中切片；公开歌单搜索可按记录序号继续翻页。

`playlist.py search` 使用 PC 歌单搜索协议；`mine` 返回“我的喜欢”“最近播放”和账号歌单；`tracks` 返回可直接交给 `playurl.py` 的曲目 ID。

`track_v2` 空正文时会回退到目标歌曲的公开详情。非会员可完整播放的歌曲会返回最高可用码率；会员曲、试听流和推荐歌曲不会冒充目标歌曲的完整流。脚本不读取额外的客户端请求配置，也不接收动态签名。

地址带 `#auth=` 时，用下面的命令解密。解密实现在同目录 `playurl.py`，不要改成调用仓库 Node 解密器或第三方加密包。解密时输出 JSON，因为结果里还有文件路径。

```text
python3 playurl/qishui/playurl.py <track_id> --decrypt output.m4a
```

### Spotify

```text
python3 playurl/spotify/playurl.py <spotify_track_id>
```

官方 Web API 不提供可直接播放的音频 URL。结果是 JSON，`playable: false`，同时给出 Spotify URI、网页、Embed URL 和支持的官方播放模式。不要把这些字段或预览片段改写成音频直链。

Spotify 搜索和歌单读取使用环境变量 `SPOTIFY_CLIENT_ID`、`SPOTIFY_CLIENT_SECRET`、`SPOTIFY_ACCESS_TOKEN`、`SPOTIFY_MARKET`，或同目录、已 gitignore 的 `credentials` JSON。搜索每次最多 10 条；`mine` 和歌单曲目必须使用用户 access token。当前官方接口只允许读取该用户拥有或协作的歌单内容，Client Credentials 只能读取允许的元数据。

### YouTube

YouTube 是单独的音源，不冒充 Spotify。歌曲搜索、真实歌单搜索和歌单读取由 `yt-dlp` 完成；`playurl.py` 返回短期音频 URL，并在 JSON 模式保留请求头和有效期。公开内容通常不需要 Cookie，受限内容可使用同目录、已 gitignore 的 Netscape `cookies.txt`；手工 PO Token 可逐行放在同目录 `token` 文件。

## 凭据

网易云、QQ、酷狗凭据以及汽水个人账号功能的凭据只放各自同目录 `cookie`。四个 `login.py` 都以原子替换写文件并设置权限 `600`。汽水公开搜索、公开歌单和非会员免费曲不要求 Cookie。Spotify 使用 OAuth 环境变量或 `credentials`，不读取网页登录 cookie。根 `.gitignore` 已忽略这些本机文件。

不要把 cookie 或播放签名写入命令、日志、测试、文档或提交。各平台 `check.py` 会实际请求只读账号接口判断是否过期，但只输出状态，不打印值。退出码统一为 `0` 有效或无需凭据、`1` 缺失/无效/过期、`2` 因网络或上游异常无法确认。

## 鸣谢与参考

本目录在接口字段、登录流程和兼容性验证过程中参考了以下开源项目，感谢原作者和贡献者的研究与维护：

- 网易云音乐：[chaunsin/netease-cloud-music](https://github.com/chaunsin/netease-cloud-music)
- QQ 音乐基础接口：[ylw1997/qqmusic-api](https://github.com/ylw1997/qqmusic-api)
- QQ 音乐 App 扫码登录与客户端协议：[L-1124/QQMusicApi](https://github.com/L-1124/QQMusicApi)
- 酷狗音乐：[MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi)
- 汽水音乐基础接口：[guowenye/qishui-api](https://github.com/guowenye/qishui-api)
- 汽水纯 HTTP 扫码、状态机与短信验证：[LuoYe17/ly-music-source](https://github.com/LuoYe17/ly-music-source)
- 汽水扫码状态、浏览器签名与限流研究：[sodahub-org/libresoda](https://github.com/sodahub-org/libresoda)
- YouTube 媒体解析：[yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp)

这些项目不是本目录脚本所调用的常驻服务。除各平台 README 明确列出的 Python 包外，脚本不会要求用户另外部署上述项目。相关项目名称、代码与协议研究成果仍分别遵循其原仓库的许可证；本项目不是网易云音乐、QQ 音乐、酷狗音乐、汽水音乐、Spotify 或 YouTube 的官方项目。

## 明确不做

- 不在脚本之间互相 import。
- 不调用本地接口补救失败请求。
- 不为汽水补伪歌单脚本。
- 不把 Spotify Embed、URI 或网页地址冒充音频直链。
- 不把试听、版权限制或空响应伪装成完整播放地址。
- 播放、搜索和歌单不增加跨平台依赖；登录所需依赖只留在该平台目录。
