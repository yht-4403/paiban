"""Manage daily LAN sharing; public tunneling requires the explicit --public mode."""
import argparse
import datetime
import json
import ipaddress
import os
from pathlib import Path
import plistlib
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / '.local' / 'preview'
LABEL = 'com.accord.preview'
DOMAIN = 'gui/' + str(os.getuid())
STATE = RUNTIME / 'status.json'
LOG = Path('/tmp/accord-preview.log')
SHANGHAI = datetime.timezone(datetime.timedelta(hours=8))


def end_of_today(now=None):
    now = now or datetime.datetime.now(SHANGHAI)
    return (now.astimezone(SHANGHAI).replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)).timestamp()


def save_state(**data):
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False))
    temporary.chmod(0o600)
    temporary.replace(STATE)


def workspace_ready():
    with urllib.request.urlopen('http://127.0.0.1:8786/api/auth/status', timeout=5) as response:
        if json.load(response)['needs_setup']:
            raise RuntimeError('请先在 http://127.0.0.1:5186/ 创建工作空间，再开放团队访问。')


def serve():
    expires_at = float(os.environ.get('ACCORD_PREVIEW_EXPIRES_AT', '0'))
    lan = os.environ.get('ACCORD_PREVIEW_MODE') == 'lan'
    children = []
    events = queue.Queue()
    def terminate(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        save_state(ready=False)
        if time.time() >= expires_at:
            return
        workspace_ready()
        if lan:
            address = os.environ['ACCORD_PREVIEW_HOST']
            url = 'http://' + address + ':5188'
        else:
            url = None
        tunnel = None if lan else subprocess.Popen([
            str(ROOT / '.local/bin/cloudflared'), 'tunnel', '--no-autoupdate',
            '--url', 'http://127.0.0.1:5188', '--protocol', 'http2',
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if tunnel is not None:
            children.append(tunnel)
        def read_tunnel():
            for line in tunnel.stdout:
                print(line.rstrip(), flush=True)
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
                if match:
                    events.put(('url', match.group()))
                if 'Registered tunnel connection' in line:
                    events.put(('connected', True))
        if tunnel is not None:
            threading.Thread(target=read_tunnel, daemon=True).start()
        deadline = time.monotonic() + 75
        connected = lan
        while not url or not connected:
            if time.time() >= expires_at:
                return
            if tunnel.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('临时隧道未能连接 Cloudflare；查看 /tmp/accord-preview.log。')
            try:
                kind, value = events.get(timeout=1)
                if kind == 'url': url = value
                else: connected = value
            except queue.Empty:
                pass
        from urllib.parse import urlsplit
        environment = dict(os.environ, ACCORD_PREVIEW_HOST=urlsplit(url).hostname)
        web = subprocess.Popen([
            shutil.which('node'), str(ROOT / 'node_modules/vite/bin/vite.js'),
            '--host', address if lan else '127.0.0.1', '--port', '5188', '--strictPort',
        ], cwd=ROOT / 'apps/web', env=environment)
        children.append(web)
        for _ in range(60):
            if web.poll() is not None:
                raise RuntimeError('团队预览前端启动失败。')
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open((url if lan else 'http://127.0.0.1:5188') + '/api/auth/status', timeout=1) as response:
                    if response.status == 200: break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError('团队预览前端未就绪。')
        awake = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())])
        children.append(awake)
        save_state(ready=True, url=url, pid=os.getpid(), expires_at=expires_at, mode='lan' if lan else 'tunnel')
        while all(process.poll() is None for process in children):
            if time.time() >= expires_at:
                print('今日临时共享已到期，关闭隧道。', flush=True)
                return
            time.sleep(1)
        raise RuntimeError('预览子进程退出，将由 launchd 重启并生成新地址。')
    finally:
        save_state(ready=False)
        for process in reversed(children):
            if process.poll() is None: process.terminate()
        for process in children:
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'serve'])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--lan', dest='lan', action='store_true', help='仅在当前局域网地址监听（默认）')
    mode.add_argument('--public', dest='lan', action='store_false', help='显式启动公网隧道')
    parser.set_defaults(lan=True)
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.action == 'serve':
        serve()
        return
    if args.action == 'status':
        loaded = subprocess.run(['launchctl', 'print', DOMAIN + '/' + LABEL], capture_output=True).returncode == 0
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        if loaded and state.get('ready') and time.time() < state.get('expires_at', 0):
            print(state['url'])
            print('自动关闭：' + datetime.datetime.fromtimestamp(state['expires_at'], SHANGHAI).isoformat())
        else:
            print('团队预览未就绪。')
        return
    if args.action == 'start':
        workspace_ready()
        if (not args.lan and not (ROOT / '.local/bin/cloudflared').exists()) or not shutil.which('node'):
            raise SystemExit('请按 README 安装 cloudflared 与 Node.js。')
        if args.lan:
            addresses = []
            for interface in ('en0', 'en1'):
                result = subprocess.run(['/usr/sbin/ipconfig', 'getifaddr', interface], capture_output=True, text=True)
                if result.returncode == 0:
                    ip = ipaddress.ip_address(result.stdout.strip())
                    if any(ip in ipaddress.ip_network(network) for network in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
                        addresses.append(str(ip))
            if not addresses:
                raise SystemExit('未找到当前 Wi-Fi 或以太网的局域网地址。')
    subprocess.run(['launchctl', 'bootout', DOMAIN + '/' + LABEL], capture_output=True)
    for _ in range(50):
        if subprocess.run(['launchctl', 'print', DOMAIN + '/' + LABEL], capture_output=True).returncode != 0: break
        time.sleep(0.2)
    save_state(ready=False)
    if args.action == 'stop':
        print('团队预览已关闭；本地开发服务继续运行。')
        return
    LOG.touch(mode=0o600, exist_ok=True)
    LOG.chmod(0o600)
    config = {
        'Label': LABEL, 'ProgramArguments': ['/usr/bin/python3', str(Path(__file__).resolve()), 'serve'],
        'WorkingDirectory': str(ROOT), 'RunAtLoad': True, 'KeepAlive': {'SuccessfulExit': False}, 'ThrottleInterval': 60,
        'EnvironmentVariables': {
            'PATH': str(Path(shutil.which('node')).parent) + ':/usr/bin:/bin',
            'ACCORD_PREVIEW_EXPIRES_AT': str(end_of_today()),
            **({'ACCORD_PREVIEW_MODE': 'lan', 'ACCORD_PREVIEW_HOST': addresses[0]} if args.lan else {}),
        },
        'StandardOutPath': str(LOG), 'StandardErrorPath': str(LOG),
    }
    path = RUNTIME / (LABEL + '.plist')
    path.write_bytes(plistlib.dumps(config)); path.chmod(0o600)
    subprocess.run(['launchctl', 'bootstrap', DOMAIN, str(path)], check=True)
    print('团队预览启动中；用 python3 tools/preview-services.py status 查看地址。')


if __name__ == '__main__':
    main()
