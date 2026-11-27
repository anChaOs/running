#!/usr/bin/env python3
"""bilibili_upload 的本地单测。HTTP 全部用假 Session，不访问 B 站。"""

from __future__ import annotations

import base64
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import requests


TOOLS_DIR = Path(__file__).resolve().parents[1]
PUB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(PUB_DIR))

import bilibili_upload  # noqa: E402
import todo_list  # noqa: E402


SAMPLE_PLAN = """\
# 测试计划

## 标题

上马前，LSD没跑够能行吗？

## 简介

### B 站

个人视频制作来自：https://github.com/anChaOs/running

B 站简介。

### YouTube

个人视频制作来自：github.com/anChaOs/running

YouTube 简介不要混进 B 站。

## 标签

B 站（5–8 个，不要堆）：

```text
#跑步 #马拉松 #上海马拉松
```

YouTube 标签：

```text
跑步, 别收这个, 马拉松
```
"""

QUOTE_PLAN = SAMPLE_PLAN.replace(
    "上马前，LSD没跑够能行吗？\n",
    "> 发这个：上马前，LSD没跑够能行吗？\n",
    1,
)

INLINE_TAG_PLAN = """\
# 测试计划

## 标题

边跑边说

## 简介

### B 站

一行简介。

## 标签

B 站：#跑步 #马拉松

YouTube 标签：

```text
别收这个, 跑步
```
"""


class FakeResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._json = {} if json_data is None else json_data
        self.headers = headers or {}
        self.text = json.dumps(self._json, ensure_ascii=False)

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class ExplodingSession:
    def post(self, *args: object, **kwargs: object) -> FakeResponse:
        raise AssertionError("dry-run must not POST")

    def get(self, *args: object, **kwargs: object) -> FakeResponse:
        raise AssertionError("dry-run must not GET")

    def put(self, *args: object, **kwargs: object) -> FakeResponse:
        raise AssertionError("dry-run must not PUT")


class CoverFailSession:
    def __init__(self) -> None:
        self.posts = 0

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.posts += 1
        return FakeResponse(json_data={"code": -400, "message": "bad cover", "data": None})

    def get(self, *args: object, **kwargs: object) -> FakeResponse:
        raise AssertionError("cover failure must stop before preupload")

    def put(self, *args: object, **kwargs: object) -> FakeResponse:
        raise AssertionError("cover failure must stop before chunks")


class ScriptedUpos:
    """封面两次、preupload、init、分片（第一次 PUT 失败）、complete、submit。"""

    def __init__(self, cover_16x9: bytes, cover_4x3: bytes) -> None:
        self.cover_16x9 = cover_16x9
        self.cover_4x3 = cover_4x3
        self.cover_bodies: list[bytes] = []
        self.cover_urls: list[str] = []
        self.pre_params: dict | None = None
        self.put_params: list[dict] = []
        self.put_headers: list[dict] = []
        self.puts = 0
        self.complete: dict | None = None
        self.submit_json: dict | None = None
        self.submit_params: dict | None = None
        self._lock = threading.Lock()

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        if url.endswith("/x/vu/web/cover/up"):
            form = kwargs["data"]
            assert isinstance(form, dict)
            encoded = str(form["cover"]).split(",", 1)[1]
            body = base64.b64decode(encoded)
            self.cover_bodies.append(body)
            hosted = f"https://archive.biliimg.com/{len(self.cover_bodies)}.jpg"
            self.cover_urls.append(hosted)
            return FakeResponse(json_data={"code": 0, "data": {"url": hosted}})
        if "uploads" in url:
            return FakeResponse(json_data={"OK": 1, "upload_id": "up-1"})
        if "x/vu/web/add/v3" in url:
            self.submit_json = kwargs["json"]  # type: ignore[assignment]
            self.submit_params = kwargs["params"]  # type: ignore[assignment]
            return FakeResponse(json_data={"code": 0, "data": {"bvid": "BV1test", "aid": 9}})
        self.complete = {"url": url, "params": kwargs.get("params"), "json": kwargs.get("json")}
        return FakeResponse(json_data={"OK": 1})

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        if "preupload" not in url:
            raise AssertionError(url)
        self.pre_params = kwargs["params"]  # type: ignore[assignment]
        return FakeResponse(
            json_data={
                "OK": 1,
                "auth": "auth-token",
                "endpoint": "//upos-cs-upcdnbda2.bilivideo.com",
                "upos_uri": "upos://ugcfx/n220101abcdef.mp4",
                "biz_id": 42,
                "chunk_size": 4,
            }
        )

    def put(self, url: str, **kwargs: object) -> FakeResponse:
        with self._lock:
            self.puts += 1
            attempt = self.puts
            params = kwargs.get("params")
            headers = kwargs.get("headers")
            if isinstance(params, dict):
                self.put_params.append(params)
            if isinstance(headers, dict):
                self.put_headers.append(headers)
        if attempt == 1:
            raise requests.ConnectionError("reset")
        return FakeResponse(headers={"ETag": '"abc"'})


