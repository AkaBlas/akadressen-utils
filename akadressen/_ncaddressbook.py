#!/usr/bin/env python
"""This module contains the class NCAddressBook which represents a NextCloud CardDav address
book."""
import asyncio
from logging import getLogger
from pathlib import Path
from types import TracebackType
from typing import Optional, Union
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import vobject
from httpx import AsyncClient, Limits, Timeout
from vobject.base import Component

from akadressen._util import ProgressLogger, check_response_status, vcard_name_to_filename


class NCAddressBook:
    """Class for interacting with a NextCloud contact book. Should be used as async context
    manager. This automatically calls :meth:`initialize`.

    Args:
        base_url (:obj:`str`): URL of the contact book of the form
            ``"https://nc.org/remote.php/dav/addressbooks/users/UserName/addressbookname/"``.
        username (:obj:`str`): Username.
        password (:obj:`str`): Password.
        timeout (:class:`httpx.Timeout`, optional): Timeout settings for the httpx client.
        limits (:class:`httpx.Timeout`, optional): Limits settings for the httpx client.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        base_url: str,
        username: str = None,
        password: str = None,
        timeout: Timeout = None,
        limits: Limits = None,
    ):
        self._base_url = base_url
        self._uids: dict[str, str] = {}
        self._v_cards: dict[str, Component] = {}
        self._client = AsyncClient(
            auth=(username, password) if username and password else None,
            verify=True,
            headers={"User-Agent": "AkaDressen-Script"},
            timeout=timeout,
            limits=limits or Limits(),
        )
        self._logger = getLogger(__name__)

    async def __aenter__(self: "NCAddressBook") -> "NCAddressBook":
        try:
            await self.initialize()
            return self
        except Exception as exc:
            await self._client.aclose()
            raise exc

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self._client.aclose()

    @property
    def uids(self) -> list[str]:
        """Gives a list of all UIDs of contacts in the address book."""
        if not self._uids:
            raise RuntimeError("Contacts where not initialized. Call `get_contacts`")
        return list(self._uids.keys())

    async def initialize(self) -> None:
        """Initializes the address book. Currently only calls :meth:`get_contacts`."""
        self._logger.debug("Initializing address book.")
        await self.refresh_contacts()

    async def refresh_contacts(self, clear: bool = True) -> list[str]:
        """Fetches the contacts of this address book and stores the corresponding UIDs and
        ETAGs.

        Args:
            clear (:obj:`bool`, optional): Whether or not to drop any currently stored UID.
                Defaults to :obj:`True`.

        Returns:
            List[:obj:`str`]: The UIDs.
        """
        self._logger.debug("Requesting all available UIDs from address book.")
        response = await self._client.request(
            "PROPFIND",
            self._base_url,
            headers={"Depth": "1"},
        )
        check_response_status(response)
        self._logger.debug("UIDs received. Parsing.")

        if clear or self._uids is None:
            self._uids = {}

        xml_data = response.content.decode()
        xml_data = xml_data.replace('<?xml version="1.0" encoding="utf-8"?>', "", 1)
        namespace = "{DAV:}"
        element = ET.XML(xml_data)

        for entry in element.iter():  # pylint: disable=too-many-nested-blocks
            if entry.tag in [namespace + "entry", namespace + "response"]:
                uid = ""
                etag = ""
                insert = False
                for refprop in entry.iter():
                    if refprop.tag == namespace + "href":
                        if not refprop.text:
                            raise RuntimeError("Something went wrong parsing the contacts.")
                        uid = refprop.text.rsplit("/", 1)[-1].removesuffix(".vcf")
                    for prop in refprop.iter():
                        for props in prop.iter():
                            if props.tag == namespace + "getcontenttype" and (
                                props.text
                                in [
                                    "text/vcard",
                                    "text/vcard; charset=utf-8",
                                    "text/x-vcard",
                                    "text/x-vcard; charset=utf-8",
                                ]
                            ):
                                insert = True
                            if props.tag == namespace + "getetag":
                                etag = props.text or ""
                        if insert and uid:
                            self._uids[uid] = etag

        return self.uids

    async def get_vcard_bytes(self, uid: str) -> bytes:
        """Retrieves a contacts vCard as bytes.

        Args:
            uid (:obj:`str`): The UID of the contact.
        """
        response = await self._client.get(urljoin(self._base_url, f"{uid}.vcf"))
        check_response_status(response)

        etag = response.headers.get("oc-etag")
        self._uids[uid] = etag

        return response.content

    async def download_vcard(self, uid: str, path: Union[str, Path] = None) -> Component:
        """Downloads a contacts vCard and returns it as Python object.

        Args:
            uid (:obj:`str`): The UID of the contact.
            path (:obj:`str` | :class:`pathlib.Path`, optional): Path to download to. If it's a
                directory or not passed, the file name will be determined by the contacts full
                name, which might override existing files.

        Returns:
            :class:`vobject.base.Component`: The vCard.
        """
        self._logger.debug("Requesting vCard from address book.")
        content = await self.get_vcard_bytes(uid)
        string_content = content.decode("utf-8")
        vcard = vobject.readOne(string_content, transform=True, validate=True)

        effective_path = Path(path) if path else None
        if effective_path is None or effective_path.is_dir():
            file_name = vcard_name_to_filename(vcard.n.value)
            self._logger.debug("No file name was specified. Using `%s`.", file_name)
            file_path = Path(file_name)
            effective_path = file_path if path is None else path / file_path

        self._logger.debug("Writing vCard to file.")
        effective_path.write_bytes(content)
        self._v_cards[uid] = vcard
        return vcard

    async def _download_vcard_with_logging(
        self, uid: str, progress_logger: ProgressLogger, path: Union[str, Path] = None
    ) -> Component:
        out = await self.download_vcard(uid=uid, path=path)
        progress_logger.log()
        return out

    async def download_all_contacts(self, directory: Union[str, Path] = None) -> list[Component]:
        """Downloads all contacts vCards and returns them as Python objects.

        Args:
            directory (:obj:`str` | :class:`pathlib.Path`, optional): Directory to download to.
                The file name will be determined by the contacts full name, which
                might override existing files.

        Returns:
            List[:class:`vobject.base.Component`:] The vCards.
        """
        progress_logger = ProgressLogger(
            self._logger, len(self.uids), message="Downloaded contact %d of %d."
        )
        out = await asyncio.gather(
            *(
                self._download_vcard_with_logging(
                    uid=uid, path=directory, progress_logger=progress_logger
                )
                for uid in self.uids
            )
        )
        return [res for res in out if not isinstance(res, BaseException)]

    async def upload_vcard(self, vcard: Component, check_override: bool = True) -> None:
        """Uploads a new or changed contact to the address book

        Args:
            vcard (:class:`vobject.base.Component`:): The vCard. Must have a UID.
            check_override (:obj:`bool`, optional): Whether or not to check for conflicts. If this
                can't be checked due to no ETAG being known for the UID, an exception will be
                raised. Pass :obj:`False` when uploading new contacts.
        """
        try:
            uid = str(vcard.uid.value)
        except AttributeError as exc:
            raise ValueError("`vcard` is missing a UUID.") from exc

        headers = {"content-type": "text/vcard"}
        etag = self._uids.get(uid)
        if etag:
            headers["If-Match"] = etag
        elif check_override:
            raise RuntimeError(
                "No etag found for this vcard. "
                "Cancelling upload to prevent unintentional overriding."
            )

        response = await self._client.put(
            urljoin(self._base_url, f"{uid}.vcf"),
            headers=headers,
            content=vcard.serialize().encode(),
        )
        check_response_status(response)

        if etag := response.headers.get("oc-etag"):
            self._uids[uid] = etag

    async def _upload_vcard_with_logging(
        self,
        vcard: Component,
        progress_logger: ProgressLogger,
        check_override: bool = True,
    ) -> None:
        await self.upload_vcard(vcard, check_override)
        progress_logger.log()

    async def upload_all_vcards(
        self, directory: Union[str, Path], check_override: bool = True
    ) -> None:
        """Uploads all vCards and in the specified directory.

        Args:
            directory (:obj:`str` | :class:`pathlib.Path`): The directory to upload the
                vcards from. All files ending on ``.vcf`` will be considered a vCard.
            check_override (:obj:`bool`, optional): Whether or not to check for conflicts. If this
                can't be checked due to no ETAG being known for the UID, an exception will be
                raised. Pass :obj:`False` when uploading new contacts.

        Returns:
            List[:class:`vobject.base.Component`:] The vCards.
        """
        files = list(Path(directory).glob("*.vcf"))
        progress_logger = ProgressLogger(
            self._logger, len(files), message="Uploaded vCard %d of %d."
        )
        await asyncio.gather(
            *(
                self._upload_vcard_with_logging(
                    vcard=vobject.readOne(
                        file.read_text(encoding="utf-8"), transform=True, validate=True
                    ),
                    check_override=check_override,
                    progress_logger=progress_logger,
                )
                for file in files
            )
        )
