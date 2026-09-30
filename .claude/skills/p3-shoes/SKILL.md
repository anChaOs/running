---
name: p3-shoes
description: 查或追加跑鞋累计里程。HUD -sk 是本场跑完后的公里。用户说跑鞋、鞋里程、-sk、鞋账本时用。账本在 training/logs/shoes.md。
---

# 跑鞋账本

账本：`training/logs/shoes.md`。这是防上下文压缩的数据源，算 `-sk` 只读它和当天 FIT，不要用对话里的旧数字。

## 口径

| 用户说的数 | 处理 |
| --- | --- |
| 开跑前 | `after = before + 本场 km` |
| 跑完后 | 直接当 `-sk`；`before = after - 本场 km` |
| 现在的生涯总里程 | 若这双鞋在本场之后还跑过，不能当本场 `-sk`。先问本场开跑前或跑完后 |

本场 km：FIT `distance` 最大值 / 1000。可用：

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import fitdecode
fit = Path("~/Movies/running-content/YYYY-MM-DD-slug/YYYY-MM-DD-run-data.fit").expanduser()
total = None
with fitdecode.FitReader(fit) as fr:
    for frame in fr:
        if getattr(frame, "name", None) != "record":
            continue
        for field in frame.fields:
            if field.name == "distance" and field.value is not None:
                v = float(field.value)
                if total is None or v > total:
                    total = v
print(f"{total/1000:.3f} km")
PY
```

HUD：

```text
-sn "<HUD 名>" -sk <跑完后累计 km>
```

`<HUD 名>` 和 `-sk` 只来自账本里**这一场**的那一行，不要沿用上一期的数。

## 追加

把新行写入场次表，更新「当前读数」。同一天只记上场那双鞋。数字保留两位小数，和 HUD 显示一致。

## 完成后

账本写好后立刻推荐下一步，把当前期的 `-sn` / `-sk` 填进提示词。

> 下一步用 `/p3-hud`（封面一并做），可以直接发：
>
> `/p3-hud`

只记账也可以停。短视频同样需要 HUD alpha，下一步仍是 `/p3-hud`。
