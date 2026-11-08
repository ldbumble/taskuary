"""M5: a signed build runs only an installer Windows calls validly signed by its own signer."""
import os, sys, tempfile
from pathlib import Path
from unittest import mock
import pytest
from taskuary import update

ME = 'CN=Northwind, O=Northwind, C=US'

def _run(sig):
    f = Path(tempfile.mkdtemp()) / 'TaskuarySetup.exe'; f.write_bytes(b'MZ')
    with mock.patch.object(update.os, 'name', 'nt'), mock.patch.object(sys, 'frozen', True, create=True), \
         mock.patch.object(update, 'signer', side_effect=lambda p: sig if p == f else ('Valid', ME)):
        update.check_signed(f, Path('Taskuary.exe'))
    return f

def test_the_same_signer_runs(): assert _run(('Valid', ME)).exists()

@pytest.mark.parametrize('sig', [('NotSigned', ''), ('HashMismatch', ME), ('Valid', 'CN=Someone Else'), ('', '')])
def test_anything_else_is_deleted_and_refused(sig):
    with pytest.raises(RuntimeError, match='not run'): _run(sig)

def test_an_unsigned_build_has_no_signer_to_hold_it_to():
    f = Path(tempfile.mkdtemp()) / 'x.exe'; f.write_bytes(b'MZ')
    with mock.patch.object(update.os, 'name', 'nt'), mock.patch.object(sys, 'frozen', True, create=True), \
         mock.patch.object(update, 'signer', return_value=('NotSigned', '')):
        update.check_signed(f, Path('Taskuary.exe'))
    assert f.exists()
