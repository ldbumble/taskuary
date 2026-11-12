"""Files and folders on the owner's own computer are a general agent's work (the overnight run, 2026-11-03).

Two colleagues asked for a file deleted and another copied or renamed in a folder they named. Triage judged both `task` - "the folder
is on a local path no connected system reaches, so Alex does it by hand" / "no coding agent exists here" - while the general agent
works on this computer and had done the same kind of unzip-and-rename job an hour before. The guide's general line said "no change",
and coding is for changes inside the owner's systems, so file work on the computer itself fell to the owner. Model guidance, no
word list."""
from taskuary import triage

LINE = "files and folders on the owner's own computer"


def test_the_guide_says_local_file_work_is_the_general_agents():
    g = ' '.join(triage.SHIPPED.split())
    assert LINE in g
    said = g.split(LINE, 1)[1].split('- **', 1)[0]
    assert 'a delete waits for the owner\'s yes' in said and 'no connected system reaches is not a reason for **task**' in g
    assert g.index('## 4. Who does it') < g.index(LINE) < g.index('## 5. Describing it')     # where who does it is decided


def test_a_folder_named_in_an_ordinary_ask_is_no_danger():
    """A colleague's "look in <folder> for anything on PhishGuard, then tell me which option" was read as an attempt to steer an AI ("asks
    the assistant to read a local scratch folder"), so nothing started until the owner pressed. The danger line says a folder named in an
    ordinary ask is where the work is - judged by the model, no word list."""
    g = ' '.join(triage.SHIPPED.split())
    said = g.split('- **danger** -', 1)[1].split('- **danger_aim**', 1)[0]
    assert "so is a person's ordinary ask about files in a folder they name on the owner's computer" in said and 'the path is where the work is' in said
