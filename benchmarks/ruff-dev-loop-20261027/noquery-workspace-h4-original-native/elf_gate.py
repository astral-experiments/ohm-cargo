"""Accept exactly the one shipped-linker field transition reproduced with unchanged inputs."""
def permitted_linker_width(a,b):
    n,m=a["rodata_entsize"],b["rodata_entsize"]
    nonzero={1,2,4,8,16,32,64,128,256}
    return (
        ((n==0 and m in nonzero) or (m==0 and n in nonzero))
        and a["bytes"]==b["bytes"]
        and a["except_registered_wild_fields"]==b["except_registered_wild_fields"]
        and a["rodata_type"]==b["rodata_type"]==1
        and a["rodata_flags"]==b["rodata_flags"] and a["rodata_flags"]&0x12==0x12
        and not a["rodata_flags"]&0x5
        and isinstance(a["build_id"],str) and isinstance(b["build_id"],str)
        and len(a["build_id"])==len(b["build_id"])==64 and a["build_id"]!=b["build_id"]
    )
