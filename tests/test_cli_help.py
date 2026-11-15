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


def test_a_start_with_no_browser_says_how_to_open_it_signed_in():
    # a container's page said only "Open Taskuary from its app, or run `taskuary --link`": no app, and no word of where to run it
    import inspect, pathlib
    assert '`taskuary --link`' in cli.HEADLESS and 'docker compose exec taskuary taskuary --link' in cli.HEADLESS
    assert 'if args.no_browser: print(HEADLESS)' in inspect.getsource(cli.main)
    docs = (pathlib.Path(__file__).resolve().parent.parent / 'docs' / 'site' / 'start-here.md').read_text(encoding='utf-8')
    assert 'docker compose exec taskuary taskuary --link' in docs and 'Open `http://127.0.0.1:7787`. Data lives' not in docs


def test_every_option_has_a_description(monkeypatch):
    bare = [a.option_strings[0] for a in _parser(monkeypatch)._actions if a.option_strings and not a.help]
    assert not bare, f'options with no help text: {bare}'
