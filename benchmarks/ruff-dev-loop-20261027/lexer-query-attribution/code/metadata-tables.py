from pathlib import Path
import json,collections,struct
class R:
 def __init__(s,b):s.v=b;s.root=int.from_bytes(b[8:16],'little');s.i=s.root;s.prev=None
 def raw(s,n):r=s.v[s.i:s.i+n];s.i+=n;return r
 def u(s):
  ret=0;j=0
  while 1:
   b=s.raw(1)[0];ret|=(b&127)<<j
   if not b&128:return ret
   j+=7
 def text(s):v=s.raw(s.u()).decode();assert s.raw(1)==b'\xc1';return v
 def sym(s):
  k=s.u()
  if k==0:return s.text()
  n=s.u()
  if k==2:return n
  assert k==1;i=s.i;s.i=n;t=s.text();s.i=i;return t
 def arr(s):
  n=s.u()
  if not n:return (0,0)
  d=s.u();s.prev=s.root-d if s.prev is None else s.prev+d;return n,s.prev
 def deps(s):
  assert s.u()==0;s.text();s.raw(32);s.sym();s.raw(2);s.text();s.raw(8)
  if s.u():s.u()
  s.u();s.u();s.raw(4);s.arr();n,pos=s.arr();s.i=pos;z=[]
  for c in range(1,n+1):
   name=s.sym();hash=s.raw(16).hex();host=s.raw(16).hex()if s.u()else None;k=s.u();extra=s.text();pr=s.u();z.append([name,c,hash,extra,host,k,pr])
  return z

names=['intrinsic', 'is_macro_rules', 'type_alias_is_checked', 'attr_flags', 'def_path_hashes', 'explicit_item_bounds', 'explicit_item_self_bounds', 'inferred_outlives_of', 'explicit_super_clauses_of', 'explicit_implied_clauses_of', 'explicit_implied_const_bounds', 'inherent_impls', 'opt_rpitit_info', 'module_children_reexports', 'ambig_module_children', 'cross_crate_inlinable', 'asyncness', 'constness', 'safety', 'defaultness', 'impl_is_fully_generic_for_reflection', 'is_exportable', 'is_reachable_non_generic', 'is_reachable_non_generic_with_export_level_c', 'attributes', 'module_children_non_reexports', 'associated_item_or_field_def_ids', 'def_kind', 'visibility', 'def_span', 'def_ident_span', 'lookup_stability', 'lookup_const_stability', 'lookup_default_body_stability', 'lookup_deprecation_entry', 'explicit_clauses_of', 'generics_of', 'type_of', 'variances_of', 'fn_sig', 'codegen_fn_attrs', 'impl_trait_header', 'const_param_default', 'object_lifetime_default', 'optimized_mir', 'mir_for_ctfe', 'trivial_const', 'closure_saved_names_of_captured_variables', 'mir_coroutine_witnesses', 'mir_coroutine_runtime_info', 'promoted_mir', 'thir_abstract_const', 'impl_parent', 'const_conditions', 'coerce_unsized_info', 'mir_const_qualif', 'rendered_const', 'rendered_precise_capturing_args', 'fn_arg_idents', 'coroutine_kind', 'coroutine_for_closure', 'adt_destructor', 'adt_async_destructor', 'coroutine_by_move_body_def_id', 'eval_static_initializer', 'trait_def', 'expn_that_defined', 'default_fields', 'params_in_repr', 'repr_options', 'def_keys', 'proc_macro_quoted_spans', 'variant_data', 'assoc_container', 'macro_definition', 'deduced_param_attrs', 'collect_return_position_impl_trait_in_trait_tys', 'doc_link_resolutions', 'doc_link_traits_in_scope', 'assumed_wf_types_for_rpitit', 'opaque_ty_origin', 'anon_const_kind', 'const_of_item', 'associated_types_for_impl_traits_in_trait_or_impl', 'live_args_for_alias_from_outlives_bounds', 'args_known_to_outlive_alias_params', 'mut_restriction', 'proc_macro']
def decode(path):
    m = path.read_bytes()
    r = R(m)
    assert r.u() == 0
    triple = r.text()
    r.raw(32)
    name = r.sym()
    assert r.raw(2) == bytes(2)
    r.text(); r.raw(8)
    if r.u(): r.u()
    r.u(); r.u(); r.raw(4)
    for _ in range(13): r.arr()
    assert r.u() == 1
    for _ in range(3): r.arr()
    assert r.u() == 0
    for _ in range(5): r.arr()
    def lazy():
        delta = r.u()
        r.prev = r.prev + delta if r.prev is not None else r.root - delta
        assert 0 < r.prev <= r.root
        return r.prev
    def table(): return r.u(), r.u(), lazy()
    tables={nm:table() for nm in names}
    ctxt, expn, expn_hash = table(), table(), table()
    lazy()
    sf = table()
    def entries(t):
        width, n, at = t
        sparse = width & 128
        width &= ~128
        assert 0 <= width <= 17
        populated = [True] * n
        if sparse:
            populated = []
            for lo in range(0,n,64):
                bitmap, count = int.from_bytes(m[at:at+8],'little'), int.from_bytes(m[at+8:at+12],'little')
                assert count == sum(populated)
                at += 12
                populated += [bool(bitmap & 1 << bit) for bit in range(min(64,n-lo))]
        out = []
        for p in populated:
            if p:
                out.append(int.from_bytes(m[at:at+width],'little'))
                at += width
            else: out.append(0)
        return out
    def lookup_span(at):
        if at==0:return None
        r.i=at
        tag=r.raw(1)[0];kind=tag&3; rootctxt=bool(tag&4);n=tag>>3
        if kind==3:
            value=int.from_bytes(r.raw(n),'little')
            return lookup_span(at-value if rootctxt else value)
        ctxt=0 if rootctxt else r.u()
        if kind==2:return [2,ctxt]
        lo=r.u()
        length=r.u() if n==31 else n
        ordinal=r.u()
        producer=r.u() if kind==1 else 0
        return [kind,ctxt,lo,length,ordinal,producer]
    keys=entries(tables['def_path_hashes']);res={};
    for nm in ['def_span','def_ident_span']:
        spans=entries(tables[nm]);res[nm]={k:(lookup_span(spans[i]) if i<len(spans)and spans[i] else None) for i,k in enumerate(keys) if k}
    return keys,res

