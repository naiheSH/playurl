# 凭据

凭据只放在本机，不写入命令、日志、测试、JSON、文档或 Git 提交。`login.py` 用原子替换写文件，并把权限设为 `600`。

## 有效性检查

```text
python3 netease/check.py
python3 qq/check.py
python3 kugou/check.py
python3 qishui/check.py
python3 spotify/check.py
python3 youtube/check.py
```

六个检查脚本完全独立，只读取自身目录的凭据，不调用根目录或其他平台脚本。网易云、QQ、酷狗和汽水会访问各自的只读账号接口，不能只根据字段存在就判定登录有效。Spotify 检查用户 access token 或 Client Credentials；YouTube 有 `cookies.txt` 时检查网页登录状态，有 PO Token 时用测试视频验证解析。所有输出都会过滤凭据值。

统一退出码：`0` 表示有效或该平台公开功能无需凭据，`1` 表示缺失、格式错误或已过期，`2` 表示网络/平台异常导致无法确认。JSON 的 `status` 会进一步区分 `valid`、`valid_sessionid_only`、`missing`、`invalid`、`expired`、`unknown` 和 `not_configured`。

## 存放位置

| 平台 | 文件 | 读取顺序 |
| --- | --- | --- |
| 网易云 | `netease/cookie` | `NETEASE_MUSIC_U`、`MUSIC_U`、文件中的 `MUSIC_U=` 或单独一行原始值 |
| QQ | `qq/cookie` | 只读同目录文件 |
| 酷狗 | `kugou/cookie` | 只读同目录文件 |
| 汽水 | `qishui/cookie` | 只读同目录文件 |
| Spotify | `spotify/credentials` | 环境变量优先，其次同目录 JSON |
| YouTube | `youtube/cookies.txt`、`youtube/token` | 文件存在才传给 `yt-dlp` |
| 汽水设备身份 | `qishui/.qishui-state/` | 纯 HTTP 登录自动读写，不是播放 cookie |

根 `.gitignore` 已忽略 `cookie`、`token`、`credentials`、`credentials.json`、`client_secret*.json`、`cookies.txt`、`.qishui-state/` 和 `login-qr.png`。

## 必需字段

| 平台 | 必须能看到的字段 | 用途 |
| --- | --- | --- |
| 网易云 | `MUSIC_U` | `mine` 和会员播放 |
| QQ | `uin` 加 `qm_keyst`、`qqmusic_key`、`music_key` 之一 | QQ 登录播放和自建歌单 |
| QQ 微信登录 | `wxuin` 加 `wxskey` | 同上 |
| 酷狗 | `userid` 和 `token`，建议同时有 `kg_mid`、`kg_dfid` | `mine`、云歌单和会员播放 |
| 汽水 | 核心为 `sessionid`；也兼容从 `sessionid_ss` 或 `sid_tt` 恢复核心值 | 个人歌单和登录播放 |
| Spotify 元数据 | `client_id`、`client_secret` | 搜索和公开歌单元数据 |
| Spotify 用户数据 | `access_token` | `mine` 和歌单曲目 |
| YouTube | 通常不需要 | 受限视频才使用 Netscape cookie 或 PO token |

酷狗登录成功后会注册设备并补写 `kg_dfid`。已有 `userid` 和 `token` 但缺少 `dfid` 时，播放脚本也会补注册并回写 cookie。

Spotify `credentials` 是 JSON 对象，可含 `client_id`、`client_secret`、`access_token`、`market`。对应环境变量是 `SPOTIFY_CLIENT_ID`、`SPOTIFY_CLIENT_SECRET`、`SPOTIFY_ACCESS_TOKEN`、`SPOTIFY_MARKET`。它不是网页 cookie。

## 哪些操作不读凭据

- 六个平台的歌曲搜索。
- 网易云、QQ、酷狗、汽水和 YouTube 的公开歌单搜索。
- 网易云公开歌单列歌、QQ 公开歌单列歌、酷狗 `specialid` 列歌。
- 汽水非会员可完整播放的公开曲目。
- Spotify `playurl.py`。它不访问网络。
- YouTube 的普通公开视频和歌单。

`mine`、虚拟歌单、酷狗云歌单和会员曲播放才读取凭据。公开接口失败后，汽水歌单脚本只在本地 cookie 已具备登录字段时才重试。

汽水先使用完整 Cookie；如果辅助字段导致请求失败，会自动退回仅携带核心 `sessionid`。`sid_guard` 中的日期不是硬性失效依据，是否过期以只读账号接口能否识别 `sessionid` 为准。

## 登录入口

国内四个平台各自运行同目录 `login.py`，不共享浏览器会话：

```text
python3 netease/login.py
python3 qq/login.py
python3 kugou/login.py
python3 qishui/login.py
```

网易云、QQ、酷狗提供随机的 `127.0.0.1` 二维码页；安装各目录可选的 `requirements-terminal.txt` 后还会在终端显示二维码。缺少终端组件不会中断登录，`--no-open` 只关闭自动打开浏览器。汽水默认不打开浏览器，也不需要安装依赖；`python3 qishui/login.py` 或 `node qishui/login.cjs` 都会把官方二维码存成 `login-qr.png`，用汽水 App 扫码。手机确认后仍可能要求短信验证码，验证码只在当次终端输入，不写入文件。只有纯 HTTP 失效时才用 `qishui/login.py --browser`。

所有 Python 脚本要求 Python 3.10+。Windows 可使用 `py -3.10` 或激活虚拟环境后的 `python`；macOS/Linux 可使用 `python3`。凭据通过同目录临时文件原子替换写入；`0600` 权限只在 macOS/Linux 具有完整语义，Windows 应依赖当前用户目录的 ACL。

网易云、QQ、酷狗首次扫码登录前安装该目录自己的 `requirements.txt`。汽水基础登录、播放、搜索和歌单只使用 Python 标准库；YouTube 需要 `yt-dlp`。
