import argparse
import logging
import sys

from risc_tool import run_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    parser.add_argument(
        "--log-file",
        type=bool,
        default=True,
        help="Enable or disable logging to a file",
    )
    args = parser.parse_args(sys.argv[1:])

    log_level = args.log_level.upper()

    run_app(
        log_level=logging.getLevelNamesMapping().get(log_level, logging.INFO),
        log_file=args.log_file,
    )
