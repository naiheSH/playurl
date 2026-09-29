# Skill Studio 适配层

本目录维护 playurl 的 Skill Studio 适配与可导入 ZIP。正式发布范围只有四个国内平台：

| 平台 | 包名 | KV key |
| --- | --- | --- |
| 网易云音乐 | `skill-studio-netease-<version>.zip` | `netease-cookie` |
| QQ 音乐 | `skill-studio-qq-<version>.zip` | `qqmusic-cookie` |
| 酷狗音乐 | `skill-studio-kugou-<version>.zip` | `kugou-cookie` |
| 汽水音乐 | `skill-studio-qishui-<version>.zip` | `qishui-cookie` |

`main` 面向传统脚本和 CLI；`skill-studio` 分支在保留这些实现的基础上增加 Agent Runtime 所需的元数据、KV 使用说明、JSON Code 入口和打包流程。Skill Studio 适配不应反向改变 `playurl.py` 的单行 URL 输出，也不应把某个平台的业务实现抽成跨平台运行时。

完整的运行契约、KV 流程、同步规则、验收边界和发版方式见 [`../doc/skill-studio.md`](../doc/skill-studio.md)。

## 目录职责

- 仓库根部的 `netease/`、`qq/`、`kugou/`、`qishui/` 是业务脚本构建输入。
- `skillstudio/<provider>/SKILL.md` 描述该平台在 Agent 中的能力路由、参数边界和凭据流程。
- `skillstudio/<provider>/scripts/runtime.py` 是 JSON stdin/stdout 入口。
- `skillstudio/<provider>/.skill-studio/`、`implementation.json` 和 `skill-metadata.json` 是导入元数据。
- `skillstudio/build_platforms.py` 重新生成元数据，把业务脚本复制到临时目录并生成确定性 ZIP。
- `dist/` 是构建产物，不是业务源码。

不要直接修改 ZIP 中复制出来的 `search.py`、`playlist.py`、`playurl.py` 或 `check.py`。业务修复应先落到仓库根部对应平台目录，再重新构建。

## 包内能力

四个正式包均提供同一个 Code 入口 `scripts/runtime.py`，通过 `action` 区分：

- `search`
- `playlist_search`
- `playlist_tracks`
- `playlist_mine`
- `playurl`
- `check`

stdin 必须是一个 JSON 对象；stdout 只返回一个格式化 JSON 对象。Skill Studio 包不包含扫码登录、短信验证、浏览器授权、本地 Cookie 文件、设备注册脚本或任何真实凭据。

## 本地构建

正式包逐个平台构建，避免把尚未进入正式发布范围的平台混入资产：

```text
python3 skillstudio/build_platforms.py netease --version 2.0.0 --output-dir dist
python3 skillstudio/build_platforms.py qq --version 2.0.0 --output-dir dist
python3 skillstudio/build_platforms.py kugou --version 2.0.0 --output-dir dist
python3 skillstudio/build_platforms.py qishui --version 2.0.0 --output-dir dist
```

生成器内部仍保留 Spotify 和 YouTube 的开发规格，因此正式发版不要使用 `all` 代替上述四个平台。CI 发布矩阵只包含四个国内平台。

## 修改后的最低检查

```text
python3 -B -m unittest discover -s tests -v
python3 -B -m unittest discover -s skillstudio/tests -v
python3 -B -m unittest discover -s skillstudio/kugou/tests -v
python3 -m compileall -q netease qq kugou qishui skillstudio tests
```

测试通过只证明本地协议、适配和包结构符合预期。发布前还应在正式 Agent Runtime 中验证出网、KV 注入、非会员歌曲解析、个人歌单和过期 Cookie；空的 `cases/verification.cases.json` 不代表正式 Runtime 验收已经完成。
