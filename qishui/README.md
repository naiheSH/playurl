# 汽水音乐

独立目录。不引用本目录以外的代码。播放、搜索、歌单、解密以及默认登录流程只使用 Python 标准库。`auth.py` 可直接集成到其他 Python 程序；`login.py` 是它的命令行封装。两者都无需浏览器或 Node.js。

## 文件

- `search.py`：公开搜歌。不读 cookie。
- `playlist.py`：读取登录账号的歌单、我的喜欢、最近播放和歌单曲目。
- `playurl.py`：用 `track_id` 请求播放地址，并可解密带 `#auth=` 的音频。
- `auth.py`：可复用的 Python 登录 API，纯 HTTP 创建/轮询二维码、处理短信二次验证和保存 Cookie；只使用标准库。
- `login.py`：`auth.py` 的命令行封装，默认不打开浏览器；`--browser` 是显式兜底。
- `check.py`：请求只读账号接口；完整 Cookie 失败时用核心 `sessionid` 复检。
- `login.cjs`：同一流程的自包含 Node.js 18+ 单文件版本，无需 `npm install`。
- `requirements.txt`：仅终端绘制二维码或 `--browser` 兜底需要，基础 Python 登录不需要安装。
- `THIRD_PARTY_NOTICES.md`：登录协议实现与内嵌二维码组件的来源、版本及许可证说明。
- `cookie`：登录凭据。已被 gitignore，不要提交。

## 命令

```text
python3 playurl/qishui/login.py
python3 playurl/qishui/check.py
node playurl/qishui/login.cjs
python3 playurl/qishui/search.py <歌名|歌名 歌手|歌手 歌名> [limit] [offset]
python3 playurl/qishui/playlist.py search <关键词> [limit] [offset]
python3 playurl/qishui/playlist.py mine [limit] [offset]
python3 playurl/qishui/playlist.py tracks <歌单 id|liked|recent> [limit] [offset]
python3 playurl/qishui/playurl.py <track_id> [--decrypt output.m4a] [--json]
```

## 推荐：无浏览器 Python 登录

```text
python3 playurl/qishui/login.py
```

默认流程只使用 Python 标准库，不启动浏览器，也不需要安装依赖。脚本把上游返回的官方二维码保存为同目录 `login-qr.png`，使用汽水音乐 App 扫码并在手机确认；若服务端要求短信二次验证，会在终端提示输入验证码。成功后完整 Cookie 被原子写入同目录 `cookie`，权限为 `0600`，不会回显凭据。二维码在流程结束后默认删除。

如果已安装可选的 `terminal-qrcode`，还会同时在终端绘制二维码；没有安装不会影响图片扫码。Homebrew Python 出现 `externally-managed-environment` 时无需为了基础登录安装任何包。确实需要终端二维码或浏览器兜底时，请使用虚拟环境：

```text
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r playurl/qishui/requirements.txt
```

常用选项：

```text
python3 playurl/qishui/login.py --help
python3 playurl/qishui/login.py --no-terminal
python3 playurl/qishui/login.py --timeout 900
python3 playurl/qishui/login.py --qr-file /tmp/qishui.png --keep-qr
python3 playurl/qishui/login.py --cookie-file /safe/path/cookie --json
python3 playurl/qishui/login.py --browser
```

### 集成到其他 Python 逻辑

把整个 `qishui` 目录复制到目标项目后，可直接导入；不要调用 `login.py` 子进程：

```python
from pathlib import Path
from qishui.auth import QishuiAuthClient

client = QishuiAuthClient()
login = client.create_qr_login()
Path("qishui-login.png").write_bytes(login.qr_png)

result = login.poll()  # 调用方按 retryAfterSec 或约 8 秒间隔继续轮询
if result.get("mfa", {}).get("needSms"):
    login.send_mfa_sms()
    result = login.validate_mfa_sms(input("短信验证码："))
if result.get("status") == "confirmed" or result.get("ok"):
    login.save_cookie("cookie")
```

主要 API：

- `QishuiAuthClient(timeout=30, state_file=...)`：创建客户端，并持久化稳定的设备身份。
- `client.create_qr_login()`：返回独立的 `QishuiLoginSession`；`qr_png` 是可直接展示的 PNG 字节，`scan_url` 是官方扫码 URL。
- `login.poll()`：返回 `waiting`、`scanned`、`confirmed`、`expired` 或 `failed`；内置最小轮询间隔与限流冷却。
- `login.send_mfa_sms()` / `login.validate_mfa_sms(code)`：处理平台要求的短信二次验证。
- `login.cookie`：仅成功后有值；应当视作密码。优先使用 `login.save_cookie(path)` 安全落盘，不要写日志。

一个 `QishuiLoginSession` 对应一个登录流程，不要跨线程并发调用它，也不要并行刷新多个二维码。

## 无依赖 Node.js 单文件

