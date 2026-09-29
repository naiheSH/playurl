# doc

这里放跨平台的对照说明。根 `README.md` 仍是使用入口，各平台目录的 `README.md` 仍是该目录的命令说明，`SKILL.md` 仍只给代理流程使用。

| 文件 | 内容 |
| --- | --- |
| [api.md](api.md) | 每个脚本实际请求的上游地址、方法和登录条件 |
| [output.md](output.md) | 搜索、歌单和播放 JSON 的稳定字段 |
| [credentials.md](credentials.md) | 凭据放在哪里、哪些字段必须存在、哪些文件不能提交 |
| [playback.md](playback.md) | 各平台音质字段、降级、播放失败类别、重试和缓存边界 |
| [runtime.md](runtime.md) | Agent Runtime 的 JSON stdin/stdout 协议、actions、退出码和示例 |
| [skill-studio.md](skill-studio.md) | Skill Studio 分支、KV 注入、适配层维护、构建发布和正式验收边界 |

不另建文件的内容：

- 平台命令参数：留在各平台 `README.md`，避免两处同时改。
- 代理操作步骤：留在各平台 `SKILL.md`。
- 签名、加密和登录算法：留在对应脚本里，文档只记录外部可见的请求和结果。
- 许可证和参考项目：留在根 `README.md` 的鸣谢部分。
