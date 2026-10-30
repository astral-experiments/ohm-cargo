#!/usr/bin/env python3
"""Verify a portable scope-limited three-arm comparison from complete per-phase projection."""
from pathlib import Path
import csv, gzip, hashlib, io, json, sys, statistics
r=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def table(name,text):
    if sys.argv[1:]==['--derive']:
        with (r/name).open('x') as f:f.write(text)
    else:
        assert (r/name).read_text()==text
def tsv(header,rows):
    st=io.StringIO();w=csv.writer(st,delimiter='\t',lineterminator='\n');w.writerow(header);w.writerows(rows);return st.getvalue()
if sys.argv[1:]!=['--derive']:
    for row in (r/'SHA256SUMS').read_text().splitlines():
        h,n=row.split('  ',1);assert '/' not in n and sha(r/n)==h
v=json.loads((r/'verified.json').read_bytes());assert sha(r/'results.json.gz')==v['projection']
raw=gzip.decompress((r/'results.json.gz').read_bytes());assert all(x not in raw for x in (b'/home/',b'/mnt/',b'.openai.org',b'/run/user/'))
a=json.loads(raw);assert a['registered']==v['ops'] and (v['slots'],v['flanks'],v['phases'])==(6,12,65) and v['full_blobs']>3
assert a['order']==[['P','G','Q'],['Q','G','P']] and a['revision']['head']=='7b13f01ba1569887a25670820764b24c206da8e5' and a['revision']['regressed_tree']=='a880a27e6d496af407411ba47a14279a631b40c3'
assert a['cargo_argv']==['cargo','+ohm','build','-p','ruff_python_parser','--locked','--offline','-j4','--message-format=json']
asset=json.loads((r/'assets.json').read_bytes())
assert asset['kernel_workload_cpu']==[28,29,30,31] and asset['wrapper']=='d47c650b19daf7bd1ecc061af88587a410226f8d42f92fe82add772b62919a67' and asset['table']=='b6653376b5e761e5f62dcfd8009fe059c84715b0138b98f0e6e3bde18afc849e'
assert asset['Cargo']=='1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add' and asset['Wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
assert asset['sdk']['parent']['source']=='7e71d3150938ff8ed82aca03416439d7e5b87ef3' and asset['sdk']['candidate']['source']=='6b7f424ece4bc978ead5546b73e1b31d5ccb1e70'
assert asset['sdk']['parent']['driver']=='66380b2752a864d14799b7931e011d4ff55ce4e326a5b77e80d8b06d9dfddd5e' and asset['sdk']['candidate']['driver']=='b2a7780120821b363986bccb91646050d963a644d13ae354ffb87348cdb20e0c'
assert all(j['members']==55 for j in asset['sdk'].values()) and asset['registry']==[[505,466],[505,466]]
member_gz=(r/'native-members.json.gz').read_bytes()
assert hashlib.sha256(member_gz).hexdigest()=='6aecb815677b655e81f8a0b4381e919a568a509c607e4aaa7606513ba64b7569'
m=json.loads(gzip.decompress(member_gz))
assert m['compact_projection']==v['projection'] and m['verifier']==sha(r/'member-audit.py') and len(m['physical_ar_files'])==82 and sum(y['bytes'] for y in m['physical_ar_files'].values())==762920714 and len(m['entries'])==130
for e in m['entries']:
    count={'ruff_python_ast':101,'ruff_python_parser':84}[e['crate']]
    lib=m['physical_ar_files'][e['sha']]
    assert e['objects']==lib['cgu_count']==count and a['actual_outputs'][e['sha']]==lib['bytes']
    nat=lib['cgu_payloads']
    for which,verdict in e['references'].items():
        ref_id=a['clean'][e['source']]['rlibs'][which][e['crate']]['sha']
        cold=m['physical_ar_files'][ref_id]
        assert verdict['same_cgu_payloads']==(nat==cold['cgu_payloads']) and verdict['same_raw']==(e['sha']==ref_id)
        if e['slot'].startswith('pair-'):
            assert verdict['same_cgu_payloads'] and not verdict['same_raw'] and not verdict['same_cgu_names'] and verdict['changed_metadata']==['lib.rmeta','lib.rmeta-link']
profiles=a['profiles'];states={'empty-A':'A','first-B':'B','edit-B':'C','restore-B':'B','unchanged-B':'B','return-A':'A','return-B':'B','unchanged-final':'B','native-edit-B':'C','native-restore-B':'B'}
ref=a['clean'];assert len({r['ELF'] for r in ref.values()})==3
assert ref['A']['verdict']=='Expr=64 signed-expression=rejected' and ref['B']['verdict']=='Expr=56 signed-expression=rejected' and ref['C']['verdict']=='Expr=56 signed-expression=accepted'
for slot,phases in profiles.items():
    role=slot[-1];assert set(states)==set(phases)
    for phase,s in phases.items():
        state=states[phase]; assert ref[state]['ELF']==s['ELF'] and ref[state]['verdict']==s['verdict'] and s['wall_ns']>0
        if phase.startswith('unchanged'):assert s['dirty']==[] and not s['codec']
        elif phase in ('edit-B','restore-B','native-edit-B','native-restore-B'):
            assert s['dirty']==['ruff_python_parser']
            if role=='Q':
                q,=s['codec'];assert q['crate']=='ruff_python_parser' and q['HEAD']==q['chosen'] and q['pre_s']>=0 and q['post_s']>=0 and q['decode_groups']>=2 and q['encode_groups']>=2
        elif phase.startswith('return'):assert s['dirty']==['ruff_python_ast','ruff_python_parser']
        if role!='Q':assert not s['codec']
for g in a['kernel_flanks']:
    assert g['real_parser']==1 and g['wild']==0
    assert (g['table_decode']>=2 and g['table_encode']>=2) if g['slot'][-1]=='Q' else (g['table_decode']==g['table_encode']==0)
pairs=[];trade=[];codec=[]
for i in (1,2):
    old=a['paired'][i-1]
    ns=lambda role,ph:profiles[f'pair-{i}-{role}'][ph]['wall_ns']
    seconds=lambda n:f'{n/1e9:.6f}'
    phases=['first-B','edit-B','restore-B','unchanged-B','return-A','return-B','unchanged-final']
    for ph in phases:
        p,g,q=[ns(role,ph) for role in 'PGQ']
        assert abs(old['phase'][ph]['Q_minus_P_s']-(q-p)/1e9)<1e-9 and abs(old['phase'][ph]['Q_minus_G_s']-(q-g)/1e9)<1e-9
        pairs.append([i,ph,seconds(p),seconds(g),seconds(q),seconds(q-p),seconds(q-g)])
        for t in profiles[f'pair-{i}-Q'][ph]['codec']:
            codec.append([i,ph,t['crate'],t['decode_groups'],t['encode_groups'],f"{t['pre_s']:.6f}",f"{t['post_s']:.6f}"])
    returns=['return-A','return-B'];edits=['edit-B','restore-B']
    gross=sum(ns('P',ph)-ns('Q',ph) for ph in returns)/2/1e9
    tax=sum(ns('Q',ph)-ns('P',ph) for ph in edits)/2/1e9
    cost=sum(ns('Q',ph)-ns('G',ph) for ph in edits)/2/1e9
    for n,vv in [('mean_return_saving_P_minus_Q_s',gross),('mean_same_B_Q_minus_P_s',tax),('mean_codec_Q_minus_G_s',cost)]:assert abs(old[n]-vv)<1e-9
    trade.append([i,f'{gross:.6f}',f'{tax:.6f}',f'{cost:.6f}',f'{gross/tax:.3f}' if tax>0 else 'no positive cost',f'{gross/cost:.3f}' if cost>0 else 'no positive cost'])
body=tsv(['pair','phase','P_seconds','G_seconds','Q_seconds','Q_minus_P_seconds','Q_minus_G_seconds'],pairs)
table('paired-seconds.tsv',body)
table('break-even.tsv',tsv(['pair','mean_P_minus_Q_branch_return_s','mean_Q_minus_P_same_B_edit_s','mean_Q_minus_G_codec_s','same_B_edits_per_branch_return','edits_per_return_codec_contrast'],trade))
table('codec.tsv',tsv(['pair','phase','crate','decode_groups','encode_groups','before_rustc_s','after_rustc_s'],codec))
libs=[]
for state,entries in a['all_raw_rcu'].items():
    assert len(entries)>=2
    for e in entries:
        for name,l in e['members'].items():
            assert l['sha'] in a['actual_outputs'] and a['actual_outputs'][l['sha']]==l['bytes']
            parent=ref[state]['rlibs']['P'][name];guard=ref[state]['rlibs'].get('G',{}).get(name)
            libs.append([state,e['slot'],e['phase'],name,l['sha'],parent['sha']==l['sha'],parent['payload_multiset']==l['payload_multiset'],guard['sha']==l['sha'] if guard else '',guard['payload_multiset']==l['payload_multiset'] if guard else ''])
table('library-parity.tsv',tsv(['source','installation','phase','crate','raw_sha256','same_raw_as_empty_P','same_payload_multiset_as_empty_P','same_raw_as_empty_G','same_payload_multiset_as_empty_G'],libs))
if sys.argv[1:]!=['--derive']:
    print(body,end='');print((r/'break-even.tsv').read_text(),end='');print(f"Verified six installations, five independent empty references, 65 Cargo commands and 12 native flank traces. {v['full_blobs']} complete output hashes.")
