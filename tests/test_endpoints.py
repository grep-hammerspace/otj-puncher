import csv
import json
import pytest
from unittest.mock import MagicMock, patch
import anthropic

from tests.constants import CSV_HEADER, SAMPLE_ROW


# ---------------------------------------------------------------------------
# POST /log-activities
# ---------------------------------------------------------------------------

def test_log_activities_no_body(client):
    c, srv = client
    resp = c.post('/log-activities')
    assert resp.status_code in (400, 415)  # 415 when no Content-Type: application/json


def test_log_activities_missing_content_field(client):
    c, srv = client
    resp = c.post('/log-activities', json={})
    assert resp.status_code == 400


def test_log_activities_empty_content(client):
    c, srv = client
    resp = c.post('/log-activities', json={'content': '   '})
    assert resp.status_code == 400


def test_log_activities_same_content_no_new(client, tmp_notes):
    c, srv = client
    text = "line one\n"
    # Server strips content before storing/comparing, so prime notes with the stripped version
    tmp_notes.write_text(text.strip())
    resp = c.post('/log-activities', json={'content': text})
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'no new content'


def test_log_activities_new_content_writes_csv(client, tmp_csv, tmp_notes, monkeypatch):
    c, srv = client
    llm_row = {
        'date': '2026/04/30',
        'time-spent': '01:00',
        'start-time': '09:00',
        'comments': 'Did some reading.',
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps([llm_row]))]
    monkeypatch.setattr(srv.anthropic_client.messages, 'create', lambda **kw: mock_msg)

    resp = c.post('/log-activities', json={'content': 'new stuff\n'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['rows_added'] == 1

    with open(tmp_csv) as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2  # header + 1 data row
    assert tmp_notes.read_text() == 'new stuff'  # server strips trailing whitespace


def test_log_activities_missing_prompt_file(client, monkeypatch):
    c, srv = client
    monkeypatch.setattr(srv, 'PROMPT_FILE', '/nonexistent/llm_prompt.txt')
    resp = c.post('/log-activities', json={'content': 'some new content\n'})
    assert resp.status_code == 500


def test_log_activities_llm_returns_invalid_json(client, monkeypatch):
    c, srv = client
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='not json at all')]
    monkeypatch.setattr(srv.anthropic_client.messages, 'create', lambda **kw: mock_msg)
    resp = c.post('/log-activities', json={'content': 'some new content\n'})
    assert resp.status_code == 500


def test_log_activities_anthropic_auth_error(client, monkeypatch):
    c, srv = client

    def raise_auth(**kw):
        raise anthropic.AuthenticationError(message='bad key', response=MagicMock(), body={})

    monkeypatch.setattr(srv.anthropic_client.messages, 'create', raise_auth)
    resp = c.post('/log-activities', json={'content': 'some new content\n'})
    assert resp.status_code == 500


def test_log_activities_anthropic_rate_limit(client, monkeypatch):
    c, srv = client

    def raise_rate(**kw):
        raise anthropic.RateLimitError(message='rate limit', response=MagicMock(), body={})

    monkeypatch.setattr(srv.anthropic_client.messages, 'create', raise_rate)
    resp = c.post('/log-activities', json={'content': 'some new content\n'})
    assert resp.status_code == 429


def test_log_activities_llm_row_missing_key(client, monkeypatch):
    c, srv = client
    # Missing 'start-time' key
    bad_row = [{'date': '2026/04/30', 'time-spent': '01:00', 'comments': 'x'}]
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(bad_row))]
    monkeypatch.setattr(srv.anthropic_client.messages, 'create', lambda **kw: mock_msg)
    resp = c.post('/log-activities', json={'content': 'some new content\n'})
    assert resp.status_code == 500


def test_log_activities_all_error_rows_writes_nothing(client, tmp_csv, monkeypatch):
    c, srv = client
    llm_response = [
        {'error': 'missing_duration', 'message': 'No duration found in input', 'raw': 'did some work today'},
        {'error': 'missing_description', 'message': 'No activity description found in input', 'raw': '2 hours'},
    ]
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(llm_response))]
    monkeypatch.setattr(srv.anthropic_client.messages, 'create', lambda **kw: mock_msg)

    resp = c.post('/log-activities', json={'content': 'new content\n'})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['rows_added'] == 0
    assert data['rows'] == []
    assert len(data['parse_errors']) == 2
    assert data['parse_errors'][0]['error'] == 'missing_duration'
    assert 'duration' in data['parse_errors'][0]['message'].lower()
    assert data['parse_errors'][1]['error'] == 'missing_description'
    assert 'description' in data['parse_errors'][1]['message'].lower()

    with open(tmp_csv) as f:
        rows = list(csv.reader(f))
    assert rows == [CSV_HEADER]  # no data rows written


