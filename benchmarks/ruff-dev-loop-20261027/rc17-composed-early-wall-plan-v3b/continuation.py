"""Read the stopped native roots and independent continuation receipts outside the clocks."""
from pathlib import Path
from catalog import digest, hashstr, must, read, sha

HERE=Path(__file__).resolve().parent
WALL_PARENT='390db41469e8784dca0268c6317ea4b58b2e51c2'
WALL_PARENT_MANIFEST='9099beedd4c6a180c1c5747c077d1a45e1868e922dc594031d5ac4a292bfc9c4'
HISTORICAL=read(HERE/'native-continuation.json')
FROZEN_SHA='609e53b6ea3eb204ccc19b55266c61ef939bc73cce0b103c325a6f325ea3f7f2'
RETAINED={'failure-1':1,'failure-2':1,'seed-repeat1':48}

def capture_roots(path,frozen):
    must(set(frozen['native_control_index'])==set(RETAINED),'unexpected retained phases')
    for name,key in [('failure.txt','traceback'),('exit','exit'),('seed.json','seed'),
                     ('commands/seed-repeat1/products.json','seed_617_products'),('source/worker.py','worker')]:
        must(sha(path/name)==frozen[key],'retained source or result changed: '+name)
    for phase,count in RETAINED.items():
        idx=frozen['native_control_index'][phase]
        ids={p.parent.name:sha(p) for p in (path/'captures'/phase).glob('*/capture.json')}
        must(idx['targets']==count==len(ids) and all(k.isdecimal() for k in ids) and
             idx['capture_tree']==digest(ids),'distinct original linker captures changed: '+phase)
        must(sha(path/'commands'/phase/'physical.json')==idx['job_file'],'retained actual jobs changed: '+phase)

def independent_files(old,new):
    fixed=[old/f for f in ('failure.txt','exit','seed.json','source/worker.py','commands/seed-repeat1/products.json')]
    for phase in RETAINED:
        fixed.append(old/'commands'/phase/'physical.json')
        fixed.extend((old/'captures'/phase).glob('*/capture.json'))
    for first in fixed:
        copy=new/first.relative_to(old)
        must(first.is_file() and copy.is_file() and not first.is_symlink() and not copy.is_symlink() and
             not first.samefile(copy),'retained observation aliases original storage: '+str(first.relative_to(old)))

def preservation(old,new,before,after):
    must(old.is_dir() and new.is_dir() and not old.is_symlink() and not new.is_symlink() and
         old.stat().st_dev==new.stat().st_dev and not old.samefile(new),'native roots are not physically independent')
    original=before['preserved_original'];copy=before['byte_matched_copy'];seed=before['seed_state']
    for tree in (original,seed):
        must(set(tree)=={'digest','objects','unique_file_bytes'} and hashstr(tree['digest']) and tree['objects']>0 and
             tree['unique_file_bytes']>0,'invalid authenticated tree receipt')
    must(original==copy and before['cross_root_regular_inode_overlap']==0 and
         before['host_visible_original_root']==str(old) and before['host_visible_copy_root']==str(new) and
         before['host_visible_original_inode']==old.stat().st_ino and before['host_visible_copy_inode']==new.stat().st_ino,
         'copy bytes, inodes or rooted path diverged')
    expected={'old_complete_tree_final_sha256':original['digest'],'old_seed_state_final_sha256':seed['digest'],
              'original_and_copy_initially_identical':True,'original_original_exit':1,'preserved_sources_and_stop':True}
    must(after==expected,'original tree not preserved after all width observations')

def registrations(installed,adopted,wall_catalog):
    must(installed==adopted==HISTORICAL,'native continuation has different source or stopped evidence')
    retired={WALL_PARENT,HISTORICAL['original_ref'],HISTORICAL['stopped_evidence_ref'],HISTORICAL['continuation_ref']}
    must(wall_catalog['catalog_protocol_ref']==HISTORICAL['continuation_ref'] and
         wall_catalog['plan_ref'] not in retired and wall_catalog['catalog_result_ref'] not in retired,
         'wall or native publication points to a predecessor')

def admissions(g,check_tree=False):
    base=g.BASE;old=base/'whole-wild-width-v1';new=base/'whole-wild-width-v2'
    work=base/'whole-wild-width-v2-protocol';oldwall=base/'wall-protocol-v3';launch=base/'wall-launch-v3b'
    must(g.manifest(oldwall)==WALL_PARENT_MANIFEST and read(base/'wall-launch-v3/binding.json')==
         {'sha256':WALL_PARENT_MANIFEST,'ref':WALL_PARENT},'original wall registration changed')
    must(not (base/'early-scheduler-wall-rc17-v3').exists() and not (base/'early-scheduler-wall-admission-v3.json').exists(),
         'original v3 admitted or clocked before replacement')
    for name in ('plan.json','analysis.py','clock.py','guards.py','elf.py','verify_result.py','historical-links.json.gz','ci-exact-heads.json'):
        must(sha(oldwall/name)==sha(HERE/name),'wall measurement or original evidence changed: '+name)
    reg=HISTORICAL
    registrations(read(work/'registration.json'),read(new/'continuation-registration.json'),read(launch/'catalog-publication.json'))
    must(g.manifest(work/'source')==reg['continuation_sha256'],'different physical continuation source')
    for root in (old,new):
        origin=read(root/'registration.json')
        must(g.manifest(root/'source')==origin['protocol']==reg['original_protocol_sha256'] and
             origin['commit']==reg['original_ref'],'original worker source or registration changed')
    must(sha(HERE/'retained-native-bindings.json')==sha(work/'source/stopped-source-binding.json')==FROZEN_SHA,'retained native provenance changed')
    frozen=read(HERE/'retained-native-bindings.json')
    must(not (old/'commands/seed-repeat2').exists() and not (old/'terminal.json').exists() and
         not (new/'continuation-failure.txt').exists(),'reuse, unexpected historical phase, or failed continuation')
    for root in (old,new):capture_roots(root,frozen)
    independent_files(old,new)
    before=read(new/'tree-before-resume.json');after=read(new/'physical-preservation.json')
    preservation(old,new,before,after)
    if check_tree:
        must(g.tree(old)==before['preserved_original'],'original full acquisition tree changed since the disjoint copy')
    return dict(native_continuation_ref=reg['continuation_ref'],native_continuation_manifest=reg['continuation_sha256'],
                stopped_native_ref=reg['stopped_evidence_ref'],stopped_native_manifest=reg['stopped_evidence_sha256'],
                retained_native_bindings_sha256=FROZEN_SHA,retained_occurrences=50,new_occurrences=249,retained_width_pairs=800,
                original_wall_ref=WALL_PARENT,original_wall_manifest=WALL_PARENT_MANIFEST,
                copy_receipt_sha256=sha(new/'tree-before-resume.json'),preservation_receipt_sha256=sha(new/'physical-preservation.json'))
