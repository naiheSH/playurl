# 接口对照

本文只记录当前脚本实际发出的上游请求。它不是官方 API 文档，也不包含签名、加密或登录凭据的实现。各平台目录互不导入，同一类功能在不同目录里是独立实现。

成功时搜索和歌单输出 JSON。播放成功时默认只输出一行 URL；失败、加 `--json`，或汽水返回需要解密的流时输出 JSON。播放地址是短期签名 URL，不要长期缓存。

## 总表

| 平台 | 脚本 | 方法 | 上游 | 登录 |
| --- | --- | --- | --- | --- |
| 网易云 | `search.py` | POST | `https://music.163.com/api/search/get/web` | 否 |
| 网易云 | `playlist.py search` | POST | 同上，`type=1000` | 否 |
| 网易云 | `playlist.py tracks` | POST | `https://music.163.com/api/v6/playlist/detail`，再请求 `https://music.163.com/api/v3/song/detail` | 否 |
| 网易云 | `playlist.py mine` | POST | `https://music.163.com/weapi/w/nuser/account/get`，再请求 `https://music.163.com/weapi/user/playlist` | 是 |
| 网易云 | `playurl.py` | POST | `https://interface.music.163.com/eapi/song/enhance/player/url/v1`，失败后回退 `https://interface.music.163.com/api/song/enhance/player/url` | 会员曲需要 |
| 网易云 | `login.py` | POST | `https://music.163.com/weapi/login/qrcode/unikey`，轮询 `https://music.163.com/weapi/login/qrcode/client/login` | 扫码 |
| QQ | `search.py` | GET | `https://c.y.qq.com/splcloud/fcgi-bin/smartbox_new.fcg` | 否 |
| QQ | `playlist.py search` | GET | `https://c.y.qq.com/soso/fcgi-bin/client_music_search_songlist` | 否 |
| QQ | `playlist.py tracks` | GET | `https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg` | 公开歌单否 |
| QQ | `playlist.py tracks liked` | POST | `https://u.y.qq.com/cgi-bin/musicu.fcg` | 是 |
| QQ | `playlist.py mine` | GET | `https://c.y.qq.com/rsc/fcgi-bin/fcg_user_created_diss` 和 `https://c.y.qq.com/fav/fcgi-bin/fcg_get_profile_order_asset.fcg` | 是 |
| QQ | `playurl.py` | POST | `https://u.y.qq.com/cgi-bin/musicu.fcg` | 会员曲需要 |
| QQ | `login.py` | 库调用 | `qqmusic_api` 的 QQ 音乐 App 扫码会话 | 扫码 |
| 酷狗 | `search.py` | GET | `https://songsearch.kugou.com/song_search_v2` | 否 |
| 酷狗 | `playlist.py search` | GET | `http://mobilecdn.kugou.com/api/v3/search/special` | 否 |
| 酷狗 | `playlist.py tracks` | GET | `http://mobilecdn.kugou.com/api/v3/special/song` | 公开歌单否 |
| 酷狗 | `playlist.py mine` | POST | `https://gateway.kugou.com/v7/get_all_list` | 是 |
| 酷狗 | `playlist.py tracks collection_*` | POST | `https://gateway.kugou.com/v4/get_list_all_file` | 是 |
| 酷狗 | `playurl.py` | GET/POST | 见下文的播放回退链 | 会员曲需要 |
| 酷狗 | `login.py` | GET | `https://login-user.kugou.com/v2/qrcode`，轮询 `/v2/get_userinfo_qrcode` | 扫码 |
| 酷狗 | `device.py` | POST | `https://userservice.kugou.com/risk/v2/r_register_dev` | 是 |
| 汽水 | `search.py` | GET | `https://api-vehicle.volcengine.com/v2/search/type` | 否 |
| 汽水 | `playlist.py search` | GET | `https://api.qishui.com/luna/pc/search/playlist` | 否 |
| 汽水 | `playlist.py tracks` | GET | `https://api.qishui.com/luna/pc/playlist/detail` | 私有歌单需要 |
| 汽水 | `playlist.py mine` | GET | `/luna/pc/me`，再请求 `/luna/pc/user/playlist` | 是 |
| 汽水 | `playurl.py` | GET/POST | `/luna/pc/track_v2`，空正文回退 `https://beta-luna.douyin.com/luna/h5/seo_track` | 会员曲需要 |
| 汽水 | `login.py` / `auth.py` | GET/POST | 默认 `https://api.qishui.com/passport/web/get_qrcode/`，轮询 `/passport/web/check_qrconnect/`；需要时再调用 `/passport/web/send_code/` 和 `/passport/web/validate_code/`。`--browser` 才打开 `https://music.douyin.com/` | 扫码 |
| Spotify | `search.py` | GET | `https://api.spotify.com/v1/search?type=track` | Client Credentials |
| Spotify | `playlist.py search` | GET | `https://api.spotify.com/v1/search?type=playlist` | Client Credentials |
| Spotify | `playlist.py tracks` | GET | `https://api.spotify.com/v1/playlists/{id}/items` | 用户 token |
| Spotify | `playlist.py mine` | GET | `https://api.spotify.com/v1/me/playlists` | 用户 token |
| Spotify | `playurl.py` | 无 | 不请求上游，只返回官方播放器入口 | 否 |
| YouTube | `search.py` | yt-dlp | `ytsearchN:<关键词>` | 通常否 |
| YouTube | `playlist.py search` | yt-dlp | `https://www.youtube.com/results?search_query=...&sp=EgIQAw%3D%3D` | 通常否 |
| YouTube | `playlist.py tracks` | yt-dlp | `https://www.youtube.com/playlist?list=<id>` | 通常否 |
| YouTube | `playurl.py` | yt-dlp | `https://www.youtube.com/watch?v=<id>` | 受限内容可选 |

