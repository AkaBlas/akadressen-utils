# AkaDressen Utils

This projects provides functionality that helps to keep your CardDav address book up to date with
the contact data of your fellow AkaBlas members.
Currently, only tested with NextCloud address books.

Running `main.py` basically does the following:

1. Download all contacts that already exist in the address book
2. Download the AkaDressen and parse them into vCards
3. Optionally look up the phone numbers and get the corresponding profile pictures from Telegram
3. Optionally look up the phone numbers and get the corresponding profile pictures from WhatsApp (see below)
4. Merge the vCards generated from the AkaDressen into the existing ones. A few notes on this:
   1. Existing data is never overwritten - at most, it's appended
   2. vCards are tricky and this is as best effort solution. You may need to manually tweak the result
   3. When making manual changes, make sure to use the UID of the already existing vCard.
      This makes sure that the existing contact is edited instead of creating a new one.
5. Upload all the changed vCards to the address book

Please carefully read `main.py` to check out where you need to insert your credentials & configurations.
Optionally, you can also read the docs of the classes & methods of tha `akadressen` package.
Note that not all methods & classes have elaborate documentation, but all user facing ones do.

## How tow run it?

* You'll need Python 3.9+
* You'll need to install the requirements of listed in `requirements.txt`, probably via
  ```shell
  $ pip install -r requirements.txt
  ```
* Then, after inserting your credentials & configs, just run 
  ```shell
  $ python main.py
  ```

## A note on profile pictures

Telegram has an open API so that you can get all your contacts profile pictures programmatically.
So this part is easy.

WhatsApp doesn't have such a functionality - there is an API, but it's only for business customers.
What we *can* do is to snatch the profile pictures when they are loaded to be shown to you.
Here is how it's done:

1. Opening web.whatsapp.com
2. Opening the dev tools of your browser and switching to the network tab
3. Scrolling through all your contacts & member lists of the relevant groups
4. Exporting the network log as HAR file

From this file, we can extract the profile pictures.

Update 11/2022: WhatsApp no longer mentions the phone number of in the profile picture URL. I have not yet found another way to get the profile picture. If you have any ideas, please let me know.
