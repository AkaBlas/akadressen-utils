#!/usr/bin/env python
# pylint: disable=missing-function-docstring
"""Module containing utility functionality to parse the data from the AkaDressen."""
import datetime

# Mostly copied from https://github.com/Bibo-Joshi/AkaNamen-Bot/blob/master/components/member.py
import re
from typing import NamedTuple, Optional, Union, overload

import dateutil.parser

_NAN = float  # = type(np.nan)


class _DEPerserInfo(dateutil.parser.parserinfo):
    MONTHS = [
        ("Jan", "January"),
        ("Feb", "February"),
        ("Mar", "March", "Mrz"),  # type: ignore[list-item]
        ("Apr", "April"),
        ("May", "May", "Mai"),  # type: ignore[list-item]
        ("Jun", "June"),
        ("Jul", "July"),
        ("Aug", "August"),
        ("Sep", "Sept", "September"),  # type: ignore[list-item]
        ("Oct", "October", "Okt"),  # type: ignore[list-item]
        ("Nov", "November"),
        ("Dec", "December", "Dez"),  # type: ignore[list-item]
    ]


def string_to_date(string: Union[str, _NAN, None]) -> Optional[datetime.date]:
    if isinstance(string, _NAN) or string is None:
        return None

    out = dateutil.parser.parse(string, parserinfo=_DEPerserInfo()).date()
    if out.year > datetime.datetime.now().year:
        out = out.replace(year=out.year - 100)
    return out


def year_from_date(date: Optional[datetime.date]) -> Optional[int]:
    if isinstance(date, _NAN) or date is None:
        return None
    return date.year


@overload
def remove_whitespaces(string: str) -> str:
    ...


@overload
def remove_whitespaces(string: Union[_NAN, None]) -> None:
    ...


def remove_whitespaces(string: Union[str, _NAN, None]) -> Optional[str]:
    if isinstance(string, _NAN) or string is None:
        return None

    return string.strip()


def expand_brunswick(address: Union[str, _NAN, None]) -> Optional[str]:
    if isinstance(address, _NAN) or address is None:
        return None

    address = remove_whitespaces(address)
    return address.replace("BS", "Braunschweig")


def phone_number(string: Union[str, _NAN, None]) -> Optional[str]:
    if isinstance(string, _NAN) or string is None:
        return None
    # Make an educated guess on when we're in brunswick …
    if (first_char := string[0]).isdigit() and first_char != "0":
        return f"0531/{string}"
    return string


def split_city_state(string: Union[str, _NAN, None]) -> tuple[Optional[str], Optional[str]]:
    if isinstance(string, _NAN) or string is None:
        return None, None

    if "," not in string:
        return (string, None)

    city, state = string.split(",", maxsplit=1)
    return city.strip(), state.strip()


class _FullStreet(NamedTuple):
    street: Optional[str] = None
    house_number: Optional[str] = None
    additional: Optional[str] = None


_FULL_STREET_PATTERN = re.compile(
    # Match the street: Neither `,` nor digits. Negative lookbehind for trailing whitespace
    r"^(((?P<street>[^,\d]+(?<! ))"
    # Followed by one or more whitespaces
    r" +"
    # House number: starts with a digit, rest doesn't matter - just not a `,`
    r"(?P<house_number>\d[^,]*))"
    # Alternatively street and house number may be swapped
    r"|((?P<house_number1>\d[^, ]*(?<! )) +(?P<street1>[^,\d]+)))"
    # Optional: additional info before the next comma, e.g. room number
    r"(, *(?P<additional>[^,]+))?"
)


def parse_full_street(string: Optional[str]) -> _FullStreet:
    if not string:
        return _FullStreet()

    if match := _FULL_STREET_PATTERN.match(string):
        full_street = match.groupdict()

        street1 = full_street.pop("street1")
        full_street["street"] = full_street["street"] or street1

        house_number1 = full_street.pop("house_number1")
        full_street["house_number"] = full_street["house_number"] or house_number1

        return _FullStreet(**full_street)

    # # If the pattern doesn't match, we make a best effort guess ...
    # parts = [part.strip() for part in string.split(",", maxsplit=2)]
    # if len(parts) >= 2:
    #     street = parts[0]
    #     city = parts[1]
    #     state = parts[2] if len(parts) >= 3 else None
    #     return _FullStreet(street=street)

    # or just fall back to putting everything as the street ...
    return _FullStreet(street=string)
