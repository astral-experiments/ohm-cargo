from pathlib import Path
import hashlib,json
d=Path(__file__).resolve().parent;s=json.loads((d/"summary.json").read_bytes());r=json.loads((d/"targets.json").read_bytes())
assert len(r)==s["target_count"]==50 and len({x["physical_exec_record_sha256"]for x in r})==len({x["one_writable_cgu_identity"]for x in r})==50
assert sum(x["files"] for x in s["distinct_explicit_names"].values())==3401
assert s["distinct_explicit_names"]["build_user_can_modify_or_replace"]=={"files":3396,"bytes":1420620362}
assert s["distinct_explicit_names"]["root_owned_and_protected_from_build_user"]=={"files":5,"bytes":7528}
assert s["selected_ty_server_e2e_explicit_names"]["build_user_can_modify_or_replace"]=={"files":389,"bytes":603691188}
assert s["selected_ty_server_e2e_explicit_names"]["root_owned_and_protected_from_build_user"]=={"files":5,"bytes":7528}
assert s["distinct_search_directory_spellings"]=={"build_user_changeable":5,"expired_transient_name_with_changeable_parent":50,"root_owned_and_protected_from_build_user":8}
assert s["intrinsically_sealed_explicit_inputs"]==0 and s["independent_higher_provider_directories_for_that_specific_name"]==1
assert s["each_target_has_a_distinct_user_changeable_native_object"] and s["targets_with_an_earlier_absent_libgcc_s_so_under_the_user_changeable_psm_build_directory"]==50
assert next(x for x in r if x["target"]=="e2e-f978f73ba5a3a2ed")["elf_sha256"]=="be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7"
assert s["private_physical_census_gzip_sha256"]=="4deff6c5bee024d42e7bc5ae39e7e8ada3128a902fdb02a0254ec4f4537493bd"
print("50 original released native commands, 3401 explicit names, 50 separate user-changeable native objects and one earlier native provider directory verified.")
