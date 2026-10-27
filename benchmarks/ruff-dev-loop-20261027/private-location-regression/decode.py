"""Inspect the final compiler's serialized retained-definition hashes and actual physical spans."""
from pathlib import Path
from functools import lru_cache
import bisect,json,re,runpy,sys
E=Path(__file__).resolve().parent
def uleb128(data, offset):
    value = 0
    shift = 0
    while offset < len(data) and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
        shift += 7
    raise ValueError("Invalid unsigned LEB128")

class Reader:
 def __init__(self,data):self.b=data;self.root=int.from_bytes(data[8:16],'little');self.i=self.root;self.prev=None
 def u(self):v,self.i=uleb128(self.b,self.i);return v
 def raw(self,n):v=self.b[self.i:self.i+n];self.i+=n;assert len(v)==n;return v
 def text(self):
  n=self.u();s=self.raw(n).decode();assert self.raw(1)==b'\xc1';return s
 def symbol(self):
  t=self.u()
  if t==0:return self.text()
  n=self.u()
  if t==2:return n
  assert t==1
  u=self.i;self.i=n;s=self.text();self.i=u;return s
 def array(self):
  n=self.u()
  if not n:return (0,0)
  delta=self.u()
  self.prev=self.root-delta if self.prev is None else self.prev+delta
  assert 0<self.prev<self.root
  return (n,self.prev)

names=['intrinsic', 'is_macro_rules', 'type_alias_is_checked', 'attr_flags', 'def_path_hashes', 'explicit_item_bounds', 'explicit_item_self_bounds', 'inferred_outlives_of', 'explicit_super_clauses_of', 'explicit_implied_clauses_of', 'explicit_implied_const_bounds', 'inherent_impls', 'opt_rpitit_info', 'module_children_reexports', 'ambig_module_children', 'cross_crate_inlinable', 'asyncness', 'constness', 'safety', 'defaultness', 'impl_is_fully_generic_for_reflection', 'is_exportable', 'is_reachable_non_generic', 'is_reachable_non_generic_with_export_level_c', 'attributes', 'module_children_non_reexports', 'associated_item_or_field_def_ids', 'def_kind', 'visibility', 'def_span', 'def_ident_span', 'lookup_stability', 'lookup_const_stability', 'lookup_default_body_stability', 'lookup_deprecation_entry', 'explicit_clauses_of', 'generics_of', 'type_of', 'variances_of', 'fn_sig', 'codegen_fn_attrs', 'impl_trait_header', 'const_param_default', 'object_lifetime_default', 'optimized_mir', 'mir_for_ctfe', 'trivial_const', 'closure_saved_names_of_captured_variables', 'mir_coroutine_witnesses', 'mir_coroutine_runtime_info', 'promoted_mir', 'thir_abstract_const', 'impl_parent', 'const_conditions', 'coerce_unsized_info', 'mir_const_qualif', 'rendered_const', 'rendered_precise_capturing_args', 'fn_arg_idents', 'coroutine_kind', 'coroutine_for_closure', 'adt_destructor', 'adt_async_destructor', 'coroutine_by_move_body_def_id', 'eval_static_initializer', 'trait_def', 'expn_that_defined', 'default_fields', 'params_in_repr', 'repr_options', 'def_keys', 'proc_macro_quoted_spans', 'variant_data', 'assoc_container', 'macro_definition', 'deduced_param_attrs', 'collect_return_position_impl_trait_in_trait_tys', 'doc_link_resolutions', 'doc_link_traits_in_scope', 'assumed_wf_types_for_rpitit', 'opaque_ty_origin', 'anon_const_kind', 'const_of_item', 'associated_types_for_impl_traits_in_trait_or_impl', 'live_args_for_alias_from_outlives_bounds', 'args_known_to_outlive_alias_params', 'mut_restriction', 'proc_macro']
kinds="CrateRoot Impl ForeignMod Use GlobalAsm TypeNs ValueNs MacroNs LifetimeNs Closure Ctor AnonConst OpaqueTy OpaqueLifetime AnonAssocTy SyntheticCoroutineBody NestedStatic".split()

