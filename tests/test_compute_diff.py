import pytest
import otj_server as srv


def test_no_notes_file_creates_and_returns_content(tmp_notes, monkeypatch):
    monkeypatch.setattr(srv, 'NOTES_FILE', str(tmp_notes))
    result = srv.compute_diff("line one\nline two\n")
    assert result == "line one\nline two\n"
    assert tmp_notes.read_text() == "line one\nline two\n"


def test_identical_content_returns_none(tmp_notes, monkeypatch):
    monkeypatch.setattr(srv, 'NOTES_FILE', str(tmp_notes))
    tmp_notes.write_text("line one\nline two\n")
    result = srv.compute_diff("line one\nline two\n")
    assert result is None


def test_new_lines_appended_returns_only_new(tmp_notes, monkeypatch):
    monkeypatch.setattr(srv, 'NOTES_FILE', str(tmp_notes))
    tmp_notes.write_text("line one\n")
    result = srv.compute_diff("line one\nline two\n")
    assert "line two\n" in result
    assert "line one" not in result


def test_modified_line_returns_new_version(tmp_notes, monkeypatch):
    monkeypatch.setattr(srv, 'NOTES_FILE', str(tmp_notes))
    tmp_notes.write_text("original line\n")
    result = srv.compute_diff("modified line\n")
    assert "modified line\n" in result


def test_content_removed_no_additions_returns_none(tmp_notes, monkeypatch):
    monkeypatch.setattr(srv, 'NOTES_FILE', str(tmp_notes))
    tmp_notes.write_text("line one\nline two\n")
    result = srv.compute_diff("line one\n")
    assert result is None


def test_empty_string_content(tmp_notes, monkeypatch):
    monkeypatch.setattr(srv, 'NOTES_FILE', str(tmp_notes))
    tmp_notes.write_text("something\n")
    result = srv.compute_diff("")
    assert result is None
