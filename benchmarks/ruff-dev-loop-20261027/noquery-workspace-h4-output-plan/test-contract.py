"""Exercise path, section and source identity controls using the exact independently inspected ELF references."""
from pathlib import Path
import copy,json,sys,tempfile
p=Path(__file__).resolve().parent;sys.path.insert(0,str(p))
from workspace_outputs import RULES, TARGET, key, units, admitted
def reject(f):
 try:f()
 except AssertionError:return
 raise RuntimeError('unexpected acceptance')
def main():
 r=RULES['known_products'];n=next(v for v in r if v.endswith('/ruff-9c601305a3f3b4b8'));e=r[n];a=e['older_reference'];c=e['new_reference']
 orig=str(TARGET/n.removeprefix('target/').replace('@observed-compiler@','v2-'+RULES['namespaces']['O']));new=orig.replace(RULES['namespaces']['O'],RULES['namespaces']['C'])
 assert key('O',orig)==key('C',new)==n and key('A',orig+'/x')!=key('C',new)
 for bad in (new,orig.replace(RULES['workspace'],'0000000000000000'),orig+'/../bin',str(TARGET.parent/'some-other-target/debug/ruff')):reject(lambda:key('O',bad))
 assert key('O',str(TARGET/'debug/ruff'))=='target/debug/ruff'
 assert admitted('A',n,a,a)=='raw' and admitted('C',n,a,c)=='exact_independently_decoded_product'
 for name,old,v in (('unrelated',a,c),(n,{**a,'raw':'a'*64},c),(n,a,{**c,'rodata_flags':0x37,'raw':'b'*64}),(n,a,{**c,'except_registered_wild_fields':'c'*64,'raw':'d'*64})):reject(lambda:admitted('C',name,old,v))
 reject(lambda:admitted('A',n,a,c))
 width={**a,'raw':'f'*64,'build_id':'e'*64,'rodata_entsize':8}
 assert admitted('A',n,a,width)=='registered_wild_worker_field' and admitted('C',n,width,c)=='exact_independently_decoded_product'
 def rows(arm,f,src=None):
  value={'reason':'compiler-artifact','package_id':'path+file:///a#b','manifest_path':'/a/Cargo.toml','target':{'name':'unit','src_path':orig},'profile':{'test':True},'features':['actual'], 'filenames':[f],'executable':f}
  if src:value[src[0]]=src[1]
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'cargo';path.write_text((json.dumps(value)+'\n')*619);return units(arm,path)
 reference=rows('O',orig);assert reference==rows('C',new)
 for field,v in [('features',[new]),('manifest_path',new),('package_id',new),('target',{'name':'unit','src_path':new}),('profile',{'test':False})]:
  assert reference!=rows('C',new,(field,v))
 return {'public_eight_refs':len(r)*2,'equal_typed_rows':619,'wrong_Cargo_namespace_and_input_paths_rejected':True,'changed_crate_metadata_and_unregistered_ELF_rejected':True,'prior_worker_width_gate_retained':True}
if __name__=='__main__':print(json.dumps(main(),sort_keys=True))
