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

This module supports formatting in to formats:

 - LOG
 - InfluxDB

 - LOG format is basically a human readable line.
 - InfluxDB format is Line Protocol (from InfluxDB), and is used to integrate
   with the rest of a Line Protocol set of logs.

Line Protocols is:

collection,tags fields timestamp

The "tags" are a tag1=value,tag2=value,
The "fields" are field1=value,field2=value

The values are quoted.

In common with the zaza.events module, the recognised fields are:

 - event: the event being indicated.
 - unit: some "unit" which is a collection of "items"
 - item: the smallest 'thing' on a unit.

All other field names (e.g. 'comment', 'to', 'from', 'log') are dealt with as
tags and recorded there.

For conncheck, the collection is/must-be written into the config.yaml so that
it can be included in the logs.

The timestamp is in ms.
"""

import atexit
import datetime
import logging
import os

from typing import (
    Any,
    Dict,
    IO,
    Optional,
    TypeVar,
)

import conncheck.config as config
import conncheck.defaults as defaults


_T = TypeVar('_T')


# event types

REQUEST_HTTP = "http-tx-send"
REQUEST_FAIL = "http-tx-fail"
REQUEST_TIMEOUT = "http-tx-timeout"
REQUEST_SUCCESS = "http-tx-ok"
REPLY_HTTP = "http-rx-send-reply"
REQUEST_DGRAM = "udp-tx-send"
REPLY_TO_DGRAN = "udp-rx-send-reply"
REPLY_DGRAM = "udp-tx-receive-reply"
START = "start"
END = "end"
TICK = "tick"
TICK_INTERVAL = 5.0


__log_file_name = None
__log_file_handle = None


logger = logging.getLogger()


def get_log_file_handle() -> IO[str]:
    """Return the log file handle."""
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


def get_log_format() -> str:
    """Return the log format as lower-cased string."""
    _config = config.get_config()
    try:
        return _config[defaults.LOG_FORMAT_KEY].lower()
    except KeyError:
        return "log"


def is_influxdb_log_format() -> bool:
    """Return true if influxdb log format."""
    return get_log_format() == "influxdb"


def atexit_close_filehandle() -> None:
    """Close the file when the script exits."""
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


_event_to_format_map = {
    START: "",
    END: "",
    TICK: "Counter: {counter}",
    REPLY_HTTP: "TO:{url} uuid:{uuid}",
    REQUEST_HTTP: "TO:{url} uuid:{uuid} counter:{counter} waiting:{wait}",
    REQUEST_FAIL: "TO:{url} uuid:{uuid} counter:{counter}",
    REQUEST_SUCCESS: (
        "uuid:{uuid} counter:{counter} reply_counter:{reply_counter}"),
    REQUEST_TIMEOUT: "TO:{url} uuid:{uuid} counter:{counter}",
    REQUEST_DGRAM: (
        "TO:{ipv4}:{port} uuid:{uuid} counter:{counter} waiting:{wait}"),
    REPLY_DGRAM: "uuid:{uuid}",
    REPLY_TO_DGRAN: "uuid:{uuid} reply_uuid:{reply_uuid} address:{ipv4}:{port}"
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

    def log_event(self, event_type: str, **kwargs) -> None:
        """Log an event to the log.

        This logs to either InfluxDB (Line Protocol) or Human LOG format.  In
        the case of InfluxDB, the collection must be set in the config.

        :param event_type: the event type from EventTypes
        :param **kwargs: Optional additional arguments for the specific event.
        :raises: KeyError for an unknown event.
        :raises: ValueError for an invalid param
        """
        if is_influxdb_log_format():
            fields = {
                'event': event_type,
                'unit': self.unit_name,
                'item': self.component_name,
            }
            for field in ('uuid', 'comment'):
                try:
                    fields[field] = kwargs.pop(field)
                except KeyError:
                    pass
            collection = config.get_config()[defaults.COLLECTION_NAME_KEY]
            log_str = format_line_protocol(
                collection, fields, kwargs, datetime.datetime.now())
        else:
            if event_type not in _event_to_format_map:
                raise KeyError(f"Unknown event type {event_type}")
            try:
                log = _event_to_format_map[event_type].format(**kwargs)
            except (KeyError, TypeError) as e:
                raise ValueError(f"Problem passing args to formatter: {e}")
            # nice ISO8601 datetime - 2020-03-20T14:32:16.458361+13:00
            now_str = datetime.datetime.now().astimezone().isoformat()
            log_str = (
                f"{now_str} {self.unit_name} {self.component_name} "
                f"{event_type} {log}")
        write_to_event_log(log_str)


def format_line_protocol(
    collection: str,
    fields: Dict[str, str],
    tags: Dict[str, str],
    timestamp: Optional[datetime.datetime]
) -> str:
    """Format the Line Protocol string.

    '{collection},{tags} {fields} {timestamp}'

    :param collection: the collection to use.
    :param fields: the collections of fields (event, unit, item)
    :param tags: any additonal tags for the line
    :param timestamp: a datetime.datetime structure for the log.
    :returns: formatting log line.
    """
    if isinstance(timestamp, datetime.datetime):
        timestamp = ("{}us".format(int(timestamp.timestamp() * 1e6)))
    return (
        "{collection}{tags}{fields}{timestamp}"
        .format(
            collection=collection,
            tags=("" if not tags else ",{}"
                  .format(format_dict(tags, tag=True))),
            fields=("" if not fields else " {}"
                    .format(format_dict(fields))),
            timestamp=(" {}".format(timestamp) if timestamp else "")))


def format_value(value: Any, tag: bool = False) -> str:
    """Format a value if it isn't quoted yet.

    :param value: the string to maybe to quote
    :param tag: if this is a tag, then don't quote it, but make sure it has no
        spaces.
    :returns: quoted value
    """
    if tag:
        if isinstance(value, str):
            return value.replace(' ', '-')
        return value
    if isinstance(value, str):
        if value.startswith('"') and value.endswith('"'):
            return value
    return '"{}"'.format(value)


def format_dict(d: Dict[_T, str], tag: bool = False) -> Dict[_T, str]:
    """Fromat a dictionary with quoted values.

    :param d: the dictionary of values to quote.
    :param tag: if the values are tags, they need have no spaces and are not
        quoted.
    :returns: single string of comma-seperated k="v" quoted items.
    """
    assert isinstance(d, dict)
    return ",".join(
        '{}={}'.format(k, format_value(v, tag=tag))
        for k, v in d.items())


def get_event_logger(name: str) -> EventLogger:
    """Return a scoped EventLogger for logging instrumentation events.

    :param name: the unique ID of the component doing the log.
    :returns: a scoped EventLogger that that can write to the appropriate file.
    """
    _config = config.get_config()
    return EventLogger(_config[defaults.UNIT_NAME_KEY], name)
