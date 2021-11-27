#!/usr/bin/env python
"""Module containing functionality to parse the AkaDressen from the AkaBlas homepage."""
import asyncio
import os
from enum import Enum
from logging import getLogger
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin
from uuid import uuid4

import numpy as np
import pandas as pd
import vobject
from camelot import read_pdf
from httpx import AsyncClient

from akadressen._data_parsers import (
    remove_whitespaces,
    year_to_int,
    expand_brunswick,
    string_to_date,
    phone_number,
    extract_names,
    extract_address,
)
from akadressen._util import check_response_status, string_to_instrument, ProgressLogger

_NAN = type(np.nan)
_logger = getLogger(__name__)


class _FileType(str, Enum):
    """All relevant types of AkaDressen files."""

    ACTIVE_MEMBERS = "latest_Akadressen-aktiv.pdf"
    MAIL_AND_PHONE = "latest_Email-%20und%20Telefonliste-aktiv.pdf"
    ALL_MEMBERS = "latest_Akadressen-aktivbisultrapassiv.pdf"


class _Const(str, Enum):
    """Constants to use in the handling of the dataframes."""

    FAMILY_NAME = "family_name"
    FULL_NAME = "full_name"
    GIVEN_NAME = "given_name"
    NICKNAME = "nickname"
    INSTRUMENT = "instrument"
    LANDLINE = "landline"
    MOBILE = "mobile"
    MAIL = "mail"
    ADDRESS = "address"
    DATE_OF_BIRTH = "date_of_birth"
    JOINED = "joined"
    PHONE = "phone"
    STREET = "street"
    HOUSE_NUMBER = "house_number"
    ADDITIONAL_ADDRESS_INFO = "additional_address_info"
    ZIP_CODE = "zip_code"
    CITY = "city"
    STATE = "state"


async def get_akadressen_vcards(
    base_url: str, username: str, password: str
) -> list[vobject.base.Component]:
    """Fetches the AkaDressen from the AkaBlas homepage, parses the data and returns the contacts
    as vCards.

    Args:
        base_url (:obj:`str`): Base URL of the AkaDressen files. File names will be added
            automatically.
        username (:obj:`str`): The username for login.
        password (:obj:`str`): The password for login.

    Returns:
        List[:class:`vobject.base.Component`]: The contacts as vCards.

    """
    _logger.debug("Downloading AkaDressen files")
    pdfs = await _download_akadressen(base_url=base_url, username=username, password=password)

    # Extract available data from the files
    _logger.debug("Processing Mail & Phone list.")
    base_table = _parse_mail_and_phone_list(pdfs[_FileType.MAIL_AND_PHONE])
    _logger.debug("Processing list of all members.")
    date_and_address = _parse_all_members(pdfs[_FileType.ALL_MEMBERS])
    _logger.debug("Processing list of active members.")
    joined = _parse_active_members(pdfs[_FileType.ACTIVE_MEMBERS])

    merged_table = base_table.merge(date_and_address, how="outer", on=_Const.FULL_NAME)
    merged_table = merged_table.merge(joined, how="outer", on=_Const.FULL_NAME)

    # replace np.Nan with None
    merged_table = merged_table.replace({np.nan: None})

    _logger.info("Transforming AkaDressen into vCards")
    progress_logger = ProgressLogger(
        _logger, len(merged_table), message="vCard %d of %d is ready."
    )
    return merged_table.apply(_row_to_card, axis=1, progress_logger=progress_logger).to_list()


async def _get(
    client: AsyncClient, base_url: str, file_name: _FileType
) -> tuple[_FileType, bytes]:
    response = await client.get(urljoin(base_url, file_name))
    check_response_status(response)
    return file_name, response.content


async def _download_akadressen(
    base_url: str, username: str, password: str
) -> dict[_FileType, bytes]:
    async with AsyncClient(
        auth=(username, password) if username and password else None,
        verify=True,
        headers={"User-Agent": "AkaDressen-Script"},
    ) as client:
        out = await asyncio.gather(*(_get(client, base_url, file_name) for file_name in _FileType))
        return {res[0]: res[1] for res in out if not isinstance(out, BaseException)}


