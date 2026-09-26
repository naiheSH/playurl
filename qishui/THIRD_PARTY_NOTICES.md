# 第三方代码说明

`auth.py`、`login.py` 与自包含构建文件 `login.cjs` 实现同一登录协议。Python 文件只使用标准库；`login.cjs` 运行时不需要安装 npm 包。

## ly-music-source

- 项目：<https://github.com/LuoYe17/ly-music-source>
- 参考版本：`bcba7fb`（2026-07-18）
- 使用范围：`auth.py` 与 `login.cjs` 中的汽水 Passport 极简请求、Cookie 会话、二维码状态机和短信二次验证流程
- 许可证：GPL-3.0-only
- 完整许可证：[`LICENSE.ly-music-source`](./LICENSE.ly-music-source)

本目录对该流程做了独立命令行封装，包括本地状态隔离、二维码文件管理、交互式验证码输入和 Cookie 原子保存。

## node-qrcode

- 项目：<https://github.com/soldair/node-qrcode>
- 版本：1.5.4
- 使用范围：终端二维码和 PNG 兜底渲染
- 许可证：MIT

```text
The MIT License (MIT)

Copyright (c) 2012 Ryan Day

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
