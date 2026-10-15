"""Small source-English catalogue. Translate presentation, never protocol or owner data."""
import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_LOCALE = 'pt-BR'
LOCALES = ('pt-BR', 'en')


def normalize(value):
    value = str(value or '').strip().replace('_', '-').lower()
    if value in ('pt', 'pt-br'): return 'pt-BR'
    return 'en' if value else DEFAULT_LOCALE


def locale(store=None):
    if os.getenv('TASKUARY_LOCALE'): return normalize(os.environ['TASKUARY_LOCALE'])
    return normalize(store.get_setting('locale', DEFAULT_LOCALE) if store else DEFAULT_LOCALE)


@lru_cache(maxsize=1)
def _catalogue():
    return json.loads(Path(__file__).with_name('i18n_pt_BR.json').read_text(encoding='utf-8'))


def text(source, language=None, **values):
    translated = _catalogue().get(source, source) if normalize(language or locale()) == 'pt-BR' else source
    return translated.format(**values) if values else translated


def presentation(meta, language=None):
    """Copy only translated display fields; type/options/match/keys remain canonical."""
    translated = meta.get('i18n', {}).get(normalize(language or locale()), {})
    return {**meta, **{k: v for k, v in translated.items() if k in ('label', 'title', 'desc', 'help')}}


def output_instruction(language):
    if normalize(language) != 'pt-BR': return ''
    return ('\n\nOUTPUT LANGUAGE: Use Brazilian Portuguese (pt-BR) for prose shown to the owner, '
            'including titles, summaries, explanations and checklist text. Keep JSON keys, enums, '
            'statuses, IDs, paths, commands, tool names and exact-response contracts unchanged. '
            'Do not translate quoted source evidence or recipient addresses. For outgoing replies, '
            "follow the recipient's language and the owner's explicit instructions. Safety and "
            'operational rules above still apply.')


def template_path(name, language=None):
    root = Path(__file__).parent / 'templates'
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in name):
        raise ValueError('Invalid rules document name')
    localized = root / normalize(language or locale()) / f'{name}.md'
    return localized if localized.is_file() else root / f'{name}.md'
