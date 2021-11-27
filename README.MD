# AkaDressen Utils

This projects provides functionality that helps to keep your CardDav address book up to date with
the contact data of your fellow AkaBlas members.
Currently, only tested with NextCloud address books.

Running `main.py` basically does the following:

1. Download all contacts that already exist in the address book
2. Download the AkaDressen and parse them into vCards
3. Optionally look up the phone numbers and get the corresponding profile pictures from Telegram
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
