"""Exercise the exact two stopped acquisitions, authenticated bootstrap and terminal reader."""
from pathlib import Path
import copy,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bootstrap_lineage as b
from catalog import sha


def run():
    old=b.RECEIPT;hist=old['approved_registration'];reg={**hist,'bootstrap_ref':b.BOOT,'bootstrap_sha256':b.BOOT_MANIFEST};tree=old['new_root_preverified']
    hashes={k:old[v] for k,v in [('old_failure','immutable_v1_exception'),('old_exit','immutable_v1_exit'),('startup_exit','startup_exit1'),
            ('startup_stderr','launcher_stderr'),('startup_failure','frozen_continuation_traceback')]}
    n=0
    def reject(fn):
        nonlocal n
        try:fn()
        except (ValueError,KeyError,FileNotFoundError):n+=1;return
        raise AssertionError('changed bootstrap evidence accepted')
    def check(ids=reg,contents=hashes,rc=b'0\n',state=tree):return b.check(hist,ids,contents,rc,state)
    assert check()['original_native_verifier_sha256']==b.VERIFIER
    for key in hashes:
        reject(lambda:check(contents={k:v for k,v in hashes.items() if k!=key}));reject(lambda:check(contents={**hashes,key:'f'*64}))
    for key in reg:reject(lambda:check(ids={**reg,key:'f'*len(reg[key])}))
    for rc in (b'1\n',b'',b'0\n0\n'):reject(lambda:check(rc=rc))
    for field in ('seed_state','byte_matched_copy','preserved_original'):
        drift=copy.deepcopy(tree);drift[field]['digest']='a'*64;reject(lambda:check(state=drift))
    for field in ('host_visible_original_inode','host_visible_copy_inode','host_visible_original_root','host_visible_copy_root','cross_root_regular_inode_overlap'):
        reject(lambda:check(state=tree|{field:None}))
    view='c'*64;done={**reg,'whole_native_view_sha256':view,'startup_snapshot_binding':b.STARTUP_SHA,'completed_original_verifier_sha256':b.VERIFIER}
    b.completion(reg,done,view,b.VERIFIER)
    for key in done:reject(lambda:b.completion(reg,done|{key:'e'*len(done[key])},view,b.VERIFIER))
    reject(lambda:b.completion(reg,done,view,'0'*64));reject(lambda:b.completion(reg,done,'d'*64,b.VERIFIER))
    return dict(rejected=n,root1_exit=hashes['old_exit'],root1_traceback=hashes['old_failure'],root2_exit=hashes['startup_exit'],root2_stderr=hashes['startup_stderr'],root2_traceback=hashes['startup_failure'],original_verify_sha256=b.VERIFIER,source_only=True)
if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