def _mark_through(media: Path, last: str) -> None:
    order = (
        "ingest",
        "edl",
        "hud-record",
        "layout",
        "preview",
        "subs",
        "final-export",
        "final-qc",
        "pack-upload",
    )
    for step in order:
        if step == "subs":
            todo_list.mark(media, "subs", "waiting-review")
            todo_list.mark(media, "subs", "aligned")
            todo_list.mark(media, "subs", "confirmed", confirmed=True)
        else:
            todo_list.mark(media, step, "done")
        if step == last:
            return


def _write_cookie(path: Path, *, csrf: str = "jct-token", expires: int | None = None) -> None:
    cookies: list[dict[str, object]] = [
        {"name": "SESSDATA", "value": "sess-value"},
        {"name": "bili_jct", "value": csrf},
        {"name": "DedeUserID", "value": "123"},
    ]
    if expires is not None:
        for item in cookies:
            if item["name"] in ("SESSDATA", "bili_jct"):
                item["expires"] = expires
    payload = {"cookie_info": {"cookies": cookies}}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_episode(
    root: Path,
    *,
    plan: str = SAMPLE_PLAN,
    video: bytes = b"0123456789",
    cover_16x9: bytes = b"wide-jpeg",
    cover_4x3: bytes = b"tall-jpeg",
    pack_through: str | None = "pack-upload",
) -> tuple[Path, Path, Path]:
    media = root / "2026-11-24-lsd-short"
    episode = root / "episode"
    upload = media / "upload"
    upload.mkdir(parents=True)
    episode.mkdir()
    (episode / "plan.md").write_text(plan, encoding="utf-8")
    (upload / "上马前.mp4").write_bytes(video)
    (upload / "cover-16x9-1920x1080.jpg").write_bytes(cover_16x9)
    (upload / "cover-4x3-1920x1440.jpg").write_bytes(cover_4x3)
    cookie = root / "cookies.json"
    _write_cookie(cookie)
    if pack_through:
        _mark_through(media, pack_through)
    return media, episode, cookie


