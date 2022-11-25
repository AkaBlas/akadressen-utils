#!/usr/bin/env python
"""Main script synchronizing the AkaDressen with a NextCloud CardDav address book."""
import asyncio
import logging

from httpx import Limits, Timeout

from akadressen import (
    NCAddressBook,
    add_telegram_profile_pictures_to_vcards,
    add_whatsapp_profile_pictures_to_vcards,
    get_akadressen_vcards,
    merge_vcards,
)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger = logging.getLogger("akadressen")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


GENERATED_VCARDS_PATH = r"\path\to\a\git\repo"


async def main() -> None:
    """Main function calling the functionality of the akadressen package"""
    async with NCAddressBook(
        base_url="https://nc.org/remote.php/dav/addressbooks/users/USERNAME/ADDESSBOOK-SLUG/",
        username="username",
        password="password",
        timeout=Timeout(20),
        limits=Limits(max_connections=5),
    ) as address_book:

        # First, fetch all currently existing contacts
        await address_book.download_all_contacts(directory=GENERATED_VCARDS_PATH)

        print(
            "I've downloaded all vCards currently in the address book. "
            "You should now stage or commit the current status so that you can compare the changes"
            " after I merge the current AkaDressen status."
        )
        input("Press Enter to continue.")

        # Parse the Akadressen
        aka_vcards = await get_akadressen_vcards(
            base_url="https://magic.path/to/AkaDressen",
            username="username",
            password="password",
        )

        # Optionally, fetch profile pictures from Telegram
        # api id & hash from my.telegram.org
        await add_telegram_profile_pictures_to_vcards(
            api_id=1234,
            api_hash="hash",
            vcards=aka_vcards,
            session_name="telegram",
        )

        # Optionally, add profile pictures from WhatsApp
        add_whatsapp_profile_pictures_to_vcards(aka_vcards, "web.whatsapp.com.har")

        # Merge AkaDressen into existing contacts
        merge_vcards(
            directory=GENERATED_VCARDS_PATH,
            akadressen_vcards=aka_vcards,
        )

        print(
            "I've merged the data from the AkaDressen into your vCards. "
            "Please carefully review the changes. Delete any vCards that should not be uploaded."
            "When done, you should commit the changes so that you can see the differences easier"
            " when updating the contacts the next time."
        )
        input("Press Enter to continue.")

        await address_book.upload_all_vcards(
            directory=GENERATED_VCARDS_PATH,
            check_override=False,
        )

        print("All Done :)")


asyncio.run(main())
