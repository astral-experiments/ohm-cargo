"""Cross the two actual images against each existing trained directory, without copying its SDK or target."""
from pathlib import Path
import os,runpy
w=runpy.run_path(str(Path.home()/'.cache/ohm-script-hash-wall-rc19-v1/host-wall-v2.py'))
D,C,images,switch,qualify,sha,save,read,dg,traces,host=(w[k] for k in ('D','C','images','switch','qualify','sha','save','read','dg','traces','host'))
X=D/'same-physical-crossover-v3';X.mkdir();out=[];fields=('ids','products','zips','checks','generations','reader','source','native_outputs')
for seed in 'AB':
 switch(seed);initial=read(traces/('secure-pre-'+seed+'.json'));original_sdk=C/'sdk/bin/cargo';marker=C/'marker';before=original_sdk.stat();actual_ids={x:(C/x).stat().st_ino for x in ('sdk','home','target','shared')};assert sha(original_sdk)==images['arms'][seed]['image'];fixed=read(D/'fixed-inodes-qa-v1/setup.json')['identities'][seed]; ids=lambda p:[p.stat().st_dev,p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns];stable={'compiler':C/'sdk/bin/rustc','driver':next((C/'sdk/lib').glob('librustc_driver-*.so'))};assert all(ids(p)==fixed[k][1]for k,p in stable.items())
 for arm in 'AB':
  backup=X/('original-cargo-'+seed);bmarker=X/('original-marker-'+seed)
  if arm!=seed:
   parked=X/('parked-'+arm);resident=D/'states'/arm;assert resident.is_dir()and (resident/'marker').read_text()==arm;resident.rename(parked);marker.rename(bmarker);marker.write_text(arm);original_sdk.rename(backup);os.link(D/'received'/('cargo-'+arm),original_sdk)
  try:
   observed=qualify(arm,'secure-physical-'+seed)
   diff=[k for k in fields if observed[k]!=initial[k]]
   assert not diff,(seed,arm,diff);assert observed['rows']==observed['fresh']==182
   out.append({'seed':seed,'image':arm,'physical_image':sha(original_sdk),'identities':actual_ids,'initial':{k:dg(initial[k])for k in fields},'after':{k:dg(observed[k])for k in fields},'native':observed['physical'],'exec':observed['actual_exec'],'rows':182,'fresh':182})
  finally:
   assert all(ids(p)==fixed[k][1]for k,p in stable.items())
   if arm!=seed:
    original_sdk.unlink();backup.rename(original_sdk);marker.unlink();bmarker.rename(marker);parked.rename(resident)
   assert original_sdk.stat().st_ino==before.st_ino and marker.read_text()==seed and {x:(C/x).stat().st_ino for x in actual_ids}==actual_ids
save(X/'complete.json',{'terminal':True,'host':host,'crossovers':out});print('physical crossover',host,len(out),sha(X/'complete.json'),flush=True)
