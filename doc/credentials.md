# 凭据

凭据只放在本机，不写入命令、日志、测试、JSON、文档或 Git 提交。检查登录时只报告字段是否存在，不打印值。`login.py` 用原子替换写文件，并把权限设为 `600`。

## 存放位置

| 平台 | 文件 | 读取顺序 |
| --- | --- | --- |
| 网易云 | `netease/cookie` | `NETEASE_MUSIC_U`、`MUSIC_U`、文件中的 `MUSIC_U=` 或单独一行原始值 |
| QQ | `qq/cookie` | 只读同目录文件 |
| 酷狗 | `kugou/cookie` | 只读同目录文件 |
| 汽水 | `qishui/cookie` | 只读同目录文件 |
| Spotify | `spotify/credentials` | 环境变量优先，其次同目录 JSON |
| YouTube | `youtube/cookies.txt`、`youtube/token` | 文件存在才传给 `yt-dlp` |

根 `.gitignore` 已忽略 `cookie`、`token`、`credentials`、`credentials.json`、`client_secret*.json` 和 `cookies.txt`。

## 必需字段

| 平台 | 必须能看到的字段 | 用途 |
| --- | --- | --- |
| 网易云 | `MUSIC_U` | `mine` 和会员播放 |
| QQ | `uin` 加 `qm_keyst`、`qqmusic_key`、`music_key` 之一 | QQ 登录播放和自建歌单 |
| QQ 微信登录 | `wxuin` 加 `wxskey` | 同上 |
| 酷狗 | `userid` 和 `token`，建议同时有 `kg_mid`、`kg_dfid` | `mine`、云歌单和会员播放 |
| 汽水 | `sessionid`、`sessionid_ss`、`sid_guard`、`sid_tt`、`uid_tt`、`uid_tt_ss` 之一 | 个人歌单和会员播放 |
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

## 登录入口

国内四个平台各自运行同目录 `login.py`，不共享浏览器会话：

```text
python3 netease/login.py
python3 qq/login.py
python3 kugou/login.py
python3 qishui/login.py
```

网易云、QQ、酷狗在终端显示二维码，并提供随机的 `127.0.0.1` 备用页。`--no-open` 不打开浏览器。汽水默认打开独立的可见 Chrome/Edge；`--direct-qr` 只作为实验性诊断，不作为常规登录方式。

首次扫码登录前安装该目录自己的 `requirements.txt`。播放、搜索和歌单除 YouTube 外不需要这些可选依赖。
