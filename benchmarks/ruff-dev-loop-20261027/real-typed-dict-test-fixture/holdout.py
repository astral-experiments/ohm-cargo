"""Measure actual stock Cargo work on the preregistered runtime-discovered TypedDict fixture."""
from pathlib import Path
import ast, collections, fcntl, hashlib, json, os, re, shutil, signal, subprocess, tempfile, time
H=Path.home()
W=H/'code/oss/ruff-ohm-whole-native-20261027'
P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
D=P/'build-script-producer-reuse16-v1'
Q=D/'runtime-mdtest-v2'; Q.mkdir(exist_ok=False)
R=D/'graph-registry'; T=D/'target-mdtest-v2'; S=Path('/dev/shm/ohm-rustc-scout-runtime-mdtest-store-v2'); Tmp=Q/'tmp'
for p in (T,S,Tmp):p.mkdir()
I='93526150df078af7dd8fc4226cdcc469539d2001'
C='be042539847afee4223e92ce271b080d70c91ea8'
F=Path('crates/ty_python_semantic/resources/mdtest/typed_dict.md')
PK=W/'crates/ty_python_semantic'
HI='2eed231b412822b4ea7eeb61c42ffbc37ad52d4b5376c3c65aaf02d1ed59f76e';HE='7ed4b83346dfc9e0cab30fa18ff53d09cb6c95945d2e754eecac8c37a10e2fc6'
def hashfile(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def sh(*cmd,**kw):return subprocess.check_output(cmd,**kw)
def save(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
assert sh('git','rev-parse','HEAD',cwd=W,text=True).strip()==I and not sh('git','status','--porcelain','-uno',cwd=W)
assert hashfile(W/F)==HI
import base64
patch=base64.b64decode(b'ZGlmZiAtLWdpdCBhL2NyYXRlcy90eV9weXRob25fc2VtYW50aWMvcmVzb3VyY2VzL21kdGVzdC90eXBlZF9kaWN0Lm1kIGIvY3JhdGVzL3R5X3B5dGhvbl9zZW1hbnRpYy9yZXNvdXJjZXMvbWR0ZXN0L3R5cGVkX2RpY3QubWQKaW5kZXggNGUyZjY0ZmI5ZGJiNDk5MTA5MmI5NjM2Y2I5Yzc4NmYxNmNlYjQyYS4uYTA4MGNlZjIwNTZkZDVlMjVjYjljMTczODIxZTIzM2U1ZDE3MGJjZiAxMDA2NDQKLS0tIGEvY3JhdGVzL3R5X3B5dGhvbl9zZW1hbnRpYy9yZXNvdXJjZXMvbWR0ZXN0L3R5cGVkX2RpY3QubWQKKysrIGIvY3JhdGVzL3R5X3B5dGhvbl9zZW1hbnRpYy9yZXNvdXJjZXMvbWR0ZXN0L3R5cGVkX2RpY3QubWQKQEAgLTc4ODksNyArNzg4OSwxMiBAQCBzdGF0aWNfYXNzZXJ0KGlzX2VxdWl2YWxlbnRfdG8oRXh0cmEsIENsb3NlZCkpCiBzdGF0aWNfYXNzZXJ0KGlzX3N1YnR5cGVfb2YoRXh0cmEsIENsb3NlZCkpCiBzdGF0aWNfYXNzZXJ0KGlzX3N1YnR5cGVfb2YoQ2xvc2VkLCBFeHRyYSkpCiBzdGF0aWNfYXNzZXJ0KGlzX2VxdWl2YWxlbnRfdG8oQWxpYXNlZEV4dHJhLCBDbG9zZWQpKQorYGBgCisKK1RoaXMgYWxzbyBhcHBsaWVzIHRvIGBnZXRgOiBhbiB1bmRlY2xhcmVkIGtleSByZXR1cm5zIG9ubHkgYE5vbmVgIG9yIHRoZSBzdXBwbGllZCBkZWZhdWx0LCB3aGV0aGVyCitgZXh0cmFfaXRlbXNgIGlzIGBOZXZlcmAgb3IgYW4gYWxpYXMgb2YgYE5ldmVyYDoKIAorYGBgcHkKIGRlZiBfKGV4dHJhOiBFeHRyYSwgYWxpYXNlZDogQWxpYXNlZEV4dHJhKSAtPiBOb25lOgogICAgIHJldmVhbF90eXBlKGV4dHJhLmdldCgibWlzc2luZyIpKSAgIyByZXZlYWxlZDogTm9uZQogICAgIHJldmVhbF90eXBlKGFsaWFzZWQuZ2V0KCJtaXNzaW5nIiwgRmFsc2UpKSAgIyByZXZlYWxlZDogTGl0ZXJhbFtGYWxzZV0KQEAgLTg1MTQsNTkgKzg1MTksMTE4IEBAIGRlZiBfKAogICAgIHJlYWRfb25seS5jbGVhcigpICAjIGVycm9yOiBbdW5yZXNvbHZlZC1hdHRyaWJ1dGVdCiBgYGAKIAotIyMjIGBnZXRgIGFjY291bnRzIGZvciBjbG9zZWQgVHlwZWREaWN0cworIyMjIGBnZXRgIG9uIGNsb3NlZCBUeXBlZERpY3RzCiAKLUFuIGFyYml0cmFyeSBzdHJpbmcga2V5IGNhbiBvbmx5IHJlZmVyIHRvIGEgZGVjbGFyZWQgaXRlbSBvbiBhIGNsb3NlZCBUeXBlZERpY3Q6CitBIGNsb3NlZCBgVHlwZWREaWN0YCBjYW5ub3QgY29udGFpbiBrZXlzIGJleW9uZCB0aG9zZSBpbiBpdHMgZGVmaW5pdGlvbi4gSGVyZSwgYFBlcnNvbmAgY2Fubm90Citjb250YWluIGFuIGAiZW1haWwiYCBrZXksIHNvIGBnZXRgIHJldHVybnMgb25seSBgTm9uZWAgb3IgdGhlIHN1cHBsaWVkIGRlZmF1bHQ6CiAKIGBgYHB5CiBmcm9tIHR5cGluZ19leHRlbnNpb25zIGltcG9ydCBUeXBlZERpY3QKIAotY2xhc3MgQ2xvc2VkKFR5cGVkRGljdCwgY2xvc2VkPVRydWUpOgorY2xhc3MgUGVyc29uKFR5cGVkRGljdCwgY2xvc2VkPVRydWUpOgogICAgIG5hbWU6IHN0cgotICAgIHllYXI6IGludAorICAgIGFnZTogaW50CiAKLUZ1bmN0aW9uYWxDbG9zZWQgPSBUeXBlZERpY3QoCi0gICAgIkZ1bmN0aW9uYWxDbG9zZWQiLAotICAgIHsibmFtZSI6IHN0ciwgInllYXIiOiBpbnR9LAotICAgIGNsb3NlZD1UcnVlLAotKQorZGVmIF8ocGVyc29uOiBQZXJzb24pIC0+IE5vbmU6CisgICAgcmV2ZWFsX3R5cGUocGVyc29uLmdldCgiZW1haWwiKSkgICMgcmV2ZWFsZWQ6IE5vbmUKKyAgICByZXZlYWxfdHlwZShwZXJzb24uZ2V0KCJlbWFpbCIsIEZhbHNlKSkgICMgcmV2ZWFsZWQ6IExpdGVyYWxbRmFsc2VdCitgYGAKIAotY2xhc3MgRW1wdHlDbG9zZWQoVHlwZWREaWN0LCBjbG9zZWQ9VHJ1ZSk6IC4uLgorQSBrZXkgb2YgdHlwZSBgc3RyYCBjb3VsZCBiZSBgIm5hbWUiYCwgYCJhZ2UiYCwgb3IgYW4gYWJzZW50IGtleSwgc28gdGhlIHJlc3VsdCBpbmNsdWRlcyBib3RoIGZpZWxkCit0eXBlcyBhbmQgdGhlIGRlZmF1bHQ6CiAKLWRlZiBfKGNsb3NlZDogQ2xvc2VkLCBmdW5jdGlvbmFsOiBGdW5jdGlvbmFsQ2xvc2VkLCBlbXB0eTogRW1wdHlDbG9zZWQsIGtleTogc3RyKSAtPiBOb25lOgotICAgIHJldmVhbF90eXBlKGNsb3NlZC5nZXQoa2V5KSkgICMgcmV2ZWFsZWQ6IHN0ciB8IGludCB8IE5vbmUKLSAgICByZXZlYWxfdHlwZShmdW5jdGlvbmFsLmdldChrZXkpKSAgIyByZXZlYWxlZDogc3RyIHwgaW50IHwgTm9uZQotICAgIHJldmVhbF90eXBlKGVtcHR5LmdldChrZXkpKSAgIyByZXZlYWxlZDogTm9uZQotICAgIHJldmVhbF90eXBlKGNsb3NlZC5nZXQoa2V5LCBiIm1pc3NpbmciKSkgICMgcmV2ZWFsZWQ6IHN0ciB8IGludCB8IExpdGVyYWxbYiJtaXNzaW5nIl0KLSAgICByZXZlYWxfdHlwZShjbG9zZWQuZ2V0KCJuYW1lIiwgRmFsc2UpKSAgIyByZXZlYWxlZDogc3RyCi0gICAgcmV2ZWFsX3R5cGUoZW1wdHkuZ2V0KGtleSwgRmFsc2UpKSAgIyByZXZlYWxlZDogTGl0ZXJhbFtGYWxzZV0KK2BgYHB5CitkZWYgXyhwZXJzb246IFBlcnNvbiwga2V5OiBzdHIpIC0+IE5vbmU6CisgICAgcmV2ZWFsX3R5cGUocGVyc29uLmdldChrZXkpKSAgIyByZXZlYWxlZDogaW50IHwgc3RyIHwgTm9uZQorICAgIHJldmVhbF90eXBlKHBlcnNvbi5nZXQoa2V5LCBiIm1pc3NpbmciKSkgICMgcmV2ZWFsZWQ6IGludCB8IHN0ciB8IExpdGVyYWxbYiJtaXNzaW5nIl0KIGBgYAogCi1BIGxpdGVyYWwga2V5IG91dHNpZGUgdGhlIGRlY2xhcmVkIHNjaGVtYSByZXR1cm5zIG9ubHkgYE5vbmVgIG9yIHRoZSBzdXBwbGllZCBkZWZhdWx0LiBUaGlzIGFsc28KLWFwcGxpZXMgdG8gc2F2ZWQgbWV0aG9kIHJlZmVyZW5jZXMsIGFuZCBkZWZhdWx0cyByZWNlaXZlIGNvbnRleHQgZnJvbSB0aGUgZXhwZWN0ZWQgcmVzdWx0IHR5cGU6CitJZiBldmVyeSBrZXkgaW4gYSB1bmlvbiBvZiBzdHJpbmcgbGl0ZXJhbHMgaXMgYWJzZW50LCBvbmx5IHRoZSBkZWZhdWx0IGNhbiBiZSByZXR1cm5lZDoKIAogYGBgcHkKIGZyb20gdHlwaW5nIGltcG9ydCBMaXRlcmFsCiAKLWRlZiBfKGNsb3NlZDogQ2xvc2VkLCBmdW5jdGlvbmFsOiBGdW5jdGlvbmFsQ2xvc2VkLCBtaXNzaW5nOiBMaXRlcmFsWyJtaXNzaW5nIiwgIm90aGVyIl0pIC0+IE5vbmU6Ci0gICAgcmV2ZWFsX3R5cGUoY2xvc2VkLmdldCgibWlzc2luZyIpKSAgIyByZXZlYWxlZDogTm9uZQotICAgIHJldmVhbF90eXBlKGNsb3NlZC5nZXQoIm1pc3NpbmciLCBGYWxzZSkpICAjIHJldmVhbGVkOiBMaXRlcmFsW0ZhbHNlXQotICAgIHJldmVhbF90eXBlKGZ1bmN0aW9uYWwuZ2V0KCJtaXNzaW5nIiwgMCkpICAjIHJldmVhbGVkOiBMaXRlcmFsWzBdCi0gICAgcmV2ZWFsX3R5cGUoY2xvc2VkLmdldChtaXNzaW5nKSkgICMgcmV2ZWFsZWQ6IE5vbmUKLSAgICByZXZlYWxfdHlwZShjbG9zZWQuZ2V0KG1pc3NpbmcsIEZhbHNlKSkgICMgcmV2ZWFsZWQ6IExpdGVyYWxbRmFsc2VdCitkZWYgXyhwZXJzb246IFBlcnNvbiwga2V5OiBMaXRlcmFsWyJlbWFpbCIsICJwaG9uZSJdKSAtPiBOb25lOgorICAgIHJldmVhbF90eXBlKHBlcnNvbi5nZXQoa2V5LCBGYWxzZSkpICAjIHJldmVhbGVkOiBMaXRlcmFsW0ZhbHNlXQorYGBgCiAKLSAgICBnZXQgPSBjbG9zZWQuZ2V0Ci0gICAgcmV2ZWFsX3R5cGUoZ2V0KCJtaXNzaW5nIikpICAjIHJldmVhbGVkOiBOb25lCi0gICAgcmV2ZWFsX3R5cGUoZ2V0KCJtaXNzaW5nIiwgRmFsc2UpKSAgIyByZXZlYWxlZDogTGl0ZXJhbFtGYWxzZV0KKyMjIyBgZ2V0YCBvbiBjbG9zZWQgVHlwZWREaWN0cyBkZWZpbmVkIHdpdGggZnVuY3Rpb25hbCBzeW50YXgKKworVGhlIGZ1bmN0aW9uYWwgc3ludGF4IGhhcyB0aGUgc2FtZSBiZWhhdmlvcjogYW4gYXJiaXRyYXJ5IHN0cmluZyBtYXkgbmFtZSBhIGRlY2xhcmVkIGZpZWxkLCBidXQgYW4KK3VuZGVjbGFyZWQgbGl0ZXJhbCBrZXkgYWx3YXlzIHJldHVybnMgdGhlIGRlZmF1bHQuCisKK2BgYHB5Citmcm9tIHR5cGluZ19leHRlbnNpb25zIGltcG9ydCBUeXBlZERpY3QKKworUGVyc29uID0gVHlwZWREaWN0KCJQZXJzb24iLCB7Im5hbWUiOiBzdHJ9LCBjbG9zZWQ9VHJ1ZSkKKworZGVmIF8ocGVyc29uOiBQZXJzb24sIGtleTogc3RyKSAtPiBOb25lOgorICAgIHJldmVhbF90eXBlKHBlcnNvbi5nZXQoa2V5KSkgICMgcmV2ZWFsZWQ6IHN0ciB8IE5vbmUKKyAgICByZXZlYWxfdHlwZShwZXJzb24uZ2V0KCJlbWFpbCIsIEZhbHNlKSkgICMgcmV2ZWFsZWQ6IExpdGVyYWxbRmFsc2VdCitgYGAKKworIyMjIGBnZXRgIG9uIGFuIGVtcHR5IGNsb3NlZCBUeXBlZERpY3QKKworQW4gZW1wdHkgY2xvc2VkIGBUeXBlZERpY3RgIGNhbm5vdCBjb250YWluIGFueSBrZXksIHNvIGV2ZW4gYSBsb29rdXAgd2l0aCBhbiBhcmJpdHJhcnkgc3RyaW5nCityZXR1cm5zIGBOb25lYDoKKworYGBgcHkKK2Zyb20gdHlwaW5nX2V4dGVuc2lvbnMgaW1wb3J0IFR5cGVkRGljdAorCitjbGFzcyBFbXB0eShUeXBlZERpY3QsIGNsb3NlZD1UcnVlKTogLi4uCisKK2RlZiBfKGVtcHR5OiBFbXB0eSwga2V5OiBzdHIpIC0+IE5vbmU6CisgICAgcmV2ZWFsX3R5cGUoZW1wdHkuZ2V0KGtleSkpICAjIHJldmVhbGVkOiBOb25lCitgYGAKKworIyMjIGBnZXRgIHRocm91Z2ggYSBzYXZlZCBtZXRob2QgcmVmZXJlbmNlCisKK1NhdmluZyBgZ2V0YCBpbiBhIHZhcmlhYmxlIHByZXNlcnZlcyBpdHMgcmV0dXJuIHR5cGVzIGZvciBhYnNlbnQga2V5czoKKworYGBgcHkKK2Zyb20gdHlwaW5nX2V4dGVuc2lvbnMgaW1wb3J0IFR5cGVkRGljdAorCitjbGFzcyBQZXJzb24oVHlwZWREaWN0LCBjbG9zZWQ9VHJ1ZSk6CisgICAgbmFtZTogc3RyCisKK2RlZiBfKHBlcnNvbjogUGVyc29uKSAtPiBOb25lOgorICAgIGdldCA9IHBlcnNvbi5nZXQKKyAgICByZXZlYWxfdHlwZShnZXQoImVtYWlsIikpICAjIHJldmVhbGVkOiBOb25lCisgICAgcmV2ZWFsX3R5cGUoZ2V0KCJlbWFpbCIsIEZhbHNlKSkgICMgcmV2ZWFsZWQ6IExpdGVyYWxbRmFsc2VdCitgYGAKKworIyMjIGBnZXRgIGRlZmF1bHQgdHlwZXMgZm9yIGFic2VudCBrZXlzCisKK1doZW4gYSBrZXkgaXMgYWJzZW50LCB0aGUgYW5ub3RhdGlvbiBvbiB0aGUgcmVzdWx0IGdpdmVzIHRoZSBlbGVtZW50IHR5cGUgZm9yIGFuIGVtcHR5IGxpc3QgcGFzc2VkCithcyB0aGUgZGVmYXVsdC4gVGhpcyBhbHNvIHdvcmtzIHRocm91Z2ggYSBzYXZlZCBtZXRob2QgcmVmZXJlbmNlOgorCitgYGBweQorZnJvbSB0eXBpbmdfZXh0ZW5zaW9ucyBpbXBvcnQgVHlwZWREaWN0CisKK2NsYXNzIENsb3NlZChUeXBlZERpY3QsIGNsb3NlZD1UcnVlKToKKyAgICBuYW1lOiBzdHIKIAorZGVmIF8oY2xvc2VkOiBDbG9zZWQpIC0+IE5vbmU6CiAgICAgdmFsdWVzOiBsaXN0W2ludF0gPSBjbG9zZWQuZ2V0KCJtaXNzaW5nIiwgcmV2ZWFsX3R5cGUoW10pKSAgIyByZXZlYWxlZDogbGlzdFtpbnRdCisgICAgZ2V0ID0gY2xvc2VkLmdldAogICAgIHNhdmVkX3ZhbHVlczogbGlzdFtpbnRdID0gZ2V0KCJtaXNzaW5nIiwgcmV2ZWFsX3R5cGUoW10pKSAgIyByZXZlYWxlZDogbGlzdFtpbnRdCitgYGAKKworQW4gYW5ub3RhdGlvbiBkb2VzIG5vdCBtYWtlIGFuIGluY29tcGF0aWJsZSBkZWZhdWx0IHZhbGlkOgorCitgYGBweQorZGVmIF8oY2xvc2VkOiBDbG9zZWQpIC0+IE5vbmU6CiAgICAgd3Jvbmc6IGludCA9IGNsb3NlZC5nZXQoIm1pc3NpbmciLCAid3JvbmciKSAgIyBlcnJvcjogW2ludmFsaWQtYXNzaWdubWVudF0KIGBgYAogCi1EZWNsYXJlZCBub24tcmVxdWlyZWQgaXRlbXMgc3RpbGwgcHJvdmlkZSBjb250ZXh0IGZvciB0aGVpciBkZWZhdWx0czoKKyMjIyBgZ2V0YCBkZWZhdWx0IHR5cGVzIGZvciBub24tcmVxdWlyZWQgaXRlbXMKKworRm9yIGEgZGVjbGFyZWQgbm9uLXJlcXVpcmVkIGl0ZW0sIHdlIGluZmVyIHRoZSB0eXBlIG9mIGFuIGVtcHR5IGxpc3QgZnJvbSB0aGUgaXRlbSdzIHR5cGUsIGV2ZW4gd2hlbgordGhlIHJlc3VsdCBoYXMgbm8gYW5ub3RhdGlvbjoKIAogYGBgcHkKK2Zyb20gdHlwaW5nX2V4dGVuc2lvbnMgaW1wb3J0IFR5cGVkRGljdAorCiBjbGFzcyBDbG9zZWRQYXJ0aWFsKFR5cGVkRGljdCwgdG90YWw9RmFsc2UsIGNsb3NlZD1UcnVlKToKICAgICB2YWx1ZXM6IGxpc3RbaW50XQogCg==')
assert hashlib.sha256(patch).hexdigest()=='1bb7dfbe145e4196851b4f78cef944ee52aafdd05956c7f29c41c0ad94c2a13c'
repo=Q/'fixture';subprocess.run(['git','init','-q',repo],check=True);(repo/F).parent.mkdir(parents=True);shutil.copyfile(W/F,repo/F)
subprocess.run(['git','apply','--reverse','-'],cwd=repo,input=patch,check=True);assert hashfile(repo/F)==HE
base=dict(PATH=str(H/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',HOME=str(H),RUSTUP_HOME=str(D/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(R),CARGO_TARGET_DIR=str(T),CARGO_BUILD_BUILD_DIR=str(S),CARGO_BUILD_JOBS='8',CARGO_NET_OFFLINE='true',LC_ALL='C.UTF-8',GIT_OPTIONAL_LOCKS='0',TMPDIR=str(Tmp))
floor=25*2**30;disks=[H,P,S];minimum={str(k):shutil.disk_usage(k).free for k in disks}
def guard():
    for k in disks:
        n=shutil.disk_usage(k).free;minimum[str(k)]=min(minimum[str(k)],n)
        assert n>floor,(k,n)
def ns(f,wd):
    return ['bwrap','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--bind',str(T),str(T),'--bind',str(S),str(S),'--bind',str(R),str(R),'--bind',str(Q),str(Q),'--ro-bind',str(f),str(W/F),'--chdir',str(wd),'--']
def execute(f,wd,args,out,err):
    guard()
    with out.open('wb') as o,err.open('wb') as e:
        child=subprocess.Popen(ns(f,wd)+list(map(str,args)),env=base,stdout=o,stderr=e,start_new_session=True)
        try:
            while True:
                try:return child.wait(timeout=1)
                except subprocess.TimeoutExpired:guard()
        except BaseException:
            os.killpg(child.pid,signal.SIGTERM);child.wait();raise
def jobs(q):
    rows=[];hashes=[]
    for f in sorted(q.glob('exec.*')):
        if not f.suffix[1:].isdigit(): continue
        lines=f.read_text(errors='replace').splitlines()
        for l in lines:
            m=re.match(r'execve\("([^"]+)", (\[.*\]), .+ = 0$',l)
            if not m:continue
            try:a=ast.literal_eval(m[2])
            except (ValueError,SyntaxError):raise RuntimeError((f,len(l)))
            nm=Path(m[1]).name
            if '--crate-name' in a:
                kind='rustc-link-only' if ('-Zlink-only' in a or any(x=='-Z'and y.split('=')[0]=='link-only' for x,y in zip(a,a[1:])))else 'rustc-full'
                rows.append({'kind':kind,'crate':a[a.index('--crate-name')+1],'command_sha256':hashlib.sha256(m[2].encode()).hexdigest()})
            elif m[1].endswith('/wild-ld/ld.bfd'):rows.append({'kind':'wild','output':Path(a[a.index('-o')+1]).name,'command_sha256':hashlib.sha256(m[2].encode()).hexdigest()})
            elif nm.startswith(('build-script-build','build_script_build')) and ('/run/' in m[1] or '/build/' in m[1]):rows.append({'kind':'build-script','name':nm,'command_sha256':hashlib.sha256(m[2].encode()).hexdigest()})
        hashes.append((f.name,hashfile(f)))
    return rows,hashes
def cargo(f,stage,mode):
    q=Q/(stage+'-'+mode);q.mkdir()
    cmd=['cargo','+ohm',('test'if mode=='test' else 'build'),'--locked','--offline','-p','ty_python_semantic','--message-format=json']+(['--test','mdtest','--no-run']if mode=='test'else [])
    rc=execute(f,W,['strace','-ff','-qq','-s','131072','-e','trace=execve','-o',q/'exec',*cmd],q/'stdout',q/'stderr')
    assert rc==0,(stage,mode,rc,(q/'stderr').read_text(errors='replace')[-3000:])
    data=[json.loads(l)for l in(q/'stdout').read_bytes().splitlines()if l.strip()];a=[d for d in data if d['reason']=='compiler-artifact'];msgs=[d['message']for d in data if d['reason']=='compiler-message'];process,raw=jobs(q);products=[]
    for row in a:
        target=row['target'];name=target['name']
        if src:=target['src_path']:
            if Path(src).is_relative_to(PK) and name in ('ty_python_semantic','mdtest'):
                for name_ in row['filenames']:
                    path=Path(name_)
                    if path.is_file():
                        products.append({'name':path.name,'bytes':path.stat().st_size,'hash':hashfile(path),'kind':target['kind'],'path':str(path)})
    result={'command':cmd,'status':rc,'artifacts':[len(a),sum(r['fresh']for r in a)],'fixture':hashfile(f),'diagnostics':[{'code':(r.get('code')or{}).get('code'),'message':r['message']}for r in msgs], 'output':products,'processes':process,'raw_exec_files':raw,'stdout_sha256':hashfile(q/'stdout'),'stderr_sha256':hashfile(q/'stderr')}
    save(q/'result.json',result);return result
def reader(f,stage,exe):
    q=Q/(stage+'-reader');q.mkdir();ls=q/'list.stdout'
    assert execute(f,PK,[exe,'--list'],ls,q/'list.stderr')==0
    names=[l.rsplit(': ',1)[0]for l in ls.read_text().splitlines()if l.endswith(': test') and re.search(r'(?:^|::|/)typed_dict[.]md: test',l)]
    assert len(names)==1,names
    args=['strace','-ff','-qq','-y','-s','2048','-e','trace=openat,read','-o',q/'file',exe,names[0],'--exact']
    rc=execute(f,PK,args,q/'read.stdout',q/'read.stderr');o=(q/'read.stdout').read_text();e=(q/'read.stderr').read_text();witness=[]
    for tf in sorted(q.glob('file.*')):
        if not tf.suffix[1:].isdigit():continue
        for l in tf.read_text(errors='replace').splitlines():
            if ('typed_dict.md' in l and re.search(r'(?:(?:^|/)typed_dict\.md|(?:^|[/\"])resources/mdtest/typed_dict\.md)',l)) and (l.startswith('openat(')or l.startswith('read(')):
                if l.startswith('openat('):witness.append({'kind':'open','status':l.rsplit(' = ',1)[-1],'sha256':hashlib.sha256(l.encode()).hexdigest()})
                else:witness.append({'kind':'read','bytes':l.rsplit(' = ',1)[-1],'sha256':hashlib.sha256(l.encode()).hexdigest()})
    rec={'status':rc,'fixture_hash':hashfile(f),'size':f.stat().st_size,'exe':hashfile(exe),'filter':names[0],'matched':['1 passed' in o,'0 failed' in o], 'list_sha256':hashfile(ls),'stdout':o,'stderr':e,'file_events':witness}
    save(q/'result.json',rec);assert rc==0 and all(rec['matched'])and any(x['kind']=='open' for x in witness)and any(x['kind']=='read' and x['bytes'].isdigit() and int(x['bytes'])>0 for x in witness),(rec['status'],rec['matched'],witness[:3],(o+e)[-600:]);return rec
with (P/'native-measure.lock').open('rb') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    r={'sdk':json.loads((D/'official16.json').read_text()) if (D/'official16.json').is_file()else {'cargo':hashfile(D/'sdk/bin/cargo'),'rustc':hashfile(D/'sdk/bin/rustc')},'source':I,'case':C,'floor':floor,'stages':{}}
    for stage,f0 in [('prime',W/F),('settled',W/F),('edit',repo/F),('restore',W/F)]:
        f=Q/(stage+'.md');shutil.copyfile(f0,f)
        if stage=='settled':f=Q/'prime.md'
        jobs_={m:cargo(f,stage,m)for m in ('build','test')}
        if stage!='prime':
            exe=next(Path(v['path'])for v in jobs_['test']['output']if v['kind']==['test'] and v['name'].startswith('mdtest-'))
            jobs_['reader']=reader(f,stage,exe)
        r['stages'][stage]=jobs_;save(Q/'partial.json',r)
    depfiles=[]; wanted={'ty_python_semantic','mdtest'}
    for prod in (v for stage in r['stages'].values() for m in ('build','test') for v in stage[m]['output']):
        pn=Path(prod['path']);dep=pn.with_suffix('.d')
        if pn.name.startswith('lib'):dep=pn.with_name(pn.name[3:]).with_suffix('.d')
        if dep.is_file() and dep.name not in {s['name']for s in depfiles}:
            data=dep.read_bytes();depfiles.append({'name':dep.name,'hash':hashfile(dep),'fixture_present':b'/resources/mdtest/typed_dict.md' in data,'rust_root_present':b'tests/mdtest.rs' in data or b'ty_python_semantic/src/lib.rs' in data})
    r['depfiles']=depfiles;r['minimum_free_bytes']=minimum;save(Q/'result.json',r);print(json.dumps(r))
