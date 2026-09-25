"""`taskuary --help` is the only manual for the command, so every option in it must say what it does."""
import argparse, pytest
from taskuary import cli


def _help(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['taskuary', '--help'])
    with pytest.raises(SystemExit) as e: cli.main()
    assert e.value.code == 0
    return capsys.readouterr().out


def _parser(monkeypatch):
    "the parser `main` builds, caught at the moment it would parse"
    class Built(Exception): pass
    def grab(self, *a, **k): raise Built(self)
    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', grab)
    with pytest.raises(Built) as e: cli.main()
    return e.value.args[0]


def test_no_browser_says_what_it_does(monkeypatch, capsys):
    assert "don't open a browser tab when the server starts" in ' '.join(_help(monkeypatch, capsys).split())


def test_every_option_has_a_description(monkeypatch):
    bare = [a.option_strings[0] for a in _parser(monkeypatch)._actions if a.option_strings and not a.help]
    assert not bare, f'options with no help text: {bare}'
