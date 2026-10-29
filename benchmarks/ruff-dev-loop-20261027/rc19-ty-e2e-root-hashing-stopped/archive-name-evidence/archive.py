"""Reconstruct a second GNU archive by replacing only seven bytes in each real member name."""
import hashlib
import re

OBJ=re.compile(rb"([A-Za-z_][A-Za-z0-9_]*-[0-9a-f]{16}\.[a-z0-9]+)\.([a-z0-9]{7})\.rcgu\.o")
def sha(body):return hashlib.sha256(body).hexdigest()

def census(blob):
    assert blob[:8]==b"!<arch>\n"
    at=8;names=b"";rows=[]
    while at<len(blob):
        header=blob[at:at+60]
        assert len(header)==60 and header[-2:]==b"`\n"
        size=int(header[48:58]);offset=at+60;end=offset+size;assert end<=len(blob)
        token=header[:16].rstrip()
        if re.fullmatch(rb"/[0-9]+",token):
            i=int(token[1:]);assert i==0 or names[i-2:i]==b"/\n"
            name=names[i:names.index(b"/\n",i)]
        else:name=token if token in (b"/",b"//") else token.removesuffix(b"/")
        if name==b"//":names=blob[offset:end]
        if size%2:assert blob[end:end+1]==b"\n"
        rows.append((name,at,offset,end,sha(header)))
        at=end+size%2
    assert at==len(blob)
    return rows

def compare(a,b):
    result={"left":sha(a),"right":sha(b),"sizes":[len(a),len(b)],"equivalent_exact_names":False}
    if a==b:return {**result,"equivalent_exact_names":True,"status":"already-identical","edits":[]}
    ax,bx=census(a),census(b)
    if len(ax)!=len(bx) or len(a)!=len(b):return {**result,"status":"different-size-or-members"}
    correspondence=[];channels={};sample=[]
    for (an,at,off,end,ah),(bn,bt,bo,be,bh) in zip(ax,bx,strict=True):
        if (at,off,end,ah)!=(bt,bo,be,bh):return {**result,"status":"different-archive-header","member":an.decode()}
        ar,br=OBJ.fullmatch(an),OBJ.fullmatch(bn)
        if bool(ar)!=bool(br) or (ar and ar[1]!=br[1]) or (not ar and an!=bn):return {**result,"status":"different-member-identity","member":an.decode()}
        if ar:correspondence.append((an,bn,ar,br))
        if an in (b"//",b"lib.rmeta-link"):
            assert an not in channels
            channels[an]=(off,end)
        elif a[off:end]!=b[off:end]:
            sample.append([an.decode(),sha(a[off:end]),sha(b[off:end])])
    if sample:return {**result,"status":"different-nonname-member-bytes","examples":sample}
    if len(set(x[0] for x in correspondence))!=len(correspondence) or not correspondence or b"//" not in channels:
        return {**result,"status":"no-unique-native-names"}
    if any(len({row[i][2] for row in correspondence})!=1 for i in (2,3)):return {**result,"status":"mixed-object-nonces"}
    changed=bytearray(a);positions=[];members=[]
    for channel,(offset,end) in channels.items():
        old_sec=a[offset:end];new_sec=b[offset:end];occurrences=[]
        for old,new,am,bm in correspondence:
            # Do not infer the filename boundary from bytes directly BEFORE old/new.
            # The encoder stores ASCII-valued sequence lengths immediately before it.
            old_hits=[m.start() for m in re.finditer(re.escape(old),old_sec)]
            new_hits=[m.start() for m in re.finditer(re.escape(new),new_sec)]
            if old_hits!=new_hits or len(old_hits)!=1:return {**result,"status":"unproven-name-occurrence","channel":channel.decode(),"member":old.decode()}
            j=old_hits[0]
            if channel==b"//" and (j!=0 and old_sec[j-2:j]!=b"/\n" or old_sec[j+len(old):j+len(old)+2]!=b"/\n"):
                return {**result,"status":"name-not-a-GNU-entry"}
            off=offset+j+am.start(2);assert changed[off:off+7]==am[2] and b[off:off+7]==bm[2]
            changed[off:off+7]=bm[2];positions.append([off,am[2].decode(),bm[2].decode()]);occurrences.append([j,old.decode(),new.decode()])
        members.append([channel.decode(),sorted(occurrences)])
    assert len({p[0] for p in positions})==len(positions) and len(positions)==len(channels)*len(correspondence)
    match=changed==b
    return {**result,"status":"entire-reconstruction-exact" if match else "different-bytes-outside-proven-fields",
            "equivalent_exact_names":match,"predicted_sha256":sha(changed),"edits":sorted(positions),"channels":members}
