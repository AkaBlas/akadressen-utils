#!/usr/bin/env python
"""Module containing functionality to parse the AkaDressen from the AkaBlas homepage."""
from enum import Enum
from io import BytesIO
from logging import getLogger
from urllib.parse import urljoin
from uuid import uuid4

import numpy as np
import pandas as pd
import vobject
from httpx import AsyncClient

from akadressen._data_parsers import (
    remove_whitespaces,
    expand_brunswick,
    string_to_date,
    phone_number,
    year_from_date,
    split_city_state,
    parse_full_street,
)
from akadressen._util import check_response_status, string_to_instrument, ProgressLogger

_NAN = type(np.nan)
_logger = getLogger(__name__)


class Const(str, Enum):
    """Constants to use in the handling of the dataframes."""

    FAMILY_NAME = "family_name"
    FULL_NAME = "full_name"
    GIVEN_NAME = "given_name"
    NICKNAME = "nickname"
    INSTRUMENT = "instrument"
    LANDLINE = "landline"
    MOBILE = "mobile"
    MAIL = "mail"
    DATE_OF_BIRTH = "date_of_birth"
    JOINED = "joined"
    STREET = "street"
    HOUSE_NUMBER = "house_number"
    FULL_STREET = "full_street"
    ADDITIONAL_ADDRESS_INFO = "additional_address_info"
    ZIP_CODE = "zip_code"
    CITY = "city"
    CITY_STATE = "city_state"
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
    csv = await _download_akadressen(base_url=base_url, username=username, password=password)
    file_like_csv = BytesIO(csv)
    file_like_csv.seek(0)
    table = pd.read_csv(file_like_csv, sep=";", encoding="utf-8")

    # gives the columns proper names
    table = table.rename(
        # pylint: disable=no-member
        columns={
            table.columns[0]: Const.FAMILY_NAME,
            table.columns[1]: Const.GIVEN_NAME,
            table.columns[2]: Const.NICKNAME,
            table.columns[3]: Const.DATE_OF_BIRTH,
            table.columns[4]: Const.FULL_STREET,
            table.columns[5]: Const.ZIP_CODE,
            table.columns[6]: Const.CITY_STATE,
            table.columns[7]: Const.LANDLINE,
            table.columns[8]: Const.MOBILE,
            table.columns[9]: Const.MAIL,
            table.columns[10]: Const.INSTRUMENT,
            table.columns[11]: Const.JOINED,
        }
    )

    # Extract available data from the files
    _logger.debug("Processing file.")

    # replace np.Nan with None
    table = table.replace({np.nan: None})

    table.loc[:, Const.FAMILY_NAME] = table.loc[:, Const.FAMILY_NAME].apply(remove_whitespaces)
    table.loc[:, Const.GIVEN_NAME] = table.loc[:, Const.GIVEN_NAME].apply(remove_whitespaces)
    table.loc[:, Const.NICKNAME] = table.loc[:, Const.NICKNAME].apply(remove_whitespaces)
    table.loc[:, Const.DATE_OF_BIRTH] = table.loc[:, Const.DATE_OF_BIRTH].apply(string_to_date)
    table.loc[:, Const.LANDLINE] = table.loc[:, Const.LANDLINE].apply(phone_number)
    table.loc[:, Const.FULL_STREET] = table.loc[:, Const.FULL_STREET].apply(remove_whitespaces)
    table.loc[:, Const.CITY_STATE] = (
        table.loc[:, Const.CITY_STATE].apply(remove_whitespaces).apply(expand_brunswick)
    )
    table.loc[:, Const.MOBILE] = (
        table.loc[:, Const.MOBILE].apply(remove_whitespaces).apply(phone_number)
    )
    table.loc[:, Const.INSTRUMENT] = (
        table.loc[:, Const.INSTRUMENT].apply(remove_whitespaces).apply(string_to_instrument)
    )
    table.loc[:, Const.JOINED] = (
        table.loc[:, Const.JOINED]
        .apply(remove_whitespaces)
        .apply(string_to_date)
        .apply(year_from_date)
    )

    # replace np.Nan with None again - for some reason that's needed
    table = table.replace({np.nan: None})

    city_state_table = table.loc[:, Const.CITY_STATE].apply(split_city_state).apply(pd.Series)
    city_state_table = city_state_table.rename(columns={0: Const.CITY, 1: Const.STATE})
    table = pd.concat([table, city_state_table], axis=1)

    street_number_table = table.loc[:, Const.FULL_STREET].apply(parse_full_street).apply(pd.Series)
    street_number_table = street_number_table.rename(
        columns={0: Const.STREET, 1: Const.HOUSE_NUMBER, 2: Const.ADDITIONAL_ADDRESS_INFO}
    )
    table = pd.concat([table, street_number_table], axis=1)

    _logger.info("Transforming AkaDressen into vCards")
    progress_logger = ProgressLogger(_logger, len(table), message="vCard %d of %d is ready.")
    return table.apply(_row_to_card, axis=1, progress_logger=progress_logger).to_list()


