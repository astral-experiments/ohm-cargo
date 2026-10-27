"""Same path, released Wild and ordinary Rust external reader: demand the one changed member."""
from pathlib import Path
x=Path(__file__).resolve().parent
exec(compile((x/'layout-cohort.py').read_text().split('out=private/"products"')[0],str(x/'layout-cohort.py'),'exec'))
from runpy import run_path
api=run_path(str(x/'audit.py'))
from collections import Counter
r=x/'selected-control';r.mkdir()
active=r/'libruff_python_trivia-control.rlib';exe=r/'caller';gold={}
for i,st in enumerate(('reversed','restored','reversed')):
 d=r/(str(i)+'-'+st);d.mkdir()
 src=x/'products'/st/'trivia.rlib';shutil.copyfile(src,active);assert sha(src)==sha(active)
 args=json.loads((root/'records/test/layout-restored/ordinary-0/argv.json').read_bytes());assert args[-2]=='-o';args[-1]=str(exe)
 j=args.index('--extern')+1
 assert args[j].startswith('ruff_python_trivia=')
 args[j]='ruff_python_trivia='+str(active)
 flags=['-Clinker-features=-lld','-Clink-self-contained=-linker','-Clink-arg=-B'+str(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld'),'-Clink-arg=-fuse-ld=bfd']
 args+=flags;save(d/'argv.json',args)
 rc=subprocess.run(['strace','-ff','-qq','-e','trace=execve','-s','100000','-o',str(d/'exec'),*args],cwd=sc['W'],env=dict(env,WILD_WRITE_LAYOUT='1'),capture_output=True);assert rc.returncode==0,rc.stderr
 result=subprocess.run([exe],capture_output=True);assert result.returncode==0 and result.stdout.decode()==plan['oracles'][st] and not result.stderr
 layout=exe.with_name(exe.name+'.layout');shutil.copy2(layout,d/'caller.layout');shutil.copy2(exe,d/'caller')
 members,index=api['archive'](active.read_bytes());files,_=api['decode_layout'](layout.read_bytes())
 obj,=[k for k in members if '9nrjcd40q7tnroj77cn9hniqd' in k]
 hits=[(p,ent,secs) for p,ent,secs,_ in files if Path(p)==active and ent and api['stable'](ent[-1])==obj];assert len(hits)==1
 _,(a,z,n),sections=hits[0];assert (n,a,z)==members[obj][:3]
 section_def,_=api['elf'](members[obj][3])
 retained={name:ran for key,(i,name,_,_) in section_def.items() if (ran:=sections[i]) is not None}
 machine,=[name for name in retained if name.startswith('.text.') and 'dedent_to' in name]
 rec={'full_exe':sha(exe),'layout':sha(layout),'stdout':result.stdout.decode(),'library':sha(active),'selected_member':obj,'dedent_text':{'section':machine,'range':retained[machine],'object_section':section_def[machine+'#0']},'input_path':str(active)}
 if st in gold:assert rec==gold[st]
 gold[st]=rec;save(d/'receipt.json',rec)
save(r/'complete.json',gold)
