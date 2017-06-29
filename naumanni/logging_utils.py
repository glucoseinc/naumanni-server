# -*- coding: utf-8 -*-
import logging
import os

try:
    import colorama
    LOG_COLORED = True
except:
    LOG_COLORED = False


SHORT_LEVELNAME_MAP = {
    'DEBUG': 'DBUG',
}
if LOG_COLORED:
    LEVEL_COLOR_MAP = {
        'DEBUG': colorama.Style.DIM + colorama.Fore.WHITE,
        'INFO': colorama.Fore.WHITE,
        'WARNING': colorama.Fore.YELLOW,
        'ERROR': colorama.Fore.RED,
        'CRITICAL': colorama.Style.BRIGHT + colorama.Fore.RED + colorama.Back.WHITE,
    }
    NAME_COLOR = colorama.Fore.MAGENTA


def set_nice_record_factory(m=None):
    if not m:
        m = logging
    old_factory = m.getLogRecordFactory()

    def nice_record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        nice_modify_record(record)
        return record

    m.setLogRecordFactory(nice_record_factory)


def nice_modify_record(record):
    """LogRecordをかっこよくする"""
    record.pid = os.getpid()
    record.levelname4 = SHORT_LEVELNAME_MAP.get(record.levelname, record.levelname[:4])

    if LOG_COLORED:
        record.nice_levelname = _colored(LEVEL_COLOR_MAP[record.levelname], record.levelname)
        record.nice_levelname4 = _colored(LEVEL_COLOR_MAP[record.levelname], record.levelname4)

        record.nice_name = _colored(NAME_COLOR, record.name)


def _colored(color, text):
    return '{}{}{}'.format(color, text, colorama.Style.RESET_ALL)
