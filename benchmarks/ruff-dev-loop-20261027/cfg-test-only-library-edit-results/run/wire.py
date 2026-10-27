"""Decode the registered file's exact source-map entry, from its unique real source checksum and actual serialized line table."""
import hashlib
def read(md,src,filename):
 b=md.read_bytes();src=src.read_bytes();v=hashlib.md5(src).digest();ix=b.find(v);assert ix>=2 and b.count(v)==1 and b[ix:ix+32]==v+bytes(16);i=ix+32
 def var():
  nonlocal i
  r=t=0
  while True:
   c=b[i];i+=1;r+=(c&127)<<t
   if c<128:return r
   t+=7;assert t<64
 implicit=var();ck=None
 if implicit:
  kind=var();size=var();assert size==32;ck=[kind,b[i:i+size].hex()];i+=size
 normalized=var();original=var();lines=var();width=var();assert width in (1,2,4) and normalized==original==len(src),(normalized,original,len(src))
 line_offsets=[0]+[i+1 for i,c in enumerate(src) if c==10 and i+1<len(src)]
 assert len(line_offsets)==lines,(len(line_offsets),lines)
 diffdata=b[i:i+(lines-1)*width];deltas=[int.from_bytes(diffdata[k:k+width],'little') for k in range(0,len(diffdata),width)];assert deltas==[y-x for x,y in zip(line_offsets,line_offsets[1:])]
 return {'rmeta_sha256':hashlib.sha256(b).hexdigest(),'md5_payload_position':ix,'encoded_source_md5':v.hex(),'carries_filename_near_entry':filename.encode() in b[max(0,ix-550):ix],'encoded_other_checksum':ck,'normalized_bytes':normalized,'original_bytes':original,'lines':lines,'bytes_per_line_delta':width,'line_delta_table_bytes':len(diffdata),'line_delta_sha256':hashlib.sha256(diffdata).hexdigest(),'line_starts_equal_to_every_line_in_actual_source':True}
