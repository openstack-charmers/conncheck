# Copyright 2021 Canonical Ltd.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Provide a mechanism for logging specific events for reporting.

This modules provides a class and global mechanism (using Python logging) to
enable logging to the 'event' file, as determined by the config for the program
(config module).  This makes it easy for a module/coroutine to log events in
a standardised way.

TODO: it would be really cool if this module was in fact sharable with the zaza
module.
"""

import atexit
import datetime
import logging
import os

from typing import (
    IO
)

import config
import defaults


# event types

SEND = "send-request"
REQUEST_HTTP = "request-http"
REQUEST_FAIL = "request-http-fail"
REQUEST_TIMEOUT = "request-http-timeout"
REQUEST_SUCCESS = "request-http-ok"
REPLY_HTTP = "reply-http-to"
REQUEST_DGRAM = "request-udp"
REPLY_DGRAM = "reply-from-udp"
REPLY_TO_DGRAN = "reply-to-udp"
START = "start"
END = "end"
TICK = "tick"
TICK_INTERVAL = 5.0


__log_file_name = None
__log_file_handle = None


logger = logging.getLogger()


def get_log_file_handle() -> IO[str]:
    global __log_file_handle
    global __log_file_name
    _config = config.get_config()
    if __log_file_handle is None:
        try:
            file = _config[defaults.LOG_FILE_KEY]
            __log_file_name = file
        except KeyError:
            raise RuntimeError("No log filename to log to?")
        mode = "at" if _config[defaults.APPEND_TO_LOG_KEY] else "wt"
        __log_file_handle = open(os.path.expandvars(file), mode)
    return __log_file_handle


def atexit_close_filehandle() -> None:
    """Function that closes the file when the script exits."""
    global __log_file_handle
    if __log_file_handle is not None:
        try:
            __log_file_handle.close()
            __log_file_handle = None
        except Exception as e:
            logging.error(f"Couldn't close {__log_file_name} due to {e}")


# ensure the event log is closed at the end of the file.
atexit.register(atexit_close_filehandle)


def write_to_event_log(msg: str) -> None:
    """Write to the log file and flush it.

    :param msg: the string to write.
    """
    h = get_log_file_handle()
    h.write(msg)
    if not msg.endswith("\n"):
        h.write("\n")
    h.flush()
    logging.debug("-> log-file: %s", msg)


class FormatEventBase:
    """Base class for formatting events."""
    pass


class FormatGeneric(FormatEventBase):
    """Class for formatting a generic event with no message."""

    def __str__(self):
        return ""


class FormatReply(FormatEventBase):
    """Class for formatting a reply."""

    def __init__(self, to: str, reply: str) -> None:
        """Initialiser of the FormatReply class."""
        self.to = to
        self.reply = reply

    def __str__(self) -> str:
        """String representation of the format."""
        return f"TO:{self.to} {self.reply}"


class FormatRequestHttp(FormatEventBase):
    """Class for formatting an HTTP request."""

    def __init__(self, url: str, wait: float) -> None:
        """Initialiser of the FormatRequestHttp class."""
        self.url = url
        self.wait = wait

    def __str__(self) -> str:
        """String representation of the format."""
        return f"TO:{self.url} waiting: {self.wait}"


class FormatRequestHttpCounter(FormatEventBase):
    """Class for formatting an HTTP request."""

    def __init__(self, url: str, counter: int) -> None:
        """Initialiser of the FormatRequestHttp class."""
        self.url = url
        self.counter = counter

    def __str__(self) -> str:
        """String representation of the format."""
        return f"TO:{self.url} counter: {self.counter}"


class FormatRequestUDP(FormatEventBase):
    """Class for formatting an HTTP request."""

    def __init__(self, ipv4: str, port: int, counter: int, wait: int) -> None:
        """Initialiser of the FormatRequestHttp class."""
        self.ipv4 = ipv4
        self.port = port
        self.counter = counter
        self.wait = wait

    def __str__(self) -> str:
        """String representation of the format."""
        return (f"TO:{self.ipv4}:{self.port} counter: {self.counter} "
                f"waiting: {self.wait}")


class FormatReplyFromUDP(FormatEventBase):
    """Class for formatting an UDP reply."""

    def __init__(self, count: str) -> None:
        """Initialiser of the FormatReplyFromUDP class."""
        self.count = count

    def __str__(self) -> str:
        """String representation of the format."""
        return f"Count:{self.count}"


class FormatReplyToUDP(FormatEventBase):
    """Class for formatting an UDP reply."""

    def __init__(self, count: str, ipv4: str, port: int) -> None:
        """Initialiser of the FormatReplyFromUDP class."""
        self.count = count
        self.ipv4 = ipv4
        self.port = port

    def __str__(self) -> str:
        """String representation of the format."""
        return f"Count:{self.count} address:{self.ipv4}:{self.port}"


_event_to_format_map = {
    START: FormatGeneric,
    END: FormatGeneric,
    TICK: FormatGeneric,
    REPLY_HTTP: FormatReply,
    REQUEST_HTTP: FormatRequestHttp,
    REQUEST_FAIL: FormatRequestHttpCounter,
    REQUEST_SUCCESS: FormatRequestHttpCounter,
    REQUEST_TIMEOUT: FormatRequestHttpCounter,
    REQUEST_DGRAM: FormatRequestUDP,
    REPLY_DGRAM: FormatReplyFromUDP,
    REPLY_TO_DGRAN: FormatReplyToUDP,
}


class EventLogger:
    """Provide a simple interface to generate events logs."""

    def __init__(self, unit_name: str, component_name: str) -> None:
        """Initialise an EventLogger.

        :param unit_name: the unit that this logger is reporting for.
        :param component_name: the part of the unit for this logger.
        """
        self.unit_name = unit_name
        self.component_name = component_name

    def log_event(self, event_type: str, *args, **kwargs) -> None:
        """Log an event to the log.

        :param event_type: the event type from EventTypes
        :param *args: additional information for the specific event.
        :param **kwargs: Optional additional arguments for the specific event.
        :raises: KeyError for an unknown event.
        :raises: ValueError for an invalid param
        """
        if event_type not in _event_to_format_map:
            raise KeyError(f"Unknown event type {event_type}")
        try:
            log = _event_to_format_map[event_type](*args, **kwargs)
        except TypeError as e:
            raise ValueError(f"Problem passing args to formatter: {e}")
        # nice ISO8601 datetime - 2020-03-20T14:32:16.458361+13:00
        now_str = datetime.datetime.now().astimezone().isoformat()
        log_str = (
            f"{now_str} {self.unit_name} {self.component_name} {event_type} "
            f"{log}")
        write_to_event_log(log_str)


def get_event_logger(name: str) -> EventLogger:
    """Return a scoped EventLogger for logging instrumentation events.

    :param name: the unique ID of the component doing the log.
    :returns: a scoped EventLogger that that can write to the appropriate file.
    """
    _config = config.get_config()
    return EventLogger(_config[defaults.UNIT_NAME_KEY], name)
