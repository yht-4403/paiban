"""Load server-only local configuration, then start the single-process API."""
import argparse
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'apps' / 'api'))
if (root / '.env').exists():
    for line in (root / '.env').read_text().splitlines():
        key, separator, value = line.partition('=')
        if separator and key.strip().startswith('ACCORD_'):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

if __name__ == '__main__':
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8786)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    uvicorn.run('accord_api.main:app', host=args.host, port=args.port, access_log=False)
