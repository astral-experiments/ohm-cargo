"""Exercise the exact registration, 50-capture adoption and physical-isolation checks offline."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from catalog import digest, sha
from continuation import HISTORICAL, RETAINED, WALL_PARENT, capture_roots, independent_files, preservation, registrations

def save(path, data):
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps(data,sort_keys=True)+'\n')

def refuse(func):
    try:func()
    except (ValueError,FileNotFoundError):return
    raise AssertionError('invalid retained outcome or registration accepted')

def main():
    registered=dict(HISTORICAL)
    pub={'plan_ref':'a'*40,'catalog_protocol_ref':HISTORICAL['continuation_ref'],'catalog_result_ref':'b'*40}
    registrations(registered,copy.deepcopy(registered),pub)
    for key in sorted(HISTORICAL):
        bad={**registered,key:'f'*len(registered[key])}
        refuse(lambda:registrations(bad,registered,pub))
        refuse(lambda:registrations(registered,bad,pub))
    for key,ref in [('catalog_protocol_ref',HISTORICAL['original_ref']),('plan_ref',WALL_PARENT),
                    ('catalog_result_ref',HISTORICAL['stopped_evidence_ref'])]:
        refuse(lambda:registrations(registered,registered,{**pub,key:ref}))
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp)
        old=base/'original';new=base/'adopted';frozen={'native_control_index':{}}
        for name,key in [('failure.txt','traceback'),('exit','exit'),('seed.json','seed'),
                         ('commands/seed-repeat1/products.json','seed_617_products'),('source/worker.py','worker')]:
            p=old/name;save(p,{'synthetic':key});frozen[key]=sha(p)
        pid=1000
        for phase,count in RETAINED.items():
            group={}
            for i in range(count):
                pid+=1;p=old/'captures'/phase/str(pid)/'capture.json';save(p,dict(phase=phase,occurrence=i))
                group[str(pid)]=sha(p)
            p=old/'commands'/phase/'physical.json';save(p,group)
            frozen['native_control_index'][phase]={'targets':count,'capture_tree':digest(group),'job_file':sha(p)}
        shutil.copytree(old,new)
        capture_roots(old,frozen);capture_roots(new,frozen);independent_files(old,new)
        tree={'digest':'a'*64,'objects':7,'unique_file_bytes':909}
        before={'preserved_original':tree,'byte_matched_copy':tree,'seed_state':dict(tree,digest='b'*64),
                'cross_root_regular_inode_overlap':0,'host_visible_original_root':str(old),'host_visible_copy_root':str(new),
                'host_visible_original_inode':old.stat().st_ino,'host_visible_copy_inode':new.stat().st_ino}
        after={'old_complete_tree_final_sha256':tree['digest'],'old_seed_state_final_sha256':before['seed_state']['digest'],
               'original_and_copy_initially_identical':True,'original_original_exit':1,'preserved_sources_and_stop':True}
        preservation(old,new,before,after)
        refuse(lambda:preservation(old,old,before,after))
        refuse(lambda:preservation(old,new,{**before,'cross_root_regular_inode_overlap':1},after))
        refuse(lambda:preservation(old,new,{**before,'host_visible_copy_root':str(old)},after))
        refuse(lambda:preservation(old,new,{**before,'byte_matched_copy':before['seed_state']},after))
        refuse(lambda:preservation(old,new,before,{**after,'original_original_exit':0}))
        for phase in RETAINED:
            q=next((new/'captures'/phase).glob('*/capture.json'));original=q.read_bytes()
            q.write_text('altered');refuse(lambda:capture_roots(new,frozen));q.write_bytes(original)
        p=new/'commands/seed-repeat1/physical.json';original=p.read_bytes();p.unlink();refuse(lambda:capture_roots(new,frozen));p.write_bytes(original)
        p.unlink();os.link(old/'commands/seed-repeat1/physical.json',p);refuse(lambda:independent_files(old,new));p.unlink();p.write_bytes(original)
        p=old/'failure.txt';p.write_text('substituted failure');refuse(lambda:capture_roots(old,frozen))
        capture_roots(new,frozen)
    return dict(native_source_binding=HISTORICAL,retained_occurrences=sum(RETAINED.values()),retained_width_pairs=800,
                refused_registration_cases=15,refused_copy_or_capture_cases=11,real_cargo_or_wild_executions=0)

if __name__=='__main__':print(json.dumps(main(),sort_keys=True,indent=2))
