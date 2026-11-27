#!/usr/bin/env python3
"""Unit tests for Cloud Run Jobs YouTube uploader (GCS default + Google Drive switchable)."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parents[1]
PUB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(PUB_DIR))
sys.path.insert(0, str(PUB_DIR / "cloud_yt"))

import job_main  # noqa: E402
import log_timeline  # noqa: E402
import sync_retrospect_drive  # noqa: E402
import todo_list  # noqa: E402
import youtube_cloud  # noqa: E402


SAMPLE_PLAN = """\
# 测试计划

## 标题

> 发这个：上马前，LSD没跑够能行吗？

## 简介

### B 站

个人视频制作来自：https://github.com/anChaOs/running

B 站简介。

### YouTube

个人视频制作来自：github.com/anChaOs/running

YouTube 简介第一行。
第二行。

## 标签

B 站（5–8 个，不要堆）：

```text
#跑步 #马拉松 #上海马拉松 #长距离跑 #破三
```

YouTube 标签：

```text
跑步, 马拉松, 上海马拉松, 长距离跑, 破三, 赛前减量
```
"""


def _mark_through_drive(media: Path) -> None:
    for step in (
        "ingest",
        "edl",
        "hud-record",
        "layout",
        "preview",
    ):
        todo_list.mark(media, step, "done")
    todo_list.mark(media, "subs", "waiting-review")
    todo_list.mark(media, "subs", "aligned")
    todo_list.mark(media, "subs", "confirmed", confirmed=True)
    for step in ("final-export", "final-qc", "pack-upload", "drive"):
        todo_list.mark(media, step, "done")


class YoutubeCloudTests(unittest.TestCase):
    def test_parse_plan_youtube(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plan = Path(td) / "plan.md"
            plan.write_text(SAMPLE_PLAN, encoding="utf-8")
            parsed = youtube_cloud.parse_plan_youtube(plan)
            self.assertEqual(parsed["title"], "上马前，LSD没跑够能行吗？")
            self.assertIn("github.com/anChaOs/running", parsed["description"])
            self.assertNotIn("https://", parsed["description"])
            self.assertEqual(parsed["tags"], ["跑步", "马拉松", "上海马拉松", "长距离跑", "破三", "赛前减量"])

    def test_parse_plan_rejects_url_in_youtube_desc(self) -> None:
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

    def test_streaming_drive_chunk_assembly_and_cleanup(self) -> None:
        parts = {
            "chunk-00": b"AAAA" * 1024,
            "chunk-01": b"BBBB" * 1024,
            "chunk-02": b"CCCC" * 512,
            "chunk-03": b"DDDD" * 256,
        }
        manifest_chunks = [(name, len(data)) for name, data in parts.items()]
        expected_bytes = b"".join(parts.values())
        expected_sha = hashlib.sha256(expected_bytes).hexdigest()

        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            chunk_dir = work / "chunks"
            video_path = work / "video.mp4"

            def fake_download(cname: str, dest: Path) -> None:
                dest.write_bytes(parts[cname])

            got_sha = job_main.assemble_drive_chunks_streaming(
                manifest_chunks,
                fake_download,
                video_path,
                chunk_dir,
                prefetch=2,
            )
            self.assertEqual(got_sha, expected_sha)
            self.assertEqual(video_path.read_bytes(), expected_bytes)
            # Every chunk must have been unlinked immediately after writing.
            self.assertEqual(list(chunk_dir.iterdir()), [])

    def test_record_upload_result_without_timeline_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td) / "2026-11-24-lsd-short"
            media.mkdir()
            _mark_through_drive(media)
            # Deliberately no logs/timeline.txt yet.
            payload = {"slug": media.name, "source": "gcs", "url": "https://youtu.be/abc123"}
            out = youtube_cloud.record_upload_result(media, payload)
            self.assertTrue(out.is_file())
            self.assertEqual(todo_list.load(media)["youtube"], "done")

            # Add an unmatched start, verify second call is idempotent when youtube is already done.
            log_timeline.start(media, "youtube-upload")
            youtube_cloud.record_upload_result(media, payload)
            tl = (media / "logs" / "timeline.txt").read_text(encoding="utf-8")
            self.assertEqual(tl.count("END"), 0)

    def test_cmd_result_falls_back_to_drive_when_bucket_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            media = Path(td) / "2026-11-24-lsd-short"
            media.mkdir()
            _mark_through_drive(media)
            log_timeline.start(media, "youtube-upload")
            missing_cfg = Path(td) / "no-config.json"
            drive_res = {"slug": media.name, "source": "drive", "url": "https://youtu.be/xyz789"}

            with mock.patch.object(youtube_cloud, "fetch_drive_result", return_value=drive_res):
                rc = youtube_cloud.main([
                    "result",
                    "--media-dir", str(media),
                    "--config", str(missing_cfg),
                ])
            self.assertEqual(rc, 0)
            self.assertEqual(todo_list.load(media)["youtube"], "done")
            saved = json.loads((media / "logs" / "youtube-upload-result.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["url"], "https://youtu.be/xyz789")
            tl = (media / "logs" / "timeline.txt").read_text(encoding="utf-8")
            self.assertIn("END", tl)
            self.assertIn("https://youtu.be/xyz789", tl)

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

    def test_retrospect_merge_preserves_archived_episodes_in_index(self) -> None:
        old_index = """\
