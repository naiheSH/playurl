# playurl v2.0.0

这是项目从首次导入到 v2.0.0 的累计更新日志。此前没有单独维护 Changelog，因此本说明同时记录基础能力、v1.0.0 发布体系以及 v2.0.0 新增的 Runtime 与 Skill Studio 支持。

## 项目能力

- 六个平台保持独立目录：网易云音乐、QQ 音乐、酷狗音乐、汽水音乐、Spotify、YouTube。
- 各平台的搜索、歌单、播放和凭据检查脚本互不导入，可单独复制和部署。
- 国内四个平台支持歌曲搜索、公开歌单搜索、歌单曲目、个人歌单以及播放结果解析。
- Spotify 使用官方 Web API 提供搜索、歌单和官方播放器信息；官方接口不提供通用音频直链。
- YouTube 使用 `yt-dlp` 搜索视频和播放列表，并解析短期音频地址。
- 搜索与歌单输出格式化 JSON；传统 `playurl.py` 成功时仍可只输出一行 URL，`--json` 返回完整结构。

## 登录与凭据

- 网易云音乐支持网易云音乐 App 扫码登录。
- QQ 音乐支持 QQ 音乐 App 扫码，不要求打开 QQ 或微信客户端。
- 酷狗音乐支持酷狗 App 扫码登录。
- 汽水音乐提供纯 HTTP Python 登录，默认不打开浏览器；同时保留 Node.js 单文件实现和浏览器兜底。
- 登录二维码可选在终端绘制；未安装终端二维码依赖时可使用 PNG 或随机 `127.0.0.1` 页面。
- 四个国内平台分别保存自己的 Cookie，并提供独立 `check.py` 实际检查凭据状态。
- Cookie 文件采用原子替换；macOS/Linux 尽量设置为 `600` 权限。
- 汽水支持会话核心字段回退、短信验证码二次输入和已有 Cookie 复用。
- Spotify 使用 OAuth client credentials 或用户 access token；YouTube 可选 Netscape Cookie 与 PO Token。

## 搜索与歌单

- 搜索支持“歌名”“歌名 歌手”“歌手 歌名”，并在本地进行匹配排序。
- 每个平台分别支持公开歌单搜索和按 offset 读取歌单曲目。
- 网易云完整读取 `trackIds` 后分批获取曲目详情。
- QQ 音乐支持公开 `disstid` 和“我的喜欢”虚拟歌单。
- 酷狗支持公开 `specialid` 与登录后的 `collection_` 云歌单。
- 汽水支持“我的喜欢”“最近播放”、账号歌单和公开歌单。
- Spotify 个人歌单及曲目读取遵循官方 OAuth 权限边界。
- 歌单只返回曲目集合，不伪造所谓“歌单播放 URL”。

## 播放与音质

- 网易云、QQ 音乐、酷狗、汽水和 YouTube 可返回实际短期播放地址；Spotify 返回官方播放方式。
- 默认只选择 M4A 或 MP3，并优先高音质；高音质不可用时按平台能力自动降级。
- FLAC 默认关闭，可在各平台自己的 `playurl.py` 中独立启用。
- 播放 JSON 统一提供平台、歌曲 ID、请求音质、实际音质、试听状态、可播放状态和限制原因等字段。
- 网易云与 QQ 音乐保留地址有效期；汽水与 YouTube 返回播放器需要携带的请求头。
- 汽水支持 AES-CTR 加密流识别与本地解密，不把会员流、试听流或推荐歌曲冒充目标歌曲完整音频。
- 播放 URL 视为短期签名地址；401/403、开始新播放或接近过期时应使用歌曲 ID 重新解析。

## Runtime 与接口统一

- 每个平台新增独立 `runtime.py`，作为 Agent Runtime / Code 工具入口。
- Runtime 从 stdin 接收一个 JSON 对象，stdout 只输出一个格式化 JSON 对象。
- 统一支持 `search`、`playlist_search`、`playlist_tracks`、`playlist_mine`、`playurl`、`check`；平台不支持的能力不会伪造。
- 输入错误返回 `invalid_input` 和退出码 `2`；执行异常返回 `execution_failed` 和退出码 `1`；完成调用返回退出码 `0`。
- 传统 argv CLI、登录脚本和 URL 单行输出保持兼容，不因 Runtime 适配而改变。
- 修复 Windows 子进程 JSON 编码，统一按 UTF-8 处理。

## Skill Studio 2.0

- 新增网易云音乐、QQ 音乐、酷狗音乐、汽水音乐四个可独立导入的 Skill Studio 包。
- 每个包使用单一 `scripts/runtime.py` 映射多项业务能力，并包含 Skill Studio contract、implementation 和运行元数据。
- 使用 Agent Runtime 注入的 KV 保存凭据，各平台使用独立 key，数据按当前 Agent 隔离。
- Skill Studio 包不包含扫码登录、设备注册、本地 Cookie、Token、credentials 或浏览器授权脚本。
- 酷狗 Skill Studio 模式不执行本地设备注册；已有设备字段仍可随 Cookie 使用。
- ZIP 构建前检查 Runtime、contract、能力映射和禁止文件，避免把本地凭据打入 Release。
- 构建版本从 Git Tag 自动解析：`skill-studio-vX.Y.Z` 生成 `X.Y.Z` 包，并追加到 main 的 `vX.Y.Z` Release。

## 跨平台与质量保障

- 核心脚本支持 Python 3.10 及以上版本。
- Windows 10/11、现代 Linux 和 macOS 使用相同的搜索、歌单、播放与检查入口。
- GitHub Actions 在 Ubuntu、Windows、macOS 上测试 Python 3.10 和 3.14。
- 自动测试覆盖音质降级、公开与个人歌单、Cookie 检查、汽水登录与解密、Spotify 官方边界、YouTube 格式选择、Runtime JSON 协议和 Skill Studio ZIP 结构。
- 汽水 Node.js 登录实现使用 Node.js 18+，并在 CI 中执行语法与自检。

## 发布方式

- main Tag 使用 `vX.Y.Z`，构建传统国内平台包。
- Skill Studio Tag 使用 `skill-studio-vX.Y.Z`，构建四个国内 Skill Studio 包。
- 两次构建将资产上传到同一个 `vX.Y.Z` GitHub Release，Release 标题统一为 `playurl vX.Y.Z`。
- v2.0.0 Release 共包含以下八个资产。

### main 资产

- `netease-2.0.0.zip`
- `qq-2.0.0.zip`
- `kugou-2.0.0.zip`
- `qishui-2.0.0.zip`

### Skill Studio 资产

- `skill-studio-netease-2.0.0.zip`
- `skill-studio-qq-2.0.0.zip`
- `skill-studio-kugou-2.0.0.zip`
- `skill-studio-qishui-2.0.0.zip`

## 明确边界

- 不把 Spotify 网页、URI 或 Embed 地址描述为音频直链。
- 不把试听、会员限制、版权限制或空响应伪装成完整播放地址。
- 不在平台脚本之间互相导入，也不要求部署参考项目作为常驻服务。
- 不在 Release 包中包含用户 Cookie、Token 或其他本机凭据。
