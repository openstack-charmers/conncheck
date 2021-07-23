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

"""CLI entry handling for the program."""


import argparse
# from typing import (
# )
import logging
import os
import sys

import conncheck.config
import conncheck.async_run_utils
import conncheck.main as main_program


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', dest='config',
                        help='The configuration file to parse.  Defaults to '
                             './config.yaml',
                        required=False)
    parser.add_argument('--log', dest='loglevel',
                        help='Loglevel [DEBUG|INFO|WARN|ERROR|CRITICAL]')
    parser.set_defaults(config="./config.yaml",
                        loglevel='INFO')
    return parser.parse_args()


def setup_logging(log_level: str ='INFO') -> None:
    """Do setup for logging.

    :returns: Nothing: This fucntion is executed for its sideffect
    :rtype: None
    """
    level = getattr(logging, log_level.upper(), None)
    if not isinstance(level, int):
        raise ValueError('Invalid log level: "{}"'.format(log_level))
    logFormatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    rootLogger = logging.getLogger()
    rootLogger.setLevel(level)
    if not rootLogger.hasHandlers():
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logFormatter)
        rootLogger.addHandler(consoleHandler)


def main() -> None:
    """Main entry for the program."""
    conncheck.async_run_utils.register_signal_handlers()
    args = parse_args()
    setup_logging(args.loglevel.upper())
    # Force a completely fresh reload of the config.
    config_file = os.path.abspath(args.config)
    try:
        _config = conncheck.config.get_config(file=config_file, reload=True)
    except conncheck.config.ConfigError as e:
        logging.error("Couldn't load config. %s", str(e))
        print("Abnormal program end; problem reading config %s" % config_file)
        sys.exit(1)
    logging.info("ConnCheck: config file: %s, log level=%s",
                 config_file, args.loglevel.upper())
    logging.info("ConnCheck starting:")
    logging.debug("config loaded: %s", _config)
    # Now run the main loop
    logging.debug("Running async main")
    conncheck.async_run_utils.run_async(main_program.async_main(args))
    logging.debug("Async main has completed - program exiting cleanly.")
    logging.info("ConnCheck ends.")


if __name__ == '__main__':
    main()
