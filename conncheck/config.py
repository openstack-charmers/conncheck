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

"""Import the config file and make the config available as a global."""

import copy
import yaml
from typing import (
    Any,
    Dict,
    Optional,
)

import conncheck.defaults as defaults
import conncheck.utils as utils

# defines for sections
LISTENERS = "listeners"
SPEAKERS = "speakers"
EVENTS = "events"

__config = None


class ConfigError(Exception):
    """Custom exception for config errors."""

    pass


def get_config(file: Optional[str] = None,
               reload: bool = False) -> Dict[str, Any]:
    """Load the config from the config file and return as a dict.

    The keys are lower-cased to make it easier to read, and the dictionary is
    deepcopied.

    :param file: the file to load, default s defaults.CONFIG_FILE
    :param reload: whether to force reload or not, default False.
    :raises: IOError if file is not found.
    """
    global __config
    if not(reload) and __config is not None:
        return copy.deepcopy(__config)
    if file is None:
        file = defaults.CONFIG_FILE
    try:
        with open(file, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"Couldn't find the file: {file}")
    except yaml.YAMLError as e:
        raise ConfigError(f"Couldn't load the config from {file} due to {e}")
    except Exception as e:
        raise ConfigError(f"Couldn't load the config from {file} due to {e}")
    try:
        __config = utils.lower_case_dict_keys(config)
    except Exception as e:
        raise ConfigError(f"There's something wrong with {file}: {e}")
    # now merge the config together
    for k, v in defaults.CONFIG_DEFAULTS.items():
        if k not in __config:
            __config[k] = copy.deepcopy(v)
    # Return copy of the config
    return copy.deepcopy(__config)