def _row_to_card(row: pd.Series, progress_logger: ProgressLogger) -> vobject.base.Component:
    vcard = vobject.vCard()

    given = row[_Const.GIVEN_NAME] or ""
    family = row[_Const.FAMILY_NAME] or ""
    nickname = row[_Const.NICKNAME] or ""
    nickname_insertion = f" ({nickname})" if nickname else ""
    full_name = f"{given}{nickname_insertion} {family}"

    org = ["AkaBlas e.V."]
    if instrument := row[_Const.INSTRUMENT]:
        org.append(instrument)
    vcard.add("org").value = org

    joined = row[_Const.JOINED]
    if instrument and joined:
        vcard.add("note").value = f"Bei AkaBlas seit {int(joined)}. Spielt {instrument}."
    elif joined:
        vcard.add("note").value = f"Bei AkaBlas seit {int(joined)}"
    elif instrument:
        vcard.add("note").value = f"Spielt {instrument} bei AkaBlas."

    vcard.add("uid").value = str(uuid4())
    vcard.add("fn").value = full_name
    vcard.add("n").value = vobject.vcard.Name(
        family=family,
        given=given,
    )
    if nickname:
        vcard.add(_Const.NICKNAME).value = nickname
    if date_of_birth := row[_Const.DATE_OF_BIRTH]:
        vcard.add("bday").value = date_of_birth.strftime("%Y%m%d")
    if row[_Const.ADDRESS]:
        additional = row[_Const.ADDITIONAL_ADDRESS_INFO] or ""
        vcard.add("adr").value = vobject.vcard.Address(
            street=(row[_Const.STREET] or "") + (f"\n{additional}" if additional else ""),
            city=row[_Const.CITY] or "",
            code=row[_Const.ZIP_CODE] or "",
            country=row[_Const.STATE] or "",
            box=row[_Const.HOUSE_NUMBER] or "",
            extended=additional,
        )
    if email := row[_Const.MAIL]:
        vcard.add("email").value = email
        vcard.email.type_param = "INTERNET"

    mobile = row[_Const.MOBILE]
    landline = row[_Const.LANDLINE]
    # The list of all members shows the mobile number if no landline is available, so we make
    # an educated guess in case we read the same number to both
    if mobile == landline:
        if mobile.startswith("01"):
            landline = None
        else:
            mobile = None

    if mobile:
        vcard.add("tel").value = mobile
        vcard.contents["tel"][-1].type_param = "CELL"
    if landline:
        vcard.add("tel").value = landline
        vcard.contents["tel"][-1].type_param = "HOME"

    progress_logger.log()
    return vcard


def _pdf_to_dataframe(pdf: bytes) -> pd.DataFrame:
    # Currently, camelot can't read directly from bytes.
    # See https://github.com/camelot-dev/camelot/pull/270
    with NamedTemporaryFile(suffix=".pdf", delete=False) as file:
        file.write(pdf)
        file.close()
        tables = read_pdf(file.name, pages="all", flavor="stream")
        os.unlink(file.name)

    # Concatenate pages and return
    return pd.concat([table.df for table in tables])


def _parse_mail_and_phone_list(pdf: bytes) -> pd.DataFrame:
    """This file contains the most detailed info, so we extract from it

    * full name
    * mobile phone number
    * mail address

    and keep the full name so that we can merge the data.
    """
    # gives the columns names
    table = _pdf_to_dataframe(pdf).rename(
        columns={
            0: _Const.FULL_NAME,
            1: _Const.MAIL,
            2: _Const.LANDLINE,
            3: _Const.MOBILE,
            4: _Const.INSTRUMENT,
        }
    )
    # Drop empty lines
    table = table.replace(r"^\s*$", np.nan, regex=True)
    table = table.dropna(thresh=4)

    # Drop unnecessary columns
    table.drop([_Const.INSTRUMENT, _Const.LANDLINE], axis=1, inplace=True)

    # Process data
    table.loc[:, _Const.FULL_NAME] = table.loc[:, _Const.FULL_NAME].apply(remove_whitespaces)
    table.loc[:, _Const.MOBILE] = table.loc[:, _Const.MOBILE].apply(phone_number)

    return table


