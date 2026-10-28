"""Retain all instruction reports, genuine migration commands, and original file checksums."""
import gzip, hashlib, io, json, os, re, tarfile
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-paths-over261-20261028')
T=H.parent/'ohm-depfile-over261-tests-20261028'
out=H/'portable-261-linter';out.mkdir()
score=H/'qualified-261-linter';assert (score/'score.json').is_file()
sha=lambda b:hashlib.sha256(b).hexdigest()
def pack(label,entries):
    records={}
    with (out/(label+'.tar.gz')).open('xb') as f,gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as z,tarfile.open(fileobj=z,mode='w|',format=tarfile.PAX_FORMAT) as tar:
        for n,p in sorted(entries.items()):
            assert not Path(n).is_absolute() and '..' not in Path(n).parts
            raw=p.read_bytes(); public=re.sub(rb'socket-firewall-registry[.][A-Za-z0-9_.-]+-[a-f0-9]{16}', b'registry-fixture-hash',raw)
            assert b'socket-firewall-registry' not in public,(n, raw[:40])
            ti=tarfile.TarInfo(n);ti.size=len(public);ti.mode=0o644
            tar.addfile(ti,io.BytesIO(public));records[n]=[sha(raw),sha(public)]
    (out/(label+'-files.json')).write_text(json.dumps(records,sort_keys=True,indent=2)+'\n')
def selected(root,skip=None):
    return {str(p.relative_to(root)):p for p in root.rglob('*') if p.is_file() and (not skip or not skip(p))}
ir=selected(score/'library/ir');assert len([n for n in ir if n.endswith('/record.json')])==32;pack('counters',ir)
native={}
for p in [score/'qualify.json',score/'score.json',H/'ready.json',H/'native-ready.json',H/'qualified-pair.json',H/'adversarial/stock.json']:
    native[str(p.relative_to(H))]=p
for d in [score/'library/qual',score/'library/post-ir',H/'warm-original',H/'warm-historical-edit',H/'warm-settled']:
    for n,p in selected(d).items():native[str(p.relative_to(H))]=p
pack('native',native)
mig={}
for case in ('tracked-file','include-str','include-bytes'):
    stock=H/'adversarial'/(case+'-stock');mig[f'original/{case}/report.json']=stock/'report.json'
    for phase in ('train1','train2','train3','change','repeat','again','clean'):
        for n,p in selected(stock/phase).items():mig[f'original/{case}/{phase}/{n}']=p
    for arm in ('parent','candidate'):
        d=H/'port-migration-v2'/arm/case
        for n,p in selected(d).items():mig[f'restored/{arm}/{case}/{n}']=p
mig['restored/complete.json']=H/'port-migration-v2/complete.json';pack('migration',mig)
controls={}
for base in ('package-controls-v3','output-wire-control'):
    for arm in ('parent','candidate'):
        root=H/base/arm
        for n,p in selected(root).items():controls[f'{base}/{arm}/{n}']=p
    controls[base+'/complete.json']=H/base/'complete.json'
controls['tests/test-results.json']=T/'test-results.json'
for n in ('all-library','dep-info','generated'):
    p=next(x for x in [T/(n+'.log'),T/(n+'.stdout')] if x.is_file());controls[f'tests/{n}.log']=p
pack('controls',controls)
print([(p.name,p.stat().st_size) for p in out.glob('*.tar.gz')],flush=True)