class BilibiliUploadTests(unittest.TestCase):
    def test_should_parse_title_desc_and_bilibili_tags_from_plan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plan = Path(td) / "plan.md"
            plan.write_text(SAMPLE_PLAN, encoding="utf-8")
            parsed = bilibili_upload.parse_plan_bilibili(plan)
        self.assertEqual(parsed["title"], "上马前，LSD没跑够能行吗？")
        self.assertIn("https://github.com/anChaOs/running", parsed["description"])
        self.assertNotIn("YouTube 简介不要混进 B 站", parsed["description"])
        self.assertEqual(parsed["tags"], ["跑步", "马拉松", "上海马拉松"])

    def test_should_parse_title_when_plan_uses_fa_zhege_line(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            episode = Path(td)
            (episode / "plan.md").write_text(QUOTE_PLAN, encoding="utf-8")
            parsed = bilibili_upload.parse_plan_bilibili(episode / "plan.md")
        self.assertEqual(parsed["title"], "上马前，LSD没跑够能行吗？")

    def test_should_parse_inline_bilibili_tags_and_ignore_youtube_fence(self) -> None:
        tags = bilibili_upload.parse_bilibili_tags_from_markdown(INLINE_TAG_PLAN)
        self.assertEqual(tags, ["跑步", "马拉松"])

    def test_should_raise_when_bilibili_section_missing(self) -> None:
        with self.assertRaises(ValueError):
            bilibili_upload.parse_bilibili_desc("## 标题\n\n只有标题\n")

    def test_should_count_unicode_code_points_and_reject_over_2000(self) -> None:
        exactly = "😀" * 2000
        self.assertEqual(bilibili_upload.check_bilibili_desc_length(exactly), 2000)
        self.assertGreater(len(exactly.encode("utf-8")), 2000)
        with self.assertRaises(ValueError) as ctx:
            bilibili_upload.check_bilibili_desc_length("字" * 2001)
        self.assertIn("2001", str(ctx.exception))

    def test_should_put_16x9_on_cover_and_4x3_on_cover43(self) -> None:
        payload = bilibili_upload.build_submit_payload(
            title="标题",
            desc="简介",
            tag="跑步,马拉松",
            cover="https://img/16x9.jpg",
            cover43="https://img/4x3.jpg",
            filename="n220101abcdef",
            biz_id=42,
            csrf="jct-token",
        )
        self.assertEqual(payload["cover"], "https://img/16x9.jpg")
        self.assertEqual(payload["cover43"], "https://img/4x3.jpg")
        self.assertEqual(payload["tid"], 238)
        self.assertEqual(payload["copyright"], 1)
        self.assertEqual(payload["tag"], "跑步,马拉松")
        self.assertEqual(payload["csrf"], "jct-token")
        self.assertEqual(payload["videos"][0]["filename"], "n220101abcdef")
        self.assertEqual(payload["videos"][0]["cid"], 42)

        form = bilibili_upload.build_cover_form(b"jpeg-bytes", "jct-token")
        self.assertTrue(form["cover"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(base64.b64decode(form["cover"].split(",", 1)[1]), b"jpeg-bytes")
        self.assertEqual(form["csrf"], "jct-token")

    def test_should_map_line_flag_onto_preupload_upcdn(self) -> None:
        for line in ("bda2", "bldsa", "tx", "qn"):
            with self.subTest(line=line):
                params = bilibili_upload.build_preupload_params("a.mp4", 3, line)
                self.assertEqual(params["upcdn"], line)
                self.assertEqual(params["r"], "upos")
                self.assertEqual(params["profile"], "ugcupos/bup")
        with self.assertRaises(ValueError):
            bilibili_upload.build_preupload_params("a.mp4", 3, "nope")

    def test_should_print_checks_and_skip_logs_when_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media, episode, cookie = _build_episode(root)
            args = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                    "--dry-run",
                ]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = bilibili_upload.run(args, session=ExplodingSession())
            text = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("上马前，LSD没跑够能行吗？", text)
            self.assertIn("cover-16x9-1920x1080.jpg", text)
            self.assertIn("cover-4x3-1920x1440.jpg", text)
            self.assertIn("pack-upload: done", text)
            self.assertIn("cookie: ok", text)
            self.assertNotIn("sess-value", text)
            self.assertNotIn("jct-token", text)
            self.assertFalse((media / "logs" / "timeline.txt").exists())
            self.assertNotEqual(todo_list.load(media).get("bilibili"), "done")

    def test_should_report_pack_upload_not_done_without_writing_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media, episode, cookie = _build_episode(root, pack_through="final-qc")
            args = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                    "--dry-run",
                ]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = bilibili_upload.run(args, session=ExplodingSession())
            self.assertEqual(rc, 1)
            self.assertIn("pack-upload: pending", buf.getvalue())
            self.assertFalse((media / "logs" / "timeline.txt").exists())

            real_args = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                ]
            )
            err = io.StringIO()
            with redirect_stderr(err):
                real_rc = bilibili_upload.run(real_args, session=ExplodingSession())
            self.assertEqual(real_rc, 1)
            self.assertIn("pack-upload is pending", err.getvalue())
            self.assertFalse((media / "logs" / "timeline.txt").exists())
            self.assertNotEqual(todo_list.load(media).get("bilibili"), "done")

    def test_should_refuse_dry_run_when_description_exceeds_2000(self) -> None:
        long_plan = SAMPLE_PLAN.replace(
            "个人视频制作来自：https://github.com/anChaOs/running\n\nB 站简介。",
            "字" * 2001,
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media, episode, cookie = _build_episode(root, plan=long_plan)
            args = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                    "--dry-run",
                ]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = bilibili_upload.run(args, session=ExplodingSession())
            text = buf.getvalue()
            self.assertEqual(rc, 1)
            self.assertIn("2001", text)
            self.assertFalse((media / "logs" / "timeline.txt").exists())

    def test_should_submit_dual_covers_and_retry_failed_chunk(self) -> None:
        cover_16x9 = b"wide-jpeg"
        cover_4x3 = b"tall-jpeg"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media, episode, cookie = _build_episode(root, cover_16x9=cover_16x9, cover_4x3=cover_4x3)
            session = ScriptedUpos(cover_16x9, cover_4x3)
            args = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                    "-l",
                    "tx",
                    "--limit",
                    "2",
                    "--retries",
                    "2",
                ]
            )
            out = io.StringIO()
            with (
                mock.patch("bilibili_upload.time.sleep") as sleep,
                redirect_stdout(out),
                redirect_stderr(io.StringIO()),
            ):
                rc = bilibili_upload.run(args, session=session)
            self.assertEqual(rc, 0)
            self.assertIn("BV1test", out.getvalue())
            self.assertIn("https://www.bilibili.com/video/BV1test", out.getvalue())
            self.assertTrue(sleep.called)
            self.assertEqual(session.cover_bodies, [cover_16x9, cover_4x3])
            self.assertIsNotNone(session.pre_params)
            assert session.pre_params is not None
            self.assertEqual(session.pre_params["upcdn"], "tx")
            self.assertEqual(session.pre_params["name"], "上马前.mp4")
            self.assertEqual(session.puts, 4)
            first_chunk = next(item for item in session.put_params if item["start"] == "0")
            self.assertEqual(first_chunk["end"], "4")
            self.assertEqual(first_chunk["partNumber"], "1")
            self.assertEqual(first_chunk["uploadId"], "up-1")
            self.assertTrue(session.put_headers)
            self.assertNotIn("Cookie", session.put_headers[0])
            self.assertEqual(session.put_headers[0].get("X-Upos-Auth"), "auth-token")
            self.assertIsNotNone(session.submit_json)
            assert session.submit_json is not None
            self.assertEqual(session.submit_json["cover"], session.cover_urls[0])
            self.assertEqual(session.submit_json["cover43"], session.cover_urls[1])
            self.assertEqual(session.submit_json["tid"], 238)
            self.assertEqual(session.submit_json["copyright"], 1)
            self.assertEqual(session.submit_json["videos"][0]["filename"], "n220101abcdef")
            self.assertEqual(session.submit_params, {"csrf": "jct-token"})
            assert session.complete is not None
            parts = session.complete["json"]["parts"]
            self.assertEqual([part["partNumber"] for part in parts], [1, 2, 3])
            self.assertTrue(all(part["eTag"] == "abc" for part in parts))
            self.assertEqual(todo_list.load(media)["bilibili"], "done")
            timeline = (media / "logs" / "timeline.txt").read_text(encoding="utf-8")
            self.assertIn("END", timeline)
            self.assertIn("https://www.bilibili.com/video/BV1test", timeline)
            self.assertNotIn("FAIL", timeline)
            self.assertNotIn("sess-value", timeline)

    def test_should_refuse_second_upload_when_bilibili_already_done(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media, episode, cookie = _build_episode(root)
            todo_list.mark(media, "bilibili", "done")
            args = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                ]
            )
            err = io.StringIO()
            with redirect_stderr(err):
                rc = bilibili_upload.run(args, session=ExplodingSession())
            self.assertEqual(rc, 1)
            self.assertIn("already done", err.getvalue())
            self.assertFalse((media / "logs" / "timeline.txt").exists())

    def test_should_record_fail_when_cover_upload_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media, episode, cookie = _build_episode(root)
            session = CoverFailSession()
            args = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                ]
            )
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                rc = bilibili_upload.run(args, session=session)
            self.assertEqual(rc, 1)
            self.assertEqual(session.posts, 1)
            self.assertIn("bad cover", err.getvalue())
            self.assertNotEqual(todo_list.load(media).get("bilibili"), "done")
            timeline = (media / "logs" / "timeline.txt").read_text(encoding="utf-8")
            self.assertIn("FAIL", timeline)
            self.assertIn("bilibili-upload", timeline)
            self.assertNotIn("END", timeline)
            again = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                    "--dry-run",
                ]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                again_rc = bilibili_upload.run(again, session=ExplodingSession())
            self.assertEqual(again_rc, 0)
            self.assertNotIn("refusing to submit again", buf.getvalue())

    def test_should_treat_retries_as_extra_attempts_after_the_first_put(self) -> None:
        def chunk(session: object, retries: int) -> dict:
            return bilibili_upload.put_chunk(
                session,
                url="https://up.example/a.mp4",
                auth="auth-token",
                upload_id="up-1",
                chunks=1,
                total=4,
                index=0,
                start=0,
                end=4,
                data=b"0123",
                retries=retries,
            )

        class Once:
            def __init__(self) -> None:
                self.puts = 0

            def put(self, url: str, **kwargs: object) -> FakeResponse:
                self.puts += 1
                if self.puts == 1:
                    raise requests.ConnectionError("reset")
                return FakeResponse(headers={"ETag": '"abc"'})

        zero = Once()
        with mock.patch("bilibili_upload.time.sleep") as sleep:
            with self.assertRaises(requests.ConnectionError):
                chunk(zero, 0)
        self.assertEqual(zero.puts, 1)
        self.assertFalse(sleep.called)

        one = Once()
        with mock.patch("bilibili_upload.time.sleep") as sleep:
            part = chunk(one, 1)
        self.assertEqual(one.puts, 2)
        self.assertEqual(part["eTag"], "abc")
        self.assertTrue(sleep.called)

    def test_should_retry_upos_complete_after_a_transport_error(self) -> None:
        class Merge:
            def __init__(self) -> None:
                self.posts = 0

            def post(self, url: str, **kwargs: object) -> FakeResponse:
                self.posts += 1
                if self.posts == 1:
                    raise requests.ConnectionError("reset")
                return FakeResponse(json_data={"OK": 1})

        session = Merge()
        with mock.patch("bilibili_upload.time.sleep") as sleep:
            bilibili_upload.complete_upload(
                session,
                url="https://up.example/a.mp4",
                auth="auth-token",
                filename="a.mp4",
                upload_id="up-1",
                biz_id=42,
                parts=[{"partNumber": 1, "eTag": "abc"}],
                retries=1,
            )
        self.assertEqual(session.posts, 2)
        self.assertTrue(sleep.called)

    def test_should_include_http_body_when_cover_status_is_not_200(self) -> None:
        class Boom:
            def post(self, url: str, **kwargs: object) -> FakeResponse:
                return FakeResponse(status_code=500, json_data={"message": "boom"})

        with self.assertRaises(RuntimeError) as ctx:
            bilibili_upload.upload_cover(Boom(), b"jpeg", {"bili_jct": "jct-token"})
        text = str(ctx.exception)
        self.assertIn("HTTP 500", text)
        self.assertIn("boom", text)

    def test_should_stop_when_preupload_or_submit_code_is_not_success(self) -> None:
        class PreFail:
            def get(self, url: str, **kwargs: object) -> FakeResponse:
                return FakeResponse(json_data={"OK": 0, "message": "no auth"})

        with self.assertRaises(RuntimeError) as ctx:
            bilibili_upload.preupload(PreFail(), "a.mp4", 3, "bda2", {"bili_jct": "jct-token"})
        self.assertIn("no auth", str(ctx.exception))

        class SubmitFail:
            def post(self, url: str, **kwargs: object) -> FakeResponse:
                return FakeResponse(json_data={"code": 21012, "message": "标题过长"})

        with self.assertRaises(RuntimeError) as ctx:
            bilibili_upload.submit_video(
                SubmitFail(),
                cookies={"bili_jct": "jct-token"},
                title="标题",
                desc="简介",
                tags=["跑步"],
                cover="https://img/16x9.jpg",
                cover43="https://img/4x3.jpg",
                filename="n220101abcdef",
                biz_id=42,
            )
        self.assertIn("21012", str(ctx.exception))
        self.assertIn("标题过长", str(ctx.exception))

    def test_should_reject_long_title_too_many_tags_and_expired_cookie_before_upload(self) -> None:
        long_title = SAMPLE_PLAN.replace("上马前，LSD没跑够能行吗？\n", ("字" * 81) + "\n", 1)
        many_tags = SAMPLE_PLAN.replace(
            "#跑步 #马拉松 #上海马拉松",
            " ".join(f"#标{i}" for i in range(11)),
        )
        long_tag = SAMPLE_PLAN.replace("#跑步 #马拉松 #上海马拉松", "#" + ("字" * 21))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media, episode, cookie = _build_episode(root, plan=long_title)
            self._assert_dry_run_problem(media, episode, cookie, "81")
            cases = (
                ("tags", many_tags, "tag count is 11", None),
                ("taglen", long_tag, "21", None),
                ("expired", SAMPLE_PLAN, "cookie expired", 1_700_000_000),
            )
            for name, plan, needle, expires in cases:
                folder = root / name
                folder.mkdir()
                media, episode, cookie = _build_episode(folder, plan=plan)
                if expires is not None:
                    cookie = folder / "expired.json"
                    _write_cookie(cookie, expires=expires)
                self._assert_dry_run_problem(media, episode, cookie, needle)
        self.assertEqual(bilibili_upload.check_bilibili_title("字" * 80), 80)
        bilibili_upload.check_bilibili_tags(["字" * 20] * 10)

    def _assert_dry_run_problem(self, media: Path, episode: Path, cookie: Path, needle: str) -> None:
        args = bilibili_upload.build_parser().parse_args(
            [
                "--media-dir",
                str(media),
                "--episode-dir",
                str(episode),
                "--cookie",
                str(cookie),
                "--dry-run",
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bilibili_upload.run(args, session=ExplodingSession())
        self.assertEqual(rc, 1)
        self.assertIn(needle, buf.getvalue())
        self.assertFalse((media / "logs" / "timeline.txt").exists())

    def test_should_print_bvid_and_refuse_a_second_submit_when_todo_mark_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media, episode, cookie = _build_episode(root)
            session = ScriptedUpos(b"wide-jpeg", b"tall-jpeg")
            args = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                    "--limit",
                    "1",
                    "--retries",
                    "2",
                ]
            )
            out = io.StringIO()
            err = io.StringIO()
            with (
                mock.patch("bilibili_upload.todo_list.mark", side_effect=OSError("disk full")),
                mock.patch("bilibili_upload.time.sleep"),
                redirect_stdout(out),
                redirect_stderr(err),
            ):
                rc = bilibili_upload.run(args, session=session)
            self.assertEqual(rc, 1)
            self.assertIn("BV1test", out.getvalue())
            self.assertIn("https://www.bilibili.com/video/BV1test", out.getvalue())
            self.assertIn("todo mark failed", err.getvalue())
            self.assertNotEqual(todo_list.load(media).get("bilibili"), "done")
            timeline = (media / "logs" / "timeline.txt").read_text(encoding="utf-8")
            self.assertIn("END", timeline)
            self.assertIn("BV1test", timeline)

            again = bilibili_upload.build_parser().parse_args(
                [
                    "--media-dir",
                    str(media),
                    "--episode-dir",
                    str(episode),
                    "--cookie",
                    str(cookie),
                ]
            )
            err2 = io.StringIO()
            with redirect_stderr(err2):
                again_rc = bilibili_upload.run(again, session=ExplodingSession())
            self.assertEqual(again_rc, 1)
            self.assertIn("refusing to submit again", err2.getvalue())
            self.assertIn("BV1test", err2.getvalue())

    def test_should_keep_login_cookie_header_when_session_jar_has_other_cookies(self) -> None:
        seen: list[dict[str, str]] = []

        class Adapter(requests.adapters.HTTPAdapter):
            def send(self, request: requests.PreparedRequest, **kwargs: object) -> requests.Response:
                seen.append({key: str(value) for key, value in request.headers.items()})
                response = requests.Response()
                response.status_code = 200
                response.url = request.url
                response.raw = None  # type: ignore[assignment]
                response._content = b'{"code":0,"data":{"url":"https://img.example/a.jpg"}}'
                return response

        session = requests.Session()
        session.cookies.set("bili_ticket", "intruder", domain=".bilibili.com", path="/")
        session.mount("https://", Adapter())
        cookies = {
            "SESSDATA": "abc%2Cdef",
            "bili_jct": "jct-token",
            "DedeUserID": "123",
        }
        bilibili_upload.upload_cover(session, b"wide", cookies)
        bilibili_upload.upload_cover(session, b"tall", cookies)
        self.assertEqual(len(seen), 2)
        for headers in seen:
            cookie_header = headers["Cookie"]
            self.assertIn("SESSDATA=abc%2Cdef", cookie_header)
            self.assertIn("bili_jct=jct-token", cookie_header)
            self.assertIn("DedeUserID=123", cookie_header)
            self.assertNotIn("bili_ticket", cookie_header)
            self.assertEqual(
                headers["Referer"],
                "https://member.bilibili.com/platform/upload/video/frame",
            )
            self.assertEqual(headers["Origin"], "https://member.bilibili.com")
            self.assertIn("Mozilla/5.0", headers["User-Agent"])

    def test_should_read_one_chunk_and_put_it_on_a_session_that_is_not_shared(self) -> None:
        class LocalSession(requests.Session):
            gate = threading.Lock()
            inflight: dict[int, int] = {}
            bad: list[int] = []

            def __init__(self) -> None:
                super().__init__()
                self.puts = 0
                self.closed = False

            def put(self, url: str, **kwargs: object) -> FakeResponse:
                ident = id(self)
                with LocalSession.gate:
                    LocalSession.inflight[ident] = LocalSession.inflight.get(ident, 0) + 1
                    if LocalSession.inflight[ident] > 1:
                        LocalSession.bad.append(ident)
                try:
                    time.sleep(0.02)
                    self.puts += 1
                    return FakeResponse(headers={"ETag": '"abc"'})
                finally:
                    with LocalSession.gate:
                        LocalSession.inflight[ident] -= 1

            def close(self) -> None:
                self.closed = True
                super().close()

        LocalSession.inflight = {}
        LocalSession.bad = []
        reads: list[tuple[int, int]] = []
        real_read = bilibili_upload._read_range

        def spy(path: Path, start: int, end: int) -> bytes:
            reads.append((start, end))
            self.assertLessEqual(end - start, 4)
            return real_read(path, start, end)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "v.mp4"
            path.write_bytes(b"0123456789abcdef")
            parent = LocalSession()
            created: list[LocalSession] = []

            def factory() -> LocalSession:
                item = LocalSession()
                created.append(item)
                return item

            with (
                mock.patch("bilibili_upload._new_chunk_session", side_effect=factory),
                mock.patch("bilibili_upload._read_range", spy),
            ):
                parts = bilibili_upload.upload_chunks(
                    parent,
                    path=path,
                    url="https://up.example/v.mp4",
                    auth="auth-token",
                    upload_id="up-1",
                    chunk_size=4,
                    limit=3,
                    retries=0,
                )
        self.assertEqual([part["partNumber"] for part in parts], [1, 2, 3, 4])
        self.assertEqual(parent.puts, 0)
        self.assertFalse(parent.closed)
        self.assertEqual(len(created), 3)
        self.assertEqual(sum(item.puts for item in created), 4)
        self.assertEqual(LocalSession.bad, [])
        self.assertTrue(all(item.closed for item in created))
        self.assertEqual(sorted(reads), [(0, 4), (4, 8), (8, 12), (12, 16)])

    def test_should_put_custom_tid_and_copyright_on_submit(self) -> None:
        class SubmitSession:
            def __init__(self) -> None:
                self.payload: dict | None = None

            def post(self, url: str, **kwargs: object) -> FakeResponse:
                payload = kwargs.get("json")
                self.payload = payload if isinstance(payload, dict) else None
                return FakeResponse(json_data={"code": 0, "data": {"bvid": "BV1tid", "aid": 3}})

        session = SubmitSession()
        bilibili_upload.submit_video(
            session,
            cookies={"bili_jct": "jct-token"},
            title="标题",
            desc="简介",
            tags=["跑步"],
            cover="https://img/16x9.jpg",
            cover43="https://img/4x3.jpg",
            filename="n220101abcdef",
            biz_id=42,
            tid=137,
            copyright=2,
        )
        assert session.payload is not None
        self.assertEqual(session.payload["tid"], 137)
        self.assertEqual(session.payload["copyright"], 2)


if __name__ == "__main__":
    unittest.main()
