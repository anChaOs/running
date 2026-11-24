---
name: p3-shoes
description: 查或追加跑鞋累计里程并算出 HUD -sn/-sk（本场跑完后累计公里）。用户说跑鞋、鞋里程、-sk、鞋账本时用。账本在 training/logs/shoes.md。
---

# 跑鞋账本

账本：`training/logs/shoes.md`（算 `-sk` 只读账本和当天 FIT，不用对话旧数字）。遵守 `p3-episode` 全局协议（本步不在 `todo.md` 新加行，但进门核对 `ingest: done`）。

## 口径

| 用户说的数 | 处理 |
| --- | --- |
| 开跑前 | `after = before + 本场 km` |
| 跑完后 | 直接当 `-sk`；`before = after - 本场 km` |
| 现在的生涯总里程 | 若本场之后还跑过，不能直接当 `-sk`，先问开跑前或跑完后 |

本场 km（FIT `distance` 最大值 / 1000）：

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, "tools")
import fitdecode
import media_layout as ml
fit = ml.find_fits(Path("~/Movies/running-content/YYYY-MM-DD-slug").expanduser())[0]
total = None
with fitdecode.FitReader(fit) as fr:
    for frame in fr:
        if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "record":
            continue
        for field in frame.fields:
            if field.name == "distance" and field.value is not None:
                v = float(field.value)
                if total is None or v > total:
                    total = v
print(f"{total/1000:.3f} km")
PY
```

HUD 参数：`-sn "<HUD 名>" -sk <跑完后累计 km>`（只来自账本中**本场**那一行，保留两位小数）。

## 追加与记日志

把新行写入场次表并更新「当前读数」（同一天只记上场那双鞋）。无脚本挂钩，用 `tools/log_timeline.py` 记 `start shoes` / `end shoes`，完成后核对 `logs/todo.md`。

## 完成后

把当前期 `-sn` / `-sk` 填好后推荐下一步（短视频同样需要 HUD alpha）：

> 下一步用 `/p3-hud`（封面并行走 `/p3-cover`）：
>
> `/p3-hud`
