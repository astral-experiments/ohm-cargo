"""Preserve the stopped qualification and execute the approved continuation in a new physical copy."""
import fcntl,hashlib,importlib.util,json,os,shutil,socket,subprocess,sys
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
OLD=P/'whole-wild-width-v1';NEW=P/'whole-wild-width-v2';PROTO=P/'whole-wild-width-v2-protocol'
G=P/'wall-protocol-v2'
sys.path.insert(0,str(G))
import guards


def write(p,value):
    with p.open('x') as f:json.dump(value,f,sort_keys=True,indent=2);f.write('\n')


def ids(root):
    return {(s.st_dev,s.st_ino) for p in root.rglob('*') if p.is_file() and not p.is_symlink() and (s:=p.stat())}


def main():
    assert socket.gethostname()=='charlie-ohm-c5-check-1025' and Path(__file__).resolve().parent==PROTO/'source'
    reg=json.loads((PROTO/'registration.json').read_bytes())
    assert reg['original_ref']=='5b9490236f0557fb748a7b7e527e45452002904b'
    assert reg['stopped_evidence_ref']=='f89d4913d40733b45227a41bb49d39cbb6d41015'
    assert reg['stopped_evidence_sha256']=='5ff97dc91c067bf0e5da4a3e3097adc193ca71169aa1f0506fd05849719c284b'
    assert not NEW.exists() and (OLD/'exit').read_text().strip()=='1' and not (OLD/'commands/seed-repeat2').exists()
    for folder,expected in [(OLD/'source',reg['original_protocol_sha256']),(PROTO/'source',reg['continuation_sha256'])]:
        assert hashlib.sha256((folder/'SHA256SUMS').read_bytes()).hexdigest()==expected
        for ln in (folder/'SHA256SUMS').read_text().splitlines():
            h,n=ln.split('  ');assert hashlib.sha256((folder/n).read_bytes()).hexdigest()==h
    with (P/'combined-native-measure.lock').open('r') as hold:
        fcntl.flock(hold,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=guards.tree(OLD);source_state=guards.tree(OLD/'states/seed')
        assert shutil.disk_usage(P).free>before['unique_file_bytes']+66*2**30
        subprocess.run(['cp','-a','--reflink=never','--',OLD,NEW],check=True)
        assert NEW.stat().st_dev==OLD.stat().st_dev and NEW.stat().st_ino!=OLD.stat().st_ino
        assert guards.tree(NEW)==before and guards.tree(NEW/'states/seed')==source_state
        assert ids(NEW).isdisjoint(ids(OLD))
        write(NEW/'tree-before-resume.json',{'preserved_original':before,'byte_matched_copy':before,'seed_state':source_state,
               'cross_root_regular_inode_overlap':0,'host_visible_original_inode':OLD.stat().st_ino,
               'host_visible_copy_inode':NEW.stat().st_ino,'host_visible_original_root':str(OLD),'host_visible_copy_root':str(NEW)})
        write(NEW/'continuation-registration.json',reg)
    ns=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp',
        '--bind',str(NEW),str(OLD),'--bind',str(NEW),str(NEW),'--chdir',str(OLD),'--']
    subprocess.run(ns+['/usr/bin/python3','-IBu',str(PROTO/'source/resume.py')],check=True)
    assert guards.tree(OLD)==before and guards.tree(OLD/'states/seed')==source_state
    assert (OLD/'exit').read_text().strip()=='1' and not (OLD/'commands/seed-repeat2').exists()
    write(NEW/'physical-preservation.json',{'old_complete_tree_final_sha256':before['digest'],'old_seed_state_final_sha256':source_state['digest'],
            'original_and_copy_initially_identical':True,'original_original_exit':1,'preserved_sources_and_stop':True})


if __name__=='__main__':main()
