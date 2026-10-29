"""Verify the read-only, privacy-safe projection of both real Rust invocations and independent writers."""
from collections import Counter
from pathlib import Path
import gzip,hashlib,json,re
p=Path(__file__).resolve().parent
def read(n):
 b=(p/n).read_bytes()
 if n.endswith('.gz'):b=gzip.decompress(b)
 return json.loads(b)
def h(b):return hashlib.sha256(b).hexdigest()
s=read('result.json');native=read('native.json.gz');typed=read('typed.json.gz');links=read('raw-bindings.json')
assert s['protocol']=='a644772c28607282fc06bb7c72f08225ea04f0a6' and s['manifest']=='327f73c1f3d1e372358ea209223ad992087c2d54e093a2440d75e4d7eb2336f1'
assert s['isolated_cpus']==list(range(8)) and s['freshly_copied_original_files']==452 and s['ordinary_native_attempts']=={'A':1,'B':1} and s['all_required_positive_and_negative_gates'] and s['unscored']
assert not any(s['post_qualification_loops'].values()) and s['new_filesystems']['A']['filesystem']!=s['new_filesystems']['B']['filesystem']
for a in 'AB':
 d=native[a];r=d['current_inputs'];ar=d['archive_members'];c=d['clones'];expected=int(a=='B')
 assert d['terminal']==['terminal','0','1','258','1',str(expected)] and d['selected_compiler_count']==1 and len(d['clones'])==expected and d['mask']==list(range(8)) and d['user']==1000
 assert len(r)==258 and len(ar)==260 and len(set(v['name'] for v in r))==258 and [v['ordinal'] for v in r]==list(range(258))
 assert [v['name'] for v in ar]==['/','//']+[v['name'] for v in r] and [v['name'] for v in r[:2]]==['lib.rmeta','lib.rmeta-link']
 assert all((v['name'],v['size'],v['sha256'])==(t['name'],t['size'],t['sha256']) for v,t in zip(r,ar[2:]))
 assert all(v['dev']>0 and v['ino']>0 and v['size']>0 and v['event']<d['publication']['event'] for v in r)
 assert all(x['event']<d['publication']['event'] and x['rc']==0 and x['original_and_held_inode'] and x['actual_selected_temporary'] and x['same_temp_as_published'] for x in c)
 assert d['publication']['source_filename']=='tmp.a' and d['publication']['target_filename'].startswith('libruff_linter')
 assert d['bytes']==101719820 and d['actual_sha256']==d['independent_sha256'] and d['whole_file_equal']
 assert d['llvm_ar_sha256']=='eedd2efbdee80acf60e17e10adeddf31be0347226245f935be95efa3ae00ec79'
 assert set(d['changed_controls'])=={'object-name','metadata-byte'} and len({d['actual_sha256'],*d['changed_controls'].values()})==3
 assert d['actual_caller']==d['independent_caller'] and d['actual_caller']['linter']==d['actual_sha256'] and d['actual_caller']['stdout']=='2 SIM222\n3 SIM222\n4 SIM222\n' and d['actual_caller']['exit']==0
 assert d['actual_caller']['stderr_sha256']==h(b'') and links[a+'/actual-reader/lint-cli']['sha256']==links[a+'/independent-reader/lint-cli']['sha256']==d['actual_caller']['executable']
 assert links[a+'/ordinary-llvm-ar-output']=={'bytes':d['bytes'],'sha256':d['actual_sha256']}
 assert len(d['actual_edited']['dirty'])==10 and d['actual_edited']['units']==d['repeat']['units']==248 and d['actual_edited']['fresh']==238 and d['repeat']['fresh']==248 and d['repeat']['physical_roles']=={'cargo':1}
 old,new=d['actual_edited']['source_fd_at_entry'],d['actual_edited']['published_stat']
 assert d['actual_edited']['source_fd_after']==old and old[:2]!=new[:2] and d['repeat']['final_stat']==new and d['actual_edited']['before_old_sha256']==d['actual_edited']['after_old_sha256']==s['starting_sha256']
 assert all(v['rc']==0 for v in d['processes']); selected,=[v for v in d['processes'] if v['is_selected']];assert selected['crate']=='ruff_linter' and selected['flags']['root_hint']==bool(expected)
 sig=d['normalized_actual_rustcs'];assert sum(v['role']=='full' for v in sig)==10 and sum(v['role']=='query' for v in sig)==expected
 assert Counter(v['raw_sha256'] for v in sig)==Counter(v['raw_sha256'] for v in d['processes'] if v['program_role']=='compiler')
 assert all(v['raw_sha256']==links[a+'/exec-'+str(v['seq'])+'.argv']['sha256'] for v in d['processes'])
 assert d['actual_edited']['physical_image_counts']['rustc']==10+expected
assert typed['A']==typed['B']
for (st,rows) in typed['A']:
 assert len(rows)==248 and sum(r['fresh'] for r in rows)==(238 if st=='edit' else 248)
assert native['A']['actual_sha256']=='f6270ca22407df33475511cdc7bb6bf476e0250399199a8b7193a44af35abc94'
assert native['B']['actual_sha256']=='11f62fc8d0af7dcc613172d3b8b2981ada850c77e6416d8bdcd7120b4488849e'
norm=lambda n: sorted((v['target'],v['without_origin_sha256']) for v in n['normalized_actual_rustcs'] if v['role']=='full')
assert norm(native['A'])==norm(native['B'])
for name,expected in [('historical','1 SIM222\n'),('parent','2 SIM222\n3 SIM222\n4 SIM222\n')]:
 cc=s['clean'][name];assert cc['caller']['stdout']==expected and cc['caller']['exit']==0
 assert cc['states']['empty']['units']==cc['states']['settled']['units']==cc['states']['settled']['fresh']==248 and cc['states']['empty']['fresh']==0
 assert cc['states']['empty']['sha256']==cc['states']['settled']['sha256']==cc['caller']['linter'] and cc['caller']['executable']==links['clean-'+name+'/caller/lint-cli']['sha256']
print('Passed 516 ordered current input receipts, two exact 101719820-byte independent archive comparisons, four expected negative digests, one real held-file clone and four actual/reconstructed native readers. Both 248-unit clean source references passed.')
