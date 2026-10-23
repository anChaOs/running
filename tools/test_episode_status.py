#!/usr/bin/env python3
"""episode_status.py 自测：临时仓库 + 临时媒体目录，逐步补文件看下一步是否跟着走。"""
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).with_name("episode_status.py")
EP = "2026-01-02-test"


def run(repo: Path, media: Path) -> str:
    return subprocess.run([sys.executable, str(TOOL), EP, "--repo", str(repo), "--media-root", str(media)],
                          capture_output=True, text=True, check=True).stdout


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        repo, media = Path(d, "repo"), Path(d, "media")
        ep, m = repo / "episodes" / EP, media / EP
        assert "/p3-scaffold" in run(repo, media)
        ep.mkdir(parents=True)
        (ep / "episode.md").write_text("---\nstatus: planned\n---\n封面句：测试封面\n专名：（占位）\n", encoding="utf-8")
        (ep / "talk.md").write_text("x", encoding="utf-8")
        (ep / "assets.md").write_text("## 制作状态\n\n- ingest: pending\n- shoes: pending\n", encoding="utf-8")
        out = run(repo, media)
        assert "专名表没填" in out and "/p3-ingest" in out, out
        (m / "hud-renders").mkdir(parents=True)
        for n in ("open", "run-a", "close"):
            (m / f"2026-01-02-{n}.mp4").touch()
        out = run(repo, media)
        assert "/p3-shoes" in out and "并行：`/p3-cover 封面句「测试封面」" in out, out
        (ep / "assets.md").write_text("## 制作状态\n\n- ingest: done\n- shoes: done（x）\n", encoding="utf-8")
        assert "> `/p3-hud`" in run(repo, media)
        (m / "hud-renders/2026-01-02-run-a-hud-preview.mp4").touch()
        assert "/p3-assemble" in run(repo, media)
        (m / "2026-01-02-run-final.mp4").touch()
        assert "/p3-subs" in run(repo, media)
        (ep / "episode.md").write_text("---\nstatus: published\n---\n", encoding="utf-8")
        assert "/p3-archive" in run(repo, media)
    print("ok test_episode_status")


if __name__ == "__main__":
    main()
