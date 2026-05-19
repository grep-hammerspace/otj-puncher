import csv
import sys
import os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests.constants import CSV_HEADER


@pytest.fixture
def tmp_csv(tmp_path):
    f = tmp_path / 'otjs.csv'
    with open(f, 'w', newline='') as fh:
        csv.writer(fh).writerow(CSV_HEADER)
    return f


@pytest.fixture
def tmp_notes(tmp_path):
    return tmp_path / 'notes.txt'


@pytest.fixture
def tmp_prompt(tmp_path):
    f = tmp_path / 'llm_prompt.txt'
    f.write_text('You are a helpful assistant.')
    return f


@pytest.fixture
def client(tmp_csv, tmp_notes, tmp_prompt, monkeypatch):
    import otj_server as srv
    monkeypatch.setattr(srv, 'NOTES_FILE', str(tmp_notes))
    monkeypatch.setattr(srv, 'OTJ_CSV', str(tmp_csv))
    monkeypatch.setattr(srv, 'PROMPT_FILE', str(tmp_prompt))
    monkeypatch.setattr(srv, '_browser_driver', None)
    srv.app.config['TESTING'] = True
    with srv.app.test_client() as c:
        yield c, srv
