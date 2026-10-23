#!/usr/bin/env python3
"""一期盘点：仓库 episodes/<期> + 媒体目录里已有什么、制作状态、下一步 /p3-xxx 提示词。

给 p3-episode「先盘点」用，也给每个 stage 做完后核对用。只读，不改文件，不打开任何播放器。

  python3 tools/episode_status.py 2026-10-23-altitude
  python3 tools/episode_status.py episodes/2026-10-23-altitude --media-root ~/Movies/running-content
  python3 tools/episode_status.py --latest
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STAGES = ["ingest", "shoes", "hud", "cover", "assemble", "qc", "subs", "upload"]


def read_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    text = path.read_text(encoding="utf-8")
    sec = text.split("## 制作状态", 1)[1] if "## 制作状态" in text else ""
    for m in re.finditer(r"^\s*-\s*([A-Za-z]+)\s*:\s*(.+?)\s*$", sec, re.M):
        out[m.group(1).lower()] = m.group(2)
    return out


def front(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    for key in ("专名", "封面句"):
        mm = re.search(rf"^\s*[-*]?\s*{key}[：:]\s*(.*)$", text, re.M)
        if mm:
            out[key] = mm.group(1).strip()
    return out


def done(v: str | None) -> bool:
    return bool(v) and re.match(r"(done|ready)(?![A-Za-z-])", v) is not None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episode", nargs="?", help="YYYY-MM-DD-slug 或 episodes/ 下路径")
    ap.add_argument("--latest", action="store_true", help="取 episodes/ 里日期最新的一期")
    ap.add_argument("--media-root", default=str(Path.home() / "Movies/running-content"))
    ap.add_argument("--repo", default=str(REPO))
    args = ap.parse_args()

    repo = Path(args.repo).expanduser()
    if args.latest or not args.episode:
        eps = sorted(p for p in (repo / "episodes").glob("20??-??-??-*") if p.is_dir())
        if not eps:
            sys.exit("episodes/ 下没有期")
        ep = eps[-1]
    else:
        ep = Path(args.episode)
        if not ep.is_dir():
            ep = repo / "episodes" / Path(args.episode).name
    name = ep.name
    date = name[:10]
    media = Path(args.media_root).expanduser() / name

    fm = front(ep / "episode.md")
    st = read_kv(ep / "assets.md")
    has = lambda p: p.exists()  # noqa: E731
    clips = sorted(media.glob(f"{date}-run-*.mp4")) if media.is_dir() else []
    clips = [c for c in clips if "final" not in c.name and "-hud" not in c.name]
    fit = list(media.glob("*.fit")) if media.is_dir() else []
    previews = list((media / "hud-renders").glob("*-hud-preview.mp4")) if media.is_dir() else []
    covers = {n: has(media / n) for n in ("cover-1920x1080.jpg", "cover-4x3-1920x1440.jpg", "cover-1080x1440.jpg")}
    final = media / f"{date}-run-final.mp4"
    titled = [p for p in media.glob("*.mp4") if not p.name.startswith(date)] if media.is_dir() else []
    subs_txt = ep / "subtitles.txt"

    print(f"# {name}  status={fm.get('status', '?')}")
    print(f"- 仓库：{'有' if ep.is_dir() else '无'} episode.md={'有' if has(ep / 'episode.md') else '无'} "
          f"talk.md={'有' if has(ep / 'talk.md') else '无'} assets.md={'有' if has(ep / 'assets.md') else '无'}")
    terms = fm.get("专名", "")
    if not terms or terms.startswith(("（", "(")):
        print("- ⚠ episode.md 专名表没填：字幕识别没有提示（p3-subs 会自动读这一行）")
    print(f"- 封面句：{fm.get('封面句') or '（未写）'}")
    print(f"- 媒体目录：{media} {'存在' if media.is_dir() else '不存在'}")
    if media.is_dir():
        print(f"  open={'有' if has(media / f'{date}-open.mp4') else '无'} run-*={len(clips)} "
              f"close={'有' if has(media / f'{date}-close.mp4') else '无'} FIT={len(fit)} "
              f"hud-preview={len(previews)}/{len(clips) or '?'} "
              f"cover={sum(covers.values())}/3 成片={'run-final' if has(final) else ('标题名' if titled else '无')} "
              f"字幕txt={'有' if has(subs_txt) else '无'}")
    print("- 制作状态：" + "，".join(f"{k}={st.get(k, '-').split('（')[0].split('(')[0].strip()}" for k in STAGES))

    # 下一步（按主轨顺序取第一个缺口）
    nxt: list[str] = []
    if fm.get("status") == "published":
        nxt.append("已发布。满 7 天 → `/p3-archive`" + ("" if media.is_dir() else "（本机没有媒体目录，可能已归档）"))
    elif not ep.is_dir() or not has(ep / "episode.md"):
        nxt.append(f"`/p3-scaffold 日期 {date} slug {name[11:]}`")
    elif not has(ep / "talk.md") and fm.get("status") in ("idea", "planned"):
        nxt.append("`/p3-topic`（还没有口播卡）")
    elif not clips:
        nxt.append("素材到了 → `/p3-ingest 原始文件在 <导出目录路径>`" +
                   ("（还没拍：先按 talk.md 拍，停在这里）" if fm.get("status") in ("idea", "planned") else ""))
    elif not done(st.get("shoes")) and not previews:
        nxt.append("`/p3-shoes 鞋是 <HUD 名>，这是开跑前/跑完后 <数字> 公里`")
    elif len(previews) < len(clips):
        nxt.append("`/p3-hud`")
    elif not (has(final) or titled):
        nxt.append("`/p3-assemble`（拼完立刻核对）")
    elif not has(subs_txt):
        nxt.append("`/p3-subs`（对着成片转写）")
    elif not done(st.get("subs")):
        nxt.append("等用户改好字幕，说「改好了」→ `/p3-subs` 对口型")
    elif not done(st.get("upload")):
        nxt.append("用户说「可以发了」→ 按 p3-subs 发布流程改名、上传准备")
    elif fm.get("status") != "published":
        nxt.append("发布后给齐 B 站 + YouTube 链接 → status=published，清临时文件")
    if clips and not all(covers.values()) and fm.get("status") != "published":
        nxt.append("并行：`/p3-cover 封面句「" + (fm.get("封面句") or "<封面句>") + "」`（不依赖 HUD）")
    print("\n下一步：\n" + "\n".join(f"> {n}" for n in nxt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
