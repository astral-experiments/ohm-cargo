"""Isolate one full 1.48MB BLAKE3 witness without changing source, actual input, compiler, or cwd within a comparison."""
import fcntl,hashlib,itertools,json,os,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import collect as x
w=x.w;m=w.m;O=x.O/'zip-cost-v1';V=x.O/'software-counters/callgrind'
def main():
    os.sched_setaffinity(0,{0});x.check_free(62)
    with (x.P/'member-build-native.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);m.q.source_gate()
        O.mkdir();active=O/'active';lookup=O/'inputs';active.mkdir();lookup.mkdir()
        original=w.contract['Cwasm-ty_wasm']['original']
        product=w.native/'Cwasm-ty_wasm/state'/original['zip_path']
        assert w.q.sha(product) in original['zips']
        expected_len=product.stat().st_size
        for condition in ('absent','equal'):
            k=O/condition;k.mkdir()
            (k/'lib.rs').write_text('pub static ZIP: &[u8] = include_bytes!("asset space.zip");\n')
            shutil.copyfile(product,k/'asset space.zip')
            if condition=='equal':shutil.copyfile(product,k/'asset\\ space.zip')
        common=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(m.images/'sdk'),str(m.sdk),'--ro-bind',str(V/'usr/lib/debug'),'/usr/lib/debug']
        locations=json.loads((w.source_k/'locations.json').read_bytes());data=[]
        for repeat in range(4):
            # Mirror each within-image comparison, retaining every identical-input trial.
            group=[('B','absent'),('B','equal'),('C','absent'),('C','equal')]
            if repeat%2:group.reverse()
            for image,condition in group:
                mv=m.images/locations[image]['driver'];rr=O/'rows'/f'{repeat+1:02}-{image}-{condition}';rr.mkdir(parents=True)
                assert w.q.sha(mv)==w.m.plan['arms'][image]['driver']
                do=common+['--ro-bind',str(mv),str(m.sdk/'lib'/mv.name),'--ro-bind',str(O/condition),str(lookup),'--bind',str(rr),str(active),'--chdir',str(lookup),'--']
                env=dict(PATH='/usr/bin:/bin',HOME='/tmp',LANG='C',LD_LIBRARY_PATH=str(m.sdk/'lib'),VALGRIND_LIB=str(V/'usr/libexec/valgrind'))
                cmd=[str(V/'usr/bin/valgrind.bin'),'--tool=callgrind','--trace-children=no','--log-file='+str(active/'v.log'),'--callgrind-out-file='+str(active/'count'),str(m.sdk/'bin/rustc'),'--sysroot',str(m.sdk),'--edition=2024','--crate-name','zip_hash_probe','--crate-type=lib','-Zchecksum-hash-algorithm=blake3','--emit=dep-info='+str(active/'zip.d'),'lib.rs']
                r=subprocess.run([*do,*cmd],env=env,capture_output=True);(rr/'stdout').write_bytes(r.stdout);(rr/'stderr').write_bytes(r.stderr);assert not r.returncode,(image,r.stderr[-600:])
                p=(rr/'zip.d').read_text();rows=[s for s in p.splitlines() if s.startswith('# checksum:') and s.endswith(r'asset\ space.zip') and f'file_len:{expected_len} ' in s]
                assert bool(rows)==(image=='C' or condition=='equal'),(rows,image,condition,p)
                counts=[int(s.split()[1]) for s in (rr/'count').read_text().splitlines() if s.startswith('summary:')];assert len(counts)==1 and counts[0]>100000
                data.append({'image':image,'case':condition,'repeat':repeat+1,'potential_checksum':rows,'ir':counts[0],'raw_count_sha':w.q.sha(rr/'count')})
        assert len({e['potential_checksum'][0] for e in data if e['potential_checksum']})==1
        x.emit(O/'complete.json',dict(raw_zip=w.q.sha(product),bytes=expected_len,results=data))
if __name__=='__main__':main()