```text
node playurl/qishui/login.cjs
```

要求 Node.js 18 或更高版本。`login.cjs` 已把登录逻辑和二维码渲染器打包进一个文件，使用者不需要运行 `npm install`，也不需要安装或启动 Chrome、Chromium、Edge、Electron、Playwright。

运行后会同时在终端绘制二维码，并把官方二维码保存为同目录 `login-qr.png`。使用汽水音乐 App 扫码并在手机确认；若服务端要求短信二次验证，脚本会发送验证码并在终端提示输入。成功后会把完整 Cookie 原子写入同目录 `cookie`，权限设为 `0600`，不会在终端回显凭据。二维码图片在流程结束后默认删除。

常用选项：

```text
node playurl/qishui/login.cjs --help
node playurl/qishui/login.cjs --no-terminal
node playurl/qishui/login.cjs --timeout 900
node playurl/qishui/login.cjs --qr-file /tmp/qishui.png --keep-qr
node playurl/qishui/login.cjs --cookie-file /safe/path/cookie --json
node playurl/qishui/login.cjs --self-test
```

登录器会持久化随机设备身份到同目录 `.qishui-state/`，并严格降低轮询频率：等待扫码时约 8 秒一次，扫码后约 6.5 秒一次；遇到上游限流会遵从返回的冷却时间。不要并行运行多个登录器，也不要连续刷新二维码。

该通路依赖汽水未公开的 Passport 接口，平台更新后仍可能变化。登录失败时再使用下方 Python 浏览器兼容方案。

## 浏览器兜底

只有纯 HTTP 通路因平台更新失效时才使用 `python3 playurl/qishui/login.py --browser`。该模式需要 `requirements.txt` 中的 Playwright 和系统已有的 Chrome、Edge 或 Chromium；使用一次性临时配置目录，成功后同样只把 Cookie 写入本目录。

直接可播时标准输出只有一行 URL。集成播放器时使用 `--json`，结果里的 `httpHeaders` 必须随音频请求发送；汽水 CDN 会拒绝缺少这些请求头的裸请求。使用 `--decrypt` 或返回的是带 `#auth=` 的加密流时也输出 JSON。失败时输出 JSON。

搜索 ID 是 `item_id`，交给 `playurl.py`。没有音质位置参数；多余参数会作为参数错误退出。脚本只取返回流里码率最高的一条。

公开歌曲搜索接口只稳定提供首批最多约 30 条候选；歌曲搜索的 `offset` 是在这批候选中切片，达到 30 后会返回空列表。公开歌单搜索支持继续按记录序号翻页，不受这个限制。

公开歌单搜索和公开歌单 `tracks` 不需要 Cookie。搜索使用汽水 PC 歌单搜索协议，`offset` 是记录序号；`tracks` 返回的歌曲 `id` 可逐首交给 `playurl.py`。`mine`、`liked` 和 `recent` 读取同目录 Cookie；完整 Cookie 被辅助字段拖累时自动退回仅携带 `sessionid`。`liked` 会自动映射到账号真实的“我喜欢的音乐”歌单。

## 播放限制

配置位于本目录 `playurl.py` 顶部：

```python
ENABLE_FLAC = False
```

汽水没有命令行音质档。默认排除 FLAC 和可能解密为 FLAC 的加密流，然后在可用 M4A/MP3 中按码率从高到低选择；最高码率不可用或受会员限制时，会选择响应中下一条允许的 M4A/MP3。改为 `True` 后，FLAC 和加密无损流也恢复进码率排序。

非会员可完整播放的歌曲可以不放 Cookie，脚本会从目标歌曲公开详情直接选取最高可用码率。同目录 `cookie` 中的登录字段用于尝试 PC 账号接口和个人歌单；脚本先发送完整 Cookie，失败时自动用核心 `sessionid` 重试，不把 `sid_guard` 的本地日期当作硬性到期日。`/luna/pc/track_v2` 返回空正文时也会回退公开详情。解析严格限定在目标 `seo_track.track_player`，不会误取推荐歌曲。

`check.py` 返回 `valid_sessionid_only` 表示辅助 Cookie 已不可用、但服务端仍认可核心会话；这时不需要重新扫码。只有核心 `sessionid` 也被只读账号接口拒绝时才返回 `expired`。

脚本不接受额外的客户端请求配置。PC 接口不可用时直接回退公开详情；公开详情中标记 `only_vip_playable` 或音质要求会员/购买时不会返回该地址，试听和推荐歌曲也不会冒充目标歌曲的完整流。

## 解密

`--decrypt` 使用本文件里的标准库 AES-CTR。脚本会先写临时文件再原子替换。实际结果为 FLAC 时自动把输出后缀改为 `.flac`，JSON 的 `decryptedFile` 是最终路径。

cookie 不要写入命令、日志、JSON 或文档。播放地址短期有效，不要长期缓存。
