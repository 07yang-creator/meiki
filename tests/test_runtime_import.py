"""Vercel loads api/mei.py by file path, with api/ NOT on sys.path. On 2026-10-07 every /api/mei call answered 500
with `could not import "api/mei.py" … ModuleNotFoundError: No module named '_db'`, while `pytest` (which puts api/ on
the path) stayed green. Load the handler the way the runtime does — in a fresh interpreter, from the repo root, through
importlib — and ask it for health."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_handler_imports_the_way_vercel_loads_it():
    code = (
        "import importlib.util; "
        "spec = importlib.util.spec_from_file_location('vc__handler__python', %r); "
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
        "status, body = m.handle('health', {}); print(status, body['service'])"
    ) % os.path.join(ROOT, 'api', 'mei.py')
    env = {k: v for k, v in os.environ.items() if not k.startswith('SUPABASE_')}
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr[-800:]
    assert r.stdout.strip() == '200 mei'
