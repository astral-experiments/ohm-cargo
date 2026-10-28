"""Audit all four raw rosters and 110 products before releasing any independent clock."""
import collections,fcntl,json,os,shutil,sys,traceback
from pathlib import Path
import worker as w
import namespace as typed
from audit_elf import changed

def main():
    with (w.p/'native-measure.lock').open('rb')as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB);w.clean();w.guard()
        assert sorted(os.sched_getaffinity(0))==list(range(8))
        direct=w.q/'launch-train'; assert (direct/'exit').read_text() in ('0','1')
        first=w.read(w.regpath(1,'B'));gold=first['products'];goldstate=w.alias_state(1,'B')
        fields={n:w.elf.normalize(goldstate/'target'/n)for n in gold}
        rows={};variations={};rejections={};rosters={}
        freeze=w.read(w.here/'paths-grant.json')
        for k in ('B','C'):
            assert len(freeze[k])==2 and freeze[k][0]==freeze['B'][0]
        assert freeze['B'][1]!=freeze['C'][1]
        assert freeze['plan']=='eeff437a2d827c20e19d0ca66de145c8e2d2ccb9' and len(freeze['path_grant'])==40 and freeze['training_protocol']=='e283426527e54e6f95848a596f421c4e4b82e3ed03e84b5a4a24f66838614b47'
        for b,a in [(1,'B'),(1,'C'),(2,'C'),(2,'B')]:
            key=w.state_label(b,a);st=w.alias_state(b,a)
            arm=w.read(w.regpath(b,a));dest=w.regpath(b,a).parent
            cold=w.read(dest.parent/'cold/roster.json')
            literal,anch=typed.anchor(w.logical_target,cold['units'])
            assert literal==freeze[a],(b,a,literal)
            raw=w.read(dest/'roster.json')
            norm,replaced=typed.canonical(w.logical_target,raw['units'],literal)
            rosters[key]={'raw_sha256':typed.digest(raw['units']),'normalized_sha256':typed.digest(norm),'diagnostics_sha256':typed.digest(raw['diagnostics']),'replaced_typed_fields':replaced,'anchor':anch}
            asserts={k:v for k,v in arm['guards'].items()if k!='roster'}
            assert asserts=={k:v for k,v in first['guards'].items()if k!='roster'}
            assert arm['oracle']==first['oracle']
            assert (w.products(b,a,arm['guards']['native_paths'])==arm['products']) and set(arm['products'])==set(gold)
            rows[key]=w.sha(w.regpath(b,a));variations[key]={};rejections[key]={}
            for n,v in arm['products'].items():
                if v==gold[n]:continue
                now=w.elf.normalize(st/'target'/n);old=fields[n]
                correct=now['normalized']==old['normalized'] and now['bytes']==old['bytes'] and now['rodata_entsize']!=old['rodata_entsize'] and min(now['rodata_entsize'],old['rodata_entsize'])==0 and now['build_id']!=old['build_id']
                variation={'raw_sha256':[gold[n],v],'gold':old,'current':now,'strictly_eligible':correct}
                variations[key][n]=variation
                if not correct:
                    diff=changed(goldstate/'target'/n,st/'target'/n)
                    rejections[key][n]={'different_sections':diff,'different_text_bytes':bool('.text'in diff and diff['.text'][0][-1]!=diff['.text'][1][-1]),**variation}
        assert len({z['normalized_sha256']for z in rosters.values()})==1
        assert len({z['diagnostics_sha256']for z in rosters.values()})==1
        data={'literal_gate_exit':(direct/'exit').read_text(),'training_protocol':freeze['training_protocol'],'grant_sha256':w.sha(w.here/'paths-grant.json'),'raw_rosters':rosters,'arm_inputs':rows,'observed_product_diffs':variations,'strict_product_rejections':rejections}
        w.put(w.q/'typed-qualification-audit.json',data)
        if any(rejections.values()):raise AssertionError(('non-allowed output differences; zero clocks',[(k,list(v))for k,v in rejections.items()if v]))
        w.put(w.q/'baseline-elf-fields.json',fields)
        w.put(w.q/'qualified.json',{'arm_receipts':rows,'reference_products':gold,'gates':first['guards'],'oracle':first['oracle'],'typed_audit_sha256':w.sha(w.q/'typed-qualification-audit.json'),'ready':True})
        print('eligible',w.sha(w.q/'qualified.json'))
if __name__=='__main__':main()
