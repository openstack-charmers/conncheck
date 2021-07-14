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

"""Define speaker classes for speaker behaviour."""

import asyncio
import logging
from typing import (
    Any,
    Dict,
    Optional,
)

import aiohttp

import events
import async_run_utils as run
import utils


class SpeakerBase:

    def __init__(self, config: Dict[str, str]) -> None:
        """Create a SpeakerBase object.

        :param config: a configuration snippet for constructing the base class
            with lower-cased keys in the dictionary.
        :raises: ValueError
        """
        try:
            self.name = config['name']
            self.protocol = config.get('protocol', 'http')
            self.send_size = config.get('send-size', 1024)
            self.wait = config.get('wait', 5)
            self.interval = config.get('interval', 10)
        except KeyError:
            raise ValueError("No name attribute provided.")

        self.events = events.get_event_logger(self.name)
        self._counter = 0

    def next_count(self) -> int:
        self._counter += 1
        return self._counter

    async def fetch(self) -> None:
        raise NotImplementedError("Need to define fetch()")

    async def speak(self) -> None:
        """Send messages until interrupted."""
        while True:
            try:
                await run.run_interruptable(self.fetch())
                logging.debug("speaker: %s, tick", self.name)
                await run.sleep(self.interval, raise_interrupt=True)
            except run.InterruptException:
                break

    async def clean_up(self) -> None:
        """Clean up if needed."""
        pass


class SpeakerUDP(SpeakerBase):

    def __init__(self, config: Dict[str, str]) -> None:
        super().__init__(config)
        self.ipv4 = config['ipv4']
        self.port = config['port']
        logging.debug("Building a SpeakerUDP")
        self.transport = None
        self.protocol = None
        self._do_clean_up = False

    def _conection_made(self):
        pass

    def _error_recieved(self, exc: Exception) -> None:
        logging.error(str(exc))

    def _connection_made(self) -> None:
        pass

    def _connection_lost(self, exc: Optional[Exception]) -> None:
        logging.debug("%s: lost connection.", self.name)
        self._do_clean_up = True

    def _datagram_received(self, message: str, addr: Any) -> None:
        logging.debug("%s: Received reply from %s", self.name, addr)
        try:
            count = message.splitlines()[0]
        except KeyError:
            count = "<no-count-detected>"
        self.events.log_event(events.REPLY_DGRAM, count)

    async def fetch(self) -> None:
        try:
            counter = self.next_count()
            message = utils.pad_text(f"{self.name} Message {counter}",
                                     self.send_size)
            await self._send(message)
            self.events.log_event(
                events.REQUEST_DGRAM, self.ipv4, self.port, counter, self.wait)
        except Exception as e:
            logging.error(
                "%s (%s) raised %s",
                self.name, self.__class__.__name__, str(e))

    async def _send(self, message: str) -> None:
        if self._do_clean_up:
            self.clean_up()
        if self.transport is None:
            loop = asyncio.get_running_loop()
            self.transport, self.protocol = (
                await loop.create_datagram_endpoint(
                    lambda: UDPClient(self),
                    remote_addr=(self.ipv4, self.port)))
            self.events.log_event(events.START)
        # Now send the message
        self.transport.sendto(message.encode())

    async def clean_up(self) -> None:
        """Clean-up the server as required."""
        try:
            self.transport.close()
        except Exception:
            # we don't really care if it errors here
            pass
        self.events.log_event(events.END)
        self.transport = None
        self.protocol = None


class UDPClient:
    def __init__(self, speaker: SpeakerUDP) -> None:
        self.speaker = speaker
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.speaker._connection_made()

    def datagram_received(self, data, addr):
        # Assume data is text
        try:
            message = data.decode()
            self.speaker._datagram_received(message, addr)
        except Exception as e:
            logging.debug("%s: couldn't decode message %s",
                          self.speaker.name, data)
            print(str(e))
            import traceback
            traceback.print_exc()

    def error_received(self, exc: Exception) -> None:
        self.speaker._error_received(exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self.speaker._connection_lost(exc)


class SpeakerHTTP(SpeakerBase):

    def __init__(self, config: Dict[str, str]) -> None:
        super().__init__(config)
        self.url = config['url']
        logging.debug("Building a SpeakerHTTP.")

    async def fetch(self) -> None:
        try:
            counter = self.next_count()
            timeout = aiohttp.ClientTimeout(total=self.wait)
            url = (self.url.format(counter=counter)
                   if "{counter}" in self.url
                   else self.url)
            self.events.log_event(events.REQUEST_HTTP, url, wait=self.wait)
            async with aiohttp.request('GET', url, timeout=timeout) as resp:
                if resp.status == 200:
                    reply = await resp.text()
                    try:
                        first = reply.splitlines()[0]
                        reply_counter = first.split(" ")[1]
                        self.events.log_event(
                            events.REQUEST_SUCCESS, counter, reply_counter)
                    except KeyError:
                        self.events.log_event(
                            events.REQUEST_SUCCESS, counter, "UNKNOWN")
        except asyncio.TimeoutError:
            self.events.log_event(events.REQUEST_TIMEOUT, url, counter)
        except aiohttp.client_exceptions.ClientConnectionError:
            self.events.log_event(events.REQUEST_FAIL, url, counter)
        print(f"{self.name} fetch done")


_protocol_to_speaker = {
    'udp': SpeakerUDP,
    'http': SpeakerHTTP,
}


def speaker_factory_from_config(config: Dict[str, str]) -> SpeakerBase:
    """Return a Speaker class based on the protocol in the config.

    Default Speaker is a UDP speaker.

    :param config: the config snipped from 'speakers' in the config file.
    :raises: ValueError if the potocol isn't known.
    """
    try:
        protocol = config.get('protocol', 'udp')
    except AttributeError:
        raise ValueError(f"config is a {type(config)} which has not .get() "
                         "method.")
    try:
        return _protocol_to_speaker[protocol](config)
    except KeyError:
        raise ValueError(f"Unknown protocol {protocol} for speaker.")
