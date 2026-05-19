import math
import pytest
import pandas as pd
from puncher import (
    check_non_empty_or_whitespace,
    validate_date,
    validate_time_spent,
    validate_start_time,
)


# --- check_non_empty_or_whitespace ---

def test_all_fields_populated_ok():
    row = pd.Series(['2026/04/30', '01:00', '09:00', 'Did reading.'])
    check_non_empty_or_whitespace(row, 0)  # should not raise


def test_empty_string_raises():
    row = pd.Series(['2026/04/30', '', '09:00', 'Did reading.'])
    with pytest.raises(ValueError, match="mandatory field"):
        check_non_empty_or_whitespace(row, 0)


def test_whitespace_only_raises():
    row = pd.Series(['2026/04/30', '  ', '09:00', 'Did reading.'])
    with pytest.raises(ValueError, match="mandatory field"):
        check_non_empty_or_whitespace(row, 0)


def test_nan_raises():
    row = pd.Series(['2026/04/30', float('nan'), '09:00', 'Did reading.'])
    with pytest.raises(ValueError, match="mandatory field"):
        check_non_empty_or_whitespace(row, 0)


# --- validate_date ---

def test_valid_date_ok():
    validate_date('2026/04/30', 0)  # should not raise


def test_date_wrong_separator_raises():
    with pytest.raises(ValueError, match="YYYY/MM/DD"):
        validate_date('2026-04-30', 0)


def test_date_wrong_order_raises():
    with pytest.raises(ValueError, match="YYYY/MM/DD"):
        validate_date('30/04/2026', 0)


def test_date_garbage_raises():
    with pytest.raises(ValueError, match="YYYY/MM/DD"):
        validate_date('not-a-date', 0)


# --- validate_time_spent ---

def test_valid_time_spent_ok():
    validate_time_spent('09:00', 0)  # should not raise


def test_time_spent_out_of_range_raises():
    with pytest.raises(ValueError, match="HH:MM"):
        validate_time_spent('25:00', 0)


def test_time_spent_garbage_raises():
    with pytest.raises(ValueError, match="HH:MM"):
        validate_time_spent('9am', 0)


# --- validate_start_time ---

def test_valid_start_time_ok():
    validate_start_time('13:30', 0)  # should not raise


def test_start_time_out_of_range_raises():
    with pytest.raises(ValueError, match="HH:MM"):
        validate_start_time('25:00', 0)


def test_start_time_garbage_raises():
    with pytest.raises(ValueError, match="HH:MM"):
        validate_start_time('9am', 0)
