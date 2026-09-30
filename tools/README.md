# tools

- `ingest/`：手机 `VID_` / FIT 收进素材目录并命名。
- `hud/`：用 FIT 给跑中素材叠配速、心率、距离、地图、天气。
- `assemble/`：把 `open` + HUD preview + `close` 拼成全长成片（叠化、字幕、封面）。不替代 60–90 秒发布剪辑。

按需加载的流程入口是 skill `p3-episode`，阶段表见 `knowledge/production/成片skills.md`。
