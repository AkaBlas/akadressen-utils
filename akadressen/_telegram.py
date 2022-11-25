#!/usr/bin/env python
"""A module containing functionality to retrieve profile pictures from Telegram based on the
phone number. """
import asyncio
from collections.abc import Sequence
from logging import getLogger
from typing import BinaryIO, Union, cast

import vobject.base
from pyrogram import Client

from akadressen._util import ProgressLogger

_logger = getLogger(__name__)


async def _add_photo_to_vcard(
    vcard: vobject.base.Component,
    photo_id: str,
    client: Client,
    progress_logger: ProgressLogger,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        if vcard.contents.get("photo"):
            return

        # Apparently pyrogram has no functionality to download directly to bytes
        file_like = await client.download_media(photo_id, in_memory=True)
        file_like = cast(BinaryIO, file_like)

        photo = vcard.add("photo")
        photo.encoding_param = "B"
        photo.type_param = "JPG"
        photo.value = file_like.read()

        progress_logger.log()


async def add_telegram_profile_pictures_to_vcards(
    api_id: Union[int, str],
    api_hash: str,
    vcards: Sequence[vobject.base.Component],
    session_name: str,
) -> None:
    """Adds profile pictures to all vCards that can be found on Telegram. Requires you to log in
    with your Telegram credentials.

    Args:
        api_id (:obj:`int` | :obj:`str`): The API ID from my.telegram.org.
        api_hash (:obj:`str`): The API Hash from my.telegram.org.
        vcards (List[:class:`vobject.base.Component`]): The vcards. Will be ideted in place.
        session_name (:obj:`str`): Name for the session name that will be created. If
            you pass the name of an already existing session, the login-process will be skipped.

    """
    async with Client(session_name, api_id, api_hash) as client:
        _logger.debug("Requesting all available contacts for this Telegram account.")

        photo_map = {}
        for contact in await client.get_contacts():
            if (phone_number := contact.phone_number) and (photo := contact.photo):
                if not phone_number.startswith("0") and not phone_number.startswith("+"):
                    phone_number = f"+{phone_number}"

                photo_map[phone_number] = photo.big_file_id

        _logger.debug("Checking vCards against found contacts.")
        tasks: list[tuple[vobject.base.Component, str]] = []
        progress_logger = ProgressLogger(
            _logger, len(vcards), message="Checked %d of %d vCards.", modulo=50
        )

        for vcard in vcards:
            if not (tel := vcard.contents.get("tel")):
                continue

            for entry in tel:
                phone_number = entry.value.strip().replace("/", "").replace(" ", "")
                photo_id = photo_map.get(phone_number)
                if not photo_id and phone_number.startswith("0"):
                    photo_id = photo_map.get(f"+49{phone_number[1:]}")

                if photo_id:
                    tasks.append((vcard, photo_id))
                    continue

            progress_logger.log()

        progress_logger = ProgressLogger(
            _logger,
            len(tasks),
            message="Downloaded %d of %d found photos.",
        )
        if tasks:
            photo_download_semaphore = asyncio.Semaphore(5)
            await asyncio.gather(
                *(
                    _add_photo_to_vcard(
                        vcard,
                        photo_id,
                        client,
                        progress_logger,
                        semaphore=photo_download_semaphore,
                    )
                    for vcard, photo_id in tasks
                )
            )
