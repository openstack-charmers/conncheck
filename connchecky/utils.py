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


"""Useful functions."""

import asyncio
import logging
from sys import version_info
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
)


def lower_case_dict_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return the same dictionary with lower cased keys."""
    return {k.lower(): v for k, v in d.items()}


def pad_text(t: str, size: int) -> str:
    """Pad out text with supplied size using new lines.

    Note that the string provide will not be shrunk to the :param:`size`.

    :param t: the text to pad
    :param size: the length wanted.
    """
    pad_line = "This line is padding. Line number {line}\n"
    if len(t) > size - 1:
        return t
    padded = f"{t}\n"
    remain = max(size - len(padded), 0)
    num_lines = int(remain / len(pad_line))
    if num_lines > 0:
        padded = "{}{}".format(
            padded,
            "".join(pad_line.format(line=n)
                    for n in range(1, num_lines + 1)))
    remain = max(int(size - len(padded)), 0)
    if remain:
        padded = "{}{}".format(padded, "=" * remain)
    return padded


# TODO: may not need this at all.
def run(*steps):
    """Run the given steps in an asyncio loop.

    If the tasks spawns other future (tasks) then these are also cleaned up
    after each step is performed.

    :returns: The result of the last asyncio.Task
    """
    if not steps:
        return
    loop = asyncio.get_event_loop()

    for step in steps:
        task = loop.create_task(step)
        loop.run_until_complete(asyncio.wait([task], loop=loop))

        # Let's also cancel any remaining tasks:
        while True:
            if version_info.major == 3 and version_info.minor >= 7:
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


def sync_wrapper(f: Coroutine) -> Callable:
    """Convert the given async coroutine into a callable function.

    This is only to be called from sync code and it runs all tasks (and cancels
    all tasks at the end of each run) for the code that is being given.

    :param f: the Coroutine to wrap
    :returns: The de-async'd function
    """
    def _wrapper(*args, **kwargs):
        async def _run_it():
            return await f(*args, **kwargs)
        return run(_run_it())
    return _wrapper
