---
name: playurl-qishui
description: 用 playurl/qishui 的独立脚本登录汽水音乐、搜索歌曲或歌单、读取个人歌单，并获取或解密 track_id 播放地址。用户提到汽水音乐、汽水扫码、歌单、track_v2、sessionid 或 #auth= 时使用。
---

# playurl 汽水音乐

只使用 `playurl/qishui/` 内的独立实现，不请求常驻本地服务。

## 路由

| 用户需求 | 文件或命令 |
| --- | --- |
| 在 Python 代码中集成登录 | 导入 `auth.py` 的 `QishuiAuthClient` |
| 命令行扫码登录 | `python3 playurl/qishui/login.py` |
| 纯 HTTP 失效时的浏览器兜底 | `python3 playurl/qishui/login.py --browser` |
| 搜歌曲 | `search.py` |
| 搜公开歌单 | `playlist.py search` |
| 我的歌单、喜欢、最近播放 | `playlist.py mine` / `playlist.py tracks` |
| 已有 track_id，要播放地址 | `playurl.py` |
| 明确要求解密 `#auth=` 地址 | `playurl.py --decrypt output.m4a` |

`item_id` 与 `track_id` 是同一数字 ID。搜索返回的 `id` 可直接交给 `playurl.py`。

## 登录

默认登录是纯 HTTP Python 通路，只使用标准库，不打开浏览器，也不要求安装依赖：

```text
python3 playurl/qishui/login.py
```

它保存官方二维码 PNG，使用汽水音乐 App 扫码；上游要求时处理短信二次验证。成功后只把完整 Cookie 原子写入同目录 `cookie`，权限为 `600`。不要打印 Cookie。

终端二维码是可选增强；缺少 `terminal-qrcode` 时使用生成的 PNG，不要因此判定登录失败。只有平台更新导致纯 HTTP 失败时才使用 `--browser`；该兜底需要 Playwright 和本机 Chrome/Edge/Chromium。

上游按设备身份限流。不要并行创建多个二维码；轮询应遵守结果中的 `retryAfterSec`。一个 `QishuiLoginSession` 不跨线程并发复用。

嵌入其他 Python 项目时直接使用：

```python
from qishui.auth import QishuiAuthClient

login = QishuiAuthClient().create_qr_login()
# 展示 login.qr_png；约 8 秒或按 retryAfterSec 调用 login.poll()
result = login.poll()
```

若 `result["mfa"]["needSms"]` 为真，调用 `send_mfa_sms()`，取得用户输入后调用 `validate_mfa_sms(code)`；成功后调用 `save_cookie(path)`。把 Cookie 当作密码，不写日志、命令、JSON、文档或提交。

## 命令

```text
python3 playurl/qishui/search.py "歌名 歌手" 10 0
python3 playurl/qishui/playlist.py search "关键词" 10 0
python3 playurl/qishui/playlist.py mine 30 0
python3 playurl/qishui/playlist.py tracks <歌单 id|liked|recent> 50 0
python3 playurl/qishui/playurl.py <track_id>
python3 playurl/qishui/playurl.py <track_id> --json
python3 playurl/qishui/playurl.py <track_id> --decrypt output.m4a
```

公开歌曲搜索只稳定覆盖首批最多约 30 条候选；歌曲 `offset` 只在这批候选中切片，到 30 后为空不是翻页失败。公开歌单搜索可按记录序号继续翻页。只有歌名和歌手精确对应时才选 ID；多条、现场、翻唱或不确定时列出 `id`、`name`、`artist` 后停止。不要选排序第一。

歌曲搜索对象只用 `id`、`name`、`artist`。`id` 是数字 `item_id`，与 `track_id` 相同。歌单对象保留 `id`、`name`、`trackCount`。用户没指定歌单时不要自动 `tracks`。

`liked` 和 `recent` 是虚拟歌单 ID，只能交给 `playlist.py tracks`，不能交给 `playurl.py`，也不能当成公开歌单 ID 搜索。

## 播放

每首单独运行一次 `playurl.py`。它不接受音质位置参数，多余参数是退出码 2。

配置位于 `playurl.py` 顶部 `ENABLE_FLAC`。默认 `False`，排除 FLAC 和潜在无损加密流，在可用 M4A/MP3 中按码率从高到低选。只有用户明确要求无损时才改为 `True`。

汽水的 `level` 是上游 quality 字符串，不是 `exhigh` 或 `lossless`。比较音质看 `format` 和 `bitrate`。

- 直接 URL：默认标准输出只有一行 URL。接入播放器必须加 `--json`，并原样发送 `httpHeaders`，否则 CDN 可能 403。
- `encrypted: true` 或 URL 带 `#auth=`：不能直接播放。只有用户明确要求时使用 `--decrypt`。解密输出 JSON，最终路径看 `decryptedFile`。
- `vip_required`：会员曲。不要改用试听、推荐或分享页地址冒充完整版本。
- `login_required`：公开详情没有非会员完整流。先纯 HTTP 登录，不要换 track_id。
- `track_v2` 空响应：脚本会回退目标歌曲公开详情；仍无完整流时停止。
- `url_unavailable` 或 `source_unavailable`：停止并报告 `restriction.message`。

成功 JSON 还可能有 `size`、`duration`、`directPlayable`、`source`。`source` 只说明命中了登录接口还是公开详情。

## 失败时怎么停

| 看到什么 | 怎么处理 |
| --- | --- |
| 退出码 2 | 命令或 ID 格式错误。不要给播放命令加音质参数 |
| 退出码 1 且 `error` 非空 | 停止并报告 `error`，不要打印响应正文 |
| `needSms` | 向用户要验证码，再调用 `validate_mfa_sms`。不要把验证码写入日志 |
| 登录 `expired` 或 `failed` | 重新运行一次登录。不要并行开多个二维码 |
| 播放 401 或 403 | 先确认带了 `httpHeaders`；仍失败再用同一 track_id 重新请求一次 |

## 禁止

- 不用歌曲搜索结果伪造歌单搜索。
- 不把其他平台 ID、歌单 ID、`liked` 或 `recent` 交给 `playurl.py`。
- 不调用本地接口补救空响应。
- 不把分享页试听、推荐歌曲或会员流冒充完整播放地址。
- 不在输出中暴露 Cookie、验证码或会话响应正文。
- 不把 `login.cjs` 当作播放或搜索入口。