## 网易云

歌曲搜索是未签名 POST。`type=1`，先取一页最多 30 条再本地排序，`offset` 只在这页里切片。歌曲 ID 是数字。

歌单搜索使用同一地址，`type=1000`，`offset` 直接传给上游。列歌先用 `n=0` 取完整 `trackIds`，再按 100 首一批请求歌曲详情。`mine` 先用 weapi 取当前账号，再取该账号歌单；它不使用未签名的普通 POST。

播放先走 eapi `player/url/v1`。没有 URL 时回退到 `player/url`，并按 `standard=128000`、`exhigh=320000`、`lossless` 的码率参数请求。默认从 `exhigh` 向 `standard` 降级；`ENABLE_FLAC=True` 时从 `lossless` 开始。返回字段里的 `expi` 是秒。

扫码登录先申请 `unikey`，二维码内容是 `https://music.163.com/login?codekey=<unikey>`。轮询码 `801` 等待、`802` 已扫码、`803` 成功、`800` 过期。成功后只保存 `MUSIC_U`。

## QQ 音乐

歌曲搜索走 smartbox，最多约 10 条，不支持 `offset`。歌曲 ID 是 `songmid`，可选 `media_mid`。

歌单搜索按每页 30 条翻页，再用 `offset` 在页内切片。公开歌单 ID 是 `disstid`；列歌参数是 `song_begin` 和 `song_num`，单次最多 200 首。`liked` 不是公开 ID，而是 dirid `201` 的「我的喜欢」，通过 `musicu.fcg` 的 `music.srfDissInfo.DissInfo/CgiGetDiss` 读取。

`mine` 同时取自建歌单和收藏歌单。自建接口带当前 `uin`；收藏接口使用 `cid=205360956`、`reqtype=3`。

播放固定 POST 到 `musicu.fcg`。先用 `music.pf_song_detail_svr/get_song_detail_yqq` 补 `media_mid`，再用 `vkey.GetVkeyServer/CgiGetVkey` 换 `purl`，拼到返回的 `sip` 上。候选文件名按 `M800`、`M500`、`C400` 降级；开启 FLAC 后才加入 `RS01` 和 `F000`。脚本会用 `Range: bytes=0-1` 探测候选地址，只有 200 或 206 才返回。

登录不直接写 QQ 网页接口。`qqmusic_api` 创建手机客户端二维码会话，成功后把 `musicid` 和 `musickey` 写成 `uin`、`qm_keyst`、`qqmusic_key`、`music_key`。

## 酷狗

歌曲搜索使用 `song_search_v2`，`appid=1014`，只取第一页最多 20 条。歌曲 ID 是 `FileHash`，同时保留 `AlbumID` 和 `MixSongID`，后两者作为 `album_id`、`album_audio_id` 传给播放脚本。

公开歌单搜索和列歌走 mobilecdn 的 `special`、`special/song`。公开歌单 ID 是 `specialid`。`collection_` 开头的是云歌单，只能登录后列歌。

登录后的歌单走 gateway，并设置 `x-router: cloudlist.service.kugou.com`。歌单列表是 `/v7/get_all_list`；云歌单曲目是 `/v4/get_list_all_file`。

播放按下面顺序尝试，拿到 URL 就停止：

