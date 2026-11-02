"""Logging: INFO on the console (DEBUG with --debug), always-DEBUG rotating file at
~/.taskuary/taskuary.log - so 'it crashed / nothing happened' is always diagnosable
after the fact. Every API request, report run, connector test and ingest logs here.
"""
import sys, tempfile
from pathlib import Path
from loguru import logger

from . import config

FMT = '{time:YYYY-MM-DD HH:mm:ss} {level: <7} {name}:{line} {message}'


def setup(debug: bool = False):
    logger.remove()
    logger.add(sys.stderr, level='DEBUG' if debug else 'INFO',
               format='<green>{time:HH:mm:ss}</green> <level>{level: <7}</level> {message}')
    f, why = config.home() / 'taskuary.log', ''
    # A log file never stops the app. On one Windows computer the data folder existed, yet loguru's os.makedirs refused it
    # ("Cannot create a file when that file already exists") and the desktop app died before its window: Python 3.12's
    # os.path.isdir can say no to a folder that Path.is_dir (and config.home's own mkdir) accepts.
    try: logger.add(f, level='DEBUG', rotation='5 MB', retention=3, enqueue=True, format=FMT)
    except OSError as e:
        why, f = str(e), Path(tempfile.gettempdir()) / 'taskuary.log'
        logger.add(f, level='DEBUG', rotation='5 MB', retention=3, enqueue=True, format=FMT)
    logger.info(f"log file: {f}" + (' (debug console)' if debug else ''))
    if why: logger.warning(f'the log file could not go in the data folder, so it is in the temp folder - {why}')
