"""Rebuild only the native-impl candidate with the original release-14 compiler, PGO and BOLT profile."""
from pathlib import Path
import contextlib,hashlib,json,os,shutil,signal,socket,subprocess,sys,time,traceback
r=Path(__file__).resolve().parent
previous=r.with_name('ohm-private-trait-release14-20261026')
lint=r.with_name('ohm-empty-lint-scope-release14-20261026')
sys.path.insert(0,str(previous));import helper as h
h.root=r
ram=Path('/run/user/1000/ohm-private-native-release14-fuse-20261027')
@contextlib.contextmanager
def overlay(name,lower):
    top=ram/name
    for d in ('upper','work'):(top/d).mkdir(parents=True)
    merged=r/(name+'-merged');merged.mkdir()
    opts=f'lowerdir={lower},upperdir={top}/upper,workdir={top}/work'
    h.run([lint/'tools/usr/bin/fuse-overlayfs','-o',opts,merged])
    try:yield merged
    finally:h.run(['fusermount3','-u',merged])
def execute(ns,env,kind):
    argv=h.recipe(kind);start=time.monotonic();log=r/(kind+'.log');minimum=None
    with log.open('xb') as fd:
        proc=subprocess.Popen(ns+argv,env=env,stdout=fd,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while proc.poll() is None:
                free=shutil.disk_usage(ram).free
                minimum=free if minimum is None else min(minimum,free)
                if free < 256*2**20 or shutil.disk_usage(r).free < 256*2**20:raise RuntimeError('private output reached the 256 MiB reserve')
                time.sleep(3)
        except BaseException:
            os.killpg(proc.pid,signal.SIGTERM);proc.wait();raise
    h.save(kind,{'rc':proc.returncode,'elapsed_s':time.monotonic()-start,'minimum_tmpfs_free':minimum,'argv':argv})
    if proc.returncode:raise RuntimeError(kind+': '+log.read_text()[-3600:])
def main():
    assert socket.gethostname()=='charlie-ohm-mono-bench' and os.getuid()==1000
    assert not ram.exists();ram.mkdir(mode=0o700);tmpview=r/'scratch';(tmpview/'current').mkdir(parents=True)
    before=h.read(previous/'receipt-B.json');spec=before['sources'];profiles=before['profiles']
    src=h.donor/'rust';low=src/'build';assert h.sumfile(low/h.driver)==h.sha_baseline
    assert subprocess.check_output(['git','--no-optional-locks','-C',src,'rev-parse','HEAD']).decode().strip()=='f1a7cf9d20b2cae39e991b178b56ba06b43dc8fa'
    assert before['driver']==h.sumfile(previous/'B-driver.so')=='051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518'
    assert all(h.sumfile(low/'opt-artifacts'/k)==v for k,v in profiles.items()) and all(h.sumfile(src/f)==v[0] for f,v in spec.items())
    prior=h.read(h.release/'base/stage.json')['env'];env={k:prior[k] for k in ('CARGO_HOME','HOME','LANG','LC_ALL','LOGNAME','PATH','RUNNER_TEMP','TMPDIR','USER')};env.update(RUST_BOOTSTRAP_CONFIG=str(h.canonical/'rust/build/ohm-release-bootstrap.toml'),DIST_TRY_BUILD='0',GITHUB_ACTIONS='false',TERM='dumb',CARGO_UNSTABLE_OHM_LINKER='lld',CARGO_NET_OFFLINE='true',RUST_BACKTRACE='full',GIT_OPTIONAL_LOCKS='0')
    with overlay('build',low) as out,overlay('cargo-home',h.donor/'cargo-home') as cout:
        ns=['/usr/bin/bwrap','--ro-bind','/','/','--ro-bind',str(h.template),str(h.release),'--ro-bind',str(h.donor),str(h.canonical),'--bind',str(out),str(h.canonical/'rust/build'),'--bind',str(cout),str(h.canonical/'cargo-home'),'--bind',str(tmpview),str(h.targetroot)]
        source={}
        for i,(f,variants) in enumerate(spec.items()):
            carrier=r/('source-'+str(i)+'.rs')
            selected=r/'encoder.rs' if f.endswith('/encoder.rs') else previous/('B-'+str(i)+'.rs')
            want='2eca99c0b8cc4a4bc2ebe4a778894a3ecc625fd376d97400300183195b8ebfd8' if f.endswith('/encoder.rs') else variants[2]
            assert h.sumfile(selected)==want
            shutil.copyfile(selected,carrier);source[f]=want;ns+=['--ro-bind',str(carrier),str(h.canonical/'rust'/f)]
        ns+=['--dev','/dev','--proc','/proc','--tmpfs','/tmp','--chdir',str(h.canonical/'rust'),'--']
        print('compiling',flush=True);execute(ns,env,'compile');assert b'Compiling rustc_metadata ' in (r/'compile.log').read_bytes()
        initial=h.sumfile(out/h.driver);tmp=tmpview/'current/.tmpkjJIsW';assert not tmp.exists();shutil.copyfile(out/h.driver,tmp)
        print('BOLT',initial,flush=True);execute(ns,env,'bolt');tmp.unlink();post=h.sumfile(out/h.driver);assert b'.bolt.org.text' in subprocess.check_output(['readelf','-SW',out/h.driver]);shutil.copyfile(out/h.driver,r/'candidate-driver.so')
        h.save('receipt',{'sources':source,'profiles':profiles,'parent_postbolt':before['driver'],'parent_prebolt':before['prebolt'],'candidate_prebolt':initial,'candidate_postbolt':post,'frontend':h.sumfile(out/h.driver.parent.parent/'bin/rustc'),'target_triple':'x86_64-unknown-linux-gnu'});print('complete',post,flush=True)
    assert h.sumfile(low/h.driver)==h.sha_baseline and all(h.sumfile(src/f)==v[0] for f,v in spec.items());shutil.rmtree(ram)
if __name__=='__main__':
    try:main()
    except BaseException:h.save('failure',{'error':traceback.format_exc()});raise
