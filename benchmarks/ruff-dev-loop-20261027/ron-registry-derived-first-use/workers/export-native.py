"""Read the complete native-first-use cohort. Includes rejected harness observations separately."""
from pathlib import Path
import io, json, hashlib, subprocess, struct, sys, tarfile
X=Path('/dev/shm/ohm-ron-consumed-v1-20261028');D=Path('/home/dev-user/.cache/ohm-ron-consumed-cargo-20261028')
series={'synchronized':{arm:X/('first-managed-'+suffix) for arm,suffix in [('official','official-v2'),('261','261-v2'),('known','known-v2'),('off','control-v2'),('v2','v2-repeat')]},'natural':{arm:X/('natural-managed-'+suffix) for arm,suffix in [('official','official-v1'),('261','261-v1'),('known','known-v1'),('off','control-v1'),('v2','v2-repeat')]},'migration':{arm:X/('migrate-natural-'+arm+'-v2') for arm in ('official','261')}}
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz');sha=lambda b:hashlib.sha256(b).hexdigest()
def put(name,data):
    item=tarfile.TarInfo(name);item.size=len(data);item.mtime=0;item.mode=0o644;t.addfile(item,io.BytesIO(data))
for experiment,arms in series.items():
    for arm,root in arms.items():
        prefix=experiment+'/'+arm+'/';record=json.loads((root/'complete.json').read_text());put(prefix+'complete.json',(root/'complete.json').read_bytes());put(prefix+'packages.json',(root/'packages.json').read_bytes());put(prefix+'Cargo.lock',(root/'ws/Cargo.lock').read_bytes());put(prefix+'calls',(root/'barrier/actual-derive-calls').read_bytes());
        for arc in root.glob('*.crate'):put(prefix+arc.name,arc.read_bytes())
        for package in (root/'vendor').iterdir():put(prefix+'checksums/'+package.name+'.json',(package/'.cargo-checksum.json').read_bytes())
        for phase,row in record['rows'].items():
            rec=root/phase;assert json.loads((rec/'row.json').read_bytes())==row
            for leaf,h in row['logs'].items():
                f=rec/leaf;blob=f.read_bytes();assert sha(blob)==h;put(prefix+phase+'/'+leaf,blob)
        if experiment=='natural':
            for slot,path in [('old',root/'original-dso'),('new',Path(record['rows']['first-edit']['macro']))]:
                data=path.read_bytes();assert sha(data)==record[slot+'_dso'];off=struct.unpack_from('<Q',data,40)[0];size,n,idx=struct.unpack_from('<HHH',data,58);rows=[struct.unpack_from('<IIQQQQIIQQ',data,off+i*size) for i in range(n)];s,l=rows[idx][4:6];names=data[s:s+l];parts={}
                for r in rows:
                    name=names[r[0]:].split(b'\0',1)[0].decode()
                    if name in ('.text','.rustc','.dynsym'):parts[name]=data[r[4]:r[4]+r[5]]
                assert {k:sha(v) for k,v in parts.items()}==record['sections'][int(slot=='new')]
                for key,value in parts.items():put(prefix+'elf/'+slot+key,value)
            if arm in ('261','v2'):
                for label,state,expected in [('warm','warm',record['rows']['again']['stdout']),('empty','independent','29/29')]:
                    p=root/state/'target/debug/cli';assert subprocess.check_output([p]).decode().strip()==expected;put(prefix+'programs/'+label,p.read_bytes())
for a in ('official','261'):
    for stem in ('first-'+a,'upgrade-'+a):
        for ext in ('out','err','exit'):put('rejected/'+stem+'.'+ext,(D/(stem+'.'+ext)).read_bytes())
for f in ['guard-inputs.sha','v2-guard-inputs.sha','derive-guard.sha','default-guard.sha','derive-guard.exit','default-guard.exit','derive-guard.err','default-guard.err']:put('build/'+f,(D/f).read_bytes())
t.close()
