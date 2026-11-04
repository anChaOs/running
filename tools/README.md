# tools

- `ingest/`：手机 `VID_` / FIT 收进素材目录并命名。
- `hud/`：用 FIT 给跑中素材叠配速、心率、距离、地图、天气。
- `subs/`：字幕初稿（`draft_subs.py`）、改字后强制对齐（`force_align.py`）、质检门（`check_subs.py`）、txt 收成 SRT（`txt_to_subs.py`）。依赖 `pip install -r tools/subs/requirements.txt`。
- `assemble/`：把 `open` + HUD preview + `close` 拼成全长成片（叠化、字幕、封面）。不替代 60–90 秒发布剪辑。
- `cover/`：三比例封面排版（4:3 / 3:4 / 16:9）。
- `publish/`：上传打包（`pack_upload.py` → 媒体目录 `upload/`）。

按需加载的流程入口是 skill `p3-episode`，阶段表见 `knowledge/production/成片skills.md`。
