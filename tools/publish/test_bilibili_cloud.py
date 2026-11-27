#!/usr/bin/env python3
"""Unit tests for bilibili_cloud.py and cloud_bili/job_main.py."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bilibili_cloud as bc  # noqa: E402
import bilibili_upload as bu  # noqa: E402


def _load_bili_job():
    path = Path(__file__).resolve().parent / "cloud_bili" / "job_main.py"
    spec = importlib.util.spec_from_file_location("cloud_bili_job_main", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bili_job = _load_bili_job()

PLAN = """\
# 标题

## 标题

> 发这个：测试视频

### B 站

测试简介内容

## 标签

B 站：

```text
#跑步 #马拉松 #破三 #测试 #日常
```
"""

PREREQ = (
    "ingest",
    "edl",
    "hud-record",
    "layout",
    "preview",
    "final-export",
    "final-qc",
    "pack-upload",
)


def _write_todo(media: Path, **states: str) -> None:
    base = {step: "done" for step in PREREQ}
    base.update(states)
    (media / "logs").mkdir(parents=True, exist_ok=True)
    (media / "logs" / "todo.md").write_text(
        bc.todo_list.render(bc.todo_list.TodoStatus(base)),
        encoding="utf-8",
    )


def _make_episode(root: Path, *, video: bytes = b"video-bytes-123") -> tuple[Path, Path]:
    media = root / "2026-11-27-taper-week"
    episode = root / "ep"
    upload = media / "upload"
    upload.mkdir(parents=True)
    episode.mkdir()
    (upload / "测试视频.mp4").write_bytes(video)
    (upload / bu.COVER_16X9).write_bytes(b"c16")
    (upload / bu.COVER_4X3).write_bytes(b"c43")
    (episode / "plan.md").write_text(PLAN, encoding="utf-8")
    _write_todo(media)
    return media, episode


def _gcs_runner(copied: list[str], sha_files: dict[str, str]):
    def fake_run(cmd, **kwargs):
        if cmd[1:3] == ["storage", "cp"]:
            copied.append(cmd[4])
            return mock.Mock(returncode=0, stdout="", stderr="")
        if cmd[1:3] == ["storage", "cat"]:
            name = Path(cmd[3]).name
            if name in sha_files:
                return mock.Mock(returncode=0, stdout=json.dumps({"sha256": sha_files[name]}), stderr="")
            return mock.Mock(returncode=1, stdout="", stderr="missing")
        return mock.Mock(returncode=0, stdout="", stderr="")

    return fake_run


class FakeBlob:
    def __init__(self, store: dict[str, bytes | None], name: str) -> None:
        self.store = store
        self.name = name
        self.deleted = False
        self.uploaded: str | None = None

    def exists(self) -> bool:
        return self.name in self.store and self.store[self.name] is not None

    def download_as_text(self, encoding: str = "utf-8") -> str:
        data = self.store[self.name]
        assert data is not None
        return data.decode(encoding)

    def download_to_filename(self, path: str) -> None:
        data = self.store[self.name]
        assert data is not None
        Path(path).write_bytes(data)

    def upload_from_string(self, data: str, content_type: str | None = None) -> None:
        self.uploaded = data
        self.store[self.name] = data.encode("utf-8")

    def delete(self) -> None:
        self.deleted = True
        self.store.pop(self.name, None)


class FakeBucket:
    def __init__(self, objects: dict[str, bytes | None]) -> None:
        self.store = dict(objects)
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str) -> FakeBlob:
        if name not in self.blobs:
            self.blobs[name] = FakeBlob(self.store, name)
        return self.blobs[name]

    def list_blobs(self, prefix: str = ""):
        return [self.blob(name) for name in list(self.store) if name.startswith(prefix)]


class FakeClient:
    def __init__(self, objects: dict[str, bytes | None]) -> None:
        self.bucket_obj = FakeBucket(objects)

    def bucket(self, name: str) -> FakeBucket:
        return self.bucket_obj


def _staged(video: bytes, meta: dict) -> dict[str, bytes | None]:
    prefix = f"staging/{meta['slug']}/"
    return {
        f"{prefix}bili_metadata.json": json.dumps(meta).encode("utf-8"),
        f"{prefix}video.mp4": video,
        f"{prefix}cover-16x9.jpg": b"c16",
        f"{prefix}cover-4x3.jpg": b"c43",
    }


class BilibiliCloudTests(unittest.TestCase):
    def test_ws_line_present(self) -> None:
        self.assertIn("ws", bu.LINES)
        self.assertEqual(bu.LINES["ws"]["upcdn"], "ws")
        self.assertEqual(bu.LINES["ws"]["zone"], "cs")

    def test_build_execute_cmd_defaults(self) -> None:
        cmd = bc.build_execute_cmd(
            "gcloud",
            project="proj",
            region="us-west1",
            job="running-bili-upload",
            slug="2026-11-27-taper-week",
            bucket="my-bucket",
            line="ws",
            limit=6,
            wait=False,
            keep_staging=True,
        )
        self.assertEqual(
            cmd[:6],
            ["gcloud", "run", "jobs", "execute", "running-bili-upload", "--project"],
        )
        self.assertIn("--async", cmd)
        joined = " ".join(cmd)
        self.assertIn("BILI_SLUG=2026-11-27-taper-week", joined)
        self.assertIn("BILI_LINE=ws", joined)
        self.assertIn("BILI_KEEP_STAGING=1", joined)
        self.assertNotIn("BILI_RUN_ID=", joined)

    def test_should_leave_line_and_limit_unset_when_flags_omitted(self) -> None:
        args = bc.build_parser().parse_args(["upload", "--media-dir", "/tmp/episode"])
        self.assertIsNone(args.line)
        self.assertIsNone(args.limit)

    def test_prepare_metadata_and_stage_reuses_matching_gcs_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media, episode = _make_episode(Path(tmp))
            meta, video, c16, c43 = bc.prepare_metadata(media, episode)
            self.assertEqual(meta["title"], "测试视频")
            self.assertEqual(meta["video_bytes"], 15)
            self.assertEqual(meta["tags"], ["跑步", "马拉松", "破三", "测试", "日常"])

            copied: list[str] = []
            with (
                mock.patch.object(bc, "gcs_object_size", return_value=15),
                mock.patch.object(bc.subprocess, "run", side_effect=_gcs_runner(copied, {
                    "bili_metadata.json": meta["sha256"],
                })),
            ):
                reused = bc.stage_to_gcs(
                    "gcloud", "my-bucket", meta["slug"], meta, video, c16, c43, dry_run=False
                )

            self.assertTrue(reused)
            self.assertEqual(len(copied), 3)
            self.assertTrue(any(dst.startswith("gs://my-bucket/staging/") for dst in copied))
            self.assertFalse(any(dst.endswith("/video.mp4") for dst in copied))

    def test_should_reupload_video_when_staged_sha256_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media, episode = _make_episode(Path(tmp))
            meta, video, c16, c43 = bc.prepare_metadata(media, episode)
            copied: list[str] = []
            with (
                mock.patch.object(bc, "gcs_object_size", return_value=meta["video_bytes"]),
                mock.patch.object(bc.subprocess, "run", side_effect=_gcs_runner(copied, {
                    "bili_metadata.json": "0" * 64,
                    "metadata.json": "1" * 64,
                })),
            ):
                reused = bc.stage_to_gcs(
                    "gcloud", "my-bucket", meta["slug"], meta, video, c16, c43, dry_run=False
                )
            self.assertFalse(reused)
            self.assertTrue(any(
                dst.startswith("gs://my-bucket/staging/") and dst.endswith("/video.mp4") for dst in copied
            ))

    def test_should_reuse_video_when_only_youtube_metadata_sha_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media, episode = _make_episode(Path(tmp))
            meta, video, c16, c43 = bc.prepare_metadata(media, episode)
            copied: list[str] = []
            with (
                mock.patch.object(bc, "gcs_object_size", return_value=meta["video_bytes"]),
                mock.patch.object(bc.subprocess, "run", side_effect=_gcs_runner(copied, {
                    "metadata.json": meta["sha256"],
                })),
            ):
                reused = bc.stage_to_gcs(
                    "gcloud", "my-bucket", meta["slug"], meta, video, c16, c43, dry_run=False
                )
            self.assertTrue(reused)
            self.assertFalse(any(dst.endswith("/video.mp4") for dst in copied))

    def test_should_use_config_line_and_limit_when_flags_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media, episode = _make_episode(Path(tmp))
            args = bc.build_parser().parse_args([
                "upload",
                "--media-dir",
                str(media),
                "--episode-dir",
                str(episode),
                "--project",
                "proj",
                "--bucket",
                "bkt",
                "--dry-run",
            ])
            with (
                mock.patch.object(bc, "load_config", return_value={
                    "default_line": "qn",
                    "default_limit": 2,
                }),
                mock.patch.object(bc, "build_execute_cmd", wraps=bc.build_execute_cmd) as build,
            ):
                rc = bc.cmd_upload(args)
            self.assertEqual(rc, 0)
            self.assertEqual(build.call_args.kwargs["line"], "qn")
            self.assertEqual(build.call_args.kwargs["limit"], 2)
            self.assertRegex(build.call_args.kwargs["run_id"], r"^[0-9a-f]{32}$")
            self.assertFalse((media / "logs" / bc.RUN_RECORD).is_file())

    def test_should_let_explicit_line_and_limit_override_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media, episode = _make_episode(Path(tmp))
            args = bc.build_parser().parse_args([
                "upload",
                "--media-dir",
                str(media),
                "--episode-dir",
                str(episode),
                "--project",
                "proj",
                "--bucket",
                "bkt",
                "--line",
                "bda2",
                "--limit",
                "3",
                "--dry-run",
            ])
            with (
                mock.patch.object(bc, "load_config", return_value={
                    "default_line": "qn",
                    "default_limit": 2,
                }),
                mock.patch.object(bc, "build_execute_cmd", wraps=bc.build_execute_cmd) as build,
            ):
                rc = bc.cmd_upload(args)
            self.assertEqual(rc, 0)
            self.assertEqual(build.call_args.kwargs["line"], "bda2")
            self.assertEqual(build.call_args.kwargs["limit"], 3)

    def test_should_block_second_upload_when_previous_start_is_inflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "2026-11-27-taper-week"
            media.mkdir()
            bc.log_timeline.start(media, bu.STEP)
            args = bc.build_parser().parse_args(["upload", "--media-dir", str(media), "--dry-run"])
            with self.assertRaises(SystemExit) as ctx:
                bc.cmd_upload(args)
            self.assertIn("without END/FAIL", str(ctx.exception))

    def test_should_block_upload_when_bilibili_todo_is_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "2026-11-27-taper-week"
            media.mkdir()
            _write_todo(media, bilibili="done")
            args = bc.build_parser().parse_args(["upload", "--media-dir", str(media), "--dry-run"])
            with self.assertRaises(SystemExit) as ctx:
                bc.cmd_upload(args)
            self.assertIn("already done", str(ctx.exception))

    def test_should_allow_retry_when_previous_attempt_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media, episode = _make_episode(Path(tmp))
            bc.log_timeline.start(media, bu.STEP)
            bc.log_timeline.fail(media, bu.STEP, rc=1, note="boom")
            args = bc.build_parser().parse_args([
                "upload",
                "--media-dir",
                str(media),
                "--episode-dir",
                str(episode),
                "--project",
                "proj",
                "--bucket",
                "bkt",
                "--dry-run",
            ])
            with mock.patch.object(bc, "load_config", return_value={}):
                rc = bc.cmd_upload(args)
            self.assertEqual(rc, 0)

    def test_should_reject_result_when_run_id_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "2026-11-27-taper-week"
            _write_todo(media)
            bc.write_run_id(media, media.name, "expected-run")
            payload = {
                "slug": media.name,
                "status": "ok",
                "bvid": "BV1test",
                "url": "https://www.bilibili.com/video/BV1test",
                "run_id": "other-run",
            }
            rc = self._result(media, payload)
            self.assertEqual(rc, 1)
            self.assertFalse((media / "logs" / "timeline.txt").exists())
            self.assertNotEqual(bc.todo_list.load(media).get("bilibili"), "done")

    def test_should_fail_timeline_when_result_status_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "2026-11-27-taper-week"
            _write_todo(media)
            bc.write_run_id(media, media.name, "run-1")
            payload = {
                "slug": media.name,
                "status": "error",
                "error": "upos down",
                "run_id": "run-1",
                "bvid": "",
            }
            rc = self._result(media, payload)
            self.assertEqual(rc, 1)
            text = (media / "logs" / "timeline.txt").read_text(encoding="utf-8")
            self.assertIn("FAIL", text)
            self.assertIn("bilibili-upload", text)
            self.assertIn("upos down", text)
            self.assertNotIn("END", text)
            self.assertNotEqual(bc.todo_list.load(media).get("bilibili"), "done")

    def test_should_not_fail_inflight_upload_when_error_result_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "2026-11-27-taper-week"
            _write_todo(media)
            bc.log_timeline.start(media, bu.STEP)
            bc.write_run_id(media, media.name, "current-run")
            payload = {
                "slug": media.name,
                "status": "error",
                "error": "old failure",
                "run_id": "old-run",
            }
            rc = self._result(media, payload)
            self.assertEqual(rc, 1)
            text = (media / "logs" / "timeline.txt").read_text(encoding="utf-8")
            self.assertIn("START", text)
            self.assertNotIn("FAIL", text)
            self.assertNotEqual(bc.todo_list.load(media).get("bilibili"), "done")

    def test_should_reject_result_when_bvid_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "2026-11-27-taper-week"
            _write_todo(media)
            bc.write_run_id(media, media.name, "run-1")
            payload = {"slug": media.name, "status": "ok", "bvid": "  ", "run_id": "run-1"}
            rc = self._result(media, payload)
            self.assertEqual(rc, 1)
            self.assertNotEqual(bc.todo_list.load(media).get("bilibili"), "done")

    def test_should_reject_result_when_slug_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "2026-11-27-taper-week"
            _write_todo(media)
            payload = {
                "slug": "other-slug",
                "status": "ok",
                "bvid": "BV1test",
                "run_id": "run-1",
            }
            rc = self._result(media, payload)
            self.assertEqual(rc, 1)
            self.assertFalse((media / "logs" / "timeline.txt").exists())

    def test_should_mark_bilibili_done_when_result_matches_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "2026-11-27-taper-week"
            _write_todo(media)
            bc.write_run_id(media, media.name, "run-1")
            payload = {
                "slug": media.name,
                "status": "ok",
                "bvid": "BV1test",
                "url": "https://www.bilibili.com/video/BV1test",
                "run_id": "run-1",
                "line": "ws",
            }
            rc = self._result(media, payload)
            self.assertEqual(rc, 0)
            self.assertEqual(bc.todo_list.load(media).get("bilibili"), "done")
            text = (media / "logs" / "timeline.txt").read_text(encoding="utf-8")
            self.assertIn("END", text)
            self.assertIn("BV1test", text)

    def _result(self, media: Path, payload: dict) -> int:
        args = bc.build_parser().parse_args([
            "result",
            "--media-dir",
            str(media),
            "--bucket",
            "bkt",
        ])
        proc = mock.Mock(returncode=0, stdout=json.dumps(payload))
        with (
            mock.patch.object(bc, "find_gcloud", return_value="gcloud"),
            mock.patch.object(bc, "load_config", return_value={}),
            mock.patch.object(bc.subprocess, "run", return_value=proc),
        ):
            return bc.cmd_result(args)


class BilibiliJobTests(unittest.TestCase):
    def test_should_reject_staged_video_when_sha256_mismatches(self) -> None:
        video = b"video-bytes-123"
        meta = {
            "slug": "slug-sha",
            "sha256": "ab" * 32,
            "video_bytes": len(video),
            "video_filename": "../evil.mp4",
        }
        client = FakeClient(_staged(video, meta))
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "slug-sha"
            work.mkdir()
            with self.assertRaises(RuntimeError) as ctx:
                bili_job.download_staging(client, "bucket", "slug-sha", work)
            self.assertIn("SHA-256", str(ctx.exception))
            self.assertTrue((work / "video.mp4").is_file())
            self.assertFalse((work.parent / "evil.mp4").exists())

    def test_should_download_video_to_fixed_name(self) -> None:
        video = b"video-bytes-123"
        meta = {
            "slug": "slug-ok",
            "sha256": hashlib.sha256(video).hexdigest(),
            "video_bytes": len(video),
            "video_filename": "../evil.mp4",
            "title": "测试视频",
        }
        client = FakeClient(_staged(video, meta))
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "slug-ok"
            work.mkdir()
            loaded, video_path, cover16, cover43 = bili_job.download_staging(
                client, "bucket", "slug-ok", work
            )
            self.assertEqual(video_path, work / "video.mp4")
            self.assertEqual(video_path.read_bytes(), video)
            self.assertEqual(cover16, work / "cover-16x9.jpg")
            self.assertEqual(cover43, work / "cover-4x3.jpg")
            self.assertEqual(loaded["title"], "测试视频")
            self.assertFalse((work.parent / "evil.mp4").exists())

    def test_should_submit_episode_upload_with_tid_and_copyright(self) -> None:
        video = b"video-bytes-123"
        slug = "slug-submit"
        meta = {
            "slug": slug,
            "title": "测试视频",
            "description": "测试简介",
            "tags": ["跑步", "马拉松"],
            "tid": 137,
            "copyright": 2,
            "run_id": "meta-run",
            "sha256": hashlib.sha256(video).hexdigest(),
            "video_bytes": len(video),
            "video_filename": "../evil.mp4",
        }
        client = FakeClient(_staged(video, meta))
        upload_result = {"bvid": "BV1job", "aid": 9, "url": "https://www.bilibili.com/video/BV1job"}
        with (
            mock.patch.object(bili_job.storage, "Client", return_value=client),
            mock.patch.object(bili_job.bu, "load_cookies", return_value={"bili_jct": "jct"}),
            mock.patch.object(bili_job.bu, "upload_episode", return_value=upload_result) as upload,
        ):
            rc = bili_job.main([
                "--slug",
                slug,
                "--bucket",
                "bkt",
                "--cookie-file",
                "/tmp/cookies.json",
                "--line",
                "ws",
                "--limit",
                "4",
                "--keep-staging",
            ])
        self.assertEqual(rc, 0)
        ready = upload.call_args.args[0]
        self.assertIsInstance(ready, bu.EpisodeUpload)
        self.assertEqual(ready.title, "测试视频")
        self.assertEqual(ready.description, "测试简介")
        self.assertEqual(ready.tags, ["跑步", "马拉松"])
        self.assertEqual(ready.pack_state, "done")
        self.assertEqual(ready.video.name, "video.mp4")
        self.assertNotIn("evil.mp4", str(ready.video))
        self.assertEqual(upload.call_args.kwargs["line"], "ws")
        self.assertEqual(upload.call_args.kwargs["limit"], 4)
        self.assertEqual(upload.call_args.kwargs["tid"], 137)
        self.assertEqual(upload.call_args.kwargs["copyright"], 2)
        result_blob = client.bucket_obj.blobs[f"results/{slug}-bili.json"]
        payload = json.loads(result_blob.uploaded or "")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["bvid"], "BV1job")
        self.assertEqual(payload["run_id"], "meta-run")
        self.assertEqual(payload["slug"], slug)

    def test_should_write_error_result_when_upload_fails(self) -> None:
        video = b"video-bytes-123"
        slug = "slug-err"
        meta = {
            "slug": slug,
            "title": "测试视频",
            "description": "测试简介",
            "tags": ["跑步"],
            "tid": 238,
            "copyright": 1,
            "run_id": "meta-run",
            "sha256": hashlib.sha256(video).hexdigest(),
            "video_bytes": len(video),
        }
        client = FakeClient(_staged(video, meta))
        with (
            mock.patch.object(bili_job.storage, "Client", return_value=client),
            mock.patch.object(bili_job.bu, "load_cookies", return_value={"bili_jct": "jct"}),
            mock.patch.object(bili_job.bu, "upload_episode", side_effect=RuntimeError("upos down")),
            self.assertRaises(RuntimeError),
        ):
            bili_job.main([
                "--slug",
                slug,
                "--bucket",
                "bkt",
                "--cookie-file",
                "/tmp/cookies.json",
                "--keep-staging",
            ])
        result_blob = client.bucket_obj.blobs[f"results/{slug}-bili.json"]
        payload = json.loads(result_blob.uploaded or "")
        self.assertEqual(payload["slug"], slug)
        self.assertEqual(payload["status"], "error")
        self.assertIn("upos down", payload["error"])
        self.assertEqual(payload["run_id"], "meta-run")
        self.assertIn("finished_at", payload)

    def test_should_keep_staging_when_youtube_metadata_exists(self) -> None:
        client = FakeClient({
            "staging/slug/video.mp4": b"video",
            "staging/slug/metadata.json": b"{}",
            "staging/slug/bili_metadata.json": b"{}",
        })
        bili_job.cleanup_staging(client, "bkt", "slug")
        self.assertIn("staging/slug/video.mp4", client.bucket_obj.store)
        self.assertTrue(all(not blob.deleted for blob in client.bucket_obj.blobs.values()))

    def test_should_delete_staging_when_youtube_metadata_is_absent(self) -> None:
        client = FakeClient({
            "staging/slug/video.mp4": b"video",
            "staging/slug/bili_metadata.json": b"{}",
        })
        bili_job.cleanup_staging(client, "bkt", "slug")
        self.assertFalse(client.bucket_obj.store)


if __name__ == "__main__":
    unittest.main()
