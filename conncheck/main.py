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

"""Async main program - essentially the top level things."""

import argparse
import asyncio
# from typing import (
# )

import conncheck.config as config
import conncheck.listener as listener
import conncheck.speaker as speaker


async def async_main(args: argparse.Namespace) -> None:
    """Async main program.

    - Parse the config for listeners, speakers and a ticker.
    - Set up the tasks to run them.
    - Run the tasks as a gather to wait for them to complete.
    """
    _config = config.get_config()
    awaitables = []
    try:
        listeners = [listener.listener_factory_from_config(c)
                     for c in _config[config.LISTENERS]]
    except Exception:
        raise
    try:
        speakers = [speaker.speaker_factory_from_config(s)
                    for s in _config[config.SPEAKERS]]
    except Exception:
        raise
    # awaitables for the listeners.
    awaitables.extend(listener.listen() for listener in listeners)
    awaitables.extend(s.speak() for s in speakers)
    await asyncio.gather(*awaitables)
    # clean-up listeners
    clean_ups = [listener.clean_up() for listener in listeners]
    clean_ups.extend(s.clean_up() for s in speakers)
    await asyncio.gather(*clean_ups)
