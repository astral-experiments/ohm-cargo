"""Continuation of untouched native qualification after Python 3.12 declined Ruff's ZIP method 93."""
from pathlib import Path
import binascii,fcntl,hashlib,os,shutil,struct,subprocess,sys,traceback,zipfile
from unittest.mock import patch
import replay as r
SELF=Path(__file__).resolve()
P=r.Q/'qualification-zstd-v1'

def member(archive,name,pwd=None):
    info=archive.getinfo(name)
    assert name=='stdlib/ty_extensions/pydantic.pyi' and info.compress_type==93 and not info.flag_bits&1 and pwd is None
    assert info.file_size<=262144 and info.compress_size<=262144 and archive.fp
    archive.fp.seek(info.header_offset)
    header=archive.fp.read(30); sig,ver,flags,method,mt,md,crc,clen,ulen,fn,extra=struct.unpack('<I5H3I2H',header)
    assert sig==0x04034b50 and method==93 and flags==info.flag_bits and archive.fp.read(fn)==name.encode()
    if not flags&8:assert (crc,clen,ulen)==(info.CRC,info.compress_size,info.file_size)
    archive.fp.seek(extra,1);encoded=archive.fp.read(info.compress_size);assert len(encoded)==info.compress_size
    result=subprocess.run(['/usr/bin/zstd','--quiet','--decompress','--stdout'],input=encoded,capture_output=True,check=True,timeout=5)
    assert len(result.stdout)==info.file_size and binascii.crc32(result.stdout)==info.CRC and not result.stderr
    return result.stdout

def holding(root,d,state,arm):
    opts=r.spawn_args(root,r.Q,state,state/'registry-home',[],r.PRODUCT/('cargo-'+arm),r.DRIVER);ix=opts.index('--')
    mounts=[v for f in r.HOLDOUT['files'] for v in ('--ro-bind',str(d/'active'/f),str(r.RUFF/f))]
    proc=subprocess.run([*opts[:ix],*mounts,*opts[ix:],sys.executable,'-B',str(SELF),'inside',str(d),arm],stdin=subprocess.DEVNULL,timeout=360)
    assert proc.returncode==0,(d,proc.returncode)
def parity(raw,pack,direction):
    proof={}
    for name in ('preflight','change','change-next','change-next-2'):
        a=r.load(raw/name/'receipt.json');b=r.load(pack/name/'receipt.json')
        for key in ('units','fresh','unit_roster_sha256','totals','rust_warnings'):assert a[key]==b[key],(direction,name,key)
        assert sorted(a['dirty'])==sorted(b['dirty'])
        for f,keys in [('rustc',('kind','crate')),('scripts',('package','sha256'))]:
            vals=lambda j:sorted(tuple(x[k] for k in keys) for x in j[f])
            assert vals(a)==vals(b),(direction,name,f)
        proof[name]={'units':a['units'],'fresh':a['fresh'],'physical':a['totals'],'unit_roster_sha256':a['unit_roster_sha256']}
    assert r.load(raw/'physical-snapshots.json')==r.load(pack/'physical-snapshots.json')
    r.dump(pack/'raw-packaged-parity.json',proof)
def main():
    assert r.sha(r.HERE/'replay.py')=='378ff0961646713188f4c9d5fe6e1e2d99379e1d1224ff6f589686332b04207c'
    assert not P.exists() and not (r.Q/'prepared.json').exists() and not (r.Q/'score').exists()
    failed=r.Q/'prepare/pydantic/parent'
    assert 'That compression method is not supported' in (failed/'failure.txt').read_text() and not (failed/'change').exists()
    assert r.load(failed/'preflight/receipt.json')['fresh']==520
    for arm in ('parent','candidate'):
        for start in ('original','edited'):
            j=r.load(r.Q/'prepare'/arm/start/'seed.json')['settled'];assert j['fresh']==520 and not j['scripts'] and not j['totals'].get('rustc-full',0)
    with (r.P/'native-measure.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        P.mkdir(mode=0o700);root=r.skeleton(P);r.floor()
        state=r.RAM/'episode';ex=r.RAM/'excluded-before-first-pydantic-edit';assert state.is_dir() and not ex.exists();state.rename(ex)
        r.dump(P/'method.json',{'replay_sha256':r.sha(r.HERE/'replay.py'),'supplement_sha256':r.sha(SELF),'decoder':str(Path('/usr/bin/zstd').resolve()),'decoder_sha256':r.sha('/usr/bin/zstd'),'decoder_version':subprocess.check_output(['/usr/bin/zstd','--version'],text=True).strip(),'failed_preflight':str(failed),'excluded_target':str(ex)})
        def case(mode,name,arm,direction,kind):
            view='original' if direction=='reverse' else 'edited'
            d=P/name;d.mkdir(parents=True);seed=r.RAM/'seeds'/arm/view;r.copy_state(seed,state)
            source=r.Q/'prepare'/arm/view/'active' if kind=='main' else r.Q/'fixture'/kind/view
            shutil.copytree(source,d/'active',copy_function=shutil.copy2)
            if kind=='holdout':holding(root,d,state,arm)
            else:r.run(root,mode,d,state,arm,direction,kind)
            assert state==r.RAM/'episode' and state.is_dir();shutil.rmtree(state)
            print('QUALIFIED',name,flush=True)
        for arm in ('parent','candidate'):
            for direction in ('reverse','restore'):
                if arm=='parent':
                    assert (r.Q/'prepare/calibration'/arm/direction/'raw-packaged-parity.json').is_file()
                    continue
                case('trace','calibration/'+arm+'/'+direction,arm,direction,'main')
                case('trace-raw','raw-calibration/'+arm+'/'+direction,arm,direction,'main')
                parity(P/'raw-calibration'/arm/direction,P/'calibration'/arm/direction,direction)
            case('trace','pydantic/'+arm,arm,'reverse','holdout')
        for arm in ('parent','candidate'):
            pp=r.load(P/'pydantic'/arm/'physical-snapshots.json')
            for name,key in [('before','original'),('change','edited'),('restore','original')]:
                matches=[z for n,z in pp[name].items() if n.endswith('zipped_typeshed.zip')]
                expected=r.HOLDOUT['files']['crates/ty_vendored/ty_extensions/pydantic.pyi'][key+'_sha256']
                assert matches and all(z['source_member_sha256']==expected for z in matches)
        r.dump(r.Q/'prepared.json',{'subjects':r.load(r.PRODUCT/'pair.json'),'disk':r.floor(),'source':r.git('rev-parse','HEAD'),'runner_sha256':r.sha(r.HERE/'replay.py'),'unscored_zip_supplement':r.sha(SELF),'unscored_qualification':str(P)})
        print('ALL RAW, PACKAGED, SEED AND ZIP GATES PASSED',flush=True)
if __name__=='__main__':
    try:
        if len(sys.argv)>1:
            _,_,out,arm=sys.argv
            with patch.object(zipfile.ZipFile,'read',member):r.nsinside('trace',out,arm,'reverse','holdout')
        else:main()
    except BaseException:
        where=Path(sys.argv[2]) if len(sys.argv)>1 else P
        if where.exists():(where/'failure.txt').write_text(traceback.format_exc())
        raise
