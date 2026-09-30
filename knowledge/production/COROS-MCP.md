# COROS MCP：把每次跑步数据接到 Claude

官方远程 MCP，Streamable HTTP + OAuth。接上之后可以直接查活动摘要，并按天下载 FIT（有日限额）。

## 连接

国内账号用中国节点（`mcp.coros.com` 会跳到 `mcpcn`，Claude 会因 resource 不匹配连不上）：

```bash
claude mcp add coros -s user --transport http https://mcpcn.coros.com/mcp
```

国际账号再用：

```bash
claude mcp add coros -s user --transport http https://mcp.coros.com/mcp
```

第一次用会打开浏览器做 COROS 授权，之后复用凭证。当前这台已写成 `mcpcn`，状态是 Needs authentication，下次对话里允许一次授权即可。

## 这套内容库怎么用

1. 问「我某天那次跑」拿到活动摘要（距离、配速、心率、手表）。
2. 用 MCP 下载该次 FIT（官方限制大约每天 50 个 FIT）。
3. 放到素材目录并命名为 `YYYY-MM-DD-run-data.fit`，和 `run-a/b/c` 放一起。
4. 再跑 `render_running_hud.py --overlay-only`。

HUD 对齐仍然看视频文件 `mtime` 和 FIT 时间窗，不走 MCP 实时数据。MCP 只负责把 FIT 拿回来。

## 来源

- [COROS MCP 帮助中心](https://support.coros.com/hc/en-us/articles/50841795180948-COROS-MCP-A-Guide-to-Connecting-Your-Training-Data-to-AI)
- 端点：`https://mcp.coros.com/mcp`
