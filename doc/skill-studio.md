# Skill Studio 接入与维护

本文只描述 `skill-studio` 分支的适配层。传统 argv CLI、扫码登录和平台接口细节分别见根 `README.md`、平台 `README.md` 及本目录其他文档。

## 分支与发布边界

| 项目 | `main` | `skill-studio` |
| --- | --- | --- |
| 使用者 | 本地脚本、CLI、普通进程调用 | Skill Studio / Agent Runtime |
| 入口 | 各业务脚本及同目录 `runtime.py` | 包内 `scripts/runtime.py` |
| 凭据 | 环境变量或平台目录的本地文件 | Agent Runtime 注入的 KV，再写入 Code 请求 |
| 登录 | 平台独立登录脚本 | 不打包、不在单次 Code 调用中登录 |
| 发布 Tag | `vX.Y.Z` | `skill-studio-vX.Y.Z` |
| Release | GitHub `vX.Y.Z` | 追加资产到同一个 GitHub `vX.Y.Z` Release |

正式 Skill Studio 资产只有网易云音乐、QQ 音乐、酷狗音乐和汽水音乐四个 ZIP。Spotify、YouTube 即使存在开发目录或生成规格，也不属于当前 Skill Studio Release。

## 运行模型

每个平台的多个能力共用一个 Code 入口。Skill Studio 先根据 `SKILL.md` 决定 action 和是否需要凭据，再调用 `scripts/runtime.py`：

```text
用户需求
  -> 平台 SKILL.md 选择 action
  -> 必要时从 Agent KV 读取 Cookie
  -> stdin 写入一个 JSON 对象
  -> scripts/runtime.py 调用同包业务模块
  -> stdout 返回一个 JSON envelope
```

Code 入口不会自行调用 KV 工具，也不会接收 Agent ID。KV 工具由 Agent Runtime 注入，Agent 负责读取值并放入请求的 `cookie` 字段。业务脚本只看到本次调用中的字符串，不能依赖 Skill Studio 宿主的内部存储实现。

成功 envelope：

```json
{
  "ok": true,
  "data": {
    "provider": "kugou",
    "playable": true,
    "url": "https://..."
  }
}
```

失败 envelope：

```json
{
  "ok": false,
  "error": {
    "code": "invalid_input",
    "message": "missing id"
  }
}
```

- 完成调用返回退出码 `0`，但仍需检查 `data.playable`、`data.trial`、`data.restriction`、`data.status` 和结果数组。
- 输入错误返回退出码 `2`、错误码 `invalid_input`。
- 加载、网络或上游异常返回退出码 `1`、错误码 `execution_failed`。
- stdout 不得混入提示文字、二维码、日志或 traceback；敏感值不得进入输出和错误信息。

各 action 的输入字段见 [`runtime.md`](runtime.md)；平台特殊字段与业务选择规则以对应 `skillstudio/<provider>/SKILL.md` 为准。

## KV 与凭据

KV 数据按当前 Agent 隔离，不能通过普通 MCP 补传或推测 Agent ID。

| 工具 | 用途 | 使用条件 |
| --- | --- | --- |
| `gf-service-kv-get` | 读取当前平台 Cookie | 个人歌单、凭据检查或需要登录态的播放之前 |
| `gf-service-kv-set` | 保存或覆盖 Cookie | 用户明确提供或更新凭据时 |
| `gf-service-kv-query` | 分页检查当前 Agent 的 key | 仅做凭据盘点；不是播放前置步骤 |
| `gf-service-kv-delete` | 删除指定 key | 仅在用户明确要求清除凭据时 |

当前包的依赖元数据把 `get`、`set` 声明为业务硬依赖；`query`、`delete` 是 Agent Runtime 提供的管理能力，在平台 `SKILL.md` 中按需使用。不要因为一次网络失败或上游限流自动删除 Cookie，也不要反复保存同一个无效值。

标准流程：

1. 公开搜索、公开歌单和通常可匿名解析的免费歌曲不读取 KV。
2. 个人能力先按平台 key 调用 `get`。
3. 读取成功后，把完整值写入 Code 请求的 `cookie` 字段，不回显。
4. 用户提供新值时，先 `set`，再调用 `check`。
5. `check` 的无效结果只说明凭据不可用；网络异常表示无法确认，不能据此删除。

Skill Studio 包不负责获取 Cookie。扫码、短信验证码、浏览器登录和平台 App 授权仍在包外完成，再由用户或接入系统把结果写入对应 KV。包中禁止包含 `login.py`、`auth.py`、`device.py`、`cookie`、`token`、`credentials`、`cookies.txt` 或 `request.json` 等登录与凭据文件。

酷狗包不会执行本地设备注册。已有 Cookie 中的 `kg_mid`、`kg_dfid` 等字段可以继续使用，但 Skill Studio Code 不创建或持久化本机设备身份。

