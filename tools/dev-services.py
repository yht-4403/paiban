"""Start/stop this checkout's macOS user launchd services without touching references."""
import argparse
import os
import plistlib
import re
import shutil
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['start','stop','status'])
args = parser.parse_args()
domain = 'gui/' + str(os.getuid())
runtime = root / '.local' / 'services'
runtime.mkdir(parents=True, exist_ok=True)

node = shutil.which('node')
python = root / '.venv' / 'bin' / 'python'
services = {
    'api': [str(python), str(root/'tools/run-api.py')],
    'web': [node or 'node', str(root/'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5186', '--strictPort'],
}
for name, command in services.items():
    label = 'com.accord.' + name
    path = runtime / (label + '.plist')
    if args.action == 'status':
        result = subprocess.run(['launchctl','print',domain+'/'+label],capture_output=True,text=True,check=False)
        print(label + (':' if result.returncode == 0 else ': not loaded'))
        for line in result.stdout.splitlines():
            if re.match(r'^\s*(state|pid|last exit code|runs) = ', line):
                print('  ' + line.strip())
        continue
    if args.action == 'start':
        if not python.exists() or not node:
            raise SystemExit('先按 README 安装 Node 依赖和 Python .venv。')
        environment = {'PATH':str(Path(node).parent)+':/usr/bin:/bin', 'PYTHONPATH':str(root/'apps/api')}
        config = {'Label':label,'ProgramArguments':command,'WorkingDirectory':str(root if name=='api' else root/'apps/web'),
            'EnvironmentVariables':environment,'RunAtLoad':True,'KeepAlive':True,
            'StandardOutPath':'/tmp/accord-'+name+'.log','StandardErrorPath':'/tmp/accord-'+name+'.log'}
        path.write_bytes(plistlib.dumps(config)); path.chmod(0o600)
    subprocess.run(['launchctl','bootout',domain+'/'+label],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    if args.action == 'start':
        for _ in range(40):
            if subprocess.run(['launchctl','print',domain+'/'+label],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode != 0:
                break
            time.sleep(0.15)
        subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
        print(label + ' started')
    else:
        print(label + ' stopped')
