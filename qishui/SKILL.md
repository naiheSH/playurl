---
name: playurl-qishui
description: 用 playurl/qishui 的独立标准库脚本搜索汽水音乐、读取个人歌单并请求 track_id 播放地址。用户提到汽水、歌单、track_v2、sessionid 或 #auth= 解密时使用。
---

# playurl 汽水音乐

只用 `playurl/qishui/` 里的独立标准库脚本。不要导入仓库解密器或其他代码，不要请求常驻本地服务。

## 按用户原话选脚本

| 用户要的 | 用这个 | 不要用 |
| --- | --- | --- |
| 歌名、歌手、找一首歌 | `search.py` | `playurl.py` |
| 已有 track_id 或 item_id，要播放地址 | `playurl.py` | 再搜一次 |
| 地址带 `#auth=`，且用户明确要求解密 | `playurl.py --decrypt output.m4a` | 仓库 Node 解密器 |
| 按关键词搜公开歌单 | `playlist.py search` | 歌曲 `search.py` |
| 我的歌单、我的喜欢、最近播放 | `playlist.py mine` | 公开搜索 |
| 没有 sessionid、要扫码登录 | `login.py` | 手工打印 cookie |
| 已有歌单 ID，要列曲目 | `playlist.py tracks` | `search.py` |
| 分享页试听 | 只有用户接受试听时才单独说明 | 不要冒充 `playurl.py` 的完整音质 |

`item_id` 和 `track_id` 是同一个数字 ID。搜索返回的 `id` 可以直接交给 `playurl.py`。

## 命令

在仓库根目录运行。

```text
python3 playurl/qishui/login.py
python3 playurl/qishui/search.py "歌名"
python3 playurl/qishui/search.py "歌名 歌手" 10 0
python3 playurl/qishui/search.py "歌手 歌名"
python3 playurl/qishui/playlist.py search "关键词" 10 0
python3 playurl/qishui/playlist.py mine 30 0
python3 playurl/qishui/playlist.py tracks <歌单 id|liked|recent> 50 0
python3 playurl/qishui/playurl.py <track_id>
python3 playurl/qishui/playurl.py <track_id> --json
python3 playurl/qishui/playurl.py <track_id> --decrypt output.m4a
```

查询可以是歌名、`歌名 歌手` 或 `歌手 歌名`。不要传音质参数；多余位置参数会以退出码 2 拒绝。

公开歌曲接口只稳定返回首批最多约 30 条候选；歌曲搜索的 `offset` 只在这批候选中切片，达到 30 后应视为没有更多结果。公开歌单搜索可继续按记录序号翻页。

## 怎么读搜索结果

搜索成功时输出 JSON，退出码 0。歌曲对象只用：

- `id`：item_id，交给 `playurl.py`。
- `name`：歌名。
- `artist`：歌手。

只有歌名和歌手都精确对应时才取 `id`。只给歌名且唯一精确命中时可以使用。多条或不确定时列出这三项后停止，不要猜。

退出码不是 0 或没有 `songs` 时停止。

## 歌单

`playlist.py mine` 返回“我的喜欢”“最近播放”和账号歌单。`playlist.py tracks` 返回歌曲 `id`、`name`、`artist`、`album` 和 `duration`；把 `id` 逐首交给 `playurl.py`。歌单命令读取同目录 Cookie。

`playlist.py search` 使用汽水 PC 歌单搜索协议，公开搜索及公开歌单详情不读 Cookie。关键词不能为空，`offset` 是结果记录序号，不是页号。`mine`、`liked` 和 `recent` 才要求登录 Cookie。

## 播放

没有命令行音质参数。配置只改本目录 `playurl.py` 顶部的 `ENABLE_FLAC`。默认是 `False`：排除 FLAC 和可能解密为 FLAC 的加密流，在非会员可用的 M4A/MP3 中按码率从高到低选择；最高档受限时使用下一条允许的流。改成 `True` 后才把 FLAC 和加密无损流恢复进排序。

脚本也会解析 `video_model`、`url_player_info`、主备 URL 列表。

- 成功且是直接 URL：标准输出只有一行 URL，退出码 0。接入播放器时使用 `--json`，并把结果中的 `httpHeaders` 原样附加到媒体请求；裸 URL 可能返回 403。
- 成功但 URL 带 `#auth=`：输出 JSON，`encrypted: true`、`directPlayable: false`。先解密，不能把它直接交给普通播放器。
- `--json`、失败或没有 URL：输出两空格缩进的多行 JSON，失败退出码 1。
- `--decrypt` 总是输出 JSON，因为结果里还有解密后的文件路径。输出路径不能以 `--` 开头。只有用户明确要求解密时才用。
- 参数错误：退出码 2。

URL 含 `#auth=` 时是加密流，不能直接播放。解密实现必须留在本目录 `playurl.py`。不要调用仓库 Node 解密器，不要安装第三方加密包。

默认 `ENABLE_FLAC = False` 时不会选择带 `#auth=` 的潜在无损流。只有用户明确要求无损或解密时，才先把该开关改为 `True`，再运行 `--decrypt`。

`--json` 的成功结果包含 `httpHeaders`，当前包括汽水 PC `User-Agent` 和官方页 `Referer`。HTTP 客户端、播放器或代理层必须把它们原样附加到获取 `url` 的请求。

`playable: false` 或空 URL 时停止。不要改用其他平台的 ID。

## 空响应

同目录 `cookie` 里的 `sessionid`、`sessionid_ss`、`sid_guard`、`sid_tt`、`uid_tt` 或 `uid_tt_ss` 只表示登录。登录不能保证 `/luna/pc/track_v2` 有正文。

空正文时会回退到目标歌曲的公开详情。只允许返回目标曲目中标记为非会员可完整播放的流；会员曲、试听流和推荐歌曲都不能冒充完整地址。公开详情也无可用流时停止，不要编造地址，也不要把空正文说成 cookie 丢失。

脚本不读取额外的客户端请求配置，也不接收动态签名。PC 接口失败时只回退公开详情；仍无可用流就按实际限制停止。

## 凭据

凭据只放同目录 `cookie`。公开搜索不读它。不要打印值，不要写入命令、日志、测试、输出 JSON 或提交。文件权限应为 `600`。检查时只报告字段是否存在。

缺少 sessionid 时运行 `login.py`。默认模式打开一次性的可见 Chrome/Edge 官方页面，在同一浏览器会话里完成扫码和 Cookie 收集；不要连续生成二维码，否则会触发上游“访问太频繁”。`--direct-qr` 只是诊断用纯 HTTP 备用流程，可能在手机确认后仍拿不到新 Cookie。成功后只原子写入同目录 `cookie`。

## 不要做

- 不用歌曲搜索结果或专辑字段伪造歌单搜索。
- 不在脚本之间互相 import。
- 不调用本地接口补救空响应。
- 不增加第三方依赖。
- 不把分享页试听 URL 写进脚本返回值。
