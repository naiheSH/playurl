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

公开歌曲搜索只稳定覆盖首批最多约 30 条候选；歌曲 `offset` 只在这批候选中切片。公开歌单搜索可按记录序号继续翻页。只有歌名和歌手精确对应时才选 ID；多条或不确定时停止并让用户选择。

## 歌单与播放

公开歌单搜索与公开歌单曲目不需要 Cookie。`mine`、`liked`、`recent` 需要登录 Cookie。`tracks` 返回的歌曲 `id` 逐首交给 `playurl.py`。

音质不使用命令行位置参数。配置位于 `playurl.py` 顶部 `ENABLE_FLAC`：默认 `False`，排除 FLAC 和潜在无损加密流，在可用 M4A/MP3 中按码率从高到低选；最高档受限时自动降级。只有用户明确要求无损时才改为 `True`。

- 直接 URL：默认标准输出只有一行 URL；接入播放器用 `--json`，并原样发送 `httpHeaders`。
- 带 `#auth=`：不能直接播放。只有用户明确要求时使用 `--decrypt`。
- 会员、购买或试听流：不能冒充非会员完整流。
- `track_v2` 空响应：脚本会回退目标歌曲公开详情；仍无完整流时停止。
- 失败和 JSON 模式：输出两空格缩进的多行 JSON。

## 禁止

- 不用歌曲搜索结果伪造歌单搜索。
- 不把其他平台 ID 交给汽水脚本。
- 不调用本地接口补救空响应。
- 不把分享页试听、推荐歌曲或会员流冒充完整播放地址。
- 不在输出中暴露 Cookie、验证码或会话响应正文。
