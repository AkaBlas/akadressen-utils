#!/usr/bin/env python
"""A module containing functionality to add profile pictures from WhatsApp to vCards based on
the phone number."""
import base64
import json
from logging import getLogger
from pathlib import Path
from typing import Union, Sequence

import vobject.base
from akadressen._util import ProgressLogger

_logger = getLogger(__name__)


def _add_photo_to_vcard(
    vcard: vobject.base.Component,
    photo: bytes,
) -> None:
    if vcard.contents.get("photo"):
        return

    photo_component = vcard.add("photo")
    photo_component.encoding_param = "B"
    photo_component.type_param = "JPG"
    photo_component.value = photo


def add_whatsapp_profile_pictures_to_vcards(
    vcards: Sequence[vobject.base.Component], network_har_log: Union[str, Path]
) -> None:
    """Adds profile pictures to all vCards that can be found on WhatsApp. Requires you to provide
    the photos by:

    1. Opening web.whatsapp.com
    2. Opening the dev tools of your browser and switching to the network tab
    3. Scrolling through all your contacts & member lists of the relevant groups
    4. Exporting the network log as HAR

    Args:
        vcards (List[:class:`vobject.base.Component`]): The vcards. Will be edited in place.
        network_har_log (:obj:`str` | :class:`pathlib.Path`): Path to the network logs.

    """
    _logger.debug("Processing WhatsApp network logs.")
    if not (data := json.loads(Path(network_har_log).read_bytes()).get("log")):
        raise RuntimeError("The data is not in a format that I can handle.")

    if not (entries := data.get("entries")):
        raise RuntimeError("The data is not in a format that I can handle.")

    photo_map: dict[str, bytes] = {}
    for entry in entries:  # pylint: disable=too-many-nested-blocks
        if (request := entry.get("request")) and (response := entry.get("response")):
            if (url := request.get("url")) and (content := response.get("content")):
                if mime_type := content.get("mimeType"):
                    if isinstance(mime_type, str) and mime_type.startswith("image/"):
                        image = content.get("text")
                        encoding = content.get("encoding")

                        if encoding.lower() == "base64":
                            photo_map[url] = base64.b64decode(image)

    _logger.debug("Checking vCards against found contacts.")
    progress_logger = ProgressLogger(
        _logger, len(vcards), message="Checked %d of %d vCards.", modulo=50
    )

    for vcard in vcards:
        if not (tel := vcard.contents.get("tel")):
            continue

        for entry in tel:
            phone_number = entry.value.strip().replace("/", "").replace(" ", "")
            for url, photo in photo_map.items():
                if phone_number in url or (
                    phone_number.startswith("0") and phone_number[1:] in url
                ):
                    _add_photo_to_vcard(vcard, photo)
                    continue

        progress_logger.log()
