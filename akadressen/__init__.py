#!/usr/bin/env python
"""A small Python package that allows to synchronize the AkaDressen with a NextCloud CardDav
address book."""
__all__ = [
    "NCAddressBook",
    "get_akadressen_vcards",
    "merge_vcards",
    "add_telegram_profile_pictures_to_vcards",
    "add_whatsapp_profile_pictures_to_vcards",
]

from ._merge_vcards import merge_vcards
from ._ncaddressbook import NCAddressBook
from ._parse_akadressen import get_akadressen_vcards
from ._telegram import add_telegram_profile_pictures_to_vcards
from ._whatsapp import add_whatsapp_profile_pictures_to_vcards
