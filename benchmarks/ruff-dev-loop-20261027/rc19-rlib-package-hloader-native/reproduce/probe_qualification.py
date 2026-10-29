import hashlib,json,os,shutil,subprocess as sp
from pathlib import Path

def probe_commands(context,variant,seed='H',source_dir='OLD'):
    R,B,W,ST,Y,S,env,invoke,cli,read,write,sha,run,H,OLD=context
    hold=B/'retired';hold.mkdir(exist_ok=True);ST.rename(hold/('before-'+variant));run(['btrfs','subvolume','snapshot',B/'snapshots'/seed,ST])
    def setsource(value):
        v=H if value=='H' else OLD;other=OLD if v==H else H;e=env()
        if sp.run(['git','diff','--quiet',v,'--'],cwd=W,env=e).returncode:
            run(['git','diff','--quiet',other,'--'],cwd=W,env=e)
            args=['git','apply']+([] if v==H else ['--reverse'])
            run(args+['--check',R/'change.patch'],cwd=W,env=e);run(args+[R/'change.patch'],cwd=W,env=e)
        run(['git','diff','--quiet',v,'--'],cwd=W,env=e)
    setsource('H'if seed=='H' else 'OLD')
    base=invoke(variant+'-base');base_data=read(base/'product.json')
    if base_data['from_this_cargo']:
        settled=invoke(variant+'-settled');base_data=read(settled/'product.json');assert not base_data['from_this_cargo']
    setsource(source_dir);top=Path(base_data['top']);unit=Path(base_data['unit']);assert os.path.samefile(top,unit)
    q=B/'native-references'/variant;q.mkdir(parents=True,exist_ok=False)
    report=R/'reports'/('proof-'+variant);report.mkdir()
    prior=top
    if variant=='real-malformed':prior=q/'invalid.a';prior.write_bytes(b'not a GNU library')
    ost=os.lstat(prior)
    ref=q/'generated-reference.a';native=R/'archive_probe-v2.so'
    mode='observe' if variant=='real-observe' else 'cow'
    ext={'LD_PRELOAD':str(native),'OHM_AR_MODE':mode,'OHM_AR_RUSTC':str(S/'official-sdk/bin/rustc'),'OHM_AR_CRATE':'ruff_linter','OHM_AR_OUT':str(unit.parent),'OHM_AR_FINAL':str(unit),'OHM_AR_PRIOR':str(prior),'OHM_AR_PRIOR_DEV':str(ost.st_dev),'OHM_AR_PRIOR_INO':str(ost.st_ino),'OHM_AR_LOG':str(report/'io.jsonl'),'OHM_AR_REFERENCE':str(ref)}
    with top.open('rb')as oldfd:
        held=q/'hold.rlib'
        # A held FD crosses publication independent of the Btrfs top-level subvolume.
        rep=invoke(variant+'-edited',extra_env=ext);cur=read(rep/'product.json')
        old=hashlib.file_digest(oldfd,'sha256').hexdigest()
    assert cur['from_this_cargo'] and old==base_data['old_candidate_sha'] and cur['old_candidate_sha']!=old
    ev=[json.loads(line)for line in (report/'io.jsonl').read_text().splitlines()]
    assert [z['event']for z in ev]==['enrolled','open','rename','exit'],ev
    last=ev[-1];assert last['closed'] and last['publications']==1 and last['alternate']=='none' and not last['reference_errno']and not last['fatal_errno'],last
    assert sha(ref)==sha(top)==sha(unit)==cur['old_candidate_sha'] and last['generated_bytes']==cur['file_bytes']
    assert last['did_clone']==int(mode=='cow'and variant!='real-malformed')
    assert last['decision']==('prior-magic' if variant=='real-malformed' else ('observe' if mode=='observe'else 'cloned'))
    if last['did_clone']:assert 0<last['skipped_bytes']<last['generated_bytes']
    cli(env(),Path.home()/'.cargo/bin/rustc',R,W,rep,([1] if source_dir=='H'else [2,3,4]),report/'consumer')
    # A fresh command cannot enter the enrolled library even if the hook is loaded.
    repeat=invoke(variant+'-repeat',extra_env={**ext,'OHM_AR_LOG':str(report/'repeat.jsonl')})
    assert not (report/'repeat.jsonl').exists() and not read(repeat/'product.json')['from_this_cargo']
    write(report/'terminal.json',{'old_fd':old,'new':cur['old_candidate_sha'],'reference':sha(ref),'mode':mode,'event':last,'consumer':read(report/'consumer/result.json'),'repeat_fresh':True,'helper_sha256':sha(native),'source':source_dir,'seed':seed})
