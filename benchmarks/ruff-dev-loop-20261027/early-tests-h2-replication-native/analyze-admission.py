"""Cross-check transport failures and the exact inherited diagnostic before the data publication."""
from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
x=json.loads((p/'setup-failure.local.json').read_bytes());assert x['cargo_output_lines']==0 and x['error']=="error: toolchain 'ohm' is not installed" and len(x['corrected_readonly_probes'])==3
s=json.loads((p/'setup-diagnostic.local.json').read_bytes())
for row in s['across_hosts'].values():
    assert row['payload_sha256']=='6d465066830c855472a3d30b1d88e0bdeb5961feac9f319f445db562ad24fa11' and row['payload_bytes']==1560
assert s['h2_quarantine']['all_108_native_committed'] and s['h2_quarantine']['source_backup_units']==617
print(json.dumps({'initial_workspace_execs':0,'genuine_second_seed_units':617,'genuine_second_seed_elf':108,'historical_full_warning_sha':next(iter(s['across_hosts'].values()))['payload_sha256']},sort_keys=True))
