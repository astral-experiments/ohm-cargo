"""Read authentic old/new incremental headers at one literal path across a driver replacement."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys

P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027'); F=P/'frozen-toolchain'
X=Path.home()/'.cache/ohm-233-position-qualified-20261027'
spec=X/'mixed-registry-seed-programs-20261027/rmake-incremental-proc-macro-source-tracked-final/fixture'
base=X/'drivers/driver-dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'
image=Path(sys.argv[1]); out=P/'mixed-registry-only-pilot'/('parse-cache-upgrade-'+sys.argv[2])
out.mkdir(mode=0o700); src=out/'src';shutil.copytree(spec,src)
cfg=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',RUSTC_BOOTSTRAP='1')
def sha(f):
    with f.open('rb') as v:return hashlib.file_digest(v,'sha256').hexdigest()
def dump(f,x):f.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def run(label,arm,argv):
    d=out/label;d.mkdir()
    ns=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(out),str(out),'--ro-bind',str(arm),str(F/'lib/librustc_driver-774a793a844d5500.so'),'--chdir',str(src),'--']
    p=subprocess.run([*ns,*map(str,argv)],env=cfg,capture_output=True)
    (d/'stdout').write_bytes(p.stdout);(d/'stderr').write_bytes(p.stderr);dump(d/'status.json',dict(returncode=p.returncode,argv=list(map(str,argv))))
    assert not p.returncode,(label,p.stderr.decode()[-800:]);return p
cpp=['rustc','+ohm','--edition=2024']
status={};original=(src/'producer.rs').read_text()
run('plugin',base,[*cpp,'maker.rs','-o',src/'libmaker.so'])
for label,driver,num,asset,inc,epoch,executed in [
    ('old-prime',base,7,'91','same',2,True),('upgrade',image,8,'379','same',3,True),
    ('upgrade-empty',image,8,'379','empty1',3,True),('future-warm',image,9,'379','same',3,False),
    ('future-empty',image,9,'379','empty2',3,True),('downgrade',base,8,'379','same',2,True),
    ('downgrade-empty',base,8,'379','empty3',2,True)]:
    (src/'producer.rs').write_text(original.replace('    7',f'    {num}'))
    (src/'parse-input.txt').write_text(asset)
    p=run(label,driver,[*cpp,'producer.rs','--extern','maker=libmaker.so','-Cincremental='+str(out/inc),'-Zcache-proc-macros','-Zpublic-api-hash','--emit=link,metadata'])
    observed=b'executed attribute' in p.stderr and b'\nexecuted derive\n' in b'\n'+p.stderr
    assert observed==executed and b'executed tracked derive' in p.stderr,(label,p.stderr)
    # Rustc may retain a (non-current) previous session on disk. Read the newest successful one.
    q=max((out/inc).glob('producer-*/s-*/query-cache.bin'),key=lambda f:f.stat().st_mtime_ns)
    with q.open('rb') as f:head=f.read(6)
    assert head==b'RSIC'+epoch.to_bytes(2,'little'),(label,q,head)
    d=out/label;shutil.copyfile(src/'libproducer.rmeta',d/'raw.rmeta')
    entry=dict(query_cache=str(q.relative_to(out)),header_hex=head.hex(),attribute_and_plain_derive_executed=observed,raw_rmeta_sha256=sha(d/'raw.rmeta'),observed=None)
    if label!='old-prime':
        (src/'external.rs').write_text('fn main() { println!("{}:{:?}:{}", producer::value(), producer::position(), producer::TRACKED); }\n')
        run(label+'-caller',driver,[*cpp,'external.rs','--extern','producer=libproducer.rlib','-L','dependency=.', '-o',src/'external'])
        entry['observed']=run(label+'-native',driver,[src/'external']).stdout.decode().strip()
        assert entry['observed'].startswith(str(num)+':') and entry['observed'].endswith(':379')
    status[label]=entry;dump(out/'results.json',status)
for warm,cold in [('upgrade','upgrade-empty'),('future-warm','future-empty'),('downgrade','downgrade-empty')]:
    for k in ['observed','raw_rmeta_sha256']:assert status[warm][k]==status[cold][k],(warm,k)
dump(out/'complete.json',dict(parent_sha256=sha(base),candidate_sha256=sha(image),results_sha256=sha(out/'results.json')))
