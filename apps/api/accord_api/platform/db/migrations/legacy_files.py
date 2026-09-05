from datetime import datetime

from accord_api.platform.config import data_root
from accord_api.platform.db.database import execute, now, query


def _safe_name(title: str) -> str:
    raw = (title or '未命名').strip() or '未命名'
    for ch in '\\/:*?"<>|':
        raw = raw.replace(ch, '_')
    return raw[:60]


def export_missing_pool_files() -> None:
    rows = query('SELECT id, title, body, path FROM artifacts')
    for r in rows:
        if r['path']:
            continue
        fpath = write_pool_file(r['title'], r['body'], '')
        execute('UPDATE artifacts SET path=? WHERE id=?', (fpath, r['id']))


def write_pool_file(title: str, body: str, author: str = '') -> str:
    POOL_DIR = data_root() / '工作池'
    POOL_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    ts = now()
    name = f'{stamp}-{_safe_name(title)}.md'
    path = POOL_DIR / name
    header = f'# {title}\n\n'
    header += f'上传人：{author or "未知"}\n时间：{ts}\n\n'
    path.write_text(header + (body or '').strip() + '\n', encoding='utf-8')
    return str(path)
