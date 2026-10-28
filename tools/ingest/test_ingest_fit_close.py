#!/usr/bin/env python3
"""ingest 自测：按时间窗挑 FIT、FIT 结束后的多段 close 自动拼成一条。

合成素材（ffmpeg lavfi 2 秒小片），FIT 用桩函数替掉 fit_window（不需要真 FIT）。不开任何播放器。
"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ingest_run_media as ing  # noqa: E402

SH = ing.SHANGHAI


def t(hms: str) -> datetime:
    return datetime.strptime(f"2026-01-02 {hms}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=SH)


def stub_windows(table: dict[str, tuple[datetime | None, datetime | None, str]]):
    ing.fit_window = lambda p: table[p.name]


def expect_exit(fn, needle: str) -> None:
    try:
        fn()
    except SystemExit as exc:
        assert needle in str(exc), exc
        return
    raise AssertionError("expected SystemExit")


def test_pick_fit() -> None:
    vids = [(t("07:00:00"), t("07:01:00")), (t("07:05:00"), t("07:35:00"))]
    a, b, c = Path("a.fit"), Path("b.fit"), Path("c.fit")
    # 早上那场重叠，晚上那场不重叠 → 选早上
    stub_windows({"a.fit": (t("06:58:00"), t("07:40:00"), "records"),
                  "b.fit": (t("19:00:00"), t("19:40:00"), "records")})
    assert ing.pick_fit([b, a], vids)[0] == a
    # 两场都大段重叠 → 停下列候选
    stub_windows({"a.fit": (t("06:58:00"), t("07:40:00"), "records"),
                  "c.fit": (t("07:00:00"), t("07:30:00"), "records")})
    expect_exit(lambda: ing.pick_fit([a, c], vids), "分不出")
    # 都不重叠 → 停
    stub_windows({"a.fit": (t("12:00:00"), t("12:30:00"), "records"),
                  "b.fit": (t("19:00:00"), t("19:40:00"), "records")})
    expect_exit(lambda: ing.pick_fit([a, b], vids), "都和视频时间窗不重叠")
    # --fit 指定
    assert ing.pick_fit([a, b], vids, "b.fit")[0] == b
    expect_exit(lambda: ing.pick_fit([a, b], vids, "zzz.fit"), "不在源目录")
    # 唯一 FIT 不重叠：照用并提示
    assert ing.pick_fit([a], vids)[0] == a
    # 只有文件名时间（无结束）：按估计时长算
    stub_windows({"a.fit": (t("06:59:00"), None, "filename"), "b.fit": (t("19:00:00"), None, "filename")})
    assert ing.pick_fit([a, b], vids)[0] == a


def test_roles() -> None:
    v = [Path(f"VID_20260102_0{h}0000.mp4") for h in range(5)]
    roles = [r for _, r in ing.propose_roles(v, False, False, n_close=2)]
    assert roles == ["open", "run-a", "run-b", "close-1", "close-2"], roles
    roles = [r for _, r in ing.propose_roles(v, False, False)]
    assert roles == ["open", "run-a", "run-b", "run-c", "close"], roles
    roles = [r for _, r in ing.propose_roles(v[:3], True, False, n_close=2)]
    assert roles == ["run-a", "close-1", "close-2"], roles
    expect_exit(lambda: ing.propose_roles(v[:3], False, False, n_close=2), "不够分")


def make_clip(path: Path, color: str, start: datetime, dur: float = 2.0) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c={color}:s=320x240:r=30:d={dur}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    end = (start + timedelta(seconds=dur)).timestamp()
    os.utime(path, (end, end))


def duration(p: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(p)], text=True))


def test_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as d:
        src, ep = Path(d, "src"), Path(d, "ep")
        media = Path(d, "media", "2026-01-02-test")
        src.mkdir()
        starts = ["06:55:00", "07:00:00", "07:20:00", "07:41:00", "07:43:00"]  # open, run×2, close×2
        for i, hms in enumerate(starts):
            make_clip(src / f"VID_20260102_{hms.replace(':', '')}.mp4", ["red", "green", "blue", "white", "gray"][i], t(hms))
        (src / "morning.fit").write_bytes(b"x")
        (src / "evening.fit").write_bytes(b"x")
        stub_windows({"morning.fit": (t("06:59:30"), t("07:40:00"), "records"),
                      "evening.fit": (t("18:00:00"), t("18:30:00"), "records")})
        sys.argv = ["ingest", "--src", str(src), "--media-root", str(media.parent), "--date", "2026-01-02", "--slug", "test",
                    "--episode-dir", str(ep), "--apply", "--skip-pause-trim"]
        ing.main()
        names = sorted(p.name for p in media.iterdir())
        for n in ("open", "run-a", "run-b", "close-1", "close-2", "close"):
            assert f"2026-01-02-{n}.mp4" in names, names
        assert "2026-01-02-run-data.fit" in names
        close = media / "2026-01-02-close.mp4"
        assert abs(duration(close) - 4.0) < 0.3, duration(close)
        assert abs(close.stat().st_mtime - (media / "2026-01-02-close-2.mp4").stat().st_mtime) < 1
        assets = (ep / "assets.md").read_text(encoding="utf-8")
        assert "close-1.mp4 + 2026-01-02-close-2.mp4" in assets, assets
        assert "morning.fit" in assets, assets


if __name__ == "__main__":
    test_pick_fit()
    test_roles()
    test_end_to_end()
    print("ok: ingest fit/close")
