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


"""Defaults in the app."""

CONFIG_FILE = "./config.yml"

# config key names
LOG_FILE_KEY = "file-log-path"
APPEND_TO_LOG_KEY = "file-log-append"
UNIT_NAME_KEY = "name"
LOG_FORMAT_KEY = "log-format"
COLLECTION_NAME_KEY = "collection"

# defaults to merge in if missing from provided config
CONFIG_DEFAULTS = {
    LOG_FILE_KEY: CONFIG_FILE,
    APPEND_TO_LOG_KEY: True,
    LOG_FORMAT_KEY: "line-protocol"
}
