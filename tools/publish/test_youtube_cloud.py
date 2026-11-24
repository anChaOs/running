#!/usr/bin/env python3
"""Unit tests for Cloud Run Jobs YouTube uploader (GCS default + Google Drive switchable)."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

PUBLISH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PUBLISH_DIR))
sys.path.insert(0, str(PUBLISH_DIR / "cloud_yt"))

import job_main  # noqa: E402
import sync_retrospect_drive  # noqa: E402
import youtube_cloud  # noqa: E402

SAMPLE_PLAN = """# 2026-11-24 发布计划

## 标题

上马前，LSD没跑够能行吗？

## 简介

### B 站

个人视频制作来自：https://github.com/anChaOs/running

B 站简介正文。

### YouTube

个人视频制作来自：github.com/anChaOs/running

YouTube 简介正文，不含链接。

## 标签

B 站（5–8 个，不要堆）：

```text
#跑步 #马拉松 #上海马拉松
```

YouTube 标签：

```text
跑步, 马拉松, 上海马拉松, 长距离慢跑
```
"""


class YoutubeCloudTests(unittest.TestCase):
    def test_parse_plan_youtube_extracts_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plan = Path(td) / "plan.md"
            plan.write_text(SAMPLE_PLAN, encoding="utf-8")
            parsed = youtube_cloud.parse_plan_youtube(plan)
            self.assertEqual(parsed["title"], "上马前，LSD没跑够能行吗？")
            self.assertIn("github.com/anChaOs/running", parsed["description"])
            self.assertNotIn("https://", parsed["description"])
            self.assertEqual(parsed["tags"], ["跑步", "马拉松", "上海马拉松", "长距离慢跑"])

    def test_parse_plan_rejects_https_in_youtube_desc(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plan = Path(td) / "plan.md"
            plan.write_text(
                SAMPLE_PLAN.replace("github.com/anChaOs/running\n\nYouTube", "https://github.com/anChaOs/running\n\nYouTube"),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                youtube_cloud.parse_plan_youtube(plan)

    def test_build_metadata_uses_pack_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media = root / "2026-11-24-lsd-short"
            ep = root / "ep"
            (media / "upload").mkdir(parents=True)
            (media / "logs").mkdir(parents=True)
            ep.mkdir()
            (ep / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
            mp4 = media / "upload" / "上马前，LSD没跑够能行吗？.mp4"
            mp4.write_bytes(b"fake-mp4-data")
            (media / "upload" / "cover-16x9-1920x1080.jpg").write_bytes(b"jpg")
            (media / "upload" / "subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
            expected_sha = hashlib.sha256(b"fake-mp4-data").hexdigest()
            (media / "logs" / "pack-sha256.txt").write_text(f"{expected_sha}  {mp4.name}\n", encoding="utf-8")

            meta, vpath, cpath, spath = youtube_cloud.build_metadata(media, ep)
            self.assertEqual(vpath, mp4)
            self.assertEqual(cpath.name, "cover-16x9-1920x1080.jpg")
            self.assertIsNotNone(spath)
            self.assertEqual(meta["sha256"], expected_sha)
            self.assertEqual(meta["privacy_status"], "public")
            self.assertEqual(meta["gcs_video_object"], "staging/2026-11-24-lsd-short/video.mp4")

    def test_build_execute_cmd_gcs_and_drive(self) -> None:
        cmd_gcs = youtube_cloud.build_execute_cmd(
            "gcloud",
            project="p1",
            region="us-west1",
            job="running-yt-upload",
            slug="2026-11-24-lsd-short",
            source="gcs",
            bucket="my-bucket",
            drive_root="跑步成片",
            wait=False,
            keep_staging=False,
        )
        self.assertIn("--async", cmd_gcs)
        self.assertIn("YT_SLUG=2026-11-24-lsd-short,YT_SOURCE=gcs,YT_DRIVE_ROOT=跑步成片,YT_GCS_BUCKET=my-bucket", cmd_gcs)

        cmd_drive = youtube_cloud.build_execute_cmd(
            "gcloud",
            project="p1",
            region="us-west1",
            job="running-yt-upload",
            slug="2026-11-24-lsd-short",
            source="drive",
            bucket="my-bucket",
            drive_root="跑步成片",
            wait=True,
            keep_staging=True,
        )
        self.assertIn("--wait", cmd_drive)
        self.assertIn(
            "YT_SLUG=2026-11-24-lsd-short,YT_SOURCE=drive,YT_DRIVE_ROOT=跑步成片,YT_GCS_BUCKET=my-bucket,YT_KEEP_STAGING=1",
            cmd_drive,
        )

    def test_parse_manifest_compatible_with_stage_drive_chunks(self) -> None:
        manifest = (
            "chunk-00 99000000\n"
            "chunk-01 80582145\n"
            "TOTAL 179582145\n"
            "SHA256 0c0f5ce7ec2cbba63eb45c49b4133dbfd86ea9d9bacfccc70cb7e1024cb6e70a  /tmp/x.mp4\n"
        )
        chunks, total, sha = job_main.parse_manifest(manifest)
        self.assertEqual(chunks, [("chunk-00", 99000000), ("chunk-01", 80582145)])
        self.assertEqual(total, 179582145)
        self.assertEqual(sha, "0c0f5ce7ec2cbba63eb45c49b4133dbfd86ea9d9bacfccc70cb7e1024cb6e70a")

    def test_retrospect_filters_binary_and_pid_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            (logs / "timeline.txt").write_text("ok\n", encoding="utf-8")
            (logs / "todo.md").write_text("ok\n", encoding="utf-8")
            (logs / "program.json").write_text("{}\n", encoding="utf-8")
            (logs / "worker.pid").write_text("1234\n", encoding="utf-8")
            (logs / "preview-qc.zip").write_bytes(b"PK\x03\x04")
            (logs / "frame.jpg").write_bytes(b"\xff\xd8")
            (logs / "sub").mkdir()
            kept = [p.name for p in sync_retrospect_drive.eligible_log_files(logs)]
            self.assertEqual(kept, ["program.json", "timeline.txt", "todo.md"])


if __name__ == "__main__":
    unittest.main()
