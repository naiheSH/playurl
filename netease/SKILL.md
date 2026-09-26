---
name: playurl-netease
description: 用 playurl/netease 的独立标准库脚本搜索网易云歌曲和歌单，并把歌曲数字 ID 换成短期 MP3 或可选 FLAC 地址。用户提到网易云、MUSIC_U、歌单 trackIds、音质或播放 URL 时使用。
---

# playurl 网易云

只用 `playurl/netease/` 里的独立脚本。搜索、歌单和播放只使用 Python 标准库；登录二维码生成依赖同目录 `requirements.txt`。不要导入仓库其他代码，不要请求 `127.0.0.1:3000`，不要把歌名当成歌曲 ID。

## 按用户原话选脚本

| 用户要的 | 用这个 | 不要用 |
| --- | --- | --- |
| 歌名、歌手、找一首歌 | `search.py` | `playurl.py` |
| 公开歌单名称 | `playlist.py search` | `search.py` |
| 已有歌单数字 ID，要里面的歌 | `playlist.py tracks` | `playurl.py` |
| 我的歌单、我喜欢的歌单 | `playlist.py mine` | 公开搜索 |
| 没有 MUSIC_U、要扫码登录 | `login.py` | 手工打印 cookie |
| 已有歌曲数字 ID，要播放地址 | `playurl.py` | 再搜一次 |

歌曲 ID 是纯数字。歌单 ID 也是纯数字。二者不能互换。

## 命令

在仓库根目录运行。`limit` 和 `offset` 都是数字，可省略。

```text
python3 -m pip install -r playurl/netease/requirements.txt
python3 playurl/netease/login.py
python3 playurl/netease/search.py "歌名"
python3 playurl/netease/search.py "歌名 歌手"
python3 playurl/netease/search.py "歌手 歌名" 10 0
python3 playurl/netease/playlist.py search "歌单关键词" 10 0
python3 playurl/netease/playlist.py tracks <歌单数字 id> 50 0
python3 playurl/netease/playlist.py mine 30 0
python3 playurl/netease/playurl.py <歌曲数字 id>
python3 playurl/netease/playurl.py <歌曲数字 id> exhigh --json
python3 playurl/netease/playurl.py <歌曲数字 id> standard
```

歌单 `offset` 是曲目序号，从 0 开始，不是页号。`tracks` 单次最多 100 首。

## 怎么读搜索结果

搜索和歌单成功时输出 JSON，退出码 0。空结果或接口失败输出 JSON 并退出码 1。参数错误退出码 2。

歌曲对象只用这三个字段：
- `id`：交给 `playurl.py` 的数字 ID。
- `name`：歌名。
- `artist`：歌手。

只有用户给的歌名和歌手都与某一条精确对应时，才取那条的 `id`。比较时忽略大小写和多余空格，不要忽略「现场」「翻唱」「伴奏」「DJ」。

只给了歌名且结果只有一条，并且歌名精确对应，可以使用。出现多条、同名、现场、翻唱、伴奏或对不上歌手时，把每条的 `id`、`name`、`artist` 列给用户，然后停止。不要选第一条，不要猜 ID，不要改用其他平台。

`playlist.py search` 的歌单对象只保留 `id`、`name`、`trackCount`。用户没指定是哪张歌单时列出这些字段并停止。确认后再 `tracks`。

`tracks` 和 `mine` 成功时读取 `songs` 与 `total`。`total` 是整张歌单的歌曲数，不是本页条数。本页每首歌只保留 `id`、`name`、`artist`。用户要整张歌单时，用 `offset` 按 100 递增继续取，直到拿满 `total` 或用户只要一部分。

`error` 非空、退出码 1 或 `songs`/`playlists` 为空时停止。不要改接口，不要请求本地服务。

## 播放

每首歌单独运行一次 `playurl.py`。歌单没有一条总播放地址。

