from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

ROOT = Path(os.environ.get("ACCORD_DATA_DIR", Path(__file__).resolve().parents[3] / ".local" / "workspace"))
ROOT.mkdir(parents=True, exist_ok=True)
ROOT.chmod(0o700)
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
POOL_DIR = ROOT / "工作池"
POOL_DIR.mkdir(exist_ok=True)
SCRATCH_DIR = DATA / "scratch"
SCRATCH_DIR.mkdir(exist_ok=True)
DB_PATH = DATA / "pool.db"

_lock = threading.RLock()
_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
DB_PATH.chmod(0o600)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")
_conn.execute("PRAGMA foreign_keys=ON")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(text: Optional[str], default: Any) -> Any:
    if not text:
        return default
    return json.loads(text)


def init() -> None:
    with _lock:
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS units (
                id TEXT PRIMARY KEY,
                person_name TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                window TEXT NOT NULL DEFAULT 'open',
                tags TEXT NOT NULL DEFAULT '[]',
                memory TEXT NOT NULL DEFAULT '[]',
                workflows TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                a_id TEXT NOT NULL,
                b_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (a_id, b_id)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                from_kind TEXT NOT NULL,
                from_unit TEXT NOT NULL,
                body TEXT NOT NULL,
                sources TEXT NOT NULL DEFAULT '[]',
                parent_id TEXT NOT NULL DEFAULT '',
                meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS handoffs (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                message_id TEXT NOT NULL DEFAULT '',
                from_unit TEXT NOT NULL,
                to_unit TEXT NOT NULL,
                mode TEXT NOT NULL,
                deadline TEXT NOT NULL DEFAULT '',
                deliver_at TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivered_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                assignee_id TEXT,
                assign_reason TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS routes (
                id TEXT PRIMARY KEY,
                from_unit TEXT NOT NULL,
                to_unit TEXT NOT NULL,
                question TEXT NOT NULL,
                urgency TEXT NOT NULL DEFAULT 'low',
                status TEXT NOT NULL,
                answer TEXT NOT NULL DEFAULT '',
                sources TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '',
                options TEXT NOT NULL DEFAULT '[]',
                evidence TEXT NOT NULL DEFAULT '',
                fail_if TEXT NOT NULL DEFAULT '',
                required_ids TEXT NOT NULL DEFAULT '[]',
                fyi_ids TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'draft',
                content_hash TEXT NOT NULL DEFAULT '',
                locked_by TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                locked_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS scratch (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meeting_msgs (
                id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                from_unit TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL DEFAULT '',
                unit_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS duty_log (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            """
        )
        def _col(table: str, name: str, spec: str) -> None:
            existing = [r[1] for r in _conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if name not in existing:
                _conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")

        _col("units", "report_times", "TEXT NOT NULL DEFAULT '[\"11:30\",\"16:30\"]'")
        _col("tasks", "module", "TEXT NOT NULL DEFAULT ''")
        _col("tasks", "how_to", "TEXT NOT NULL DEFAULT ''")
        _col("tasks", "artifact", "TEXT NOT NULL DEFAULT ''")
        _col("tasks", "await_note", "TEXT NOT NULL DEFAULT ''")
        _col("decisions", "acks", "TEXT NOT NULL DEFAULT '[]'")
        _col("decisions", "missing_ids", "TEXT NOT NULL DEFAULT '[]'")
        _col("decisions", "convened_ids", "TEXT NOT NULL DEFAULT '[]'")
        _col("decisions", "pushed_at", "TEXT NOT NULL DEFAULT ''")
        _col("decisions", "attendee_ids", "TEXT NOT NULL DEFAULT '[]'")
        _col("decisions", "conclusion", "TEXT NOT NULL DEFAULT ''")
        _col("decisions", "wrap_todos", "TEXT NOT NULL DEFAULT '[]'")
        _col("decisions", "wrap_memory", "TEXT NOT NULL DEFAULT ''")
        _col("decisions", "wrap_title", "TEXT NOT NULL DEFAULT ''")
        _col("tasks", "remind_at", "TEXT NOT NULL DEFAULT ''")
        _col("conversations", "channel", "TEXT NOT NULL DEFAULT 'agent'")
        _col("conversations", "channel_handoff", "TEXT NOT NULL DEFAULT ''")
        _col("conversations", "human_for", "TEXT NOT NULL DEFAULT ''")
        _col("artifacts", "path", "TEXT NOT NULL DEFAULT ''")
        _col("artifacts", "author", "TEXT NOT NULL DEFAULT ''")
        _col("artifacts", "kind", "TEXT NOT NULL DEFAULT 'file'")
        _conn.commit()
    export_missing_pool_files()


def row_unit(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "person_name": row["person_name"],
        "agent_name": row["agent_name"],
        "window": row["window"],
        "tags": _loads(row["tags"], []),
        "memory": _loads(row["memory"], []),
        "workflows": _loads(row["workflows"], []),
        "report_times": _loads(row["report_times"] if "report_times" in row.keys() else None, ["11:30", "16:30"])
        or ["11:30", "16:30"],
        "created_at": row["created_at"],
    }


def row_task(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "detail": row["detail"],
        "status": row["status"],
        "assignee_id": row["assignee_id"],
        "assign_reason": row["assign_reason"],
        "tags": _loads(row["tags"], []),
        "module": row["module"] if "module" in row.keys() else "",
        "how_to": row["how_to"] if "how_to" in row.keys() else "",
        "artifact": row["artifact"] if "artifact" in row.keys() else "",
        "await_note": row["await_note"] if "await_note" in row.keys() else "",
        "remind_at": row["remind_at"] if "remind_at" in row.keys() else "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def row_route(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "from_unit": row["from_unit"],
        "to_unit": row["to_unit"],
        "question": row["question"],
        "urgency": row["urgency"],
        "status": row["status"],
        "answer": row["answer"],
        "sources": _loads(row["sources"], []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def row_decision(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "context": row["context"],
        "options": _loads(row["options"], []),
        "evidence": row["evidence"],
        "fail_if": row["fail_if"],
        "required_ids": _loads(row["required_ids"], []),
        "fyi_ids": _loads(row["fyi_ids"], []),
        "status": row["status"],
        "content_hash": row["content_hash"],
        "locked_by": row["locked_by"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "locked_at": row["locked_at"],
        "acks": _loads(row["acks"] if "acks" in row.keys() else None, []),
        "missing_ids": _loads(row["missing_ids"] if "missing_ids" in row.keys() else None, []),
        "convened_ids": _loads(row["convened_ids"] if "convened_ids" in row.keys() else None, []),
        "pushed_at": row["pushed_at"] if "pushed_at" in row.keys() else "",
        "attendee_ids": _loads(row["attendee_ids"] if "attendee_ids" in row.keys() else None, []),
        "conclusion": row["conclusion"] if "conclusion" in row.keys() else "",
        "wrap_todos": _loads(row["wrap_todos"] if "wrap_todos" in row.keys() else None, []),
        "wrap_memory": row["wrap_memory"] if "wrap_memory" in row.keys() else "",
        "wrap_title": row["wrap_title"] if "wrap_title" in row.keys() else "",
    }


def execute(sql: str, args: tuple = ()) -> None:
    with _lock:
        _conn.execute(sql, args)
        _conn.commit()


def query(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return list(_conn.execute(sql, args).fetchall())


def query_one(sql: str, args: tuple = ()) -> Optional[sqlite3.Row]:
    with _lock:
        return _conn.execute(sql, args).fetchone()


def list_units() -> list[dict]:
    return [row_unit(r) for r in query("SELECT * FROM units ORDER BY created_at")]


def get_unit(unit_id: str) -> Optional[dict]:
    row = query_one("SELECT * FROM units WHERE id=?", (unit_id,))
    return row_unit(row) if row else None


def list_tasks() -> list[dict]:
    return [row_task(r) for r in query("SELECT * FROM tasks ORDER BY created_at DESC")]


def get_task(task_id: str) -> Optional[dict]:
    row = query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    return row_task(row) if row else None


def list_routes() -> list[dict]:
    return [row_route(r) for r in query("SELECT * FROM routes ORDER BY created_at DESC")]


def get_route(route_id: str) -> Optional[dict]:
    row = query_one("SELECT * FROM routes WHERE id=?", (route_id,))
    return row_route(row) if row else None


def list_decisions() -> list[dict]:
    return [row_decision(r) for r in query("SELECT * FROM decisions ORDER BY created_at DESC")]


def get_decision(decision_id: str) -> Optional[dict]:
    row = query_one("SELECT * FROM decisions WHERE id=?", (decision_id,))
    return row_decision(row) if row else None


def list_meeting_msgs() -> list[dict]:
    rows = query("SELECT * FROM meeting_msgs ORDER BY created_at")
    return [
        {
            "id": r["id"],
            "decision_id": r["decision_id"],
            "from_unit": r["from_unit"],
            "body": r["body"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def add_meeting_msg(decision_id: str, from_unit: str, body: str) -> dict:
    mid = new_id("mm")
    ts = now()
    execute(
        "INSERT INTO meeting_msgs (id, decision_id, from_unit, body, created_at) VALUES (?,?,?,?,?)",
        (mid, decision_id, from_unit, body, ts),
    )
    return {
        "id": mid,
        "decision_id": decision_id,
        "from_unit": from_unit,
        "body": body,
        "created_at": ts,
    }


def list_duty(limit: int = 80) -> list[dict]:
    rows = query("SELECT * FROM duty_log ORDER BY created_at DESC LIMIT ?", (limit,))
    out = []
    for row in reversed(rows):
        out.append(
            {
                "id": row["id"],
                "unit_id": row["unit_id"],
                "role": row["role"],
                "content": row["content"],
                "sources": _loads(row["sources"], []),
                "created_at": row["created_at"],
            }
        )
    return out


def row_conv(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "a_id": row["a_id"],
        "b_id": row["b_id"],
        "created_at": row["created_at"],
        "channel": row["channel"] if "channel" in row.keys() else "agent",
        "channel_handoff": row["channel_handoff"] if "channel_handoff" in row.keys() else "",
        "human_for": row["human_for"] if "human_for" in row.keys() else "",
    }


def row_msg(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "from_kind": row["from_kind"],
        "from_unit": row["from_unit"],
        "body": row["body"],
        "sources": _loads(row["sources"], []),
        "parent_id": row["parent_id"],
        "meta": _loads(row["meta"], {}),
        "created_at": row["created_at"],
    }


def row_handoff(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "from_unit": row["from_unit"],
        "to_unit": row["to_unit"],
        "mode": row["mode"],
        "deadline": row["deadline"],
        "deliver_at": row["deliver_at"],
        "status": row["status"],
        "created_at": row["created_at"],
        "delivered_at": row["delivered_at"],
    }


def list_conversations() -> list[dict]:
    return [row_conv(r) for r in query("SELECT * FROM conversations ORDER BY created_at")]


def get_conversation(cid: str) -> Optional[dict]:
    row = query_one("SELECT * FROM conversations WHERE id=?", (cid,))
    return row_conv(row) if row else None


def find_conversation(a: str, b: str) -> Optional[dict]:
    left, right = sorted([a, b])
    row = query_one("SELECT * FROM conversations WHERE a_id=? AND b_id=?", (left, right))
    return row_conv(row) if row else None


def list_messages() -> list[dict]:
    return [row_msg(r) for r in query("SELECT * FROM messages ORDER BY created_at")]


def get_message(mid: str) -> Optional[dict]:
    row = query_one("SELECT * FROM messages WHERE id=?", (mid,))
    return row_msg(row) if row else None


def list_handoffs() -> list[dict]:
    return [row_handoff(r) for r in query("SELECT * FROM handoffs ORDER BY created_at DESC")]


def get_handoff(hid: str) -> Optional[dict]:
    row = query_one("SELECT * FROM handoffs WHERE id=?", (hid,))
    return row_handoff(row) if row else None


def _safe_name(title: str) -> str:
    raw = (title or "未命名").strip() or "未命名"
    for ch in '\\/:*?"<>|':
        raw = raw.replace(ch, "_")
    return raw[:60]


def export_missing_pool_files() -> None:
    rows = query("SELECT id, title, body, path FROM artifacts")
    for r in rows:
        if r["path"]:
            continue
        fpath = write_pool_file(r["title"], r["body"], "")
        execute("UPDATE artifacts SET path=? WHERE id=?", (fpath, r["id"]))


def write_pool_file(title: str, body: str, author: str = "") -> str:
    POOL_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ts = now()
    name = f"{stamp}-{_safe_name(title)}.md"
    path = POOL_DIR / name
    header = f"# {title}\n\n"
    header += f"上传人：{author or '未知'}\n时间：{ts}\n\n"
    path.write_text(header + (body or "").strip() + "\n", encoding="utf-8")
    return str(path)


def save_scratch(filename: str, data: bytes, unit_id: str) -> dict:
    SCRATCH_DIR.mkdir(exist_ok=True)
    orig = Path(filename).name or "粘贴"
    stem = _safe_name(Path(orig).stem)
    suffix = Path(orig).suffix[:12] or ".bin"
    sid = new_id("sc")
    path = SCRATCH_DIR / f"{sid}-{stem}{suffix}"
    path.write_bytes(data)
    ts = now()
    execute(
        "INSERT INTO scratch (id, unit_id, title, path, created_at) VALUES (?,?,?,?,?)",
        (sid, unit_id or "", orig, str(path), ts),
    )
    return {"id": sid, "title": orig, "path": str(path), "scratch": True, "created_at": ts}


def get_scratch(sid: str) -> Optional[dict]:
    row = query_one("SELECT * FROM scratch WHERE id=?", (sid,))
    if not row:
        return None
    return {
        "id": row["id"],
        "unit_id": row["unit_id"],
        "title": row["title"],
        "path": row["path"],
        "created_at": row["created_at"],
        "scratch": True,
    }


def scratch_for_agent(ids: list[str], limit_each: int = 12000) -> list[dict]:
    image_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    out = []
    for sid in ids or []:
        s = get_scratch(sid)
        if not s:
            continue
        suffix = Path(s.get("path") or "").suffix.lower()
        if suffix in image_ext:
            body = "（图片，已作为附图发给你，请直接看图）"
            kind = "image"
        else:
            body = read_pool_file(s.get("path") or "", limit_each) or "（过程附件，未进工作池）"
            kind = "file"
        out.append(
            {
                "id": s["id"],
                "title": s["title"],
                "path": s["path"],
                "scratch": True,
                "kind": kind,
                "content": body,
            }
        )
    return out


def save_upload(filename: str, data: bytes, unit_id: str, author: str = "") -> dict:
    POOL_DIR.mkdir(exist_ok=True)
    orig = Path(filename).name or "附件"
    stem = _safe_name(Path(orig).stem)
    suffix = Path(orig).suffix[:12]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{stem}{suffix}"
    path = POOL_DIR / name
    path.write_bytes(data)
    aid = new_id("a")
    ts = now()
    title = orig
    note = f"附件 {orig}（{len(data)} 字节）\n上传人：{author or '未知'}\n时间：{ts}"
    execute(
        "INSERT INTO artifacts (id, task_id, unit_id, title, body, path, author, kind, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (aid, "", unit_id or "", title, note, str(path), author or "", "file", ts),
    )
    return {
        "id": aid,
        "task_id": "",
        "unit_id": unit_id or "",
        "title": title,
        "body": note,
        "path": str(path),
        "author": author or "",
        "created_at": ts,
    }


def get_artifact(aid: str) -> Optional[dict]:
    row = query_one("SELECT * FROM artifacts WHERE id=?", (aid,))
    if not row:
        return None
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "unit_id": row["unit_id"],
        "title": row["title"],
        "body": row["body"],
        "path": row["path"] if "path" in row.keys() else "",
        "author": row["author"] if "author" in row.keys() else "",
        "created_at": row["created_at"],
    }


def update_pool_file(aid: str, body: str, author: str = "") -> Optional[dict]:
    art = get_artifact(aid)
    if not art or not art.get("path"):
        return None
    path = Path(art["path"])
    try:
        path.resolve().relative_to(POOL_DIR.resolve())
    except ValueError:
        return None
    ts = now()
    header = f"# {art.get('title') or path.stem}\n\n上传人：{author or art.get('author') or '未知'}\n时间：{art.get('created_at') or ts}\n修订：{ts}\n\n"
    text = body if isinstance(body, str) else str(body)
    if path.suffix.lower() in {".md", ".txt", ".html", ".js", ".css", ".json", ".py"}:
        path.write_text(header + text.strip() + "\n", encoding="utf-8")
    else:
        path.write_text(text, encoding="utf-8")
    execute("UPDATE artifacts SET body=?, author=? WHERE id=?", (text[:4000], author or art.get("author") or "", aid))
    art["body"] = text
    return art


def add_artifact(task_id: str, unit_id: str, title: str, body: str, author: str = "") -> dict:
    aid = new_id("a")
    ts = now()
    fpath = write_pool_file(title, body, author)
    execute(
        "INSERT INTO artifacts (id, task_id, unit_id, title, body, path, author, kind, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (aid, task_id or "", unit_id or "", title, body, fpath, author or "", "file", ts),
    )
    return {
        "id": aid,
        "task_id": task_id or "",
        "unit_id": unit_id or "",
        "title": title,
        "body": body,
        "path": fpath,
        "author": author or "",
        "created_at": ts,
    }


def list_artifacts() -> list[dict]:
    rows = query("SELECT * FROM artifacts ORDER BY created_at DESC")
    names = {u["id"]: u["person_name"] for u in list_units()}
    out = []
    for r in rows:
        author = r["author"] if "author" in r.keys() and r["author"] else ""
        if not author:
            author = names.get(r["unit_id"] or "", "")
        out.append(
            {
                "id": r["id"],
                "task_id": r["task_id"],
                "unit_id": r["unit_id"],
                "title": r["title"],
                "body": r["body"],
                "path": r["path"] if "path" in r.keys() else "",
                "author": author,
                "kind": r["kind"] if "kind" in r.keys() and r["kind"] else "file",
                "name": Path(r["path"]).name if "path" in r.keys() and r["path"] else (r["title"] or ""),
                "rel": _pool_rel(r["path"] if "path" in r.keys() else ""),
                "abs": _pool_abs(r["path"] if "path" in r.keys() else ""),
                "created_at": r["created_at"],
            }
        )
    return out


def _pool_abs(path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve())
    except OSError:
        return path


def _pool_rel(path: str) -> str:
    if not path:
        return ""
    try:
        return Path(path).resolve().relative_to(POOL_DIR.resolve()).as_posix()
    except ValueError:
        return Path(path).name


def list_file_artifacts() -> list[dict]:
    out = []
    for a in list_artifacts():
        if (a.get("kind") or "file") != "file":
            continue
        name = (a.get("name") or a.get("path") or "").replace("\\", "/")
        if name.endswith(".meta.json"):
            continue
        out.append(a)
    return out


def add_memory(unit_id: str, title: str, body: str, tags: Optional[list] = None, source: str = "") -> dict:
    mid = new_id("mem")
    ts = now()
    execute(
        "INSERT INTO memories (id, unit_id, title, body, tags, source, created_at) VALUES (?,?,?,?,?,?,?)",
        (
            mid,
            unit_id or "",
            (title or "")[:80],
            (body or "")[:4000],
            json.dumps(tags or [], ensure_ascii=False),
            source,
            ts,
        ),
    )
    return {
        "id": mid,
        "unit_id": unit_id or "",
        "title": (title or "")[:80],
        "body": (body or "")[:4000],
        "tags": tags or [],
        "source": source,
        "created_at": ts,
    }


def list_memories() -> list[dict]:
    rows = query("SELECT * FROM memories ORDER BY created_at DESC")
    return [
        {
            "id": r["id"],
            "unit_id": r["unit_id"],
            "title": r["title"],
            "body": r["body"],
            "tags": _loads(r["tags"], []),
            "source": r["source"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


_TEXT_EXT = {
    ".md",
    ".txt",
    ".json",
    ".csv",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".xml",
    ".yml",
    ".yaml",
    ".log",
    ".ini",
    ".toml",
    ".sql",
    ".bat",
    ".ps1",
    ".r",
    ".sh",
    ".c",
    ".h",
    ".java",
    ".go",
    ".rs",
}


def _read_docx(path: Path, limit: int) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    parts = [t.text for t in root.iter() if t.tag.endswith("}t") and t.text]
    return "\n".join(parts)[:limit]


def read_pool_file(path_str: str, limit: int = 16000) -> str:
    path = Path(path_str or "")
    if not path.is_file():
        return ""
    suffix = path.suffix.lower()
    try:
        if suffix in _TEXT_EXT:
            return path.read_text(encoding="utf-8", errors="replace")[:limit]
        if suffix == ".docx":
            return _read_docx(path, limit)
        size = path.stat().st_size
        return f"（二进制文件 {path.name}，{size} 字节，打不开正文。文本/Markdown/Word 可以读。）"
    except Exception as exc:
        return f"（读取失败：{exc}）"


def pool_for_agent(
    question: str = "",
    extra_text: str = "",
    limit_each: int = 12000,
    max_files: int = 8,
) -> list[dict]:
    arts = list_file_artifacts()
    blob = ((question or "") + " " + (extra_text or "")).lower()
    scored = []
    for a in arts:
        name = ((a.get("title") or "") + " " + (a.get("path") or "")).lower()
        hit = 0
        if name and name[:40] and name[:40] in blob:
            hit += 5
        title = (a.get("title") or "").lower()
        if title and title in blob:
            hit += 6
        for w in re.findall(r"[a-zA-Z0-9]{2,}|[\u4e00-\u9fff]{2,}", blob):
            if w in ("资料", "文件", "改一下", "工作区", "那个"):
                continue
            if w in name:
                hit += 2
        scored.append((hit, a))
    scored.sort(key=lambda x: (x[0], x[1].get("created_at") or ""), reverse=True)
    if not any(h > 0 for h, _ in scored):
        scored = [(1, a) for a in arts[:max_files]]
    out = []
    for hit, a in scored[:max_files]:
        body = read_pool_file(a.get("path") or "", limit_each)
        if not body:
            body = (a.get("body") or "")[:limit_each]
        out.append(
            {
                "id": a.get("id") or "",
                "title": a.get("title") or "",
                "path": a.get("path") or "",
                "author": a.get("author") or "",
                "created_at": a.get("created_at") or "",
                "url": f"/api/pool/{a.get('id')}/file" if a.get("id") else "",
                "content": body,
            }
        )
    return out


def get_state(key: str, default: str = "") -> str:
    row = query_one("SELECT value FROM project_state WHERE key=?", (key,))
    return row["value"] if row else default


def get_state_at(key: str) -> str:
    row = query_one("SELECT updated_at FROM project_state WHERE key=?", (key,))
    return row["updated_at"] if row else ""


def set_state(key: str, value: str) -> None:
    ts = now()
    with _lock:
        _conn.execute(
            """INSERT INTO project_state (key, value, updated_at) VALUES (?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, value, ts),
        )
        _conn.commit()


def unit_load(unit_id: str) -> int:
    row = query_one(
        "SELECT COUNT(*) AS n FROM tasks WHERE assignee_id=? AND status!='done'",
        (unit_id,),
    )
    return int(row["n"]) if row else 0


def snapshot() -> dict:
    units = list_units()
    tasks = list_tasks()
    routes = list_routes()
    handoffs = list_handoffs()
    for unit in units:
        uid = unit["id"]
        unit["load"] = sum(1 for t in tasks if t["assignee_id"] == uid and t["status"] != "done")
        unit["queued"] = sum(
            1 for r in routes if r["to_unit"] == uid and r["status"] in ("queued", "batch_ready")
        )
        unit["escalated"] = sum(1 for r in routes if r["to_unit"] == uid and r["status"] == "escalated")
        unit["urgent_n"] = sum(
            1
            for h in handoffs
            if h["to_unit"] == uid and h["mode"] == "urgent" and h["status"] == "delivered"
        )
        unit["batch_n"] = sum(
            1
            for h in handoffs
            if h["to_unit"] == uid and h["mode"] == "deadline" and h["status"] == "delivered"
        )
        unit["waiting_n"] = sum(1 for h in handoffs if h["to_unit"] == uid and h["status"] == "scheduled")
    open_tasks = [t for t in tasks if t["status"] != "done"]
    unanswered = [r for r in routes if r["status"] in ("queued", "escalated", "batch_ready")]
    unlocked = [d for d in list_decisions() if d["status"] != "locked"]
    return {
        "units": units,
        "tasks": tasks,
        "routes": routes,
        "conversations": list_conversations(),
        "messages": list_messages(),
        "handoffs": handoffs,
        "decisions": list_decisions(),
        "meeting_msgs": list_meeting_msgs(),
        "duty_log": list_duty(),
        "artifacts": list_file_artifacts(),
        "memories": list_memories()[:80],
        "pool_dir": str(POOL_DIR),
        "git": get_state("git"),
        "git_at": get_state_at("git"),
        "pulse": {
            "open_tasks": len(open_tasks),
            "unassigned": sum(1 for t in open_tasks if not t["assignee_id"]),
            "deep_work": sum(1 for u in units if u["window"] == "closed"),
            "pending_routes": len(unanswered),
            "open_decisions": len(unlocked),
            "urgent": sum(u["urgent_n"] for u in units),
            "batch": sum(u["batch_n"] for u in units),
        },
        "now": now(),
    }
