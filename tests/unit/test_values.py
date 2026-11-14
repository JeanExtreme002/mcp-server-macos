"""What pymacos reads from macOS, as JSON can carry it."""

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from mcp_server_macos._values import plain


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        (True, True),
        (3, 3),
        (2.5, 2.5),
        ("héllo", "héllo"),
        (datetime(2026, 11, 14, 8, 37, 14), "2026-11-14T08:37:14"),
        (datetime(2026, 11, 14, 8, 37, 14, tzinfo=timezone.utc), "2026-11-14T08:37:14+00:00"),
        (date(2026, 11, 14), "2026-11-14"),
        (time(8, 37), "08:37:00"),
        (timedelta(minutes=1, seconds=30.5), 90.5),
        (Path("/Users/me/a b.txt"), "/Users/me/a b.txt"),
        (b"\x00\x01\xff", "AAH/"),
        (bytearray(b"hi"), "aGk="),
        ((1, "two", 3.0), [1, "two", 3.0]),
        ([], []),
        ({}, {}),
        ({1: "one", "two": 2}, {"1": "one", "two": 2}),
    ],
)
def test_plain(value: Any, expected: Any) -> None:
    assert plain(value) == expected
    json.dumps(plain(value))


def test_plain_goes_all_the_way_down() -> None:
    value = {
        "kMDItemAuthors": ("Ana", "Bo"),
        "kMDItemContentCreationDate": datetime(2026, 1, 2, 3, 4, 5),
        "nested": [{"icon": b"\x89PNG", "where": Path("/tmp")}, {3, 3}],
    }

    assert plain(value) == {
        "kMDItemAuthors": ["Ana", "Bo"],
        "kMDItemContentCreationDate": "2026-01-02T03:04:05",
        "nested": [{"icon": "iVBORw==", "where": "/tmp"}, [3]],
    }


def test_plain_keeps_true_apart_from_one() -> None:
    # A preference set to true must not come back as 1, nor 1 as true.
    assert plain([True, 1, 1.0]) == [True, 1, 1.0]
    assert [type(item) for item in plain([True, 1, 1.0])] == [bool, int, float]


def test_plain_of_something_unknown_is_its_text() -> None:
    assert plain(complex(1, 2)) == "(1+2j)"