def test_log_activities_mixed_rows_writes_only_valid(client, tmp_csv, monkeypatch):
    c, srv = client
    valid_row = {
        'date': '2026/05/22',
        'time-spent': '2:00',
        'start-time': '10:00',
        'comments': 'Worked on IOT554 assignment',
        'posted': '',
    }
    llm_response = [
        valid_row,
        {'error': 'missing_duration', 'message': 'No duration found in input', 'raw': 'had a meeting'},
    ]
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(llm_response))]
    monkeypatch.setattr(srv.anthropic_client.messages, 'create', lambda **kw: mock_msg)

    resp = c.post('/log-activities', json={'content': 'new content\n'})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['rows_added'] == 1
    assert len(data['rows']) == 1
    assert data['rows'][0]['comments'] == 'Worked on IOT554 assignment'
    assert len(data['parse_errors']) == 1
    assert data['parse_errors'][0]['raw'] == 'had a meeting'

    with open(tmp_csv) as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2  # header + 1 valid row only
    assert rows[1][3] == 'Worked on IOT554 assignment'


# ---------------------------------------------------------------------------
# GET /prepare-browser
# ---------------------------------------------------------------------------

def test_prepare_browser_success(client, monkeypatch):
    c, srv = client
    monkeypatch.setattr(srv, 'prepare_browser', lambda: MagicMock())
    resp = c.get('/prepare-browser')
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'ready'


def test_prepare_browser_failure(client, monkeypatch):
    c, srv = client

    def explode():
        raise RuntimeError("geckodriver not found")

    monkeypatch.setattr(srv, 'prepare_browser', explode)
    resp = c.get('/prepare-browser')
    assert resp.status_code == 500


def test_prepare_browser_quits_old_driver(client, monkeypatch):
    c, srv = client
    old_driver = MagicMock()
    monkeypatch.setattr(srv, '_browser_driver', old_driver)
    monkeypatch.setattr(srv, 'prepare_browser', lambda: MagicMock())
    resp = c.get('/prepare-browser')
    assert resp.status_code == 200
    old_driver.quit.assert_called_once()


# ---------------------------------------------------------------------------
# POST /submit-otjs
# ---------------------------------------------------------------------------

def test_submit_otjs_no_body(client):
    c, srv = client
    resp = c.post('/submit-otjs')
    assert resp.status_code in (400, 415)  # 415 when no Content-Type: application/json


def test_submit_otjs_missing_mfa_code(client):
    c, srv = client
    resp = c.post('/submit-otjs', json={})
    assert resp.status_code == 400


def test_submit_otjs_browser_not_ready(client):
    c, srv = client
    resp = c.post('/submit-otjs', json={'mfa_code': '123456'})
    assert resp.status_code == 503


def test_submit_otjs_validation_error(client, monkeypatch):
    c, srv = client
    monkeypatch.setattr(srv, '_browser_driver', MagicMock())

    def raise_value(driver, code):
        raise ValueError("Row 2 invalid date")

    monkeypatch.setattr(srv, 'login_and_submit_otjs', raise_value)
    resp = c.post('/submit-otjs', json={'mfa_code': '123456'})
    assert resp.status_code == 400


def test_submit_otjs_unexpected_error(client, monkeypatch):
    c, srv = client
    monkeypatch.setattr(srv, '_browser_driver', MagicMock())

    def explode(driver, code):
        raise RuntimeError("something went wrong")

    monkeypatch.setattr(srv, 'login_and_submit_otjs', explode)
    resp = c.post('/submit-otjs', json={'mfa_code': '123456'})
    assert resp.status_code == 500


def test_submit_otjs_nothing_to_post(client, monkeypatch):
    c, srv = client
    monkeypatch.setattr(srv, '_browser_driver', MagicMock())
    monkeypatch.setattr(srv, 'login_and_submit_otjs',
                        lambda d, c: {"posted": [], "failed": [], "nothing_to_post": True})
    resp = c.post('/submit-otjs', json={'mfa_code': '123456'})
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'nothing_to_post'


def test_submit_otjs_all_posted(client, monkeypatch):
    c, srv = client
    monkeypatch.setattr(srv, '_browser_driver', MagicMock())
    monkeypatch.setattr(srv, 'login_and_submit_otjs',
                        lambda d, c: {"posted": [2, 3], "failed": [], "nothing_to_post": False})
    resp = c.post('/submit-otjs', json={'mfa_code': '123456'})
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'ok'


def test_submit_otjs_all_failed(client, monkeypatch):
    c, srv = client
    monkeypatch.setattr(srv, '_browser_driver', MagicMock())
    monkeypatch.setattr(srv, 'login_and_submit_otjs',
                        lambda d, c: {"posted": [], "failed": [{"row": 2}], "nothing_to_post": False})
    resp = c.post('/submit-otjs', json={'mfa_code': '123456'})
    assert resp.status_code == 502


