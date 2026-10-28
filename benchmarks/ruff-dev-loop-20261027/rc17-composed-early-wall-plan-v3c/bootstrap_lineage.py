"""Authenticate the one-namespace bootstrap and retain both original failed launches."""
from pathlib import Path
from catalog import must, read, sha

HERE=Path(__file__).resolve().parent
WALL_B='18d39259d88610e634243199b707c5435a506d77'
WALL_B_MANIFEST='2db9f4a735f6ebaab6f86c77e5643d6a99dd00c7691d62de2bb1e168720ce3c8'
BOOT='4de32538d02e25b5c8f75e58eea48c9b55fd0445'
BOOT_MANIFEST='72fbc1e3b648cdd6a89ca117bf6ba8b4cb8a163e2610327389dbe5a97f58f159'
STARTUP_SHA='cd8d653f5db451375782840f0f920196a6943253681f16d9cee4f46f40b53fc8'
VERIFIER='ef9d5f2ae76597aea7070ca978909d7fa38ec69a369b4ad2ca058642ed8aca35'
RECEIPT=read(HERE/'bootstrap-startup.json')


def check(historical, registration, hashes, code, before):
    must(sha(HERE/'bootstrap-startup.json')==STARTUP_SHA and historical==RECEIPT['approved_registration'], 'different registered bootstrap startup')
    must(registration=={**historical,'bootstrap_ref':BOOT,'bootstrap_sha256':BOOT_MANIFEST},'different bootstrap registration')
    expected={k:RECEIPT[v] for k,v in [('old_failure','immutable_v1_exception'),('old_exit','immutable_v1_exit'),
               ('startup_exit','startup_exit1'),('startup_stderr','launcher_stderr'),('startup_failure','frozen_continuation_traceback')]}
    must(hashes==expected and code==b'0\n','original failure pair or bootstrap exit diverged')
    must(before==RECEIPT['new_root_preverified'],'bootstrap did not adopt the exact original seed, tree and inodes')
    fields={'native_bootstrap_ref':BOOT,'native_bootstrap_manifest':BOOT_MANIFEST,'original_native_verifier_sha256':VERIFIER,
            'bootstrap_startup_sha256':STARTUP_SHA,'bootstrap_prior_stderr_sha256':hashes['startup_stderr'],
            'bootstrap_prior_traceback_sha256':hashes['startup_failure'],'v3b_wall_ref':WALL_B,'v3b_wall_manifest':WALL_B_MANIFEST}
    return fields


def completion(reg,done,view,verifier):
    must(verifier==VERIFIER and done=={**reg,'whole_native_view_sha256':view,'startup_snapshot_binding':STARTUP_SHA,
         'completed_original_verifier_sha256':VERIFIER},'bootstrap did not finish on the previously registered verifier and view')


def physical(g, historical):
    base=g.BASE;old=base/'whole-wild-width-v1';new=base/'whole-wild-width-v2';work=base/'whole-wild-width-v2-protocol';boot=base/'whole-wild-width-v2-bootstrap'
    must(g.manifest(base/'wall-protocol-v3b')==WALL_B_MANIFEST and read(base/'wall-launch-v3b/binding.json')=={'ref':WALL_B,'sha256':WALL_B_MANIFEST}
         and not any((base/n).exists() for n in ('early-scheduler-wall-admission-v3b.json','early-scheduler-wall-admission-v3b.failure','early-scheduler-wall-rc17-v3b')),
         'v3b registration changed or already attempted')
    must(not boot.is_symlink() and boot.is_dir() and g.manifest(boot/'source')==BOOT_MANIFEST and sha(boot/'source/startup-binding.json')==STARTUP_SHA,
         'wrong installed native bootstrap source')
    files={'old_failure':old/'failure.txt','old_exit':old/'exit','startup_exit':work/'exit','startup_stderr':work/'stderr',
           'startup_failure':new/'continuation-failure.txt'}
    required=[*files.values(),boot/'exit',boot/'registration.json',new/'tree-before-resume.json',new/'bootstrap-completion.json',new/'source/verify.py',new/'wall-view.json']
    must(all(f.is_file() and not f.is_symlink() and f.resolve()==f.absolute() for f in required),'an original, bootstrap or terminal receipt is missing or aliased')
    reg=read(boot/'registration.json');done=read(new/'bootstrap-completion.json');view=sha(new/'wall-view.json')
    completion(reg,done,view,sha(new/'source/verify.py'))
    fields=check(historical,reg,{k:sha(f) for k,f in files.items()},(boot/'exit').read_bytes(),read(new/'tree-before-resume.json'))
    return {**fields,'bootstrap_registration_sha256':sha(boot/'registration.json'),'bootstrap_completion_sha256':sha(new/'bootstrap-completion.json')}