1. POST `http://tracker.kugou.com/v6/priv_url`
2. GET `https://gateway.kugou.com/v5/url`，`x-router: trackercdn.kugou.com`，先后用 H5 和 Android 参数
3. GET `https://wwwapi.kugou.com/play/songinfo`
4. GET `https://wwwapiretry.kugou.com/play/songinfo`
5. 只在 `standard` 档再 GET `https://m.kugou.com/app/i/getSongInfo.php`

默认音质是 `exhigh`，不可用时降到 `standard`。`ENABLE_FLAC=True` 才把 `flac` 放进候选。`tracker_type=part` 会标成试听。

扫码登录先请求 `/v2/qrcode`，二维码指向酷狗 H5 登录页。轮询 `/v2/get_userinfo_qrcode`：`1` 等待，`2` 已扫码，`4` 成功，`0` 过期。成功后调用设备注册接口换 `dfid`，再保存 `userid`、`token`、`kg_mid`、`kg_dfid`。播放时如果已登录但没有 `dfid`，也会调用同一注册接口补写 cookie。

## 汽水

歌曲搜索走车机公开搜索，`search_type=music`、`search_source=qishui`，最多取 30 条候选，`offset` 只在这批结果里切片。歌曲 ID 是 `item_id`。

歌单搜索走 PC 协议 `/luna/pc/search/playlist`，可用返回的 `next_cursor` 继续翻页。公开歌单曲目走 `/luna/pc/playlist/detail`；接口失败且本地已登录时，才带 cookie 重试。`mine` 先读 `/luna/pc/me` 取用户 ID，再读 `/luna/pc/user/playlist`。`liked` 和 `recent` 是虚拟 ID，分别对应喜欢歌单或 `/luna/pc/me/collection/mixed`、`/luna/pc/me/recently-played-media`。

播放先 POST `/luna/pc/track_v2`，失败再 GET 同一路径。空正文或未登录时回退到公开详情 `seo_track`。公开详情必须校验 `seo_track.track.id` 与请求的曲目一致。会员曲、试听和推荐流不会冒充目标歌曲的完整流。默认只选择非加密的 M4A/MP3，并按码率从高到低；`ENABLE_FLAC=True` 才纳入 FLAC 和带 `play_auth` 的流。

请求汽水 CDN 时必须带播放结果里的 `httpHeaders`。URL 带 `#auth=` 时，`playurl.py <id> --decrypt <文件>` 会下载并解密，输出 JSON 和解密后的路径。

默认登录不打开浏览器。`auth.py` 先 GET `/passport/web/get_qrcode/`，二维码使用返回的 `qrcode_index_url`，再 POST `/passport/web/check_qrconnect/`。手机确认后若要求短信二次验证，再调用 `/passport/web/send_code/` 和 `/passport/web/validate_code/`。登录是否完成只看 cookie 里有没有 `sessionid` 一类字段。`--browser` 才打开 `https://music.douyin.com/`，从同一浏览器会话收集 cookie，只作为纯 HTTP 失效后的兜底。设备身份写在已忽略的 `.qishui-state/`，不要并行刷新多个二维码。

## Spotify

搜索和歌单元数据先用 Client Credentials 向 `https://accounts.spotify.com/api/token` 换 token，授权值是 `grant_type=client_credentials`。配置来自 `SPOTIFY_CLIENT_ID`、`SPOTIFY_CLIENT_SECRET`、`SPOTIFY_MARKET`，或同目录已忽略的 `credentials` JSON。

歌曲搜索是 `/v1/search?type=track`，歌单搜索是 `type=playlist`，每次最多 10 条。`mine` 调用 `/v1/me/playlists`，列歌调用 `/v1/playlists/{id}/items`；这两项必须使用用户 access token，Client Credentials 不够。

`playurl.py` 不访问网络。它校验 22 位 track id 后返回 `playable: false`，以及 `spotifyUri`、`spotifyUrl`、`embedUrl`。这些不是音频直链。

## YouTube

三个脚本都调用本机 `yt-dlp`，没有自己拼接 YouTube InnerTube 请求。公开内容通常不需要凭据。存在 `cookies.txt` 时传给 `--cookies`；存在 `token` 时作为 `po_token` 传给 `--extractor-args`。

歌曲搜索使用 `ytsearchN:` 和 `--flat-playlist`。歌单搜索打开带 `sp=EgIQAw==` 的 YouTube 结果页，这个参数表示只搜索播放列表。列歌使用 playlist URL，并用 `--playlist-start`、`--playlist-end` 控制区间。

播放使用 watch URL。默认格式选择器是 `bestaudio[ext=m4a]/bestaudio[ext=mp3]`；`standard` 额外限制 `abr<=160`。`ENABLE_FLAC=True` 才把 FLAC 放在最前。返回的是短期音频 URL，JSON 模式保留请求头和有效期。