## 构建与同步

`skillstudio/build_platforms.py` 执行两类工作：

1. 根据平台规格重新生成 `.skill-studio/`、`implementation.json`、`skill-metadata.json` 和 `agents/openai.yaml`。
2. 从仓库根部对应平台目录复制 `search.py`、`playlist.py`、`playurl.py`、`check.py`，连同适配入口写入 ZIP。

因此，根部平台脚本是业务实现来源，`skillstudio/<provider>/scripts/runtime.py` 是宿主适配来源。维护时遵循：

1. 业务接口、解析、分页或音质问题先修改根部平台脚本，并运行普通测试。
2. JSON 协议、凭据注入或 action 路由问题修改 Skill Studio runtime 和相应测试。
3. Agent 决策、KV key 或能力边界变化修改对应 `SKILL.md`。
4. 能力 ID、schema、依赖或版本变化修改生成器，不手改最终 ZIP。
5. 重新构建四个正式包，检查生成器产生的元数据 diff 和 ZIP 内容。

构建示例：

```text
python3 skillstudio/build_platforms.py kugou --version 2.0.0 --output-dir dist
```

期望文件名为 `dist/skill-studio-kugou-2.0.0.zip`。ZIP 时间戳、排序和权限由生成器固定；在相同构建环境中，相同提交、平台和版本应生成相同字节。构建后至少确认：

- 存在 `SKILL.md`、`scripts/runtime.py`、四个业务模块、`.skill-studio/contract.json` 和 `implementation.json`。
- contract 中的 capability 与 `implementation.json` 映射一致。
- 包内不存在登录、设备注册、凭据或本地请求快照文件。
- `manifest.json` 与 `skill-metadata.json` 的版本等于构建版本。

## CI 与版本

`.github/workflows/build.yml` 有三种触发结果：

| 触发方式 | 包版本 | 是否发布 Release |
| --- | --- | --- |
| 推送 `skill-studio` 分支 | 7 位提交 SHA | 否，只生成 Actions artifact |
| 手动 `workflow_dispatch` | 输入的版本，允许带 `v` | 是 |
| 推送 `skill-studio-vX.Y.Z` Tag | 从 Tag 去掉前缀 | 是 |

推荐发布顺序：

1. 先在 `main` 完成并验证业务改动，创建 `vX.Y.Z`，生成传统四个平台资产。
2. 把同版本所需业务改动同步到 `skill-studio`，完成适配测试。
3. 从确认过的 `skill-studio` 提交创建 `skill-studio-vX.Y.Z`。
4. CI 把四个 `skill-studio-<provider>-X.Y.Z.zip` 上传或覆盖到同一个 `vX.Y.Z` Release。

两个 Tag 指向不同分支的提交是正常设计；版本号必须一致。不要用普通 `skill-studio` 分支构建出的 SHA 包冒充正式版本资产。

## 验收范围

本地最低检查：

```text
python3 -B -m unittest discover -s tests -v
python3 -B -m unittest discover -s skillstudio/tests -v
python3 -B -m unittest discover -s skillstudio/kugou/tests -v
python3 -m compileall -q netease qq kugou qishui skillstudio tests
```

这些检查覆盖 JSON envelope、action 映射、凭据注入不回显、元数据一致性、禁止文件和跨平台 Python 语法。它们不替代正式 Runtime 验收。

正式环境至少验证：

- Code 能实际访问平台 HTTPS 接口。
- `get`/`set` 在当前 Agent 隔离范围内生效，Cookie 不出现在回复和日志中。
- 公开搜索和公开歌单在没有 Cookie 时可运行。
- 有效 Cookie 能读取个人歌单，无效 Cookie 能得到明确状态。
- 至少一首非会员国语流行歌曲能返回目标歌曲的实际 URL，而不是试听、会员流或其他歌曲。
- 返回 `httpHeaders` 的汽水地址由播放器原样携带请求头。
- 播放 URL 过期或返回 401/403 后，可以用歌曲 ID 重新解析。

`cases/verification.cases.json` 为空时，只表示当前包没有内置平台侧正式用例，不能表述为“已完成 Runtime 自动验收”。

## 已知约束

- 业务脚本必须访问外部音乐平台。当前生成元数据中的 `network: forbidden` / `network: false` 是现有导入兼容字段，不能理解为脚本可离线工作；若目标 Runtime 按该字段阻断网络，导入后将无法完成真实搜索和播放，需先与平台的 Code 出网策略对齐。
- 播放地址是短期签名 URL，只长期保存歌曲 ID 和歌单 ID，不把 URL 当作 token 或永久资源。
- Skill Studio 的 `check` 是凭据状态检查，不负责刷新或永久续期 Cookie。
- 登录流程需要交互和外部 App，不适合塞入一次 JSON stdin/stdout Code 调用。
