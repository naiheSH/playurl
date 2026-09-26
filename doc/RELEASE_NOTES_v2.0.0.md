# playurl v2.0.0

v2.0.0 将 main 的传统独立包与 `skill-studio` 分支的国内平台 Skill Studio 包统一展示在同一个 GitHub Release 中。两套代码继续独立维护，发布资产不会互相覆盖。

## Skill Studio 新增

- 新增网易云音乐、QQ 音乐、酷狗音乐、汽水音乐四个独立 Skill Studio 包。
- 每个平台均可单独导入、拆分和复用，不依赖其他平台目录。
- Code 入口统一改为 JSON stdin/stdout：stdin 接收一个 JSON 对象，stdout 只输出一个 JSON 对象，成功退出码为 `0`。
- 搜索歌曲、搜索歌单、歌单曲目、个人歌单、播放地址和 Cookie 检查分别映射为明确能力。
- 使用 Agent Runtime 注入的 KV 保存账号凭据，各平台使用独立 key，数据按当前 Agent 隔离。
- Skill Studio 包不包含扫码登录、设备注册、本地 Cookie、Token、credentials 或浏览器授权脚本。

## 播放与歌单改进

- 完善四个平台的公开歌曲搜索、歌单搜索、歌单曲目和个人歌单输出。
- 默认优先 M4A 或高音质 MP3；高音质不可用时按平台能力降级。
- FLAC 默认不参与选择，仍可在原脚本配置中启用。
- 播放结果明确返回实际音质、试听状态、可播放状态、限制原因和播放器所需请求头。
- 短期播放 URL 过期后，可使用同一歌曲 ID 重新解析，不长期缓存旧地址。

## 凭据与安全

- 网易云使用 `netease-cookie`，QQ 音乐使用 `qqmusic-cookie`，酷狗使用 `kugou-cookie`，汽水音乐使用 `qishui-cookie`。
- Runtime 在调用期间注入凭据，不把 Cookie 写入 Skill ZIP，也不在正常错误信息中回显凭据。
- 保留各平台独立的 Cookie 有效性检查能力。
- 酷狗 Skill Studio 模式不执行本地设备注册；已有设备字段继续随 Cookie 使用。

## 兼容性与测试

- main 原有 argv 命令行工具和登录脚本不受 Skill Studio 包影响。
- 保持 Windows、Linux、macOS 的原脚本兼容性。
- 新增 Skill Studio 包结构、JSON 协议、能力路由、凭据注入、敏感信息防泄露和 ZIP 内容测试。
- GitHub Actions 会分别生成四个 Skill Studio ZIP，并上传到 main 共用的 `v2.0.0` Release。

## Skill Studio Release 资产

- `playurl-netease-skill-studio-2.0.0.zip`
- `playurl-qq-skill-studio-2.0.0.zip`
- `playurl-kugou-skill-studio-2.0.0.zip`
- `playurl-qishui-skill-studio-2.0.0.zip`
