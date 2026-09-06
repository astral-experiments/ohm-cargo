#!/usr/bin/env python3
"""Read Spotlight status for one fresh task-owned volume at its standard mount."""
import json
from pathlib import Path
import plistlib
import subprocess
import time

root = Path('/private/tmp/codex-cargo-targets/cargo/isolated/clippy-spotlight-smoke')
image = root / 'standard-mount.sparsebundle'
receipt = {'scope': 'fresh task-owned volume; read indexing status only', 'commands': []}
def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True)
    receipt['commands'].append({'argv': list(map(str, argv)), 'returncode': result.returncode,
                                'stdout': result.stdout, 'stderr': result.stderr})
    (root / 'standard-mount.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return result
assert run(['hdiutil', 'create', '-size', '1g', '-type', 'SPARSEBUNDLE', '-fs', 'APFS',
            '-volname', 'OhmClippySpotlightStandard', str(image)]).returncode == 0
attached = run(['hdiutil', 'attach', '-nobrowse', '-noautoopen', '-plist', str(image)])
assert attached.returncode == 0
mount = Path(next(item['mount-point'] for item in plistlib.loads(attached.stdout.encode())['system-entities']
                  if item.get('volume-kind') == 'apfs' and 'mount-point' in item))
receipt['mount'] = str(mount)
try:
    for delay in [0, 2, 5]:
        time.sleep(delay)
        run(['/usr/bin/mdutil', '-s', str(mount)])
finally:
    assert run(['hdiutil', 'detach', str(mount)]).returncode == 0
print(json.dumps(receipt, indent=2))
