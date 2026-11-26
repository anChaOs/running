#!/usr/bin/env python3
"""把 upload/ 成片用 Web UPOS 双封面投到 B 站。

16:9 封面进 cover，4:3 封面进 cover43。Cookie 用 biliup 扫码保存的 cookies.json。
分片线路 -l：bda2 / bldsa / tx / qn。只依赖标准库和仓库 .venv 里的 requests。
"""

from __future__ import annotations

import argparse
import base64
import json
import queue
import re
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import log_timeline  # noqa: E402
import pack_upload  # noqa: E402
import todo_list  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COOKIE = Path("~/Movies/running-content/.biliup/cookies.json")
COVER_UP_URL = "https://member.bilibili.com/x/vu/web/cover/up"
PREUPLOAD_URL = "https://member.bilibili.com/preupload"
SUBMIT_URL = "https://member.bilibili.com/x/vu/web/add/v3"
REQUIRED_COOKIES = ("SESSDATA", "bili_jct", "DedeUserID")
COVER_16X9 = "cover-16x9-1920x1080.jpg"
COVER_4X3 = "cover-4x3-1920x1440.jpg"
STEP = "bilibili-upload"
TID = 238
COPYRIGHT = 1
TITLE_MAX = 80
TAG_MAX_COUNT = 10
TAG_MAX_LEN = 20
_TIMELINE_END = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})  END\s+(?P<step>\S+)(?:\s+(?P<rest>.*))?$"
)
# biliup-rs 0.2.4 的线路 query。默认 bda2。
LINES: dict[str, dict[str, str]] = {
    "bda2": {"probe_version": "20221109", "upcdn": "bda2", "zone": "cs"},
    "bldsa": {"zone": "cs", "upcdn": "bldsa", "probe_version": "20221109"},
    "tx": {"zone": "cs", "upcdn": "tx", "probe_version": "20221109"},
    "qn": {"probe_version": "20221109", "upcdn": "qn", "zone": "cs"},
}
MEMBER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://member.bilibili.com/platform/upload/video/frame",
    "Origin": "https://member.bilibili.com",
}


@dataclass
class EpisodeUpload:
    media_dir: Path
    episode_dir: Path
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    video: Path | None = None
    cover_16x9: Path | None = None
    cover_4x3: Path | None = None
    cookies: dict[str, str] = field(default_factory=dict)
    pack_state: str = "pending"
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _cookie_expiry(item: dict[str, Any]) -> int | None:
    """biliup 把 passport 的 expires 存成 Unix 秒。0 或缺省当作会话 cookie，不判过期。"""
    raw = item.get("expires")
    if raw in (None, "", 0, "0"):
        return None
    try:
        stamp = int(raw)
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    if stamp > 10_000_000_000:
        stamp //= 1000
    return stamp


