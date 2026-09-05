#!/usr/bin/env python3
"""Publish user-selected local text artifacts to an Accord work pool."""

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


SUPPORTED = {
    ".md",
    ".markdown",
    ".txt",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".log",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".py",
    ".html",
    ".css",
}
IGNORED_DIRS = {
    ".git",
    ".local",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}
DEFAULT_CONFIG = Path.home() / ".config" / "accord" / "cli-session.json"


class CliError(RuntimeError):
    pass


def api_url(value: str) -> str:
    value = value.rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise CliError("服务地址必须以 http:// 或 https:// 开头。")
    return value[:-4] if value.endswith("/api") else value


def call(base_url: str, path: str, *, payload=None, session=""):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if session:
        headers["Authorization"] = f"Bearer {session}"
    request = urllib.request.Request(
        base_url + "/api" + path,
        data=body,
        headers=headers,
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response), response.headers
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode()).get("detail")
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = None
        raise CliError(detail or f"Accord 请求失败（{error.code}）。") from None
    except urllib.error.URLError:
        raise CliError("无法连接 Accord，请确认服务地址和运行状态。") from None


def save_session(
    path: Path, *, base_url: str, account_id: str, account_name: str, session: str
):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "base_url": base_url,
                "account_id": account_id,
                "account_name": account_name,
                "session": session,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def load_session(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise CliError(
            "尚未登录。请先运行：python3 tools/accord_share.py login"
        ) from None
    if not all(
        isinstance(data.get(key), str) and data[key] for key in ("base_url", "session")
    ):
        raise CliError("本地登录信息无效，请重新登录。")
    return data


def read_artifact(path: Path):
    path = path.expanduser().resolve()
    if not path.is_file():
        raise CliError(f"文件不存在：{path}")
    if path.suffix.lower() not in SUPPORTED:
        raise CliError(f"暂不支持：{path.name}")
    if path.stat().st_size > 256_000:
        raise CliError(f"{path.name} 超过 256 KB。")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise CliError(f"{path.name} 不是 UTF-8 文本。") from None
    if not content.strip():
        raise CliError(f"{path.name} 没有可读取的文字。")
    if len(content) > 16_000:
        raise CliError(f"{path.name} 超过 16,000 个字符。")
    return path, content


def recent_files(root: Path, *, limit: int):
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise CliError(f"目录不存在：{root}")
    found = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [
            name
            for name in dirs
            if name not in IGNORED_DIRS and not name.startswith(".")
        ]
        for name in files:
            path = Path(current) / name
            if path.suffix.lower() in SUPPORTED and not path.is_symlink():
                try:
                    found.append((path.stat().st_mtime, path))
                except OSError:
                    continue
    return [path for _, path in sorted(found, reverse=True)[:limit]]


def login(args):
    base_url = api_url(args.url)
    catalog, _ = call(base_url, "/auth/accounts")
    accounts = catalog.get("accounts", [])
    if not accounts:
        raise CliError("当前工作空间没有可选身份。")
    selected = None
    if args.account:
        selected = next(
            (
                account
                for account in accounts
                if args.account.strip() in (account.get("id"), account.get("name"))
            ),
            None,
        )
        if not selected:
            raise CliError("找不到这个身份，请使用账号姓名或稳定 ID。")
    else:
        if not sys.stdin.isatty():
            raise CliError("非交互环境请使用 --account 指定身份。")
        for index, account in enumerate(accounts, 1):
            group = "演示成员" if account.get("kind") == "demo" else "体验账号"
            print(f"{index}. {account['name']} · {group}")
        choice = input("选择身份编号：").strip()
        if not choice.isdigit() or not 1 <= int(choice) <= len(accounts):
            raise CliError("身份编号无效。")
        selected = accounts[int(choice) - 1]
    result, _ = call(base_url, "/auth/select", payload={"account_id": selected["id"]})
    session = result.get("session_token", "")
    if not session:
        raise CliError("身份选择成功，但没有收到 CLI 会话。")
    save_session(
        args.config,
        base_url=base_url,
        account_id=selected["id"],
        account_name=selected["name"],
        session=session,
    )
    print(f"已连接 Accord：{selected['name']} · {base_url}")


def status(args):
    saved = load_session(args.config)
    state, _ = call(saved["base_url"], "/state", session=saved["session"])
    member = next(
        (item for item in state["members"] if item["id"] == state["me"]), None
    )
    name = member["person_name"] if member else saved.get("account_name", state["me"])
    print(f"{state['project']['name']} · {name}")


def logout(args):
    saved = load_session(args.config)
    call(saved["base_url"], "/auth/logout", payload={}, session=saved["session"])
    args.config.unlink(missing_ok=True)
    print("已退出 Accord。")


def publish(args):
    saved = load_session(args.config)
    artifacts = [read_artifact(Path(value)) for value in args.files]
    if args.dry_run:
        for path, _ in artifacts:
            print(f"将放入工作池：{path}")
        return
    for path, content in artifacts:
        result, _ = call(
            saved["base_url"],
            "/resources",
            session=saved["session"],
            payload={
                "operation_id": str(
                    uuid5(
                        NAMESPACE_URL,
                        "|".join(
                            (
                                saved["base_url"],
                                saved.get("account_id", saved.get("account_name", "")),
                                str(path),
                                hashlib.sha256(content.encode()).hexdigest(),
                            )
                        ),
                    )
                ),
                "title": path.stem[:160],
                "body": content,
                "scope": "team",
                "resource_ids": [],
            },
        )
        print(f"已放入工作池：{path.name} · {result['id']}")


def list_recent(args):
    for path in recent_files(Path(args.root), limit=args.limit):
        print(path)


def parser():
    result = argparse.ArgumentParser(
        description="把明确选中的本地成品发布到 Accord 工作池；不会自动扫描或公开聊天。"
    )
    result.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get("ACCORD_CLI_CONFIG", DEFAULT_CONFIG)),
    )
    commands = result.add_subparsers(dest="command", required=True)
    login_parser = commands.add_parser("login", help="选择固定身份并保存本机会话")
    login_parser.add_argument("--url", default="http://127.0.0.1:8786")
    login_parser.add_argument("--account", help="账号姓名或稳定 ID；省略时显示选择列表")
    login_parser.set_defaults(run=login)
    status_parser = commands.add_parser("status", help="查看当前连接的工作空间")
    status_parser.set_defaults(run=status)
    logout_parser = commands.add_parser("logout", help="退出并撤销本机 CLI 会话")
    logout_parser.set_defaults(run=logout)
    publish_parser = commands.add_parser("publish", help="把指定文件放入团队工作池")
    publish_parser.add_argument("files", nargs="+")
    publish_parser.add_argument("--dry-run", action="store_true")
    publish_parser.set_defaults(run=publish)
    recent_parser = commands.add_parser("recent", help="列出近期修改的可选文本文件")
    recent_parser.add_argument("root", nargs="?", default=".")
    recent_parser.add_argument(
        "--limit", type=int, default=12, choices=range(1, 51), metavar="1-50"
    )
    recent_parser.set_defaults(run=list_recent)
    return result


def main():
    args = parser().parse_args()
    try:
        args.run(args)
    except CliError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