def test_submit_otjs_partial(client, monkeypatch):
    c, srv = client
    monkeypatch.setattr(srv, '_browser_driver', MagicMock())
    monkeypatch.setattr(srv, 'login_and_submit_otjs',
                        lambda d, c: {"posted": [2], "failed": [{"row": 3}], "nothing_to_post": False})
    resp = c.post('/submit-otjs', json={'mfa_code': '123456'})
    assert resp.status_code == 207


# ---------------------------------------------------------------------------
# DELETE /reset-notes
# ---------------------------------------------------------------------------

def test_reset_notes_deletes_notes_and_clears_csv(client, tmp_notes, tmp_csv):
    c, srv = client
    tmp_notes.write_text("some notes\n")
    with open(tmp_csv, 'a', newline='') as f:
        csv.writer(f).writerow(SAMPLE_ROW)

    resp = c.delete('/reset-notes')
    assert resp.status_code == 200
    assert not tmp_notes.exists()

    with open(tmp_csv) as f:
        rows = list(csv.reader(f))
    assert rows == [CSV_HEADER]


def test_reset_notes_works_without_notes_file(client, tmp_csv):
    c, srv = client
    with open(tmp_csv, 'a', newline='') as f:
        csv.writer(f).writerow(SAMPLE_ROW)

    resp = c.delete('/reset-notes')
    assert resp.status_code == 200

    with open(tmp_csv) as f:
        rows = list(csv.reader(f))
    assert rows == [CSV_HEADER]


def test_reset_notes_csv_header_preserved(client, tmp_csv):
    c, srv = client
    resp = c.delete('/reset-notes')
    assert resp.status_code == 200
    with open(tmp_csv) as f:
        content = f.read()
    assert content.strip() == ','.join(CSV_HEADER)


# ---------------------------------------------------------------------------
# DELETE /clear-last-row
# ---------------------------------------------------------------------------

def test_clear_last_row_no_data_rows(client):
    c, srv = client
    resp = c.delete('/clear-last-row')
    assert resp.status_code == 400


def test_clear_last_row_single_row_removed(client, tmp_csv):
    c, srv = client
    with open(tmp_csv, 'a', newline='') as f:
        csv.writer(f).writerow(SAMPLE_ROW)

    resp = c.delete('/clear-last-row')
    assert resp.status_code == 200
    assert resp.get_json()['removed_row'] == SAMPLE_ROW

    with open(tmp_csv) as f:
        rows = list(csv.reader(f))
    assert rows == [CSV_HEADER]


def test_clear_last_row_only_last_of_many_removed(client, tmp_csv):
    c, srv = client
    row_a = ['2026/04/28', '01:00', '09:00', 'First.', '']
    row_b = ['2026/04/29', '02:00', '10:00', 'Second.', '']
    row_c = ['2026/04/30', '01:30', '12:00', 'Third.', '']
    with open(tmp_csv, 'a', newline='') as f:
        w = csv.writer(f)
        w.writerow(row_a)
        w.writerow(row_b)
        w.writerow(row_c)

    resp = c.delete('/clear-last-row')
    assert resp.status_code == 200
    assert resp.get_json()['removed_row'] == row_c

    with open(tmp_csv) as f:
        rows = list(csv.reader(f))
    assert rows == [CSV_HEADER, row_a, row_b]


def test_clear_last_row_removes_last_notes_line(client, tmp_csv, tmp_notes):
    c, srv = client
    with open(tmp_csv, 'a', newline='') as f:
        csv.writer(f).writerow(SAMPLE_ROW)
    tmp_notes.write_text("line one\nline two\nline three\n")

    resp = c.delete('/clear-last-row')
    assert resp.status_code == 200
    assert tmp_notes.read_text() == "line one\nline two\n"


def test_clear_last_row_single_notes_line_becomes_empty(client, tmp_csv, tmp_notes):
    c, srv = client
    with open(tmp_csv, 'a', newline='') as f:
        csv.writer(f).writerow(SAMPLE_ROW)
    tmp_notes.write_text("only line\n")

    resp = c.delete('/clear-last-row')
    assert resp.status_code == 200
    assert tmp_notes.read_text() == ""


def test_clear_last_row_no_notes_file_still_removes_csv_row(client, tmp_csv):
    c, srv = client
    with open(tmp_csv, 'a', newline='') as f:
        csv.writer(f).writerow(SAMPLE_ROW)

    resp = c.delete('/clear-last-row')
    assert resp.status_code == 200

    with open(tmp_csv) as f:
        rows = list(csv.reader(f))
    assert rows == [CSV_HEADER]
