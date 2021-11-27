#!/usr/bin/env python
# pylint: disable=missing-function-docstring
"""Module containing utility functionality to parse the data from the AkaDressen."""
# Mostly copied from https://github.com/Bibo-Joshi/AkaNamen-Bot/blob/master/components/member.py
import re
import datetime
from typing import Union, Optional, NamedTuple, Pattern, overload

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


def string_to_date(string: Union[str, _NAN]) -> Optional[datetime.date]:
    if isinstance(string, _NAN):
        return None

    out = dateutil.parser.parse(string, parserinfo=_DEPerserInfo()).date()
    if out.year >= datetime.datetime.now().year:
        out = out.replace(year=out.year - 100)
    return out


def year_to_int(string: Union[str, _NAN]) -> Optional[int]:
    if isinstance(string, _NAN):
        return None
    out = datetime.datetime.strptime(string, "%y").date()
    if out.year > datetime.datetime.now().year:
        out = out.replace(year=out.year - 100)
    return out.year


_LEADING_WHITESPACE_PATTERN: Pattern = re.compile(r"\b(?=\w)(\w) (\w)")
_TRAILING_WHITESPACE_PATTERN: Pattern = re.compile(r"(\w) ([^0-9])\b(?<=\w)")


@overload
def remove_whitespaces(string: str) -> str:
    ...


@overload
def remove_whitespaces(string: _NAN) -> None:
    ...


def remove_whitespaces(string: Union[str, _NAN]) -> Optional[str]:
    if isinstance(string, _NAN):
        return None

    string = re.sub(_LEADING_WHITESPACE_PATTERN, r"\g<1>\g<2>", string)
    return re.sub(_TRAILING_WHITESPACE_PATTERN, r"\g<1>\g<2>", string)


_NICK_NAME_PATTERN = re.compile(r"([^\)]+)\(")
_GIVEN_NAME_PATTERN = re.compile(r"\(([^\)]+)\)")


def extract_names(string: str) -> tuple[str, str, Optional[str]]:
    # First, get the nickname, if present
    nickname_match = _NICK_NAME_PATTERN.match(string)
    nickname = nickname_match.group(1).strip() if nickname_match else None

    # If we have a nickname, getting first and last name is easy
    if "(" in string:
        match = _GIVEN_NAME_PATTERN.search(string)
        if not match:
            raise RuntimeError("Something when wrong applying a regex pattern.")
        given_name = match.group(1)
        family_name = string.split(")")[-1]

    # If we don't, things are more complicated:
    # First-Second Last  # doable
    # First Last-SecondLast  # doable
    # First Last with Multiple Names  # harder
    # First SecondFirst Last  # harder
    # We use the following rule:
    # If all words are capitalized, we assume the last name to the last word only
    # If some words are lower case, we assume the last name to start with the last capitalized word
    # that comes right before the first lowercase word
    else:
        names = string.split()
        if all(name.isupper() for name in names):
            family_name = names[-1]
            given_name = string.rsplit(maxsplit=1)[0]
        else:
            idx = 0
            for idx, name in enumerate(names):
                if name.islower():
                    idx = idx - 1
                    break
            given_name = " ".join(names[:idx])
            family_name = " ".join(names[idx:])

    given_name = given_name.strip()
    family_name = family_name.strip()

    return given_name, family_name, nickname


def expand_brunswick(address: Union[str, _NAN]) -> Optional[str]:
    if isinstance(address, _NAN):
        return None

    address = remove_whitespaces(address)
    return address.replace("BS", "Braunschweig")


def phone_number(string: Union[str, _NAN]) -> Optional[str]:
    if isinstance(string, _NAN):
        return None
    # Make an educated guess on when we're in brunswick …
    if (first_char := string[0]).isdigit() and first_char != "0":
        return f"0531/{string}"
    return string


class _Address(NamedTuple):
    street: Optional[str] = None
    house_number: Optional[str] = None
    additional: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


_ADDRESS_PATTERN = re.compile(
    # Match the street: Neither `,` nor digits. Negative lookbehind for trailing whitespace
    r"^(((?P<street>[^,\d]+(?<! ))"
    # Followed by one or more whitespaces
    r" +"
    # House number: starts with a digit, rest doesn't matter - just not a `,`
    r"(?P<house_number>\d[^,]*))"
    # Alternatively street and house number may be swapped
    r"|((?P<house_number1>\d[^, ]*(?<! )) +(?P<street1>[^,\d]+)))"
    # r")"
    # `,` and optional whitespaces for separation
    ", *"
    # Optional: additional info before the next comma, e.g. room number
    r"((?P<additional>[^,]+), *)?"
    # 5 digit zip code and the city name
    r"(?P<zip_code>\d{5}) *(?P<city>[^,]+)"
    # Optinally state/country
    r"(, *(?P<state>.*))?"
)


def extract_address(string: Optional[str]) -> _Address:
    if not string:
        return _Address()

    if match := _ADDRESS_PATTERN.match(string):
        address = match.groupdict()

        street1 = address.pop("street1")
        address["street"] = address["street"] or street1

        house_number1 = address.pop("house_number1")
        address["house_number"] = address["house_number"] or house_number1

        return _Address(**address)

    # If the pattern doesn't match, we make a best effort guess ...
    parts = [part.strip() for part in string.split(",", maxsplit=2)]
    if len(parts) >= 2:
        street = parts[0]
        city = parts[1]
        state = parts[2] if len(parts) >= 3 else None
        return _Address(street=street, city=city, state=state)

    # or just fall back to putting everything as the street ...
    return _Address(street=string)
