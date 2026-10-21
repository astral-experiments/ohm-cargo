assert status['integrity_complete'] == ['check', 'test']
status.update(state='both workflows passed integrity', quiet=ref.quiet())
core.atomic_json(phase_status(phase), status)
for workflow, _ in STAGES[phase]['plan']:
    output = paths(phase, workflow)['output']
    with (output / 'analysis-stdout.json').open('x') as stream:
        subprocess.run([sys.executable, '-I', '-B', str(runner), 'analyze', str(output), '--confidence', '.99', '--resamples', '20000', '--seed', '1701', '--minimum-pairs', str(STAGES[phase]['pairs'])], stdout=stream, check=True)
    result = gate(phase, output)
    core.atomic_json(output / 'gate.json', result)
    status['completed'].append({'workflow': workflow, 'directory': str(output), **result})
    core.atomic_json(phase_status(phase), status)
verify_seal(expected_seal)
status.update(state='complete', completed_at=core.utc_now(), quiet=ref.quiet(), uv=ref.uv_identity(), both_workflows_pass=all((row['passes_gate'] for row in status['completed'])), significant_native_regression=any((row['significant_native_regression'] for row in status['completed'])))
core.atomic_json(phase_status(phase), status)