def _parse_all_members(pdf: bytes) -> pd.DataFrame:
    """This file contains not all data types but the ones that are present are there for the
    non-active members as well, so we extract

    * first, last & nickname
    * date of birth
    * address
    * landline phone number
    * instrument

    and keep the full name so that we can merge the data.
    """
    # gives the columns names
    table = _pdf_to_dataframe(pdf).rename(
        columns={
            0: _Const.FULL_NAME,
            1: _Const.ADDRESS,
            2: _Const.LANDLINE,
            3: _Const.DATE_OF_BIRTH,
            4: _Const.INSTRUMENT,
        }
    )
    # Drop empty lines
    table = table.replace(r"^\s*$", np.nan, regex=True)
    table = table.dropna(thresh=4)

    # Process data
    table.loc[:, _Const.FULL_NAME] = table.loc[:, _Const.FULL_NAME].apply(remove_whitespaces)
    table.loc[:, _Const.DATE_OF_BIRTH] = table.loc[:, _Const.DATE_OF_BIRTH].apply(string_to_date)
    table.loc[:, _Const.INSTRUMENT] = table.loc[:, _Const.INSTRUMENT].apply(string_to_instrument)
    table.loc[:, _Const.LANDLINE] = table.loc[:, _Const.LANDLINE].apply(phone_number)

    names_table = table.loc[:, _Const.FULL_NAME].apply(extract_names).apply(pd.Series)
    names_table.rename(
        columns={
            0: _Const.GIVEN_NAME,
            1: _Const.FAMILY_NAME,
            2: _Const.NICKNAME,
        },
        inplace=True,
    )
    table = pd.concat([table, names_table], axis=1)

    table.loc[:, _Const.ADDRESS] = table.loc[:, _Const.ADDRESS].apply(expand_brunswick)
    address_table = table.loc[:, _Const.ADDRESS].apply(extract_address).apply(pd.Series)
    address_table.rename(
        columns={
            0: _Const.STREET,
            1: _Const.HOUSE_NUMBER,
            2: _Const.ADDITIONAL_ADDRESS_INFO,
            3: _Const.ZIP_CODE,
            4: _Const.CITY,
            5: _Const.STATE,
        },
        inplace=True,
    )
    table = pd.concat([table, address_table], axis=1)

    return table


def _parse_active_members(pdf: bytes) -> pd.DataFrame:
    """In addition to the info from _parse_mail_and_phone_list, here we just extract

    * year someone joined

    and keep the full name so that we can merge the data.
    """
    # gives the columns names
    table = _pdf_to_dataframe(pdf).rename(
        columns={
            0: _Const.FULL_NAME,
            1: _Const.DATE_OF_BIRTH,
            2: _Const.ADDRESS,
            3: _Const.PHONE,
            4: _Const.INSTRUMENT,
            5: _Const.JOINED,
        }
    )
    # Drop empty lines
    table = table.replace(r"^\s*$", np.nan, regex=True)
    table = table.dropna(thresh=4)

    # Drop unnecessary columns
    table.drop(
        [_Const.DATE_OF_BIRTH, _Const.ADDRESS, _Const.PHONE, _Const.INSTRUMENT],
        axis=1,
        inplace=True,
    )

    # Process data
    table.loc[:, _Const.FULL_NAME] = table.loc[:, _Const.FULL_NAME].apply(remove_whitespaces)
    table.loc[:, _Const.JOINED] = table.loc[:, _Const.JOINED].apply(year_to_int)

    return table
