import sqlite3
import threading
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.mark.parametrize('backend', ['sqlite', 'mysql'])
@pytest.mark.parametrize('failure', [None, 'connect', 'query'])
def test_warmup_does_not_block_startup(tmp_path, monkeypatch, caplog, backend, failure):
    app = create_app(tmp_path / 'warmup.sqlite3')
    assert app.state.store.connect == app.state.store.base.connect
    entered, release = threading.Event(), threading.Event()
    workers = []
    connection = MagicMock(spec=sqlite3.Connection if backend == 'sqlite' else ['cursor'])
    execute = connection.execute if backend == 'sqlite' else connection.cursor.return_value.__enter__.return_value.execute
    if failure == 'query':
        execute.side_effect = RuntimeError('warmup query unavailable')

    def connect():
        workers.append(threading.current_thread())
        entered.set()
        assert release.wait(5), 'startup waited for warmup'
        if failure == 'connect':
            raise RuntimeError('warmup connect unavailable')
        context = MagicMock()
        context.__enter__.return_value = connection
        return context

    monkeypatch.setattr(app.state.store, 'connect', connect)
    try:
        with TestClient(app) as client:
            assert entered.wait(2)
            assert workers[0].daemon and workers[0].is_alive()
            assert client.get('/').status_code == 200
            release.set()
            workers[0].join(2)
            assert not workers[0].is_alive()
            assert client.get('/').status_code == 200
    finally:
        release.set()
        for worker in workers:
            worker.join(2)  # Only the test waits; application startup/shutdown must not.
            assert not worker.is_alive()
    if failure != 'connect':
        execute.assert_called_once_with('SELECT 1')
    assert ('Database warmup failed' in caplog.text) == bool(failure)