def decode(p, source_fragment):
    m=p.read_bytes();r=Reader(m);assert r.u()==0; triple=r.text(); full=r.raw(32);name=r.symbol()
    assert r.raw(2)==bytes(2);suffix=r.text();crate=r.raw(8)
    if r.u(): r.u()
    r.u();r.u();r.raw(4)
    for _ in range(13):r.array()
    assert r.u()==1
    for _ in range(3):r.array()
    assert r.u()==0
    for _ in range(5):r.array()
    def lazy():
        delta=r.u(); r.prev=r.prev+delta if r.prev is not None else r.root-delta;assert 0<r.prev<=r.root;return r.prev
    def table(): return r.u(),r.u(),lazy()
    ts={label:table()for label in names}
    ctxt,expn,expn_hash=table(),table(),table();lazy();sf=table()
    for _ in range(2):r.array()
    flags=r.raw(9); assert max(flags)<4 and r.u()==1
    public,epublic=table(),table();global_fp=r.raw(16).hex()
    def entries(t):
        width,n,at=t;sparse=bool(width&128);width&=127;assert width<=17
        mapping=[True]*n
        if sparse:
            mapping=[]; prior=0
            for lo in range(0,n,64):
                bits=int.from_bytes(m[at:at+8],'little');count=int.from_bytes(m[at+8:at+12],'little');at+=12;assert count==prior;prior+=bits.bit_count()
                mapping.extend(bool(bits&(1<<bit))for bit in range(min(64,n-lo)))
        out=[]
        for b in mapping:
            if b:out.append(int.from_bytes(m[at:at+width],'little'));at+=width
            else:out.append(0)
        return out
    @lru_cache(None)
    def span(at):
        if not at:return None
        r.i=at;tag=r.raw(1)[0];k=tag&3;root=bool(tag&4);n=tag>>3
        if k==3:
            z=int.from_bytes(r.raw(n),'little');return span(at-z if root else z)
        ctx=0 if root else r.u()
        if k==2:return [k,ctx]
        lo=r.u();sz=r.u() if n==31 else n
        return [k,ctx,lo,sz,r.u(),r.u() if k==1 else 0]
    ids=entries(ts['def_path_hashes']); retained=entries(public);sps=entries(ts['def_span']);idents=entries(ts['def_ident_span']);keys=entries(ts['def_keys'])
    @lru_cache(None)
    def defname(i):
        r.i=keys[i];parent=r.u();assert parent in (0,1),(name,i,parent)
        par=r.u() if parent else None;tag=r.u();assert tag<len(kinds),(i,tag)
        arg=r.symbol() if tag in (5,6,7,8,13,14)else None;dis=r.u()
        s=str(arg)if arg is not None else '{'+kinds[tag]+'}';s+=('#'+str(dis))if dis else ''
        return (defname(par)+'::'+s)if par is not None else str(name)
    files=[]
    for at in entries(sf):
        r.i=at;ty,local=r.u(),r.u();assert(ty,local)==(0,0),(name,ty,local)
        path,wd,fullpath=r.text(),r.text(),r.text();r.u()
        def shash():
            k=r.u();assert r.u()==32;return r.raw(32).hex()
        sk=shash();ch=shash()if r.u()else None
        norm,orig,nl=r.u(),r.u(),r.u();w=r.u()if nl else 0;raw=r.raw(w*max(0,nl-1));starts=[0] if nl else []
        for lo in range(0,len(raw),w or 1):
            starts.append(starts[-1]+int.from_bytes(raw[lo:lo+w],'little'))
        files.append((path,norm,starts,sk))
    focus=[i for i,(v,*rest) in enumerate(files)if source_fragment in v]
    def physical(x):
        if not x:return None
        k=x[0]
        if k!=0 or x[4]not in focus:return x
        f=files[x[4]]
        def lc(o):
            l=bisect.bisect_right(f[2],o)-1;return[l+1,o-f[2][l]+1]
        return [*x,lc(x[2]),lc(x[2]+x[3])]
    facts={}; focused=[]
    for i,dp in enumerate(ids):
        fp=retained[i] if i<len(retained) else 0;h=fp.to_bytes(17,'little')[1:].hex() if fp else None
        ds=span(sps[i]) if i<len(sps) else None;di=span(idents[i]) if i<len(idents)else None
        if h:facts[f'{dp:016x}']=[h,defname(i)]
        if any(v and len(v)>3 and v[0]==0 and v[4]in focus for v in (ds,di)):
            focused.append({"id":i,"path_hash":f'{dp:016x}',"name":defname(i),"retained_scc":h,"def":physical(ds),"ident":physical(di)})
    return {"name":name,"private_public_raw":full.hex(),"global":global_fp,"files":[[i,files[i][0],files[i][1],files[i][3]]for i in focus],"source_table":[[i,f[0],f[1],f[3]]for i,f in enumerate(files)],"defs":facts,"focus":focused}

if __name__=="__main__":
    p=Path(sys.argv[1]);o=decode(p,sys.argv[2]);print(o['name'],o['global'],len(o['defs']),o['files'],len(o['focus']));print(o['focus'][:4])
    if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(o)+'\n')