def load_cookies(path: Path, now: float | None = None) -> dict[str, str]:
    """读取 biliup cookies.json。CSRF 是 bili_jct。不打印 cookie 值。"""
    path = Path(path).expanduser()
    if not path.is_file():
        raise ValueError(f"biliup cookie file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"biliup cookie file is not JSON: {path}") from exc
    raw = data.get("cookie_info", {}).get("cookies") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise ValueError(f"unrecognized biliup cookie file: {path}")
    found: dict[str, str] = {}
    expires_at: dict[str, int] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if name and value is not None:
            key = str(name)
            found[key] = str(value)
            stamp = _cookie_expiry(item)
            if stamp is not None:
                expires_at[key] = stamp
    missing = [name for name in REQUIRED_COOKIES if not found.get(name)]
    if missing:
        raise ValueError("biliup cookie missing " + ", ".join(missing))
    current = time.time() if now is None else now
    expired = [name for name in ("SESSDATA", "bili_jct") if expires_at.get(name, current + 1) <= current]
    if expired:
        raise ValueError("biliup cookie expired: " + ", ".join(expired))
    return found


def cookie_header(cookies: dict[str, str]) -> str:
    """SESSDATA 在文件里已经百分号编码，按原样拼，不再编码一次。"""
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def member_headers(cookies: dict[str, str]) -> dict[str, str]:
    headers = dict(MEMBER_HEADERS)
    headers["Cookie"] = cookie_header(cookies)
    return headers


def extract_section(markdown: str, heading: str, stop: str) -> str:
    lines = markdown.splitlines()
    in_section = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not in_section:
            if re.match(heading, stripped):
                in_section = True
            continue
        if re.match(stop, stripped):
            break
        out.append(line)
    return "\n".join(out).strip()


def parse_title(episode_dir: Path) -> str:
    try:
        return pack_upload.title_from_plan(episode_dir)
    except SystemExit as exc:
        message = str(exc) if exc.code else ""
        raise ValueError(message or f"Could not parse title from {episode_dir / 'plan.md'}") from None


def parse_bilibili_desc(markdown: str) -> str:
    desc = extract_section(markdown, r"^###\s+B\s*站\s*$", r"^#{2,3}\s+")
    if not desc:
        raise ValueError("Could not parse ### B 站 description from plan.md")
    return desc


def split_tags(raw: str) -> list[str]:
    tags: list[str] = []
    for part in re.split(r"[\s,，]+", raw.strip()):
        tag = part.strip().lstrip("#").strip()
        if tag:
            tags.append(tag)
    return tags


def parse_bilibili_tags(section: str) -> list[str]:
    """## 标签 里 B 站那一段。代码块或「B 站：」同一行都可以。去掉 #，不收 YouTube 标签。"""
    label = re.search(r"^B\s*站.*$", section, flags=re.M)
    if label is None:
        raise ValueError("Could not parse Bilibili tags from plan.md")
    after = section[label.end() :]
    after = re.split(r"^YouTube\b.*$", after, maxsplit=1, flags=re.M)[0]
    fence = re.search(r"```[^\n]*\n(.*?)```", after, flags=re.S)
    if fence:
        raw = fence.group(1)
    else:
        inline = re.search(r"[：:]\s*(\S.*?)\s*$", label.group(0))
        raw = inline.group(1) if inline else ""
    tags = split_tags(raw)
    if not tags:
        raise ValueError("Could not parse Bilibili tags from plan.md")
    return tags


def parse_bilibili_tags_from_markdown(markdown: str) -> list[str]:
    section = extract_section(markdown, r"^##\s+标签\s*$", r"^##\s+")
    if not section:
        raise ValueError("Could not parse ## 标签 from plan.md")
    return parse_bilibili_tags(section)


def parse_plan_bilibili(plan_path: Path) -> dict[str, Any]:
    """标题、B 站简介、B 站标签。字数是否超限由 check_bilibili_desc_length 另判。"""
    plan_path = Path(plan_path)
    text = plan_path.read_text(encoding="utf-8")
    return {
        "title": parse_title(plan_path.parent),
        "description": parse_bilibili_desc(text),
        "tags": parse_bilibili_tags_from_markdown(text),
    }


def check_bilibili_desc_length(text: str, limit: int = pack_upload.BILIBILI_DESC_MAX) -> int:
    """按 Python Unicode 码位计数，不是 UTF-8 字节。"""
    count = len(text)
    if count > limit:
        raise ValueError(f"Bilibili description is {count} Unicode code points; limit is {limit}")
    return count


def check_bilibili_title(title: str, limit: int = TITLE_MAX) -> int:
    """创作中心标题上限 80 个码位。超限在预检拒绝，避免分片传完才被 submit 打回。"""
    count = len(title)
    if count > limit:
        raise ValueError(f"Bilibili title is {count} Unicode code points; limit is {limit}")
    return count


def check_bilibili_tags(
    tags: list[str],
    *,
    max_count: int = TAG_MAX_COUNT,
    max_len: int = TAG_MAX_LEN,
) -> None:
    """创作中心标签最多 10 个，单条最多 20 个码位。"""
    if len(tags) > max_count:
        raise ValueError(f"Bilibili tag count is {len(tags)}; limit is {max_count}")
    for tag in tags:
        count = len(tag)
        if count > max_len:
            shown = tag if count <= 30 else tag[:30] + "..."
            raise ValueError(f"Bilibili tag is {count} Unicode code points; limit is {max_len}: {shown}")


def tags_csv(tags: list[str]) -> str:
    return ",".join(tags)


def resolve_upload_assets(media_dir: Path) -> tuple[Path, Path, Path]:
    upload = media_dir / "upload"
    if not upload.is_dir():
        raise FileNotFoundError(f"upload/ directory not found in {media_dir}; run pack_upload.py first")
    mp4s = sorted(p for p in upload.glob("*.mp4") if p.is_file())
    if len(mp4s) != 1:
        names = [p.name for p in mp4s]
        raise ValueError(f"Expected exactly 1 .mp4 in {upload}, found {len(mp4s)}: {names}")
    cover_16x9 = upload / COVER_16X9
    cover_4x3 = upload / COVER_4X3
    missing = [p.name for p in (cover_16x9, cover_4x3) if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing cover(s) in {upload}: {', '.join(missing)}")
    if mp4s[0].stat().st_size <= 0:
        raise ValueError(f"video is empty: {mp4s[0]}")
    return mp4s[0], cover_16x9, cover_4x3


def episode_dir_for(media_dir: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    return REPO_ROOT / "episodes" / media_dir.name


def successful_bilibili_note(media_dir: Path) -> str | None:
    """时间表里最近一条成功的 bilibili-upload。投稿已发出但 todo 没标上时，用它拦住下一次投稿。"""
    path = Path(media_dir) / "logs" / "timeline.txt"
    if not path.is_file():
        return None
    found: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = _TIMELINE_END.match(raw.strip())
        if not match or match.group("step") != STEP:
            continue
        rest = match.group("rest") or ""
        note_match = re.search(r"(?:^|\s)note=(.*)$", rest)
        found = note_match.group(1).strip() if note_match else STEP
    return found


def preflight(media_dir: Path, episode_dir: Path, cookie_path: Path) -> EpisodeUpload:
    ready = EpisodeUpload(media_dir=media_dir, episode_dir=episode_dir)
    plan = episode_dir / "plan.md"
    if not plan.is_file():
        ready.problems.append(f"plan.md not found: {plan}")
    else:
        text = plan.read_text(encoding="utf-8")
        try:
            ready.title = parse_title(episode_dir)
        except ValueError as exc:
            ready.problems.append(str(exc))
        else:
            try:
                check_bilibili_title(ready.title)
            except ValueError as exc:
                ready.problems.append(str(exc))
        try:
            ready.description = parse_bilibili_desc(text)
        except ValueError as exc:
            ready.problems.append(str(exc))
        else:
            try:
                check_bilibili_desc_length(ready.description)
            except ValueError as exc:
                ready.problems.append(str(exc))
        try:
            ready.tags = parse_bilibili_tags_from_markdown(text)
        except ValueError as exc:
            ready.problems.append(str(exc))
        else:
            try:
                check_bilibili_tags(ready.tags)
            except ValueError as exc:
                ready.problems.append(str(exc))
    try:
        video, cover_16x9, cover_4x3 = resolve_upload_assets(media_dir)
    except (FileNotFoundError, ValueError) as exc:
        ready.problems.append(str(exc))
    else:
        ready.video = video
        ready.cover_16x9 = cover_16x9
        ready.cover_4x3 = cover_4x3
    status = todo_list.load(media_dir)
    ready.pack_state = status.get("pack-upload", "pending")
    if ready.pack_state != "done":
        ready.problems.append(f"logs/todo.md pack-upload is {ready.pack_state}; need done")
    if status.get("bilibili") == "done":
        ready.problems.append("logs/todo.md bilibili is already done")
    prior = successful_bilibili_note(media_dir)
    if prior:
        ready.problems.append(
            f"logs/timeline.txt already has END bilibili-upload ({prior}); refusing to submit again"
        )
    try:
        ready.cookies = load_cookies(cookie_path)
    except ValueError as exc:
        ready.problems.append(str(exc))
    return ready


def format_preflight(ready: EpisodeUpload) -> str:
    lines = [
        f"title: {ready.title}",
        f"description: {len(ready.description)} Unicode code points",
        f"tags: {tags_csv(ready.tags)}",
        f"video: {ready.video if ready.video else '(missing)'}",
        f"cover-16x9: {ready.cover_16x9 if ready.cover_16x9 else '(missing)'}",
        f"cover-4x3: {ready.cover_4x3 if ready.cover_4x3 else '(missing)'}",
        f"pack-upload: {ready.pack_state}",
        f"cookie: {'ok' if ready.cookies else 'missing'}",
    ]
    if ready.problems:
        lines.append("problems:")
        lines.extend(f"- {item}" for item in ready.problems)
    return "\n".join(lines)


def build_cover_form(image: bytes, csrf: str) -> dict[str, str]:
    encoded = base64.b64encode(image).decode("ascii")
    return {"cover": f"data:image/jpeg;base64,{encoded}", "csrf": csrf}


def build_preupload_params(filename: str, size: int, line: str) -> dict[str, str]:
    if line not in LINES:
        known = ", ".join(LINES)
        raise ValueError(f"unknown line {line}; choose from {known}")
    params = {
        "r": "upos",
        "profile": "ugcupos/bup",
        "ssl": "0",
        "version": "2.11.0",
        "build": "2110000",
        "name": filename,
        "size": str(size),
    }
    params.update(LINES[line])
    return params


def upos_url(endpoint: str, upos_uri: str) -> str:
    host = endpoint.strip()
    for prefix in ("https:", "http:"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    host = host.strip("/")
    path = upos_uri.removeprefix("upos://").lstrip("/")
    return f"https://{host}/{path}"


def video_filename_from_upos(upos_uri: str) -> str:
    name = upos_uri.removeprefix("upos://").rstrip("/").split("/")[-1]
    return Path(name).stem


def chunk_ranges(total: int, chunk_size: int) -> list[tuple[int, int, int]]:
    """(index, start, end)。end 是 start+长度，和 biliup-rs 一样，不是闭区间。"""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    ranges: list[tuple[int, int, int]] = []
    start = 0
    index = 0
    while start < total:
        end = min(start + chunk_size, total)
        ranges.append((index, start, end))
        start = end
        index += 1
    return ranges


def chunk_query(
    *,
    upload_id: str,
    chunks: int,
    total: int,
    index: int,
    start: int,
    end: int,
) -> dict[str, str]:
    return {
        "uploadId": upload_id,
        "chunks": str(chunks),
        "total": str(total),
        "chunk": str(index),
        "size": str(end - start),
        "partNumber": str(index + 1),
        "start": str(start),
        "end": str(end),
    }


def build_submit_payload(
    *,
    title: str,
    desc: str,
    tag: str,
    cover: str,
    cover43: str,
    filename: str,
    biz_id: int,
    csrf: str,
    tid: int = TID,
    copyright: int = COPYRIGHT,
) -> dict[str, Any]:
    """Web add/v3。cover 是 16:9 URL，cover43 是 4:3 URL。"""
    return {
        "copyright": copyright,
        "source": "",
        "tid": tid,
        "cover": cover,
        "cover43": cover43,
        "title": title,
        "desc_format_id": 0,
        "desc": desc,
        "dynamic": "",
        "subtitle": {"open": 0, "lan": ""},
        "tag": tag,
        "videos": [
            {
                "filename": filename,
                "title": title,
                "desc": "",
                "cid": biz_id,
            }
        ],
        "open_subtitle": False,
        "interactive": 0,
        "dolby": 0,
        "lossless_music": 0,
        "no_reprint": 0,
        "open_elec": 0,
        "up_selection_reply": False,
        "up_close_reply": False,
        "up_close_danmu": False,
        "web_os": 1,
        "csrf": csrf,
    }


def _json_or_text(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text[:300]}


def _raise_api(body: Any, what: str) -> None:
    message = body.get("message") if isinstance(body, dict) else None
    code = body.get("code") if isinstance(body, dict) else None
    detail = message or body
    raise RuntimeError(f"{what} failed: code={code} {detail}")


def ensure_http_ok(response: Any, what: str) -> None:
    """4xx/5xx 带上响应正文。B 站业务 code 另由调用方看 JSON。"""
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and status >= 400:
        text = str(getattr(response, "text", "") or "")
        raise RuntimeError(f"{what} failed: HTTP {status} {text[:300]}")


def _retry_call(label: str, retries: int, fn: Callable[[], Any]) -> Any:
    """retries 是失败后的额外次数。第一次不算重试。"""
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")
    last_exc: BaseException | None = None
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            print(
                f"{label} attempt {attempt} failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 8))
    assert last_exc is not None
    raise last_exc


def _chunk_sessions(session: Any, limit: int) -> tuple[queue.SimpleQueue[Any], list[Any]]:
    """requests.Session 不能并发 PUT。每个工人一个 Session；测试里的假对象继续共用。"""
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    pool: queue.SimpleQueue[Any] = queue.SimpleQueue()
    owned: list[Any] = []
    if isinstance(session, requests.Session):
        owned = [_new_chunk_session() for _ in range(limit)]
        for item in owned:
            pool.put(item)
    else:
        for _ in range(limit):
            pool.put(session)
    return pool, owned


def _new_chunk_session() -> requests.Session:
    return requests.Session()


def upload_cover(session: Any, image: bytes, cookies: dict[str, str]) -> str:
    csrf = cookies["bili_jct"]
    response = session.post(
        COVER_UP_URL,
        data=build_cover_form(image, csrf),
        headers=member_headers(cookies),
        timeout=60,
    )
    ensure_http_ok(response, "cover upload")
    body = _json_or_text(response)
    if not isinstance(body, dict) or body.get("code") != 0:
        _raise_api(body, "cover upload")
    url = (body.get("data") or {}).get("url")
    if not url:
        raise RuntimeError(f"cover upload failed: no url in {body}")
    return str(url)


def preupload(session: Any, filename: str, size: int, line: str, cookies: dict[str, str]) -> dict[str, Any]:
    response = session.get(
        PREUPLOAD_URL,
        params=build_preupload_params(filename, size, line),
        headers=member_headers(cookies),
        timeout=60,
    )
    ensure_http_ok(response, "preupload")
    body = _json_or_text(response)
    if not isinstance(body, dict) or body.get("OK") != 1:
        _raise_api(body, "preupload")
    missing = [key for key in ("auth", "endpoint", "upos_uri", "biz_id", "chunk_size") if key not in body]
    if missing:
        raise RuntimeError(f"preupload missing {', '.join(missing)}")
    return body


def init_upload(session: Any, url: str, auth: str, retries: int) -> str:
    def once() -> str:
        response = session.post(
            f"{url}?uploads&output=json",
            headers={"X-Upos-Auth": auth},
            timeout=60,
        )
        ensure_http_ok(response, "upos init")
        body = _json_or_text(response)
        upload_id = body.get("upload_id") if isinstance(body, dict) else None
        if not upload_id:
            raise RuntimeError(f"upos init failed: {body}")
        return str(upload_id)

    return str(_retry_call("upos init", retries, once))


def _read_range(path: Path, start: int, end: int) -> bytes:
    with path.open("rb") as handle:
        handle.seek(start)
        data = handle.read(end - start)
    if len(data) != end - start:
        raise RuntimeError(f"short read {path} at {start}:{end}")
    return data


def put_chunk(
    session: Any,
    *,
    url: str,
    auth: str,
    upload_id: str,
    chunks: int,
    total: int,
    index: int,
    start: int,
    end: int,
    data: bytes,
    retries: int,
) -> dict[str, Any]:
    def once() -> dict[str, Any]:
        response = session.put(
            url,
            params=chunk_query(
                upload_id=upload_id,
                chunks=chunks,
                total=total,
                index=index,
                start=start,
                end=end,
            ),
            data=data,
            headers={"X-Upos-Auth": auth},
            timeout=240,
        )
        ensure_http_ok(response, f"chunk {index + 1}/{chunks}")
        etag = response.headers.get("ETag") or response.headers.get("Etag") or "etag"
        return {"partNumber": index + 1, "eTag": str(etag).strip('"')}

    part = _retry_call(f"chunk {index + 1}/{chunks}", retries, once)
    return dict(part)


def upload_chunks(
    session: Any,
    *,
    path: Path,
    url: str,
    auth: str,
    upload_id: str,
    chunk_size: int,
    limit: int,
    retries: int,
) -> list[dict[str, Any]]:
    total = path.stat().st_size
    ranges = chunk_ranges(total, chunk_size)
    chunks = len(ranges)

    def one(item: tuple[int, int, int], put_session: Any) -> dict[str, Any]:
        index, start, end = item
        data = _read_range(path, start, end)
        part = put_chunk(
            put_session,
            url=url,
            auth=auth,
            upload_id=upload_id,
            chunks=chunks,
            total=total,
            index=index,
            start=start,
            end=end,
            data=data,
            retries=retries,
        )
        print(f"chunk {index + 1}/{chunks} ok", flush=True)
        return part

    parts: list[dict[str, Any]] = []
    session_pool, owned = _chunk_sessions(session, limit)

    def one_on_own_session(item: tuple[int, int, int]) -> dict[str, Any]:
        put_session = session_pool.get()
        try:
            return one(item, put_session)
        finally:
            session_pool.put(put_session)

    try:
        with ThreadPoolExecutor(max_workers=limit) as pool:
            futures = [pool.submit(one_on_own_session, item) for item in ranges]
            try:
                for future in futures:
                    parts.append(future.result())
            except Exception:
                for future in futures:
                    future.cancel()
                raise
    finally:
        for item in owned:
            item.close()
    parts.sort(key=lambda part: int(part["partNumber"]))
    return parts


def complete_upload(
    session: Any,
    *,
    url: str,
    auth: str,
    filename: str,
    upload_id: str,
    biz_id: int,
    parts: list[dict[str, Any]],
    retries: int,
) -> None:
    def once() -> None:
        response = session.post(
            url,
            params={
                "name": filename,
                "uploadId": upload_id,
                "biz_id": str(biz_id),
                "output": "json",
                "profile": "ugcupos/bup",
            },
            json={"parts": parts},
            headers={"X-Upos-Auth": auth},
            timeout=60,
        )
        ensure_http_ok(response, "upos complete")
        body = _json_or_text(response)
        if not isinstance(body, dict) or body.get("OK") != 1:
            _raise_api(body, "upos complete")

    _retry_call("upos complete", retries, once)


def submit_video(
    session: Any,
    *,
    cookies: dict[str, str],
    title: str,
    desc: str,
    tags: list[str],
    cover: str,
    cover43: str,
    filename: str,
    biz_id: int,
) -> dict[str, Any]:
    csrf = cookies["bili_jct"]
    payload = build_submit_payload(
        title=title,
        desc=desc,
        tag=tags_csv(tags),
        cover=cover,
        cover43=cover43,
        filename=filename,
        biz_id=biz_id,
        csrf=csrf,
    )
    response = session.post(
        SUBMIT_URL,
        params={"csrf": csrf},
        json=payload,
        headers=member_headers(cookies),
        timeout=60,
    )
    ensure_http_ok(response, "submit")
    body = _json_or_text(response)
    if not isinstance(body, dict) or body.get("code") != 0:
        _raise_api(body, "submit")
    data = body.get("data") or {}
    bvid = data.get("bvid")
    if not bvid:
        raise RuntimeError(f"submit failed: no bvid in {body}")
    return {
        "bvid": str(bvid),
        "aid": data.get("aid"),
        "url": f"https://www.bilibili.com/video/{bvid}",
    }


def upload_episode(
    ready: EpisodeUpload,
    *,
    line: str,
    limit: int,
    retries: int,
    session: Any,
) -> dict[str, Any]:
    if not ready.ok or ready.video is None or ready.cover_16x9 is None or ready.cover_4x3 is None:
        raise ValueError("episode is not ready to upload")
    cookies = ready.cookies
    cover = upload_cover(session, ready.cover_16x9.read_bytes(), cookies)
    cover43 = upload_cover(session, ready.cover_4x3.read_bytes(), cookies)
    video = ready.video
    probe = preupload(session, video.name, video.stat().st_size, line, cookies)
    url = upos_url(str(probe["endpoint"]), str(probe["upos_uri"]))
    auth = str(probe["auth"])
    upload_id = init_upload(session, url, auth, retries)
    parts = upload_chunks(
        session,
        path=video,
        url=url,
        auth=auth,
        upload_id=upload_id,
        chunk_size=int(probe["chunk_size"]),
        limit=limit,
        retries=retries,
    )
    complete_upload(
        session,
        url=url,
        auth=auth,
        filename=video.name,
        upload_id=upload_id,
        biz_id=int(probe["biz_id"]),
        parts=parts,
        retries=retries,
    )
    return submit_video(
        session,
        cookies=cookies,
        title=ready.title,
        desc=ready.description,
        tags=ready.tags,
        cover=cover,
        cover43=cover43,
        filename=video_filename_from_upos(str(probe["upos_uri"])),
        biz_id=int(probe["biz_id"]),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", type=Path, required=True, help="~/Movies/running-content/YYYY-MM-DD-slug")
    parser.add_argument("--episode-dir", type=Path, default=None, help="默认 episodes/<slug>")
    parser.add_argument("--cookie", type=Path, default=DEFAULT_COOKIE, help="biliup cookies.json")
    parser.add_argument("-l", "--line", default="bda2", choices=tuple(LINES), help="UPOS 线路，默认 bda2")
    parser.add_argument("--limit", type=int, default=6, help="分片并发，默认 6")
    parser.add_argument("--retries", type=int, default=3, help="分片或合并失败后的额外重试次数，默认 3")
    parser.add_argument("--dry-run", action="store_true", help="只打印检查，不上传、不改 logs")
    return parser


def run(args: argparse.Namespace, session: Any | None = None) -> int:
    if args.limit < 1:
        print("--limit must be >= 1", file=sys.stderr)
        return 1
    if args.retries < 0:
        print("--retries must be >= 0", file=sys.stderr)
        return 1
    media_dir = Path(args.media_dir).expanduser().resolve()
    episode_dir = episode_dir_for(media_dir, args.episode_dir)
    ready = preflight(media_dir, episode_dir, Path(args.cookie))
    report = format_preflight(ready)
    if args.dry_run:
        print(report)
        return 0 if ready.ok else 1
    if not ready.ok:
        print(report, file=sys.stderr)
        return 1

    if session is None:
        session = requests.Session()
    video = ready.video
    assert video is not None
    print(
        f"bilibili upload {video.name} ({video.stat().st_size} bytes) line={args.line} limit={args.limit}",
        flush=True,
    )
    try:
        with log_timeline.span(media_dir, STEP) as timeline:
            result = upload_episode(
                ready,
                line=args.line,
                limit=args.limit,
                retries=args.retries,
                session=session,
            )
            timeline.note = f"{result['bvid']} {result['url']}"
    except Exception as exc:
        print(f"bilibili upload failed: {exc}", file=sys.stderr)
        return 1
    print(result["bvid"])
    print(result["url"])
    try:
        todo_list.mark(media_dir, "bilibili", "done")
    except Exception as exc:
        print(
            f"bilibili submitted {result['bvid']} but todo mark failed: {exc}",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
