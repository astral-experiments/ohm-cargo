"""Exact frozen workload-template validator with only its need dependency."""
from types import SimpleNamespace

def need(condition, message):
    if not condition:
        raise AssertionError(message)

c = SimpleNamespace(need=need)

def validate_template(config, template):
    c.need({k: v for k, v in config.items() if k not in ('env', 'record_files')} ==
           {k: v for k, v in template.items() if k not in ('env', 'record_files')}, 'workload command/path changed')
    c.need(set(template['env']) <= set(config['env']) and
           all(config['env'][k] == v for k, v in template['env'].items()), 'configured environment changed')
    c.need(all(v is None for k, v in config['env'].items() if k not in template['env']), 'new inherited setting was not cleared')
    c.need(config['record_files'] == sorted(set(config['record_files'])), 'nonunique input closure')
