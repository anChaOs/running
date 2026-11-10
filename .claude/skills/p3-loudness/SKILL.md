---
name: p3-loudness
description: 已废弃的旧响度补跑入口。响度必须进入 final_export.py 的唯一最终编码，不对已有成片二次编码。
---

# 已废弃

正式流程不再使用 `loudness_only.py`。`final_export.py` 在最终导出中完成两遍 loudnorm：第一遍只向 null 输出做测量，第二遍把响度滤镜和字幕、HUD、stats、拼接一起写入最终 HEVC 文件。

不要对 `run-final` 使用 `-c:v copy` 的响度补跑，也不要在最终导出后再次编码。响度目标和 AAC/采样率规格见 `tools/export-spec.json`。
