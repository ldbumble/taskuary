"""Files and folders on the owner's own computer are a general agent's work (the overnight run, 2026-11-03).

Two colleagues asked for a file deleted and another copied or renamed in a folder they named. Triage judged both `task` - "the folder
is on a local path no connected system reaches, so Alex does it by hand" / "no coding agent exists here" - while the general agent
works on this computer and had done the same kind of unzip-and-rename job an hour before. The guide's general line said "no change",
and coding is for changes inside the owner's systems, so file work on the computer itself fell to the owner. Model guidance, no
word list."""
from taskuary import triage

LINE = "**Files and folders on the owner's own computer are general too**"


def test_the_guide_says_local_file_work_is_the_general_agents():
    g = ' '.join(triage.SHIPPED.split())
    assert LINE in g
    said = g.split(LINE, 1)[1].split('- **', 1)[0]
    assert 'unzip' in said and 'a delete waits for the owner\'s yes' in said and 'not a reason for **task**' in said
    assert g.index('## 4. Who does it') < g.index(LINE) < g.index('## 5. Describing it')     # where who does it is decided