# Running Retrospect Index

最后同步：2026-11-20 12:00:00 +08:00

| Slug | 标题 | 状态 | Bilibili | YouTube | logs | episode-repo | publish-report.html |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `2026-11-01-archived` | 旧期\\|带竖线 | `published` | https://www.bilibili.com/video/BVold | https://youtu.be/old1 | 5 files | episode.md, plan.md | yes |
"""
        parsed_remote = sync_retrospect_drive.parse_index_md(old_index)
        self.assertIn("2026-11-01-archived", parsed_remote)
        self.assertEqual(parsed_remote["2026-11-01-archived"]["title"], "旧期|带竖线")
        self.assertTrue(parsed_remote["2026-11-01-archived"]["has_report"])

        with tempfile.TemporaryDirectory() as td:
            ep_root = Path(td) / "episodes"
            archived_ep = ep_root / "2026-11-01-archived"
            archived_ep.mkdir(parents=True)
            (archived_ep / "episode.md").write_text(
                "---\ntitle: 旧期|新标题\nstatus: published\n---\n- Bilibili：https://www.bilibili.com/video/BVold\n- YouTube：https://youtu.be/old1\n",
                encoding="utf-8",
            )
            synced = [
                {
                    "slug": "2026-11-24-lsd-short",
                    "title": "上马前，LSD没跑够能行吗？",
                    "status": "published",
                    "bilibili": "https://www.bilibili.com/video/BVnew",
                    "youtube": "https://youtu.be/new1",
                    "logs_files": ["timeline.txt", "todo.md"],
                    "repo_files": ["episode.md", "plan.md"],
                    "has_report": True,
                }
            ]
            merged = sync_retrospect_drive.merge_index_records(
                synced=synced,
                local_only=[],
                remote_index=parsed_remote,
                episodes_root=ep_root,
            )
            rendered = sync_retrospect_drive.render_index(merged)
            self.assertIn("`2026-11-24-lsd-short`", rendered)
            self.assertIn("`2026-11-01-archived`", rendered)
            self.assertIn("旧期\\|新标题", rendered)
            self.assertIn("| 5 files |", rendered)

    def test_should_keep_gcs_staging_when_bili_metadata_exists(self) -> None:
        bucket = mock.Mock()
        bili_blob = mock.Mock()
        bili_blob.exists.return_value = True
        bucket.blob.return_value = bili_blob
        client = mock.Mock()
        client.bucket.return_value = bucket
        with mock.patch.object(job_main.storage, "Client", return_value=client):
            removed = job_main.cleanup_gcs_staging("bucket", "2026-11-27-taper-week")
        self.assertEqual(removed, 0)
        client.list_blobs.assert_not_called()
        bucket.blob.assert_called_with("staging/2026-11-27-taper-week/bili_metadata.json")

    def test_should_delete_gcs_staging_when_bili_metadata_is_absent(self) -> None:
        blob = mock.Mock()
        bucket = mock.Mock()
        bucket.blob.return_value.exists.return_value = False
        client = mock.Mock()
        client.bucket.return_value = bucket
        client.list_blobs.return_value = [blob]
        with mock.patch.object(job_main.storage, "Client", return_value=client):
            removed = job_main.cleanup_gcs_staging("bucket", "slug")
        self.assertEqual(removed, 1)
        blob.delete.assert_called_once()


if __name__ == "__main__":
    unittest.main()
