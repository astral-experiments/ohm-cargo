"""Independently validate the public projection against its raw hashes, exact inputs and sources."""
from collections import Counter
from pathlib import Path
import json,gzip,hashlib,re
p=Path(__file__).resolve().parent
def read(n):
    b=(p/n).read_bytes()
    return json.loads(gzip.decompress(b) if n.endswith('.gz') else b)
def h(b):return hashlib.sha256(b).hexdigest()
s,n,t,raw=map(read,['result.json','native.json.gz','typed.json.gz','raw-bindings.json'])
assert s['admitted'] and s['unscored'] and s['commands']=={'edits':4,'immediate_repeats':4}
assert s['plan']=='86fd410922315ae22b9d3de58f50b30ba1e8939a' and s['plan_sha256']=='0184771b39300ce849a1eb46d5590031cbf9d80855a383b4dcdc1fbdeca184d0'
assert s['terminal_sha256']==raw['reports/complete-private-writable-controls.json']['sha256'] and s['runtime_sha256']==raw['reports/registration.json']['sha256']
assert s['control_copy_errno']==13 and not s['control_copy_additional_builds'] and raw['parent/A/negative-controls.json']['bytes']==0 and raw['parent/A/negative-controls.stderr']['bytes']>0
assert s['order']==[[a,d] for d in ('parent','historical') for a in 'AB']
k=s['budget'];assert k['worker']==list(range(8)) and k['observer']==[8] and min(k['observed_initial_outer_bytes']+k['final_outer_bytes'])>k['outer_each_minimum']==25*2**30 and k['per_btrfs_minimum']==2**30
nonce=re.compile(r'(ruff_linter-[a-z0-9]+\.[a-z0-9]+)\.([a-z0-9]{7})\.rcgu\.o')
for d,ex in [('parent','2 SIM222\n3 SIM222\n4 SIM222\n'),('historical','1 SIM222\n')]:
    assert t[d+'-A']==t[d+'-B']
    for step,rs in t[d+'-A']:
        assert len(rs)==248 and sum(r['fresh'] for r in rs)==(238 if step=='edit' else 248)
        if step=='edit':assert sorted(r['target'] for r in rs if not r['fresh'])==sorted('ruff_db ruff_linter ruff_python_ast ruff_python_codegen ruff_python_importer ruff_python_index ruff_python_literal ruff_python_parser ruff_python_semantic ruff_ranged_value'.split())
    clean=s['independent_clean'][d];assert clean['caller']['exit']==0 and clean['caller']['stdout']==ex and clean['states']['empty']['fresh']==0 and clean['states']['settled']['fresh']==248 and clean['states']['empty']['units']==clean['states']['settled']['units']==248 and clean['states']['settled']['sha256']==clean['states']['empty']['sha256']==clean['caller']['linter']
    ordinary=n[d+'-A'];treat=n[d+'-B'];assert treat['actual']!=ordinary['actual']
    assert ordinary['reader']['executable']==treat['reader']['executable']
    strip=lambda v:sorted((i['sig']['target'],i['sig']['without_origin_sha256']) for i in v['processes'] if i.get('sig',{}).get('role')=='full')
    assert len(strip(ordinary))==10 and strip(treat)==strip(ordinary)
    for a in 'AB':
        v=n[d+'-'+a];compiled=v['processes'];inputs=v['open_files'];archives=v['members'];w=v['observed'];m=v['exact_name_check'];r=v['rechecked_actual'];assert r==m
        assert w['edit']['events']==['create','publish','remove'] and w['edit']['returncode']==w['repeat']['returncode']==0 and w['repeat']['events']==w['repeat']['names']==[]
        obs=[e['name'] for e in w['edit']['names']];fdnames=[i['name'] for i in inputs[2:]];assert len(obs)==len(set(obs))==256 and sorted(obs)==sorted(fdnames) and all(e['mask'] in (0x100,0x80) and (e['mask']==0x80 or e['cookie']==0) for e in w['edit']['names'])
        assert h(b'\0'.join(q.encode() for q in sorted(obs)))==m['names_sha256']==v['fd_names_sha256'] and {nonce.fullmatch(i)[2] for i in obs}=={m['current_nonce']}
        assert len(inputs)==258 and len(archives)==260 and [o['name'] for o in archives]==['/','//',*[i['name'] for i in inputs]]
        assert [r['name'] for r in inputs[:2]]==['lib.rmeta','lib.rmeta-link'] and all(k['size']>0 and k['ino']>0 and k['dev']>0 and k['seq']<v['publish_seq'] for k in inputs) and all(i['direct_object_in_selected_directory'] for i in inputs[2:])
        assert all((a0['name'],a0['size'],a0['sha256'])==(b0['name'],b0['size'],b0['sha256']) for a0,b0 in zip(inputs,archives[2:]))
        assert v['bytes']==m['bytes']==101719820 and m['expected_sha256']==m['actual_sha256']==v['actual']==v['independent'] and v['independent_equal']
        assert m['literal_equal'] and m['reference_sha256']==v['ordinary_reference']==ordinary['actual'] and m['fields']==512 and m['objects']==256
        assert v['archiver']=='eedd2efbdee80acf60e17e10adeddf31be0347226245f935be95efa3ae00ec79' and set(v['ordinary_writer_negatives'])=={'object-name','metadata-byte'} and len({v['actual'],*v['ordinary_writer_negatives'].values()})==3
        assert set(v['name_oracle_negatives'])=={'changed-object-byte','missing-current-name','wrong-current-name','wrong-real-source'} and all(r0['exception'] in ('ValueError','AssertionError') for r0 in v['name_oracle_negatives'].values())
        assert v['reader']['exit']==0 and v['reader']['stdout']==ex and v['reader']['linter']==v['actual'] and v['reader']['stderr_sha256']==h(b'')
        assert v['uid']==1000 and v['cpu']==list(range(8)) and v['tools']['cargo']==s['cargo'][a] and v['tools']['rustc']==s['rustc'] and v['tools']['stock-wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
        assert v['repeat_processes']==[['cargo',0]] and all(i['rc']==0 for i in compiled) and sum(i['selected'] for i in compiled)==1 and not {i['program'] for i in compiled}&{'gcc','collect2','ld.bfd','wild','cc','wild-linker'}
        assert v['terminal']==['terminal','0','1','258','1',str(int(a=='B'))];assert len(v['clones'])==int(a=='B') and all(z['seq']<v['publish_seq'] and z['exit']==0 and z['actual_origin'] and z['actual_tmp'] and z['same_tmp_as_publish'] for z in v['clones'])
        q=v['protected_old_fds'];assert q['source_fd_at_entry']==q['source_fd_after'] and q['before_old_sha256']==q['after_old_sha256'] and q['published_stat'][:2]!=q['source_fd_at_entry'][:2] and v['unchanged_output_stat']==q['published_stat']
        if d=='historical':assert q['before_old_sha256']==n['parent-'+a]['actual']
        else:assert q['before_old_sha256']==s['independent_clean']['historical']['caller']['linter']
print('Passed four byte-exact 101,719,820-byte archives, 1,024 independently delivered and opened native object names, 16 rejected filename/source/mutation controls, two real FICLONEs, eight genuine Cargo commands, and both independent clean SIM222 verdicts. No timing samples.')
