"""Compute the exact StableCrateId used to name the compiler incremental directory."""
M=2**64-1
def rot(a,i):return ((a<<i)|(a>>(64-i)))&M
def round_(s):
    a,b,c,d=s;a=(a+b)&M;b=rot(b,13)^a;a=rot(a,32);c=(c+d)&M;d=rot(d,16)^c;a=(a+d)&M;d=rot(d,21)^a;c=(c+b)&M;b=rot(b,17)^c;c=rot(c,32);return a,b,c,d
def sip13_low(msg):
    a,b,c,d=0x736f6d6570736575,0x646f72616e646f6d^0xee,0x6c7967656e657261,0x7465646279746573
    rem=len(msg)%8;whole=len(msg)-rem;chunks=[int.from_bytes(msg[i:i+8],'little') for i in range(0,whole,8)]
    chunks.append((len(msg)&255)<<56|int.from_bytes(msg[whole:],'little'))
    for v in chunks:a,b,c,d=round_((a,b,c,d^v));a^=v
    c^=0xee
    for _ in range(3):a,b,c,d=round_((a,b,c,d))
    return a^b^c^d
def stable_id(name,metadata,exe,version):
    b=name.encode()+b'\xffmetadata'
    for m in sorted(set(metadata)):b+=len(m.encode()).to_bytes(8,'little')+m.encode()
    return sip13_low(b+(b'exe' if exe else b'lib')+version.encode())
def b36(n):
    s=''
    while n:s='0123456789abcdefghijklmnopqrstuvwxyz'[n%36]+s;n//=36
    return s.rjust(13,'0')
