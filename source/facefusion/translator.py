import importlib
from typing import Optional

from facefusion import locales_zh
from facefusion.types import Language, LocalePoolSet, Locales

LOCALE_POOL_SET : LocalePoolSet = {}
CURRENT_LANGUAGE : Language = 'zh'


def __autoload__(module_name : str) -> None:
    try:
        __locales__ = importlib.import_module(module_name + '.locales')
        load(__locales__.LOCALES, module_name)
    except ImportError:
        pass


def load(__locales__ : Locales, module_name : str) -> None:
    pool = dict(__locales__)
    zh = locales_zh.ZH_LOCALES.get(module_name)

    if zh:
        pool['zh'] = zh
    LOCALE_POOL_SET[module_name] = pool


def set_language(language : Language) -> None:
    global CURRENT_LANGUAGE
    CURRENT_LANGUAGE = language


def get(notation : str, module_name : str = 'facefusion') -> Optional[str]:
    if module_name not in LOCALE_POOL_SET:
        __autoload__(module_name)

    locales = LOCALE_POOL_SET.get(module_name)

    for language in (CURRENT_LANGUAGE, 'en'):
        current = locales.get(language) if locales else None

        if current is None:
            continue

        result = _resolve(current, notation)

        if result is not None:
            return result
    return None


def _resolve(current : dict, notation : str) -> Optional[str]:
    for fragment in notation.split('.'):
        if fragment in current:
            current = current.get(fragment)

            if isinstance(current, str):
                return current
        else:
            break
    return None