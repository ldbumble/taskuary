"""Locale changes presentation without changing protocol or user-authored documents."""
import ast
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from taskuary import connectorcatalog, i18n, llm, server, settings_schema
from taskuary.store import SQLiteStore


def test_default_fallback_and_placeholders(monkeypatch):
    monkeypatch.delenv('TASKUARY_LOCALE', raising=False)
    assert i18n.locale() == 'pt-BR'
    assert i18n.text('task not found') == 'tarefa não encontrada'
    assert i18n.text('task not found', 'en') == 'task not found'
    assert i18n.text('task not found', 'de') == 'task not found'
    assert i18n.text('untranslated text') == 'untranslated text'
    assert 'http://localhost' in i18n.text('Taskuary is already running at {url} - opening it.', url='http://localhost')


def test_settings_and_catalog_preserve_contracts():
    for key, source in settings_schema.knobs().items():
        translated = settings_schema.knobs('pt-BR')[key]
        assert translated['type'] == source['type']
        assert translated.get('options') == source.get('options')
        assert translated['group'] == source['group']
        assert translated['label']
    for source, translated in zip(connectorcatalog.cards(), connectorcatalog.cards('pt-BR')):
        for key in ('type', 'match', 'group', 'planned'):
            assert translated[key] == source[key]
    assert settings_schema.refuse('locale', 'pt-BR') == ''
    assert settings_schema.refuse('locale', 'en') == ''
    assert settings_schema.refuse('locale', 'other')


def test_seed_projection_preserves_customizations_and_english(tmp_path, monkeypatch):
    monkeypatch.delenv('TASKUARY_LOCALE', raising=False)
    store = SQLiteStore(str(tmp_path / 'locale.db'))
    assert store.get_setting('locale') == 'pt-BR'
    assert 'Escreva suas regras' in store.get_doc('style')
    assert 'fromhistory:start' in store.get_doc('style')
    assert 'OUTPUT LANGUAGE:' not in store.doc('soul')
    store.set_setting('locale', 'en', 'owner')
    assert 'Write your own rules' in store.get_doc('style')
    assert 'OUTPUT LANGUAGE:' not in store.doc('soul')
    store.save_doc('style', 'CUSTOM {{owner}}', 'owner')
    store.set_setting('locale', 'pt-BR', 'owner')
    assert store.get_doc('style') == 'CUSTOM {{owner}}'
    store.cx.close()
    store = SQLiteStore(str(tmp_path / 'locale.db'))
    assert store.get_doc('style') == 'CUSTOM {{owner}}'
    store.cx.close()


def test_prompt_instruction_preserves_keys_and_recipient_language(tmp_path, monkeypatch):
    monkeypatch.delenv('TASKUARY_LOCALE', raising=False)
    store = SQLiteStore(str(tmp_path / 'llm.db'))
    seen = []
    wrapped = llm._Scrubbed(lambda system, user: seen.append((system, user)), store)
    wrapped('Return JSON {"kind":"general"}', 'unchanged evidence')
    assert 'Return JSON {"kind":"general"}' in seen[0][0]
    assert 'Brazilian Portuguese (pt-BR)' in seen[0][0]
    assert "recipient's language" in seen[0][0]
    assert seen[0][1] == 'unchanged evidence'
    store.cx.close()


def test_api_errors_and_locale_setting(tmp_path, monkeypatch):
    monkeypatch.delenv('TASKUARY_LOCALE', raising=False)
    store = SQLiteStore(str(tmp_path / 'api.db'))
    with patch.object(server, 'store', store):
        client = TestClient(server.app)
        response = client.get('/api/tasks/999999')
        assert response.status_code == 404
        assert response.json()['detail'] == 'tarefa não encontrada'
        assert client.patch('/api/settings', json={'name': 'locale', 'value': 'bad'}).status_code == 422
        assert client.patch('/api/settings', json={'name': 'locale', 'value': 'en'}).status_code == 200
        assert client.get('/api/tasks/999999').json()['detail'] == 'task not found'
        assert client.get('/api/how-it-works').json()['text'].startswith('# How it works')
        store.set_setting('locale', 'pt-BR', 'owner')
        assert client.get('/api/how-it-works').json()['text'].startswith('# Como funciona')
    store.cx.close()


def test_every_cli_help_has_a_translation():
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / 'taskuary/i18n_pt_BR.json').read_text())
    tree = ast.parse((root / 'taskuary/cli.py').read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != 'add_argument': continue
        for keyword in node.keywords:
            if keyword.arg == 'help' and isinstance(keyword.value, ast.Call):
                assert ast.literal_eval(keyword.value.args[0]) in catalog
