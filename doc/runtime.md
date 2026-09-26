# Agent Runtime JSON 接口

六个平台各自提供独立的 `runtime.py`，用于只支持 JSON stdin/stdout 的 Agent Runtime、Code 工具或进程调用。它们只加载同目录脚本，平台目录单独复制后仍可使用。

传统命令行入口没有改变：`playurl.py` 成功时仍默认只输出一行 URL；只有 `runtime.py` 始终输出 JSON。

## 调用约定

- stdin：一个 UTF-8 JSON 对象，最大 1 MiB。
- stdout：恰好一个两空格缩进的 UTF-8 JSON 对象；不会混入提示文字。
- 成功执行：退出码 `0`，返回 `{"ok": true, "data": ...}`。
- 输入错误：退出码 `2`，错误码 `invalid_input`。
- 加载、网络或上游执行异常：退出码 `1`，错误码 `execution_failed`。

`playable: false`、Spotify 的 `provider_limited`、空搜索结果、凭据过期等都是已成功取得的业务结果，所以仍是 `ok: true`、退出码 `0`。调用方应继续检查 `data.playable`、`data.status`、`data.restriction` 和结果数组，而不是只看进程退出码。

```json
{
  "ok": true,
  "data": {
    "provider": "netease",
    "playable": true,
    "url": "https://..."
  }
}
```

```json
{
  "ok": false,
  "error": {
    "code": "invalid_input",
    "message": "missing id"
  }
}
```

## Actions

| `action` | 输入 | 平台 |
| --- | --- | --- |
| `search` | `query`，可选 `limit`、`offset`、`timeout` | 全部 |
| `playlist_search` | `query`，可选 `limit`、`offset`、`timeout` | 全部 |
| `playlist_tracks` | `id`，可选 `limit`、`offset`、`timeout` | 全部 |
| `playlist_mine` | 可选 `limit`、`offset`、`timeout` | 除 YouTube 外 |
| `playurl` | `id`，以及下表的平台字段 | 全部 |
| `check` | 可选 `timeout` | 全部 |

所有 action 也接受连字符写法，例如 `playlist-tracks`。字段别名包括 `keywords`、`playlistId` 和 `playlist_id`。

`playurl` 的平台字段：

| 平台 | `id` | 可选字段 |
| --- | --- | --- |
| 网易云 | 数字歌曲 ID | `quality` |
| QQ | songmid | `quality`、`mediaMid` / `media_mid` |
| 酷狗 | hash | `quality`、`albumId` / `album_id`、`albumAudioId` / `album_audio_id` |
| 汽水 | 数字 track_id | `decryptOutput` / `decrypt_output`，用于把加密流写入指定文件 |
| Spotify | 22 位 track ID | 无；只返回官方播放模式，不返回音频直链 |
| YouTube | video ID 或 URL | `quality`：`high` 或 `standard` |

## 示例

macOS / Linux：

```text
printf '%s\n' '{"action":"playurl","id":"347230"}' | python3 playurl/netease/runtime.py
printf '%s\n' '{"action":"search","query":"晴天 周杰伦","limit":5}' | python3 playurl/qq/runtime.py
printf '%s\n' '{"action":"check"}' | python3 playurl/qishui/runtime.py
```

Windows PowerShell：

```text
'{"action":"check"}' | python playurl\netease\runtime.py
'{"action":"playlist_tracks","id":"歌单ID","limit":50}' | python playurl\kugou\runtime.py
```

宿主程序应直接写入 JSON，而不是拼 shell 命令：

```python
import json
import subprocess

request = {"action": "playurl", "id": "347230", "quality": "exhigh"}
process = subprocess.run(
    ["python3", "playurl/netease/runtime.py"],
    input=json.dumps(request),
    text=True,
    capture_output=True,
)
response = json.loads(process.stdout)
```

扫码、短信验证码等登录流程是有状态交互，不适合单次 stdin/stdout 调用，因此仍使用每个平台自己的 `login.py`。Runtime 会读取这些登录脚本已经保存到同目录的凭据。
