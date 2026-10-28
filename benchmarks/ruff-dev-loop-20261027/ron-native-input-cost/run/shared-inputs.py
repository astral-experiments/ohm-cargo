"""Count shared literal input files across the 50 actual Wild argv. This is a size census, not a validity proof."""
import ast,collections,gzip,hashlib,json,os,re,sys
from pathlib import Path
o=Path.home()/'.cache';source=o/'ohm-ron-fixed-whole-native-h4-20261028-v1';p=source/'results/fixed-release-rust/unchanged-3';st=source/'states/fixed-release-rust';sys.path.insert(0,str(o/'ohm-noquery-full-native-h4-20261028-v2/protocol'));import engine as q
r=q.load(p/'native-processes.json');allv={};per={}
for pid,packed,out,rc,sig,exe in r['linkers']:
    assert rc==0 and packed;line,=[q for q in (p/'trace'/('exec.'+str(pid))).read_bytes().splitlines() if b'/ld.bfd",' in q and re.search(rb'\)\s+= 0$',q)]
    cmd=ast.literal_eval(re.search(rb'execve\((?:"[^"]+"),\s*(\[.*\]),\s*0x',line)[1].decode());sz=0;n=0;unknown=[];role=Path(out).name
    for i,s in enumerate(cmd[1:],1):
        if s==out or not s.startswith('/') or cmd[i-1]in('-plugin','-dynamic-linker'):continue
        f=Path(s);origin='external'
        for pref,real,group in [(q.TARGET,st/'target','private-target'),(q.BUILD,st/'build','private-build'),(q.FROZEN,q.FROZEN,'sdk')]:
            if f.is_relative_to(pref):f=real/f.relative_to(pref);origin=group;break
        if not f.is_file():unknown.append([f.name,origin]);continue
        v=f.stat();identity=str(v.st_dev)+':'+str(v.st_ino);n+=1;sz+=v.st_size
        record=allv.setdefault(identity,{'size':v.st_size,'name':f.name,'class':origin,'locations':[]});assert record['size']==v.st_size and role not in record['locations'];record['locations'].append(role)
    per[role]={'bytes':sz,'literal_positive_files_still_materialized':n,'not_still_materialized':unknown}
d={'sum_still_materialized':sum(t['bytes']for t in per.values()),'inode_deduplicated_bytes':sum(t['size']for t in allv.values()),'distinct_still_materialized':len(allv),'total_still_materialized':sum(t['literal_positive_files_still_materialized']for t in per.values()),'retained_literal_inputs':allv,'individual':per,'warning':'No failed-lookups, implicit -l inputs or now-removed ephemeral files are inferred from this census.'}
sys.stdout.buffer.write(gzip.compress(json.dumps(d,sort_keys=True,separators=(',',':')).encode(),mtime=0))
