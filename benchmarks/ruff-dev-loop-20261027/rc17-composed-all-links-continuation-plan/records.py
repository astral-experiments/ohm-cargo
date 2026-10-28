"""Match the original worker's JSON wire representation, preserving every channel."""
import json


def check_wire(memory, disk):
    encoded=(json.dumps(memory,sort_keys=True,indent=2)+'\n').encode()
    assert encoded==disk
    return json.loads(disk)


def compare(phase,current,old,registry,expected):
    seed=phase.startswith('seed')
    for key in ['fresh','units','counts','roster','diagnostics','exes','e2e','ty_server']:
        assert current[key]==old[key],(phase,key)
    assert len(registry)==78
    if seed:
        assert all(old['native'][k]==v for k,v in registry.items())
        assert set(current['native'])==set(old['native'])-set(registry)
    else:
        assert set(current['native'])==set(old['native'])
    for k in set(current['native'])-set(expected):
        assert current['native'][k]==old['native'][k]
