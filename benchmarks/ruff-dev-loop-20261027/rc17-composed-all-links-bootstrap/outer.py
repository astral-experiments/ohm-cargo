"""Launch frozen native code with the missing import path and verify the old physical tree."""
import fcntl, hashlib, json, subprocess, sys
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
ORIGINAL=P/'whole-wild-width-v1';COPY=P/'whole-wild-width-v2'
PREVIOUS=P/'whole-wild-width-v2-protocol';THIS=P/'whole-wild-width-v2-bootstrap';SOURCE=THIS/'source'
sys.path.insert(0,str(P/'wall-protocol-v2'))
import guards
sys.path.insert(0,str(SOURCE))
import flat


def write(p,record):
    with p.open('x') as f:json.dump(record,f,sort_keys=True,indent=2);f.write('\n')


def main():
    reg=guards.read(THIS/'registration.json');old=guards.read(SOURCE/'startup-binding.json')
    assert Path(__file__).resolve().parent==SOURCE and len(reg['bootstrap_ref'])==40
    assert reg['bootstrap_sha256']==guards.sha(SOURCE/'SHA256SUMS')
    for directory in [SOURCE,PREVIOUS/'source',ORIGINAL/'source']:
        for line in (directory/'SHA256SUMS').read_text().splitlines():
            h,n=line.split('  ');assert guards.sha(directory/n)==h
    assert old['approved_registration']==guards.read(PREVIOUS/'registration.json')==guards.read(COPY/'continuation-registration.json')
    assert (PREVIOUS/'exit').read_text().strip()=='1' and guards.sha(PREVIOUS/'stderr')==old['launcher_stderr']
    assert guards.sha(COPY/'continuation-failure.txt')==old['frozen_continuation_traceback']
    assert not (COPY/'commands/seed-repeat2').exists() and not (COPY/'captures/seed-repeat2').exists()
    before=old['new_root_preverified']['preserved_original'];seed=old['new_root_preverified']['seed_state']
    with (P/'combined-native-measure.lock').open('r') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert guards.tree(ORIGINAL)==before and guards.tree(COPY/'states/seed')==seed
    with (P/'combined-native-measure.lock').open('r') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        __import__('os').sched_setaffinity(0,set(range(16)))
        flat.run()
    assert guards.tree(ORIGINAL)==before and guards.tree(ORIGINAL/'states/seed')==seed
    assert (ORIGINAL/'exit').read_text().strip()=='1' and not (ORIGINAL/'commands/seed-repeat2').exists()
    assert guards.sha(COPY/'continuation-failure.txt')==old['frozen_continuation_traceback']
    assert guards.sha(PREVIOUS/'stderr')==old['launcher_stderr'] and guards.sha(PREVIOUS/'exit')==old['startup_exit1']
    write(COPY/'physical-preservation.json',{'old_complete_tree_final_sha256':before['digest'],'old_seed_state_final_sha256':seed['digest'],
       'original_and_copy_initially_identical':True,'old_capture_and_startup_exits':1,'preserved_sources_and_stop':True,
       'startup_traceback_sha256':old['frozen_continuation_traceback']})
    write(COPY/'bootstrap-completion.json',{**reg,'whole_native_view_sha256':guards.sha(COPY/'wall-view.json'),
         'startup_snapshot_binding':guards.sha(SOURCE/'startup-binding.json'),
         'completed_original_verifier_sha256':guards.sha(COPY/'source/verify.py')})


if __name__=='__main__':main()
