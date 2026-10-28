"""Source-matched independent unspaced-target control; scratch medium, old canonical SDK/home and vendor corpus."""
import fcntl,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import collect as x
w=x.w;m=w.m
O=x.O/'unspaced-native-v1'
def existing_view(image,arm):
    d=w.native/(arm+'-ty_wasm')
    checks=json.loads((d/'binding.json').read_bytes())['hashes']
    locations=json.loads((w.source_k/'locations.json').read_bytes());images=m.images
    name=next(Path(n).name for n in checks if 'librustc_driver-' in n)
    dirs=['--ro-bind',str(images/locations['common']),str(m.sdk),'--ro-bind',str(images/locations[image]['cargo']),str(m.sdk/'bin/cargo'),'--ro-bind',str(images/locations[image]['driver']),str(m.sdk/'lib'/name)]
    return w.native/('view-'+arm)/'rustup',dirs,checks
def main():
    os.sched_setaffinity(0,set(range(8)));x.check_free(68)
    with (x.P/'member-build-native.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);w.q.source_gate()
        O.mkdir(mode=0o700);m.o=O;m.target=O/'ruff_target';m.target.mkdir();m.toolview=existing_view
        assert ' ' not in str(m.target)
        phases=[('cold','original'),('train','original'),('settled','original'),('edit','reversed'),('edited-noop','reversed'),('restore','original'),('restore-noop','original')]
        all_={}
        for image in 'BC':
            x.check_free(65)
            rows=m.worker(image+'wasm','ty_wasm','original',phases)
            for r in rows[2:]:
                assert r['units']==304
                if r['step'] in ('edit','restore'):
                    assert sorted((c,k) for c,k in r['jobs'])==[('ty_vendored','full'),('ty_wasm','full')] and r['wild']==1,r
                else:assert r['jobs']==[] and not r['wild'] and not r['dirty'],r
            all_[image]=rows
        for a,b in zip(all_['B'],all_['C']):
            assert a['zip']==b['zip']
            assert a['outputs']['debug/libty_wasm.so']==b['outputs']['debug/libty_wasm.so']
        w.q.source_gate();x.emit(O/'complete.json',all_)
if __name__=='__main__':main()
