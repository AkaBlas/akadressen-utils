#!/usr/bin/env python
"""This module contains utility functionality for internal use within the akadressen package."""
import logging
from logging import Logger
from threading import Lock

import vobject.vcard
from httpx import HTTPError, Response


def check_response_status(response: Response) -> None:
    """Checks if the responses status code indicates success. Raises an exception otherwise.

    Args:
        response (:class:`httpx.Response`): The response.
    """
    if not 200 <= response.status_code <= 299:
        raise HTTPError(f"{response.text}")


_INSTRUMENTS: dict[str, str] = {
    "flö": "Flöte",
    "kla": "Klarinette",
    "obe": "Oboe",
    "hlz": "Holz",
    "sax": "Saxophon",
    "asx": "Altsaxophon",
    "tsx": "Tenorsaxophon",
    "fag": "Fagott",
    "trp": "Trompete",
    "flü": "Flügelhorn",
    "Flügelhorn": "Flügelhorn",
    "flügelhorn": "Flügelhorn",
    "teh": "Tenorhorn",
    "hrn": "Horn",
    "pos": "Posaune",
    "tub": "Tuba",
    "tpd": "Topfdeckel",
    "git": "Gitarre",
    "bss": "E-Bass",
}


def string_to_instrument(string: str) -> str:
    """Converts a string into a nicer representation of the instrument that it describes,
    if possible.
    """
    return _INSTRUMENTS.get(string, string)


def vcard_name_to_filename(name: vobject.vcard.Name) -> str:
    """Given the name property of a vCard, builds the corresponding file name.

    Args:
        name (:class:`vobject.vcard.Name`): The name.

    Returns:
        :obj:`str`: The file name.
    """
    prefix = f"{name.prefix}+" if name.prefix else ""
    additional = f"+{name.additional}" if name.additional else ""
    family = f"{name.family}+{name.suffix}" if name.suffix else name.family

    return f"{family}_{prefix}{name.given}{additional}.vcf".replace(" ", "+")


class ProgressLogger:  # pylint: disable=too-few-public-methods
    """Helper class to log the progress for a number of tasks.

    Args:
        logger (:class:`logging.Logger`): The logger to use.
        total_number (:obj:`int`): The total number of tasks that is expected to be handled.
        level (:obj:`int`, optional): Logging level. Defaults to :attr:`logging.INFO`.
        message (:obj:`str`, optional): Message to use for logging. Must contain exactly two
            ``'%d'``, where the number of finished tasks and ``total_number`` will be inserted.
            Defaults to ``'%d/%d tasks done.'``
        modulo (:obj:`int` | :obj:`None`, optional): If passed, :meth:`log` will only emit a log
            entry if the current count modulo this number is zero (or it's the last task).
            Defaults to 10.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        logger: Logger,
        total_number: int,
        level: int = logging.INFO,
        message: str = None,
        modulo: int = 10,
    ):
        self._logger = logger
        self._total_number = total_number
        self._level = level
        self._message = message or "%d/%d tasks done."
        self._count = 0
        self._modulo = modulo
        self.__lock = Lock()

    def log(self) -> None:
        """Signals that a tasks was done and makes the logger emit a corresponding log entry."""
        with self.__lock:
            self._count = self._count + 1

            if not self._modulo or (
                self._count % self._modulo == 0 or self._count >= self._total_number
            ):
                self._logger.log(self._level, self._message, self._count, self._total_number)
