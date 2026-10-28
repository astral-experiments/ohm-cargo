"""Export public observations after terminal and recheck them without native paths or executables."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import checks as g
import analysis
import verify


def admission(folder):
    a=verify.verify_preflight(folder);assert a==g.read(folder/'admission.json')
    frozen=g.read(folder/'frozen.json')
    return dict(admitted=a,admission_sha256=g.sha(folder/'admission.json'),registration=g.read(folder/'registration.json'),
                native_result_ref=g.P['native_result_ref'],canonical_typed=frozen['model']['typed'],
                declared=frozen['files'],tools=frozen['tools'],ci=g.read(folder/'ci-current.json'),
                probes=[slot(folder/f'00-{i}-{arm}',0,i,arm) for i,arm in enumerate(g.P['unscored_preflight_order'],1)])


def slot(d,block,pos,arm):
    ordinary=d/'ordinary';post=d/'follow'
    receipt=dict(block=block,slot=pos,arm=arm,start=g.read(d/'start.json'),checked=g.read(d/'verified.json'),
                 stderr=(ordinary/'stderr').read_text(),stdout=(ordinary/'stdout').read_text(),
                 first_files=g.read(ordinary/'files.json'),repeat_files=g.read(post/'files.json'),listings={},
                 repeat_jobs=g.read(post/'jobs.json'),physical=g.read(post/'inventory.json'),repeat_typed=None,
                 raw={})
    if (ordinary/'clock.json').is_file():
        receipt['clock']=g.read(ordinary/'clock.json');receipt['raw_clock_bytes']=(ordinary/'clock.json').read_text()
    else:
        receipt['untimed']=g.read(ordinary/'unclocked-exit.json')
    repeat=g.events((post/'cargo.stdout').read_bytes())
    receipt['repeat_typed']={k:repeat[k] for k in ('typed','roster','diag','units','fresh')}
    receipt['target_basenames']={name:Path(path).name for name,path in repeat['targets'].items()}
    for stage,folder in (('first',ordinary),('repeat',post)):
        receipt['listings'][stage]={label:(folder/('list-'+label+'.stdout')).read_text() for label in sorted(g.P['harnesses'])}
    for path in sorted(d.rglob('*')):
        if path.is_file():
            receipt['raw'][str(path.relative_to(d))]=g.sha(path)
    return receipt


def collect(result,admit):
    fixed=admission(admit)
    if (result/'failure.txt').is_file():
        x=verify.stopped(result)
        for item in x['slots']:
            d=result/f"{item['block']:02d}-{item['slot']}-{item['arm']}"
            item['preserved_slot_files']={str(q.relative_to(d)):g.sha(q) for q in sorted(d.rglob('*'))
                                            if 'fresh-physical-copy' not in q.relative_to(d).parts and q.is_file()}
            item['product_differences']={}
            for key in ('ordinary/files.json','follow/files.json'):
                if (d/key).is_file():
                    got=g.read(d/key);want=fixed['declared']
                    item['product_differences'][key]={k:{'expected':want.get(k),'observed':got.get(k)}
                          for k in sorted(set(want)|set(got)) if want.get(k)!=got.get(k)}
            if item['clock_present']:
                item['raw_clock_bytes']=(d/'ordinary/clock.json').read_text()
        return dict(status='failed',frozen=fixed,original=x,source=g.manifest(HERE),statistics=None)
    actual=verify.all_slots(result,admit);assert actual==g.read(result/'result.json')
    return dict(status='complete',frozen=fixed,registration=g.read(result/'registration.json'),
                grant=g.read(result/'grant.json'),terminal=g.read(result/'terminal.json'),source=g.manifest(HERE),
                rows=[slot(result/f'{b:02d}-{s}-{a}',b,s,a) for b,o in enumerate(g.P['order'],1) for s,a in enumerate(o,1)],
                raw_result_sha256=g.sha(result/'result.json'),statistics=actual['statistics'])


def hash_text(s):
    return hashlib.sha256(s.encode()).hexdigest()


def raw_json(x):
    return hash_text(json.dumps(x,sort_keys=True,indent=2)+'\n')


def portable_slot(row,i,j,a,f):
    assert (row['block'],row['slot'],row['arm'])==(i,j,a)
    start=row['start'];w=row['checked'];r=row['raw']
    assert (start['block'],start['slot'],start['arm'])==(i,j,a) and start['scored'] is (i>0)
    assert start['admission']==(f['admission_sha256'] if i else None) and start['cargo']==g.P['cargo'][a]
    assert start['cpu']==g.P['cpus'] and start['seed']['digest']==f['admitted']['physical_seed']['digest']
    assert start['copy']=='cp -a --reflink=never' and start['independent_regular_files']==f['admitted']['physical_seed']['unique_files']
    assert r['start.json']==w['start']==raw_json(start) and r['verified.json']==raw_json(w)
    assert not row['stdout'] and hash_text(row['stdout'])==w['stdout']==r['ordinary/stdout']
    assert hash_text(row['stderr'])==w['stderr']==r['ordinary/stderr'] and 'Finished ' in row['stderr']
    assert not g.re.search(r'^\s*(?:Blocking|error|warning|Running)\b',row['stderr'],g.re.M)
    shown=g.re.findall(r'^\s*Executable .+ \((.+)\)\s*$',row['stderr'],g.re.M)
    assert sorted(Path(s).name for s in shown)==sorted(row['target_basenames'].values())
    assert set(row['target_basenames'])==set(g.P['harnesses'])
    for stage,key,note in (('first','first_files','ordinary'),('repeat','repeat_files','follow')):
        g.validate_files(row[key],f['declared'])
        assert raw_json(row[key])==r[note+'/files.json']==w[('ordinary' if stage=='first' else 'repeat')+'_files']
        assert set(row['listings'][stage])==set(g.P['harnesses'])
        for label,s in row['listings'][stage].items():
            assert hash_text(s)==r[note+'/list-'+label+'.stdout']==g.A['first']['harness'][label]['listing']
            assert r[note+'/list-'+label+'.stderr']==g.EMPTY_SHA
    m=row['repeat_typed'];assert m['units']==m['fresh']==11 and m['diag']==[]
    assert m['typed']==w['repeat_typed']==f['canonical_typed'] and g.dig(m['typed'])==m['roster']==g.A['first']['roster']
    inv=row['physical'];assert inv['tools']==row['repeat_jobs']==w['repeat_tools']==[] and inv['cargo_execs']==2
    assert w['repeat_stdout']==r['follow/cargo.stdout'] and w['repeat_stderr']==r['follow/cargo.stderr']
    assert raw_json(inv)==r['follow/inventory.json']==w['repeat_traces']
    assert inv['trace_files']=={k.removeprefix('follow/trace/'):v for k,v in r.items() if k.startswith('follow/trace/')}
    assert r['follow/jobs.json']==raw_json([])
    if i==0:
        assert 'clock' not in row and row['untimed']=={'command':g.P['command'],'exit':0}
        assert raw_json(row['untimed'])==r['ordinary/unclocked-exit.json']
        return None
    t=json.loads(row['raw_clock_bytes']);assert t==row['clock']
    assert hash_text(row['raw_clock_bytes'])==r['ordinary/clock.json'] and t['command']==g.P['command'] and t['exit']==0
    assert all(type(t[k]) is int for k in ('start','stop','elapsed_ns')) and 0<t['start']<t['stop'] and t['elapsed_ns']==t['stop']-t['start']
    return t


def check(packet):
    f=packet['frozen'] if 'frozen' in packet else packet
    assert f['admitted']['admitted'] is True and g.WIDTH.fullmatch(f['admission_sha256'])
    assert f['admission_sha256']==raw_json(f['admitted'])
    assert f['admitted']['wall_manifest']==f['registration']['wall_sha256']==g.manifest(HERE)
    assert f['native_result_ref']==f['registration']['native_result_ref']==g.P['native_result_ref']
    assert f['registration']['native_result_sha256']==g.P['native_result_sha256']
    assert f['admitted']['registration']==raw_json(f['registration'])
    assert f['tools']['sdk']==g.P['sdk'] and f['tools']['arms']==g.P['cargo']
    assert f['admitted']['ci']==raw_json(f['ci']);g.ci(f['ci'])
    assert len(f['probes'])==2 and f['admitted']['clocks']==0
    for j,(arm,probe) in enumerate(zip(g.P['unscored_preflight_order'],f['probes'],strict=True),1):
        assert portable_slot(probe,0,j,arm,f) is None and probe['raw']['verified.json']==f['admitted']['preflight'][j-1]
    if 'status' not in packet:
        return {'status':'native_preflight_passed','verified_unclocked':2,'admission_sha256':f['admission_sha256']}
    assert packet['source']==g.manifest(HERE)
    if packet['status']=='failed':
        assert packet['statistics'] is packet['original']['statistics'] is None
        rows=packet['original']['slots']
        expected=[(i,j,a) for i,o in enumerate(g.P['order'],1) for j,a in enumerate(o,1)]
        assert [(x['block'],x['slot'],x['arm']) for x in rows]==expected[:len(rows)]
        for x in rows:
            if x['clock_present']:
                assert hash_text(x['raw_clock_bytes'])==x['raw_hashes']['clock.json']
                t=json.loads(x['raw_clock_bytes']);assert t['command']==g.P['command'] and t['elapsed_ns']==t['stop']-t['start']
        return dict(status='failed',clocks=sum(x['clock_present'] for x in rows),statistics=None,first_failure_sha256=packet['original']['failure_sha256'])
    assert packet['status']=='complete' and len(packet['rows'])==48
    assert packet['registration']==f['registration']
    g.grant_valid(f['registration'],packet['grant'],f['admission_sha256'])
    term=packet['terminal'];assert term['phase']=='all_slots_finished' and term['slots']==48
    assert term['admission']==f['admission_sha256'] and term['grant']==raw_json(packet['grant'])
    rows=[];stop=0
    for i,order in enumerate(g.P['order'],1):
        ns={}
        for j,a in enumerate(order,1):
            t=portable_slot(packet['rows'][2*(i-1)+j-1],i,j,a,f)
            assert stop<t['start'];stop=t['stop'];ns[a]=t['stop']-t['start']
        rows.append(dict(block=i,order=order,ns=ns))
    stats=analysis.evaluate(g.P,rows);assert stats==packet['statistics']
    return dict(status='complete',raw_clocks=48,verified_pairs=24,physical_empty_repeats=48,statistics=stats)


if __name__=='__main__':
    op,*args=sys.argv[1:]
    if op=='verify':
        path,=map(Path,args);print(json.dumps(check(json.loads(gzip.decompress(path.read_bytes()))),sort_keys=True,indent=2))
    else:
        if op=='admission':
            folder,=map(Path,args);packet=admission(folder)
        else:
            assert op=='result';result,admit=map(Path,args);packet=collect(result,admit)
        check(packet)
        sys.stdout.buffer.write(gzip.compress(json.dumps(packet,sort_keys=True,separators=(',',':')).encode(),mtime=0))
