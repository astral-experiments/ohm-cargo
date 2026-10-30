def role(av):
 """Return an enabled rustc link-only request only when both Cargo's flag and the cached recipe are present."""
 tokens=[];i=0
 while i<len(av):
  t=av[i]
  if t=='-Z':
   assert i+1<len(av),'trailing -Z'
   tokens.append((av[i+1],'split'));i+=2;continue
  if t.startswith('-Z') and len(t)>2:tokens.append((t[2:],'joined'))
  i+=1
 flags=[]
 for token,spelling in tokens:
  if token=='link-only':flags.append((True,spelling))
  elif token.startswith('link-only='):
   value=token.partition('=')[2]
   assert value in ('yes','no','true','false','on','off','1','0'),token
   flags.append((value in ('yes','true','on','1'),spelling))
 assert len(flags)<=1,flags
 recipes=[t for t in av if not t.startswith('-') and t.endswith('.rlink')]
 if not flags or not flags[0][0]:
  assert not recipes,('recipe on an unclassified compiler invocation',recipes)
  return False,'full-or-probe',()
 assert len(recipes)==1 and '--crate-name' in av and '--out-dir' in av and not any(not t.startswith('-') and t.endswith('.rs') for t in av),('ambiguous link invocation',recipes)
 return True,flags[0][1],tuple(recipes)
def self_test_roles():
 good=('--crate-name','x','--out-dir','d','spec.rlink')
 for flag,mode in [(('-Z','link-only'),'split'),(('-Zlink-only',),'joined'),(('-Z','link-only=yes'),'split'),(('-Zlink-only=on',),'joined')]:assert role(good+flag)==(True,mode,('spec.rlink',))
 for flags in [('-Zrelink-only',),('-Z','relink-only'),('-Z','link-only=no'),('-Zlink-only=off',),('-Z','other')]:assert role(('--crate-name','x','x.rs')+flags)==(False,'full-or-probe',())
 for bad in [good,good+('-Z',),good+('-Z','link-only','x.rs'),('--crate-name','x','-Z','link-only'),good+('-Z','link-only','-Zlink-only')]:
  try:role(bad)
  except AssertionError:continue
  raise AssertionError(bad)
self_test_roles()
