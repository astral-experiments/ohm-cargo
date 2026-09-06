#!/usr/bin/env python3
"""Check volume-scoped Spotlight controls on a fresh task-owned APFS image."""
import json
from pathlib import Path
import subprocess

root = Path('/private/tmp/codex-cargo-targets/cargo/isolated/clippy-spotlight-smoke')
root.mkdir(exist_ok=False)
mount = root / 'volume'
mount.mkdir()
image = root / 'storage.sparsebundle'
receipt = {'scope': 'fresh disposable task-owned APFS volume only', 'commands': []}
def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True)
    receipt['commands'].append({'argv': list(map(str, argv)), 'returncode': result.returncode,
                                'stdout': result.stdout, 'stderr': result.stderr})
    (root / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return result
assert run(['hdiutil', 'create', '-size', '1g', '-type', 'SPARSEBUNDLE', '-fs', 'APFS',
            '-volname', 'OhmClippySpotlightSmoke', str(image)]).returncode == 0
assert run(['hdiutil', 'attach', '-nobrowse', '-noautoopen', '-mountpoint', str(mount), str(image)]).returncode == 0
try:
    (mount / '.metadata_never_index').touch()
    run(['/usr/bin/mdutil', '-s', str(mount)])
    run(['/usr/bin/mdutil', '-i', 'off', str(mount)])
    run(['/usr/bin/sudo', '-n', '/usr/bin/mdutil', '-i', 'off', str(mount)])
    run(['/usr/bin/mdutil', '-s', str(mount)])
finally:
    assert run(['hdiutil', 'detach', str(mount)]).returncode == 0
print(json.dumps(receipt, indent=2))
