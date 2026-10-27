"""Recheck the registered schedules, complete file receipts, admitted ELF-domain and all timings."""
from pathlib import Path
import csv,gzip,hashlib,json,sys
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P))
from analyze import analyze
from elf_gate import permitted_linker_width
def sha(x):return hashlib.sha256(x).hexdigest()
plan=json.loads((P/'plan.json').read_bytes());a=json.loads(gzip.decompress((P/'commands.json.gz').read_bytes()));host=a['host']
rows=list(csv.DictReader((P/'times.csv').read_text().splitlines()));orders=plan['schedule']['orders'];subjects=set('ABC' if host=='h4' else 'DC')
assert sha((P/'plan.json').read_bytes())==a['series']['plan'] and a['manifest']==a['series']['runner']
assert a['times_csv'].encode()==(P/'times.csv').read_bytes() and a['raw_csv_file_sha256']==sha((P/'times.csv').read_bytes())
want=len(orders)*len(subjects);assert len(rows)==len(a['samples'])==a['series']['slots']==want
assert want*3==a['series'].get('commands',a['series'].get('completed_commands'))
for ident,arr in a['validated_input_sets'].items():
    assert sha(json.dumps(arr,separators=(',',':'),sort_keys=True).encode())==ident
    assert len(arr) in (0,45) and all(h=='blake3' and len(d)==64 and n>0 for _,h,d,n in arr)
ordinary=None;roster=None;comparisons=0;width_changes=0;internal_widths=0
for row in rows:
    arm=row['arm'];block,slot=int(row['block']),int(row['slot']);assert arm in subjects and orders[block-1][slot-1]==arm
    n=f'score-{block:02d}-{slot}-{arm}';s=a['samples'][n];phases=s['command']
    if ordinary is None:ordinary=s['ordinary']
    assert s['ordinary']==ordinary and ordinary['passed'] is True and ordinary['stdlib_test_count']>0 and 'E712' in ordinary['lint']
    for ph in ('cold','first','settled'):
        x=phases[ph];c=x['cmd'];assert x['executables']==102 and x['test_harnesses']==84 and x['ordinary_binaries_and_examples']==18
        receipts=x['proof_record_hash'];assert receipts['depinfo_sha256']==c['ron_depinfo'] and receipts['encoded_sha256']==c['ron_fingerprint'] and len(receipts['seal_blake3'])==64
        ref=a['same_subject_natives'][arm+'/'+ph];assert len(x['native'])==len(ref)==110 and x['native'].keys()==ref.keys()
        changed=[k for k in ref if x['native'][k]!=ref[k]];assert sorted(changed)==sorted(x['same_subject_diff']) and all(permitted_linker_width(x['native'][k],ref[k]) for k in changed)
        width_changes+=len(changed);comparisons+=len(ref)
        assert len(a['validated_input_sets'][x['checked_physical_input_set']])==c['checksums']==(0 if ph=='cold' and arm!='C' else 45) and c['ron_complete']==bool(c['checksums'])
        assert c['elapsed_ns']==int(row[ph+'_ns'])>0 and c['fresh']=={'cold':0,'first':619 if arm=='C' else 563,'settled':619}[ph]
        if roster is None:roster=c['roster']
        assert roster==c['roster']
    cc,ff,ss=(phases[ph]['native'] for ph in ('cold','first','settled'));assert ff==ss
    changed=[k for k in cc if cc[k]!=ff[k]];assert not changed if arm=='C' else all(permitted_linker_width(cc[k],ff[k]) for k in changed)
    internal_widths+=len(changed)
analysis=analyze(plan,rows);assert analysis==json.loads((P/'analysis.json').read_bytes());print(json.dumps(dict(host=host,slots=want,commands=want*3,elf_reference_comparisons=comparisons,same_subject_registered_width_changes=width_changes,internal_full_link_registered_width_changes=internal_widths,claims_pass=analysis['claims_pass'],floors_pass=analysis['floors_pass']),sort_keys=True))
