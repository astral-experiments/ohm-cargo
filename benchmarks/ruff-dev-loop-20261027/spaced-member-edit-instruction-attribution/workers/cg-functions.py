"""Read only the supervisor's process profile; retain normalized self counts for the hashed code path."""
import collections,hashlib,json,re,statistics,subprocess,sys
from pathlib import Path
P=Path(sys.argv[1]);S=P/'cargo-grind-v2'
assert (S/'complete.json').is_file()
root=S/'function-summary';root.mkdir()
# Only demangle ELF-derived LLVM hashes. Standard output paths are not exported.
def funcs(f):
    proc=subprocess.run([str(P/'software-counters/callgrind/usr/bin/callgrind_annotate'),'--show=Ir','--inclusive=no','--auto=no','--show-percs=no','--threshold=100',str(f)],capture_output=True,check=True)
    sha=hashlib.sha256(proc.stdout).hexdigest();info={};total=None;hist=collections.Counter();labels=collections.Counter()
    for raw in proc.stdout.decode(errors='replace').splitlines():
        m=re.match(r'^\s*([0-9,]+)\s+(.*)$',raw)
        if not m:continue
        n=int(m.group(1).replace(',',''));s=m.group(2).strip()
        if s=='PROGRAM TOTALS':total=n;continue
        if ':' not in s:continue
        # Annotation rows contain source path:function [image]. Collapse raw debug/Ruff registry prefixes.
        fn=s.split(':',1)[1].split(' [')[0];fn=re.sub(r'\.llvm\.\d+','',fn)
        labels[fn]+=n
        fl=fn.lower()
        if 'blake3' in fl:group='blake3'
        elif 'checksum' in fl:group='checksum (outside blake3)'
        elif 'fingerprint' in fl:group='other Cargo fingerprint'
        elif 'dep_info' in fl or 'depinfo' in fl:group='other dep-info'
        else:group='all other functions'
        hist[group]+=n
    assert total is not None and total>10000000
    return total,dict(hist),labels,sha
rows=[];names=set();allseries={}
for e in sorted(S.glob('rows/*/edit/supervisor.json')):
    r=json.loads(e.read_bytes());p=e.parent/('callgrind.'+r['process']);total,hist,labels,raw=funcs(p);idx,image=e.parent.parent.name.split('-')
    assert abs(total-r['ir'])<5000000,(total,r['ir'])
    rows.append({'pair':idx,'image':image,'profile_sha':r['native_profile_sha'],'annotation_sha':raw,'self_counts':hist,'annotated_total':total,'ir':r['ir']})
    allseries[idx,image]=labels;names.update(labels)
for fn in sorted(names):
    pass
diffs=[]
for fn in names:
    v=[allseries[idx,'C'][fn]-allseries[idx,'B'][fn] for idx in sorted({x[0] for x in allseries})]
    diffs.append((abs(statistics.median(v)),fn,v))
# Only a small source-level category ledger is made portable. Full annotations remain on this host.
out={'rows':rows,'largest_median_deltas':[{'function':fn,'c_minus_b':v} for _,fn,v in sorted(diffs,reverse=True)[:32]]}
(root/'functions.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
print([(x['pair'],x['image'],x['ir'],x['self_counts'].get('blake3')) for x in rows])