成功时标准输出只有一行完整 URL，退出码 0。原样交给播放器。不要截断，不要改成只报域名，不要再包一层 JSON。

只有需要判断音质、试听或到期时才加 `--json`。命令行 JSON 使用两空格缩进的多行格式，仍可直接交给 JSON 解析器。JSON 字段：

- `requested`：这次请求的档。
- `level`：实际拿到的档。低于 `requested` 不是脚本错误。
- `type`：应为 `mp3`。
- `trial`：`true` 是试听片段，不要说成完整歌曲。
- `expi`：剩余秒数。接近它、过期、401 或 403 时，用同一个歌曲 ID 重新请求。
- `playable`：`false` 时没有可用 URL，停止，不要换平台编一个地址。
- `loggedIn`：只说明这次有没有读到 `MUSIC_U`。
- `restriction`：非空时把 `category` 告诉用户，不要重试同一请求。

## 音质

配置只改本目录 `playurl.py` 顶部的 `ENABLE_FLAC`。默认是 `False`，命令行可选档只有 `exhigh`、`standard`。顺序为 `exhigh MP3 → standard MP3`；高音质不可用时会自动降级。改成 `True` 后默认档变成 `lossless`，顺序为 `lossless FLAC → exhigh MP3 → standard MP3`，脚本会随档位切换 `encodeType`。

命令行第二个参数只覆盖这一次。关闭 FLAC 时，`flac`、`hires`、`lossless`、`jymaster` 不在可选档里，会回落到默认 `exhigh`，不得返回 FLAC。未识别的音质同样回落，不要为此改歌曲 ID。

`level` 与 `requested` 使用同一套名字。实际格式看 `type`，不要只凭 `level` 判断是 MP3 还是 FLAC。`level` 低于 `requested` 是账号或版权限制。

## 凭据

搜歌和公开歌单不读 cookie。`mine` 和登录播放才读。

没有 `MUSIC_U` 时运行 `login.py`。它打印并打开随机的 `127.0.0.1` 页面，只用于展示二维码和状态；使用网易云音乐 App 扫码后原子写入同目录 `cookie`。这个临时页面不是播放服务。首次使用前安装同目录 `requirements.txt`；搜索、歌单和播放不需要它。

读取顺序只有：环境变量 `NETEASE_MUSIC_U`、环境变量 `MUSIC_U`、同目录 `cookie` 的 `MUSIC_U=`。`mine` 必须走 weapi。不要改成未签名的普通 POST，空 200 不是成功。

不要打印 cookie，不要写入命令、日志、测试、JSON 或提交。文件权限应为 `600`。只长期保存歌曲 ID、歌单 ID 和曲目序号。

## 失败时怎么停

| 看到什么 | 怎么处理 |
| --- | --- |
| 退出码 2 | 参数或 ID 格式错误。修正命令，不重试同一命令 |
| 退出码 1 且 `error` 非空 | 把 `error` 告诉用户并停止 |
| `playable: false` | 没有可用 URL。不要换平台编地址 |
| `restriction.category` 为 `url_unavailable` | 上游没有完整地址。不要把空 URL 缓存成成功 |
| `loggedIn: false` 且会员曲失败 | 先走 `login.py`，不要改歌曲 ID |
| `trial: true` | 这是试听。明确告诉用户，不要说成完整歌曲 |
| 401、403 或接近 `expi` | 只用同一个数字歌曲 ID 重新请求一次 |

不要因为搜索排序第一就自动换一首同名曲。不要用其他平台 cookie 补救。

## 不要做

- 不在脚本之间互相 import。
- 不调用本地接口补救失败请求。
- 不把试听地址说成完整音质。
- 不给搜索、歌单或播放增加第三方依赖；登录依赖只放同目录。
- 不把其他平台的 ID 传给这个脚本。
- 不把歌单 ID 交给 `playurl.py`，也不把歌曲 ID 交给 `playlist.py tracks`。
