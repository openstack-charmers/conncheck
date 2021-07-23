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


"""Define listener classes for listener behaviour."""

import asyncio
from typing import (
    Any,
    Awaitable,
    Dict,
    Optional,
)
import logging

import aiohttp
import aiohttp.web

import conncheck.events as events
import conncheck.utils as utils
import conncheck.async_run_utils as run


class ListenerBase:
    """Listener Base class."""

    def __init__(self, config: Dict[str, str]) -> None:
        """Create a ListenerBase object.

        :param config: a configuration snippet for constructing the base class
            with lower-cased keys in the dictionary.
        :raises: ValueError
        """
        try:
            self.name = config['name']
            self.ipv4 = config.get('ipv4', '0.0.0.0')
            self.protocol = config.get('protocol', 'http')
            self.port = config.get('port', 80)
            self.reply_size = config.get('reply-size', 1024)
        except KeyError:
            raise ValueError("No name attribute provided.")

        self.events = events.get_event_logger(self.name)
        self._counter = 0

    def next_count(self) -> int:
        """Return the next counter."""
        self._counter += 1
        return self._counter

    async def listen(self) -> None:
        """List loop; not expected to exit until told to."""
        pass

    async def clean_up(self) -> None:
        """Clean up after ourselves, prior to being shutdown."""
        pass

    def __str__(self) -> str:
        """Return string description."""
        return (f"{self.__class__.__name__}: {self.name} listening on "
                f"{self.ipv4}:{self.port} using protocol {self.protocol}, "
                f"reply size is: {self.reply_size}")


class ListenerUDP(ListenerBase):
    """Listener UDP class."""

    class UDPServer:
        """UDP Server class."""

        def __init__(self, listener):
            """Initialise a UDPServer instance."""
            self.listener = listener

        def connection_made(self, transport):
            """Connection_made callback."""
            logging.debug("UDPServer for %s made", self.listener.name)
            self.transport = transport

        def datagram_received(self, data, addr):
            """Datagram_received callback."""
            # assume it is text.
            message = data.decode()
            reply = self.listener._handle_datagram(message, addr)
            # assume reply is text; encode it to bytes
            self.transport.sendto(reply.encode(), addr)

        def error_received(self, exc: Exception) -> None:
            """Error_received callback."""
            self.listener._error_received(exc)

        def connection_lost(self, exc: Optional[Exception]) -> None:
            """Connection_lost callback."""
            self.listener._connection_lost(exc)

    def __init__(self, *args, **kwargs) -> None:
        """Initialise a ListenerUDP object."""
        super().__init__(*args, **kwargs)
        logging.debug(f"Creating {self}")
        self.transport = None
        self.protocol = None

    def _handle_datagram(self, message: str, addr: Any) -> None:
        """Handle the incoming datagram and reply to it."""
        logging.debug("%s: incoming dgram from %s", self.name, addr)
        try:
            line = message.splitlines()[0]
            count = line.split(" ")[2]
        except KeyError:
            count = "<not-detected>"
        self.events.log_event(events.REPLY_TO_DGRAN, count=count, ipv4=addr[0],
                              port=addr[1])
        return utils.pad_text(f"{count}\n", self.reply_size)

    def _connection_lost(self, exc: Optional[Exception]) -> None:
        """Handle the lost connection with a debug."""
        logging.debug("%s: lost connection.", self.name)

    def _error_received(self, exc: Exception) -> None:
        """Handle an error by just logging in with debug."""
        logging.debug("%s: error received: %s.", self.name, exc)

    async def listen(self) -> None:
        """Listen 'forever' for datagrams."""
        # One protocol instance will be created to serve all
        # client requests.
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: self.UDPServer(self),
            local_addr=(self.ipv4, self.port))

        self.events.log_event(events.START)
        logging.info("Listener %s(%s), listening on: %s:%s",
                     self.__class__.__name__, self.name, self.ipv4, self.port)

        # now wait until the process ends.
        while run.keep_running():
            logging.debug("listener: %s, tick", self.name)
            await run.sleep(events.TICK_INTERVAL)

    async def clean_up(self) -> None:
        """Clean-up the server as required."""
        try:
            self.transport.close()
        except Exception:
            # we don't really care if it errors here
            pass
        self.events.log_event(events.END)
        self.transport = None


class ListenerHTTP(ListenerBase):
    """HTTP Listener class."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialise an HTTP Listener."""
        super().__init__(*args, **kwargs)
        logging.debug(f"Creating {self}")
        self.server = None
        self.runner = None
        self.site = None

    def _make_handler(self) -> Awaitable[aiohttp.ClientResponse]:
        async def handler(
            request: aiohttp.web.Request
        ) -> aiohttp.web.Response:
            counter = self.next_count()
            self.events.log_event(events.REPLY_HTTP, url=request.remote,
                                  counter=counter)
            reply = f"Response {counter} from {self.name}.\n"
            return aiohttp.web.Response(
                text=utils.pad_text(reply, self.reply_size))

        return handler

    async def listen(self) -> None:
        """Listen on the configured address and port for this listener."""
        self.server = aiohttp.web.Server(self._make_handler())
        self.runner = aiohttp.web.ServerRunner(self.server)
        await self.runner.setup()
        self.site = aiohttp.web.TCPSite(self.runner, self.ipv4, self.port)
        await self.site.start()
        # log that we've started the lister.
        self.events.log_event(events.START)
        logging.info("Listener %s(%s), listening on: %s:%s",
                     self.__class__.__name__, self.name, self.ipv4, self.port)

        # now wait until the process ends.
        while run.keep_running():
            logging.debug("listener: %s, tick", self.name)
            await run.sleep(events.TICK_INTERVAL)

    async def clean_up(self) -> None:
        """Clean-up the server as required."""
        try:
            await self.site.stop()
            await self.runner.cleanup()
            await self.runner.shutdown()
            await self.server.shudown()
        except Exception:
            # we don't really care if it errors here
            pass
        self.events.log_event(events.END)
        self.site = None
        self.runner = None
        self.server = None


_protocol_to_listener = {
    'udp': ListenerUDP,
    'http': ListenerHTTP,
}


def listener_factory_from_config(config: Dict[str, str]) -> ListenerBase:
    """Return a Listener class based on the protocol in the config.

    Default listener is a UDP listener.

    :param config: the config snipped from 'listeners' in the config file.
    :raises: ValueError if the potocol isn't known.
    """
    try:
        protocol = config.get('protocol', 'udp')
    except AttributeError:
        raise ValueError(f"config is a {type(config)} which has not .get() "
                         "method.")
    try:
        return _protocol_to_listener[protocol](config)
    except KeyError:
        raise ValueError(f"Unknown protocol {protocol} for listener.")
