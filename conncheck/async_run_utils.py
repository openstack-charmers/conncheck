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


"""The core runner for the app; runs the asyncio loop."""

import asyncio
import logging
import signal
import time
from typing import (
    Any,
    Awaitable,
)
import sys #import version_info


def run_async(step: Awaitable) -> Any:
    """Run the given step in the asyncio loop.

    If the tasks spawns other future (tasks) then these are also cleaned up
    after the step is performed.

    :returns: The result of the  asyncio.Task
    """
    loop = asyncio.get_event_loop()

    task = loop.create_task(step)
    loop.run_until_complete(asyncio.wait([task], loop=loop))

    is_ge_37 = sys.version_info.major >=3 and sys.version_info.minor >= 7
    # Cancel any remaining tasks:
    while True:
        if is_ge_37:
            try:
                tasklist = asyncio.all_tasks()
            except RuntimeError:
                # no running event loop
                break
        else:
            tasklist = asyncio.Task.all_tasks()
        pending_tasks = [p for p in tasklist if not p.done()]
        if pending_tasks:
            logging.info(
                "async -> sync. cleaning up pending tasks: len: {}"
                .format(len(pending_tasks)))
            for pending_task in pending_tasks:
                pending_task.cancel()
                try:
                    loop.run_until_complete(pending_task)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logging.error(
                        "A pending task caused an exception: {}"
                        .format(str(e)))
        else:
            break

    return task.result()


async def sleep(timeout: float,
                sleep: float = 0.1,
                raise_interrupt: bool = False) -> None:
    """Sleep for a period, but only whilst we keep_running().

    Essentially, asyncio.sleep() but checking that we've not been been asked to
    quit via a signal.

    :param timeout: the time to wait before returning.
    :param sleep: the micro-sleeps between checking for keep_running()
    :param raise_interrupt: If True, an interrupt is raised.
    :raises: InterruptException if raise_interrupt is True
    """
    assert timeout >= 0.0
    assert sleep >= 0.0
    start = time.time()
    while keep_running(raise_interrupt=raise_interrupt):
        await asyncio.sleep(sleep)
        now = time.time()
        if start + timeout < now:
            break


class BreakoutException(Exception):
    """Exception to allow breaking out of an awaitable."""

    pass


class InterruptException(Exception):
    """Exception to signal that we've been gracefully interrupted."""

    pass


async def run_interruptable(aw: Awaitable) -> Any:
    """Run a task that doesn't know about interruptions.

    This runs an awaitable that doesn't know about interruptions.
    It cancels the task if the program is being stopped and then raises the
    InterruptException.

    :param aw: the Awaitable that needs to be run.
    :raises InterruptException
    """
    done = False
    result = None

    async def check_interrupted() -> None:
        nonlocal done
        while not done:
            if not keep_running():
                logging.debug("Breaking out.")
                raise BreakoutException()
            await asyncio.sleep(0.1)

    async def _run_task() -> Any:
        nonlocal result, done
        result = await aw
        done = True
        return result

    task = asyncio.create_task(_run_task())
    try:
        await asyncio.gather(task, check_interrupted())
    except BreakoutException:
        task.cancel()
        raise InterruptException()

    return result


# If True, then we've been interrupted.
_interrupt = False
_registered = False


def keep_running(raise_interrupt: bool = False) -> bool:
    """Test if the program is to be interrupted.

    :param raise_interrupt: If True raise an interrupt instead.
    """
    if raise_interrupt and _interrupt:
        raise InterruptException()
    return not _interrupt


def handler(signum, _):
    logging.info("Received %s, setting interrupt to end program.",
                 signal.Signals(signum).name)
    global _interrupt
    _interrupt = True


def register_signal_handlers(force: bool = False) -> None:
    """Register the handler for INT, HUP and TERM signals.

    :param force: whether to force a registration of the handler.
    """
    global _registered
    if not _registered or force:
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGHUP, handler)
        signal.signal(signal.SIGTERM, handler)
        _registered = True
