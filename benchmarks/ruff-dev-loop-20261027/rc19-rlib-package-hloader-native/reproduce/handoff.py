"""Private final custody, input identities, and ordinary stock archive member readout."""
from pathlib import Path
import hashlib
import json
import os
import stat
import subprocess as sp

def h(b):
    return hashlib.sha256(b).hexdigest()

def dig(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()

def rec(path, data):
    path.write_bytes(json.dumps(data, sort_keys=True, indent=2).encode()+b'\n')

def tree(root):
    total=0
    count=0
    c=hashlib.sha256()
    types={}
    for p in sorted(root.rglob('*')):
        st=p.lstat()
        kind=stat.S_IFMT(st.st_mode)
        types[str(kind)]=types.get(str(kind),0)+1
        pair=[os.fsencode(p.relative_to(root)).hex(),st.st_mode]
        if stat.S_ISREG(st.st_mode):
            pair.extend([st.st_size,dig(p)]);total+=st.st_size
        elif stat.S_ISLNK(st.st_mode):
            pair.append(os.fsencode(os.readlink(p)).hex())
        else:
            assert stat.S_ISDIR(st.st_mode),(p,kind)
        encoded=json.dumps(pair,separators=(',',':')).encode()
        c.update(len(encoded).to_bytes(8,'little'));c.update(encoded)
        count+=1
    return {'file_mode_content_tree_sha256':c.hexdigest(),'files_and_dirs':count,'logical_regular_bytes':total,'types':types}

def archive(path):
    raw=path.read_bytes()
    assert raw[:8]==b'!<arch>\n'
    offset=8;names=b'';vals=[]
    while offset<len(raw):
        hdr=raw[offset:offset+60];assert len(hdr)==60 and hdr[58:]==b'`\n'
        token=hdr[:16].rstrip(b' ');sz=int(hdr[48:58]);start=offset+60
        value=memoryview(raw)[start:start+sz];assert len(value)==sz
        if token==b'//':
            names=bytes(value);name=token
        elif token.startswith(b'/')and token[1:].isdigit():
            dest=int(token[1:]);end=names.index(b'/\n',dest);name=names[dest:end]
        else:name=token.rstrip(b'/') or b'/'
        vals.append({'name':name.decode(),'offset':start,'size':sz,'sha256':h(value)})
        offset=start+sz+(sz%2)
    assert offset==len(raw)
    return {'sha256':h(raw),'length':len(raw),'members':vals}

def summary(a,b):
    ac=[row for row in a['members']if row['name'].endswith('.o')]
    bc=[row for row in b['members']if row['name'].endswith('.o')]
    assert len(ac)==len(bc)==256
    # Report actual archive order even when code-generation member labels differ.
    pairs=list(zip(ac,bc))
    return {'ordered_elf_count':[len(ac),len(bc)],'equal_names':sum(x['name']==y['name']for x,y in pairs),
            'equal_payloads_in_order':sum(x['sha256']==y['sha256']for x,y in pairs),
            'equal_offset_and_size':sum((x['offset'],x['size'])==(y['offset'],y['size'])for x,y in pairs),
            'equal_size':sum(x['size']==y['size']for x,y in pairs),'old_first_elf_offset':ac[0]['offset'],'new_first_elf_offset':bc[0]['offset'],
            'equal_aligned_4096':sum(x['offset']%4096==y['offset']%4096 for x,y in pairs),
            'non_elf':[[{k:v for k,v in row.items()} for row in aa['members']if not row['name'].endswith('.o')]for aa in (a,b)]}

def custody(ctx):
    R,B,W,ST,S,env,run,H,OLD=ctx
    reports=R/'reports';work=reports/'handoff';work.mkdir()
    sources={'H':B/'snapshots/H/target/debug/libruff_linter.rlib',
             'stock-edited':B/'snapshots/stock-edited/target/debug/libruff_linter.rlib',
             'stock-restored':B/'snapshots/stock-restored/target/debug/libruff_linter.rlib',
             'empty-edited':B/'snapshots/independent-empty-edited/target/debug/libruff_linter.rlib'}
    for name in ('real-cow','real-observe','real-malformed','real-restored'):
        sources[name]=B/'native-references'/name/'generated-reference.a'
    archives={k:archive(p)for k,p in sources.items()}
    expected={'H':'fresh-H','stock-edited':'stock-post-reverse','stock-restored':'stock-restored-repeat','empty-edited':'independent-empty-repeat'}
    for tag,rep in expected.items():
        assert archives[tag]['sha256']==json.loads((reports/rep/'product.json').read_bytes())['old_candidate_sha']
    for tag in ('real-cow','real-observe','real-malformed','real-restored'):
        assert archives[tag]['sha256']==json.loads((reports/('proof-'+tag)/'terminal.json').read_bytes())['new']
    rec(work/'archives-private.json',archives)
    p=[('H','stock-edited'),('stock-edited','stock-restored'),('H','real-cow'),('H','real-observe'),('stock-edited','real-restored'),
       ('real-cow','real-observe'),('real-observe','real-malformed'),('stock-edited','empty-edited'),('real-cow','empty-edited')]
    deltas={k+'_'+v:summary(archives[k],archives[v])for k,v in p}
    rec(work/'archive-deltas.json',deltas)
    source=sp.run(['git','diff','--quiet',H,'--'],cwd=W,env=env())
    if source.returncode:
        run(['git','diff','--quiet',OLD,'--'],cwd=W,env=env())
        run(['git','apply','--check',R/'change.patch'],cwd=W,env=env());run(['git','apply',R/'change.patch'],cwd=W,env=env())
    run(['git','diff','--quiet',H,'--'],cwd=W,env=env()); assert sp.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip()==H
    reg=B/'retired/home-before-empty-edited';assert reg.is_dir() and (reg/'registry').is_dir()
    cfg=reg/'config.toml';assert cfg.is_file()
    donor=B/'snapshots/H'; val=sp.check_output(['btrfs','property','get','-ts',donor,'ro'],text=True).strip();assert val=='ro=true',val
    caps=int(next(z.split()[1]for z in Path('/proc/self/status').read_text().splitlines()if z.startswith('CapEff:')),16)
    assert not caps
    free=lambda path:os.statvfs(path).f_bavail*os.statvfs(path).f_frsize
    v={'seed_top':archives['H']['sha256'],'active_empty_top':archives['empty-edited']['sha256'],
       'archive_manifest':dig(work/'archives-private.json'),'archive_deltas':dig(work/'archive-deltas.json'),
       'source':H,'parent':OLD,'git_diff_exit':0,'logical_home':'cargo-home','readonly_target_donor':'snapshots/H',
       'registry_donor':'retired/home-before-empty-edited','registry_tree':tree(reg),'registry_donor_logical_config':dig(cfg),
       'readonly_btrfs_property':val,'euid':os.geteuid(),'caps':caps,'cpus':sorted(os.sched_getaffinity(0)),
       'btrfs_available':free(B),'backing_available':free(R),'image_logical_bytes':(R/'private.btrfs').stat().st_size,
       'image_allocated_bytes':(R/'private.btrfs').stat().st_blocks*512}
    rec(work/'terminal.json',v);print(json.dumps(v,sort_keys=True),flush=True)