async def _get(client: AsyncClient, base_url: str, file_name: str) -> bytes:
    response = await client.get(urljoin(base_url, f"latest_{file_name}"))
    check_response_status(response)
    return response.content


async def _download_akadressen(base_url: str, username: str, password: str) -> bytes:
    async with AsyncClient(
        auth=(username, password) if username and password else None,
        verify=True,
        headers={"User-Agent": "AkaDressen-Script"},
    ) as client:
        return await _get(client, base_url, "Akadressen_CSV.csv")


def _row_to_card(row: pd.Series, progress_logger: ProgressLogger) -> vobject.base.Component:
    vcard = vobject.vCard()

    given = row[Const.GIVEN_NAME] or ""
    family = row[Const.FAMILY_NAME] or ""
    nickname = row[Const.NICKNAME] or ""
    nickname_insertion = f" ({nickname})" if nickname else ""
    full_name = f"{given}{nickname_insertion} {family}"

    org = ["AkaBlas e.V."]
    if instrument := row[Const.INSTRUMENT]:
        org.append(instrument)
    vcard.add("org").value = org

    joined = row[Const.JOINED]
    if instrument and joined:
        vcard.add("note").value = f"Bei AkaBlas seit {int(joined)}. Spielt {instrument}."
    elif joined:
        vcard.add("note").value = f"Bei AkaBlas seit {int(joined)}"
    elif instrument:
        vcard.add("note").value = f"Spielt {instrument} bei AkaBlas."

    vcard.add("uid").value = uuid4().hex
    vcard.add("fn").value = full_name
    vcard.add("n").value = vobject.vcard.Name(
        family=family,
        given=given,
    )
    if nickname:
        vcard.add(Const.NICKNAME).value = nickname
    if date_of_birth := row[Const.DATE_OF_BIRTH]:
        vcard.add("bday").value = date_of_birth.strftime("%Y-%m-%d")
    if row[Const.FULL_STREET]:
        additional = row[Const.ADDITIONAL_ADDRESS_INFO] or ""
        vcard.add("adr").value = vobject.vcard.Address(
            street=(row[Const.STREET] or "") + (f"\n{additional}" if additional else ""),
            city=row[Const.CITY] or "",
            code=str(int(row[Const.ZIP_CODE])) if row[Const.ZIP_CODE] else "",
            country=row[Const.STATE] or "",
            box=row[Const.HOUSE_NUMBER] or "",
            extended=additional,
        )
    if email := row[Const.MAIL]:
        vcard.add("email").value = email
        vcard.email.type_param = "INTERNET"

    mobile = row[Const.MOBILE]
    landline = row[Const.LANDLINE]

    if mobile:
        vcard.add("tel").value = mobile
        vcard.contents["tel"][-1].type_param = "CELL"
    if landline:
        vcard.add("tel").value = landline
        vcard.contents["tel"][-1].type_param = "HOME"

    progress_logger.log()
    return vcard
