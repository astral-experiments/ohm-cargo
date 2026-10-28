"""Apply a diagnostic-only trace to the unmodified -18 Cargo release parent."""
from pathlib import Path
import sys
root=Path(sys.argv[1]);file=root/'src/compiler/job_queue/mod.rs';s=file.read_text()
def one(a,b):
    global s
    assert s.count(a)==1,a
    s=s.replace(a,b)
one("impl<'gctx> DrainState<'gctx> {",'''// Private native-scheduler diagnostic. No scheduling rule or cost is changed.
fn trace_queue(event: serde_json::Value) {
    use std::sync::{Mutex, OnceLock};
    use std::io::Write;
    static SINK: OnceLock<Option<Mutex<std::fs::File>>> = OnceLock::new();
    let sink = SINK.get_or_init(|| std::env::var_os("OHM_QUEUE_DIAGNOSTIC")
        .map(|p| Mutex::new(std::fs::OpenOptions::new().create_new(true).write(true).open(p).unwrap())));
    if let Some(sink) = sink {
        let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() as u64;
        writeln!(sink.lock().unwrap(), "{}", serde_json::json!([t,event])).unwrap();
    }
}

fn diagnostic_finish<'q>(
    queue: &'q mut DependencyQueue<Unit, Artifact, Job>,
    unit: &Unit,
    artifact: &Artifact,
    runner: &BuildRunner<'_, '_>,
) -> Vec<&'q Unit> {
    let newly = queue.finish(unit, artifact);
    trace_queue(serde_json::json!(["edge", runner.bcx.unit_to_index[unit], format!("{artifact:?}"),
        newly.iter().map(|u| runner.bcx.unit_to_index[*u]).collect::<Vec<_>>()]));
    newly
}

impl<'gctx> DrainState<'gctx> {''')
old='        self.queue.queue(unit.clone(), job, queue_deps, 100);'
one(old,'''        let observed: Vec<_> = if unit.is_local() && unit.requires_upstream_objects() && !unit.mode.is_run_custom_build() {
            build_runner.outputs(unit).ok().into_iter().flat_map(|a| {
                a.iter().map(|o| {
                    let meta = std::fs::symlink_metadata(&o.path);
                    serde_json::json!([o.path, format!("{:?}",o.flavor), meta.as_ref().ok().filter(|m| m.is_file()).map(|m| m.len()),
                        meta.as_ref().err().map(|e| e.raw_os_error()), meta.as_ref().ok().is_some_and(|m|m.is_symlink())])
                }).collect::<Vec<_>>()
            }).collect()
        } else { Vec::new() };
        trace_queue(serde_json::json!(["register", build_runner.bcx.unit_to_index[unit],
            unit.pkg.name().as_str(), unit.target.name(), format!("{:?}", unit.mode), format!("{:?}", unit.target.kind()),
            job.freshness().is_dirty(), queue_deps.iter().map(|(u,e)| (build_runner.bcx.unit_to_index[u],format!("{e:?}"))).collect::<Vec<_>>(),observed]));
'''+old)
one('        self.queue.queue_finished();','        self.queue.queue_finished();\n        trace_queue(serde_json::json!(["initial"]));')
one('            self.pending_queue.insert(idx, (unit, job, priority));','''            trace_queue(serde_json::json!(["dequeue", build_runner.bcx.unit_to_index[&unit],priority,idx,self.active.len(),self.tokens.len()+1]));
            self.pending_queue.insert(idx, (unit, job, priority));''')
one('            let (unit, job, _) = self.pending_queue.pop().unwrap();','''            let (unit, job, priority) = self.pending_queue.pop().unwrap();
            trace_queue(serde_json::json!(["service", build_runner.bcx.unit_to_index[&unit],priority,self.active.len(),self.tokens.len()+1,self.pending_queue.len(),self.next_id]));''')
one('            Message::Run(id, cmd) => {','''            Message::Run(id, cmd) => {
                trace_queue(serde_json::json!(["process",build_runner.bcx.unit_to_index[&self.active[&id]],id.0]));''')
import re
s,n=re.subn(r'self\.queue\.finish\(([^,;]+), ([^;]+?)\);',r'diagnostic_finish(&mut self.queue, \1, \2, build_runner);',s)
assert n==4,n
file.write_text(s)
