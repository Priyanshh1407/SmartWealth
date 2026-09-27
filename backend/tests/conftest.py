import os
import tempfile
import importlib
from pathlib import Path


TEST_CHECKPOINT_PATH = (
    Path(tempfile.gettempdir())
    / f'smartwealth-pytest-{os.getpid()}.sqlite'
)
os.environ['CHECKPOINT_PATH'] = str(TEST_CHECKPOINT_PATH)
os.environ['RUN_STORAGE_MODE'] = 'durable'
os.environ.setdefault('OFFLINE_DEMO_MODE', 'true')
os.environ.setdefault('API_DELAY_SECONDS', '0')
def pytest_sessionfinish(session, exitstatus):
    try:
        graph_builder = importlib.import_module('backend.app.graph.builder')
        graph_builder.conn.close()
    except (ImportError, AttributeError):
        pass
    for suffix in ('', '-shm', '-wal'):
        Path(f'{TEST_CHECKPOINT_PATH}{suffix}').unlink(missing_ok=True)
