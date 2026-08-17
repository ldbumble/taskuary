"""Logging: INFO on the console (DEBUG with --debug), always-DEBUG rotating file at
~/.taskuary/taskuary.log - so 'it crashed / nothing happened' is always diagnosable
after the fact. Every API request, report run, connector test and ingest logs here.
"""
import sys
from loguru import logger

from . import config


def setup(debug: bool = False):
    logger.remove()
    logger.add(sys.stderr, level='DEBUG' if debug else 'INFO',
               format='<green>{time:HH:mm:ss}</green> <level>{level: <7}</level> {message}')
    logger.add(config.home() / 'taskuary.log', level='DEBUG', rotation='5 MB', retention=3,
               enqueue=True, format='{time:YYYY-MM-DD HH:mm:ss} {level: <7} {name}:{line} {message}')
    logger.info(f"log file: {config.home() / 'taskuary.log'}" + (' (debug console)' if debug else ''))
