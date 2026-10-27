from pathlib import Path
import hashlib,json,os,subprocess,sys
p=Path(sys.argv[1]).resolve();p.mkdir(); env=dict(os.environ)
def run(argv):
 r=subprocess.run(argv,cwd=p,env=env,capture_output=True)
 assert r.returncode==0,(argv,r.stderr[:2000]);return r
actual=p/'actual dep'; decoy=p/'actual\\ dep';actual.mkdir();decoy.mkdir()
real=actual/'libd.rlib';fake=decoy/'libd.rlib';fake.write_bytes(b'a legal decoy file behind the escaped spelling')
(p/'lib.rs').write_text('pub fn value() -> u32 { 17 }\n'); (p/'main.rs').write_text('fn main() {println!("{}", d::value());}\n')
r1=['rustc','+ohm','--crate-name','d','--crate-type=rlib','lib.rs','-o',str(real)]
r2=['rustc','+ohm','--edition=2021','main.rs','--extern','d='+str(real),'-Zbinary-dep-depinfo','-Zchecksum-hash-algorithm=sha256','--emit=dep-info=case.d,link=app']
run(r1);run(r2);out=run(['./app']).stdout.decode()
lines=(p/'case.d').read_text().splitlines();match=[s for s in lines if s.startswith('# checksum:') and s.endswith(str(real).replace(' ','\\ '))]
H=lambda x:hashlib.sha256(x).hexdigest()
assert len(match)==1 and out=='17\n'
record=dict(rustc=run(['rustc','+ohm','-vV']).stdout.decode(),argv=[r1,r2],stdout=out,actual=H(real.read_bytes()),decoy=H(fake.read_bytes()),reported=match[0],matches_actual=H(real.read_bytes()) in match[0],matches_decoy=H(fake.read_bytes()) in match[0])
(p/'receipt.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({k:record[k] for k in ('stdout','matches_actual','matches_decoy','actual','decoy')}))
