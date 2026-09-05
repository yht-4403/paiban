"""Install the pinned, checksum-verified official macOS ARM64 tunnel client."""
import hashlib
import io
from pathlib import Path
import platform
import tarfile
import urllib.request

VERSION = '2026.8.3'
SHA256 = '40c9144d86df8937c5b43293a1f7d2d2107029aa74725023dd46b1b27154352f'

if __name__ == '__main__':
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('此安装器仅适用于 macOS ARM64；其他平台请按 Cloudflare 官方文档安装。')
    root = Path(__file__).resolve().parent.parent
    destination = root / '.local/bin/cloudflared'
    if destination.exists():
        raise SystemExit('本地 cloudflared 已存在，保留现有文件；本次没有安装或更新。')
    url = f'https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-darwin-arm64.tgz'
    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise SystemExit('官方安装包 SHA-256 校验失败，停止安装。')
    with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as archive:
        member = next(item for item in archive.getmembers() if item.isfile() and item.name.rsplit('/', 1)[-1] == 'cloudflared')
        binary = archive.extractfile(member).read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as output:
        output.write(binary)
    destination.chmod(0o755)
    print(f'cloudflared {VERSION} 已安装，官方 SHA-256 校验通过。')
