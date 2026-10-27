from pathlib import Path
import json,os,resource,subprocess,sys,time
d=Path(sys.argv[1]); timed=sys.argv[2]=="1"; argv=sys.argv[3:]
with (d/"stdout").open("xb") as f,(d/"stderr").open("xb") as e:
    begin=time.monotonic_ns() if timed else None
    p=subprocess.run(argv,stdout=f,stderr=e)
    duration=time.monotonic_ns()-begin if timed else None
u=resource.getrusage(resource.RUSAGE_CHILDREN)
(d/"child.json").write_text(json.dumps({"exit":p.returncode,"wall_ns":duration,"cpu_user_s":u.ru_utime if timed else None,"cpu_system_s":u.ru_stime if timed else None,"faults_minor":u.ru_minflt,"faults_major":u.ru_majflt,"voluntary_switches":u.ru_nvcsw,"involuntary_switches":u.ru_nivcsw,"input_blocks":u.ru_inblock,"output_blocks":u.ru_oublock,"rss_kib":u.ru_maxrss,"affinity":sorted(os.sched_getaffinity(0)),"argv":argv},indent=2)+"\n")
sys.exit(p.returncode)
