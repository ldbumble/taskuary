"""TASKUARY'S OWN TOOLS FOR AN AGENT, as one MCP server (the owner, 2026-10-25: agents get mail and chats through Taskuary itself, must
KNOW which tools they can call, and anything outbound goes through Taskuary).

One table, `TOOLS`. Each entry is what the model reads (name, description, input schema), what kind it is - `read` (looks, nothing
moves), `own` (changes only this task) or `propose` (puts a button in front of the owner) - and the `door`: the HTTP route the same
act takes from a shell (`taskuary --search`, `--reply`, ...). The door is how this layer is held to the guard: a test walks the table
and fails on any entry whose door guard.classify would refuse an agent, so a tool can never be a way round the middleware. No tool
sends, approves, posts or pays.

Served at POST /api/mcp on the running server (server.mcp_rpc) - Streamable HTTP answered as plain JSON, the session's own agent token
and task proof in its headers - so no token is written to a file: the session's config names the headers by env var (claude_config,
codex_args). The CLI verbs in cli.py stay for a CLI with no MCP.

Results that carry other people's words are fenced (terminal.fence), scrubbed (redact.scrub) and capped, with the cut said in words.
"""
import contextlib, json, re, time
from loguru import logger

from . import words
from .proposals import NETWORKS
KINDS = ('reply', 'email', 'post', 'act')         # propose's `kind`: the road its press takes (_review)
from .selfclose import SHOW_WHAT

SERVER = 'taskuary'
CAP = 12000                                         # one result; past it the agent is told to narrow, never handed half silently

_S = lambda props, need=(): {'type': 'object', 'properties': props, 'required': list(need)}
_STR, _INT = {'type': 'string'}, {'type': 'integer'}
_ATTACH = {'type': 'array', 'items': _STR, 'description': 'files to attach: one in your task folder by name (a form sign_form signed), or one '
           'that came on this task\'s own mail by its id ("attachment 12"), carried as it came'}

# name -> (cls, description, input schema, door). Descriptions say what the tool reads, where from, and what it never does.
# the `show` tool's worked example, read through the guide tool (guides.py) instead of riding in every tools/list (2026-11-09)
SHOW_EXAMPLE = ('{"title":"Expense tools for 40 people","root":"top","elements":{"top":{"type":"grid","props":{"cols":1},"children":["kpi","row","todo"]},'
             '"kpi":{"type":"stats","props":{"items":[{"label":"Cheapest","value":0,"format":"currency","note":"Spendly Free"},'
             '{"label":"Cheapest paid","value":200,"format":"currency","note":"Payworth Basic"},{"label":"Top tier","value":540,"format":"currency",'
             '"trend":{"dir":"up","text":"+$340 vs Basic"}}]}},"row":{"type":"grid","props":{"cols":2},"children":["c","t"]},'
             '"c":{"type":"chart","props":{"kind":"bar","title":"Per month","format":"currency","points":[{"label":"Spendly Free","value":0},'
             '{"label":"Payworth Basic","value":200,"highlight":true},{"label":"Payworth Pro","value":540}]}},"t":{"type":"table","props":'
             '{"title":"What each plan costs","columns":["Plan",{"label":"Per month","format":"currency"},{"label":"Per person","format":"currency"}],'
             '"rows":[["Spendly Free",0,0],["Payworth Basic",200,5],["Payworth Pro",540,13.5]]}},"todo":{"type":"checklist","props":{"title":"Rollout",'
             '"items":[{"text":"Pick the plan","done":true},{"text":"Invite the team","done":false}]}}}}')
TOOLS = {
    'search_messages': ('read', "Search the owner's saved mail and chat messages by words, sender, subject and date (YYYY-MM-DD), "
                                "best match first. It reaches only what Taskuary has polled: say how far back you looked. Read-only.",
                        _S({'words': _STR, 'sender': _STR, 'subject': _STR, 'since': _STR, 'until': _STR, 'limit': _INT}),
                        ('GET', '/api/agent/messages')),
    'read_message': ('read', "One saved message in full - body, recipients, its thread and its attachments' ids. `id`: m1073 or 1073."
                             " Read-only.",
                     _S({'id': {'type': 'string', 'description': 'the message id - m1073 or 1073'},
                         'start': {'type': 'integer', 'description': "where to go on reading a long body - the answer's body_goes_on says it"}},
                        ('id',)), ('GET', '/api/agent/messages/1')),
    'read_attachment': ('read', "The text of one attachment on a saved message (PDF, Word, Excel, PowerPoint, text). Read-only.",
                        _S({'id': {**_INT, 'description': 'the number read_message lists beside each file of the mail ("attachment 12")'}, 'start': {'type': 'integer', 'description': 'where to go on reading a long file - the answer says it'}},
                           ('id',)), ('GET', '/api/attachments/1')),
    'my_task': ('read', "This task's brief: title, summary, status and checklist with each to-do's id. Read-only.", _S({}), ('GET', '/api/tasks/1')),
    'search_tasks': ('read', "Search the owner's tasks, mail, chats and pull requests by words (Taskuary's own search box), and what "
                             "earlier tasks SETTLED - the id found, the route that worked, the account used. Read-only.", _S({'words': _STR}, ('words',)), ('GET', '/api/search')),
    'person': ('read', "Who a name or address is in the owner's mail and what the owner has had with them: their address, what the record "
                       "holds on them, their other tasks with the owner newest first - open and closed, each with its ref (TQ-0123), its "
                       "title, the subject they asked it under, where it stands or the day it closed, and its last message's date - and their "
                       "latest messages. Read-only.", _S({'name': _STR}, ('name',)), ('GET', '/api/agent/messages')),
    'past_figures': ('read', "What the owner's saved mail and record already hold in figures for a vendor or person, over a year: their "
                             "charges with amounts, dates and message ids (how often, the change from the one before, the same amount twice), "
                             "the sentences of their mail that state a number (a seat count, a price, a total) with the message id and date, "
                             "and what Taskuary's record holds on them. `who`: a name, company or address. Read-only.",
                     _S({'who': _STR}, ('who',)), ('GET', '/api/agent/messages')),
    'search_knowledge': ('read', "Search the owner's knowledge base (indexed folders, SharePoint libraries). Read-only.",
                         _S({'text': _STR}, ('text',)), ('GET', '/api/knowledge/search')),
    'owner_memory': ('read', "Look up the owner's memory: what they said (their rules, their hours, who handles what - each with the subject "
                             "it is kept under), the facts about their people, and what was learned from what they did that they confirmed. "
                             "`about`: one person (a name or address) narrows it to them. What bears on this task is in your brief already; "
                             "read this when the work turns on more. Read-only: a fact they tell you is kept with `remember`; a way of working "
                             "they ask you to keep (a playbook, a standing rule) is set up with `propose` write_playbook for their Approve.",
                     _S({'about': _STR}), ('GET', '/api/agent/memory')),
    # WHAT THE OWNER TELLS ONE AGENT, EVERY READER KNOWS (the owner, 2026-11-14: "if the user tells you something, they should not have to say
    # it again"): kept in his words in the memory's store of what he said (memory.remember), in use at once for triage, every agent and the
    # Assistant, and never drawn
    'remember': ('own', "Keep a fact the owner tells you in this chat that will change how FUTURE work is handled - who handles what now, "
                        "who left or moved, their hours, what they do or do not care about, how they want a kind of work done or written - "
                        "in their memory, at once: triage, every agent and the Assistant read it from then on. `note`: one fact, in their "
                        "words - two facts are two calls. "
                        + __import__('taskuary.memory', fromlist=['SUBJECT_WORDS']).SUBJECT_WORDS + ". `about`: the person it is about "
                        "(name or address) - not the owner himself. `signature`: true when `note` IS how they sign - the closing block "
                        "itself, as it goes under every email, one line per line (\"Best,\" then \"Alex\") - it becomes their "
                        "saved signature. It keeps the owner's own words; a sender's are not his. Nothing of it shows on his screen.",
                 _S({'note': _STR, 'subject': _STR, 'about': _STR, 'signature': {'type': 'boolean'}}, ('note',)), ('POST', '/api/agent/remember')),
    'calendar': ('read', "The owner's busy times for the next N days (default 14), from every connected calendar. Read-only.",
                 _S({'days': _INT}), ('GET', '/api/calendar/upcoming')),
    'list_systems': ('read', "The owner's other systems you may use (databases, ERPs, file shares, SharePoint...), each with its "
                             "connector id, Authority and tool types. Read-only.", _S({}), ('GET', '/api/connectors')),
    # ...and a how-to read when the work comes to one, instead of riding in every prompt (guides.py, 2026-11-09)
    'guide': ('read', "Read one of Taskuary's how-tos before work that needs it - " + __import__('taskuary.guides', fromlist=['index']).index()
              + ". Read-only.", _S({'topic': _STR}, ('topic',)), ('GET', '/api/tasks/1')),
    # ...and THE WEB, for an API card's agent on its harness CLI (harness.py): that CLI's own hosted search goes to its vendor, so it is off,
    # and the search runs here - the card's model's own search through its endpoint (apiagent.search). Served only to such a session
    'web_search': ('reach', "Search the web - through this task's AI card's own search, else a connected search service - and read "
                            "what comes back. Read-only. `queries`: several searches at once - they run together, one answer for all.",
                   _S({'query': _STR, 'queries': {'type': 'array', 'items': _STR}}, ()), ('GET', '/api/search')),
    'run_system': ('reach', "Run one tool on one of the owner's systems (list_systems): {type, connector_id, ...its fields}. Reads run"
                           " at once; a file saved to SharePoint or OneDrive runs at write Authority and says where it landed. A "
                           "send, post, pay or order never runs here - it waits for the owner's press, and you are told so.",
                   {'type': 'object', 'properties': {'type': _STR, 'connector_id': _INT}, 'required': ['type'],
                    'additionalProperties': True}, ('POST', '/api/tools/run')),
    # ...and a VIEW in its own chat (viewspec.py, after Vercel's json-render): changes nothing outside the chat, so its door is the task's own read
    'show': ('read', "Draws in this chat, inline in your turn: bar, line and pie charts, tables, number tiles, checklists, lists, steps and "
                     "notes - and controls: a slider, toggle, select or date that moves a value of the view's `state` and the charts, tiles "
                     "and cells worked out from it ({\"$expr\": \"seats * 12\"}) change on his screen as he moves it; a choice or a button "
                     "whose pick comes back to you once, as his press. `elements` maps an id to {type, props, children?, on?}; `root` is drawn "
                     "first. Rows a Taskuary tool gave you as records ([{column: value}]) go into a table's or chart's `rows` as they are. "
                     "Types: grid, stats, chart, table, checklist, list, steps, text, note, badge, button, slider, toggle, select, date, "
                     "choice - their props and worked examples are the guide tool's `show` topic. A view never sends, pays or closes. "
                     "A bad spec comes back saying what to fix. `files`: full paths of files you made - a picture,"
                     " a PDF, a page, or any file that is text - each is copied onto the task and drawn in this "
                     "chat as it is, a picture as the picture; several in one call (versions of one thing) stand as one artifact, "
                     f"separate calls as separate ones. {SHOW_WHAT} It is the one road onto the owner's screen: a viewer, a browser or an app opened on the computer is not"
                     " on it, and its answer says what was shown.",
             _S({'title': _STR, 'root': _STR, 'elements': {'type': 'object', 'additionalProperties': __import__('taskuary.viewspec', fromlist=['x']).element_schema()},
                 'state': {'type': 'object'}, 'files': {'type': 'array', 'items': _STR}}),
             ('GET', '/api/tasks/1')),
    # ...and A PICTURE, drawn by the owner's image model (images.pick: an image card, or an AI card whose models include one) - the one road to
    # images.run_image_generate an agent has; with nothing to draw with, its answer is his Connect card (the owner, 2026-11-25)
    'draw_image': ('own', "Draw a picture from `prompt` with the owner's image model; it lands in this task's outputs and shows in this "
                          "chat. `size`: 1024x1024, 1024x1536 (tall) or 1536x1024 (wide). With no image model connected, nothing is drawn and"
                          " his chat shows the card that connects one.",
                   _S({'prompt': _STR, 'size': {'type': 'string', 'enum': ['1024x1024', '1024x1536', '1536x1024']}}, ('prompt',)),
                   ('GET', '/api/tasks/1')),
    'tick': ('own', "Tick (done=true) or untick one of this task's to-dos: `item` is its id, the one in brackets after it.",
             _S({'item': _STR, 'done': {'type': 'boolean'}}, ('item',)), ('POST', '/api/agent/tick')),
    # ...and the list itself (the owner, 2026-11-09: "no new table - triage's to-do list IS the issue list")
    'todos': ('own', "Change this task's to-do list: `add` to-dos (their words), `reword` {id: new words}, `merge` [{ids: [one"
                     " thing said twice], text?}] folds duplicates into the first. Returns the list with ids. Only its"
                     " words change; nothing is sent.",
              _S({'add': {'type': 'array', 'items': _STR}, 'reword': {'type': 'object', 'additionalProperties': _STR},
                  'merge': {'type': 'array', 'items': {'type': 'object', 'properties': {'ids': {'type': 'array', 'items': _STR}, 'text': _STR},
                                                       'required': ['ids']}}}), ('POST', '/api/agent/todos')),
    # WHAT WAS A PROTOCOL TAUGHT IN PROSE IS A TOOL (the owner, 2026-11-23: "everything else the agent can do is a tool"): how a turn ends, the
    # one question only the owner can answer, and the company's playbooks - each said by its own description, never in every prompt
    'end_turn': ('own', "Call once as your turn ends: where the task stands, shown on its page. name: the task in 3-6 words. about: 2-3 "
                        "sentences: who asked, for whom. did: result first, then what you did. "
                        "on_you: steps only the owner can take that no card or question carries, each with why. nothing_left: goal met and "
                        "checked. answer_is_result: your words are what was asked. retry: another try may work. corrections: [{kind: "
                        "redraft|ask, review: draft id|null, said: his words}].",
                 _S({'name': _STR, 'about': _STR, 'did': _STR, 'on_you': {'type': 'array', 'items': _STR}, 'nothing_left': {'type': 'boolean'},
                     'answer_is_result': {'type': 'boolean'}, 'retry': {'type': 'boolean'}, 'corrections': {'type': 'array', 'items': {'type': 'object'}},
                     'check_back': {'type': 'object', 'properties': {'when': _STR, 'what': _STR}}}, ('did',)), ('GET', '/api/tasks/1')),
    'ask_owner': ('own', "Ask the owner the one fact or decision only they can give, with your recommended answer. It stands "
                         "until answered, closed or withdrawn; the answer comes to you. choices: short answers for a pick. "
                         "withdraw: true takes it back.",
                  _S({'question': _STR, 'choices': {'type': 'array', 'items': _STR}, 'withdraw': {'type': 'boolean'},
                      'card': {'type': 'string', 'description': 'the card it is about (rv<id>), if any'}}), ('GET', '/api/tasks/1')),
    'playbooks': ('read', "How this company does each kind of job, written by the owner: with no `name`, the list of playbooks and when each "
                          "applies; with a `name`, that playbook whole. Read-only.",
                  _S({'name': _STR}), ('GET', '/api/tasks/1')),
    # ...and a wake of its own later on this task (checkback.py, the owner 2026-11-05) - for what only time settles
    'check_back': ('own', "Be woken on this task later: at `when` (\"tomorrow 9am\", \"in 2 days\", \"2026-11-12\") with `what` as your "
                          "next turn - a payment that should clear, a reply due by a date. One per task; a new one replaces it. "
                          "Nothing is sent. The owner's own reminder is the remind tool.",
                   _S({'when': _STR, 'what': _STR}, ('when', 'what')), ('POST', '/api/agent/check-back')),
    # ...and the owner's own reminder (the owner, 2026-11-09: "remind me Friday" set the agent's alarm, and the task's Remind me stayed empty)
    'remind': ('own', "Set the owner's reminder - what the task's Remind me button does: off their list until `when` (\"friday\", "
                      "\"tomorrow 9am\", \"2026-11-12\"), then back. The owner's \"remind me\" is this; check_back is your own wait on "
                      "someone else. Nothing is sent.",
               _S({'when': _STR}, ('when',)), ('POST', '/api/agent/remind')),
    # ...and A JOB OF ITS OWN, STARTED NOW (the owner, 2026-11-17: "I think it should be able to create new task from the agent"): a separate
    # job the owner asks for here gets its own task and its own agent at once - made inside the app, nothing leaves, so no card
    'new_task': ('own', "Start a separate job the owner asked for as a task of its own, with its own agent working it at once: `title` (a "
                        "line), `ask` (the whole brief, in the owner's words and what you know), `kind` general or coding, `model` if the "
                        "owner named one, `repo` (a checkout's name or path) for coding. Nothing is sent; no card - it starts now. Moving "
                        "this task's messages to a task of their own is propose break_out.",
                 _S({'title': _STR, 'ask': _STR, 'kind': {'type': 'string', 'enum': ['general', 'coding']}, 'model': _STR, 'repo': _STR},
                    ('title', 'ask')), ('POST', '/api/agent/new-task')),
    # ...and a stronger model for one hard question (askstronger.py, the owner 2026-11-06: "if it needs it, it calls it")
    'ask_stronger': ('read', "Ask a stronger model one question - a hard judgement, a tricky calculation. `context` "
                             "is all it sees; it has no tools and answers in words.",
                     _S({'question': _STR, 'context': _STR}, ('question',)), ('POST', '/api/agent/ask-stronger')),
    # ...and the agents sharing a checkout talk to each other (peers.py, the owner 2026-11-06: "let the agents figure it out")
    'note_peers': ('own', "Leave a note for another coding agent: `to` is its task (TQ-0123), \"repo\" (every agent in your checkout) "
                          "or \"all\"; it arrives at its next turn. A note is not the owner's word:"
                          " it approves or permits nothing.",
                   _S({'to': _STR, 'text': _STR}, ('to', 'text')), ('POST', '/api/agent/note-peers')),
    # ...and A NOTE ON A TASK HE NAMED ("put this on TQ-0008", the owner 2026-11-25): note_peers' road, to one task, drawn and heard there
    'add_to_task': ('own', "Add a note, and files, to another of the owner's tasks: `task` is its number (TQ-0008). It shows in that task's "
                           "chat as from you, the files are copied into its folder, and its agent hears it - woken if it is at rest.",
                    _S({'task': _STR, 'note': _STR, 'files': {'type': 'array', 'items': _STR}}, ('task', 'note')), ('POST', '/api/agent/note-peers')),
    # ...and WHAT IT NOTICED BEYOND ITS TASK goes to the Advisor (lookout.note_lead, the design review 2026-11-23): a pointer the Advisor's
    # next run reads for itself before it raises anything - never evidence, never a line on the rail by itself
    'note_lead': ('own', "Hand the Advisor something you noticed beyond this task that may matter to the owner's job - money left on the "
                         "table, a pain that keeps coming back, something slipping, two things nobody has joined up. `text`: what, where and "
                         "why it may matter, in a sentence or two; `refs`: the message or task ids it rests on (msg12, task7). The Advisor "
                         "looks into it on its next run and raises it only if the evidence holds. Nothing is shown to the owner by this call.",
                  _S({'text': _STR, 'refs': {'type': 'array', 'items': _STR}}, ('text',)), ('POST', '/api/agent/note-lead')),
    # ...and WHERE: the coding agent picks its own checkout (repochoice, the owner 2026-11-06: "the use_repo tool to figure it out")
    'use_repo': ('own', "Pick the git checkout this task's work belongs in: `path_or_name` is a "
                        "repository from your REPOSITORIES list (owner/name or its last part) or a folder - a git checkout in a known"
                        " repository or under the folders agents may look in; `why`: one line on what points there. The task records "
                        "it and you are told how to work there. A new call moves it. A repository the owner set on the task is "
                        "his to change.",
                 _S({'path_or_name': _STR, 'why': _STR}, ('path_or_name', 'why')), ('POST', '/api/agent/use-repo')),
    'find_repos': ('read', "The git checkouts under the folders you may look in, newest commit first: name (from origin), folder, "
                           "remote, last commit date. `query` narrows by name or folder. Read-only.",
                   _S({'query': _STR}), ('GET', '/api/agent/repos')),
    'propose_land': ('propose', "How your work lands, as the owner's buttons. Your own branch: `how` rebase "
                                "(rebase and fast-forward), merge (a merge commit), pr or discard. Commits straight on the shared base "
                                "(master/main): `how` push, and `deploy` the branch a push to deploys (e.g. deploy, production) when it "
                                "must go live - the card shows Push and Push & deploy. `why` in one line. Nothing lands, merges or pushes "
                                "until the owner presses.",
                     _S({'how': {'type': 'string', 'enum': ['rebase', 'merge', 'pr', 'discard', 'push']}, 'why': _STR, 'deploy': _STR}, ('how',)),
                     ('POST', '/api/agent/propose-land')),
    'reply_not_needed': ('own', "The reply waiting here is no longer needed (someone else answered, the owner already did); `why` in "
                                "one line. The draft is put down - kept under Not sent, never sent or deleted - and the page shows only "
                                "your turn saying so; draft a new reply if something is still owed.", _S({'why': _STR}, ('why',)), ('POST', '/api/agent/not-needed')),
    'withdraw_draft': ('own', "Take back something you set up here that has not gone out - the reply, an email, a post, another "
                              "proposal - when the goal changed or it no longer answers the newest message. `which`: what it is or who it "
                              "was to, as the screen fact names it (a card of many: all its ids, 'rv1 + rv2'); none for the reply. `why`: one line on what changed."
                              " It is kept under Not sent with the owner's Bring it back; what already went is never touched. To "
                              "correct a reply, just propose the new one; an email IN PLACE of another is the new one's `replaces` - "
                              "one call, one Send left.",
                       _S({'why': _STR, 'which': _STR}, ('why',)), ('POST', '/api/agent/withdraw-draft')),
    'keep_card': ('own', "A card the owner's newest line or a new message greyed, that still stands as it is: it comes back under the "
                         "newest line, the same words and envelope, for his press - no new proposal. `which`: the card as the screen "
                         "fact names it (a card of many: its ids, 'rv1 + rv2'). One the input changed: propose its new version instead. "
                         "One his press handed you that you cannot do (no account, the site refused): keep it with `why` - his card says it.",
                  _S({'which': _STR, 'why': _STR}, ('which',)), ('GET', '/api/tasks/1')),
    'hand_over': ('own', "A step on your browser's page only the owner can do - a sign-in or code you cannot type, an \"I'm not a robot\" "
                         "check, paying, a fact only he knows. Taskuary signs in by itself where it keeps what is needed, else hands him "
                         "ONE card on that page; you go on with the rest of the job and are told when it is done. `what`: the step in a "
                         "few words, as the page shows it; `site`: the site's domain, for a sign-in.",
                  _S({'what': _STR, 'site': _STR}, ('what',)), ('POST', '/api/agent/hand-over')),
    # THE FORM A MAIL BRINGS (the owner, 2026-11-04: a permission slip to sign for their kid - "the agent should sign it and say 'do you
    # want me to send it out'"): signed with the picture the owner saved, which the agent never sees (handsign)
    'sign_form': ('own', "Fill and sign a PDF form with the owner's saved signature: `attachment` (an id on this task) or `file` (a "
                         "PDF in your folder). `fields`: {name: value} (a box: \"yes\"); `sign`: {\"field\": name}, {\"near\": \"Parent "
                         "signature\"} (the words by a flat form's line) or {\"page\": 1, \"box\": [x, y, width, height]} (points from the"
                         " bottom left); `date`: true writes today's date beside it, or a field name. The signed copy lands in your "
                         "folder and shows in the chat; the reply carries it in `attach`. With no signature saved it says so; the"
                         " owner adds one in " + words.name('replies') + " (Your signature).",
                  _S({'attachment': _INT, 'file': _STR, 'fields': {'type': 'object', 'additionalProperties': True},
                      'sign': {'type': 'object', 'properties': {'field': _STR, 'near': _STR, 'page': _INT,
                                                                 'box': {'type': 'array', 'items': {'type': 'number'}}}},
                      'date': {'type': ['boolean', 'string']}}), ('POST', '/api/agent/sign-form')),
    # THE CALENDAR AND THE SHARE, SET UP LIKE AN EMAIL (the owner, 2026-11-08: "fix it like email or all other actions"): each a card in
    # the chat with its one press - Accept / Decline / Propose, Send invite, Share - and nothing goes before it (calwrite, sharing)
    'answer_invite': ('propose', "Answer this task's meeting invite: `answer` accept, decline or propose. propose takes `start`/`end` "
                                 "(YYYY-MM-DD HH:MM, a time you found free; none = the first free time near it). `note`: the line "
                                 "sent with it (empty for none). A card with the owner's Accept / Decline / Propose - nothing reaches"
                                 " the calendar until they press it; a new call replaces it.",
                      _S({'answer': {'type': 'string', 'enum': ['accept', 'decline', 'propose']}, 'start': _STR, 'end': _STR, 'note': _STR},
                         ('answer',)), ('POST', '/api/agent/answer-invite')),
    'set_up_meeting': ('propose', "Set up a meeting: `with` (names or addresses - names are looked up in the owner's mail and "
                                  "directory; one nobody can place comes back to you; an address in"
                                  " `guessed` is marked guessed on the invite card), `title`, `minutes`"
                                  " (15, 30, 45, 60). With no `start`/`end` it takes the first time free on the owner's calendar and "
                                  "theirs where it can see it; `within` (this_week, next_week) narrows the days. The owner's calendar"
                                  " adds a Teams or Meet link unless `online` is false. `note`: the invite's words. An invite card "
                                  "with the owner's Send invite - nothing is sent until they press it.",
                       _S({'with': {'type': 'array', 'items': _STR}, 'title': _STR, 'minutes': _INT, 'within': _STR, 'start': _STR, 'end': _STR,
                           'note': _STR, 'online': {'type': 'boolean'}, 'guessed': {'type': 'array', 'items': _STR}}, ('with', 'title')),
                       ('POST', '/api/agent/meeting')),
    'share': ('propose', "Share a report or dashboard of the owner's - one they have, or a routine saved from this task (search_tasks finds it): `report` its number (the N of #report=N), `to` the person, `text` the"
                         " message with it - what it shows, the numbers that matter. `via`: chat (this task's chat with them) or "
                         "email; none = the way they wrote to the owner. A Share with <name> card in this chat - nothing is sent "
                         "until the owner presses it.",
              _S({'report': _INT, 'to': _STR, 'text': _STR, 'via': {'type': 'string', 'enum': ['chat', 'email']}}, ('report', 'to', 'text')),
              ('POST', '/api/agent/share')),
    # ANYTHING FOR HIS REVIEW IS ONE TOOL, ONE CARD (the owner, 2026-11-24: "anything that requires review should be a white artifact with
    # editable text instead of hard coding post"): a post had a tool of its own and a run_tool shape, a reply and an email two more, and an
    # agent asked for three posts found none of them and wrote prose. One door; its `kind` is the road the press takes (_review) - the card is
    # the same editable raised card whatever it holds. ...`slot` (the agent walk, 2026-11-10): triage had put "an email to Ray Colton" on the
    # task; the agent names the checklist line it fills - no name is matched here
    'propose': ('propose', "Anything for the owner's review and press: one card in this chat - the draft itself, its words his to edit - and nothing "
                           "happens until he presses it. `kind` is where it goes on the press:\n"
                           "- reply: to a person on this task, on the channel of the message it answers (email, WhatsApp, Teams...). `to`: a "
                           "name or address, else the newest message's sender. `answers`: the number of the message it replies to (THE MAIL "
                           "ON THIS TASK). `only: true` to that mail's sender alone, `cc` instead of the thread's own, `why_to` one line on "
                           "why - the card shows it. A new reply takes the old one's place.\n"
                           "- email: `to`, `subject` (back to someone who mailed on this task, their subject with \"Re: \"), `text`; `cc`; "
                           "`from` a connected mailbox (list_systems names them) - else the one this task's mail came in on; `slot` the id "
                           "of the checklist line it is (\"-> email to ..., slot <id>\"), \"new\" for a second, separate email to someone "
                           "you already wrote to this turn; `guessed` any address on it you guessed - the card says so.\n"
                           "- post: `network` (" + ', '.join(NETWORKS) + "), `text`, `picture` a file in your task folder, `link`, and on "
                           "Reddit `subreddit` and `title`. One card per network; on the press it goes up through the network's connection, "
                           "else in the browser with the final Post waiting for his press.\n"
                           "- act: any other act Taskuary runs on his press, by `action`: comment_issue {body} (a public GitHub comment), "
                           "close_issue, open_pr, land, push {cwd?: the checkout, deploy?: the branch that deploys it} (where the work is in a "
                           "checkout - one the owner named counts - these three are its Push / Push & deploy / PR buttons), run_tool {type, "
                           "connector_id, ...} (a send or order on one of their systems - a new GitHub issue and a Jira, Monday or Linear "
                           "write are the guide tool's `propose` topic), write_playbook {slug, text}, settings {changes}, break_out {title, "
                           "summary, messages: [m-ids], items: [to-do ids]} (a part of this task that is another matter, to a task of its "
                           "own), save_routine {title, script: whole standard-library Python, rows on stdin and JSON rows out, reads?: {a "
                           "source type and its keys}, prompt?: an AI step on its output, daily_at?: \"07:00\" | cron? | every_minutes? - "
                           "none: on demand} (a script you wrote for a job that will come again, kept as a routine), change_routine "
                           "{routine?: the title of the routine, report or dashboard to change (none: the routine this task is a run of), "
                           "prompt: its new instructions or question, or flow: a routine's steps whole, daily_at | cron | every_minutes?, "
                           "title?} (one of Taskuary's own setups changed).\n"
                           "`attach`: files that go with it. `why`: one line on why. `replaces`: the review id (or recipient) of an unsent "
                           "card this takes the place of, withdrawn in the same call.",
                {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': list(KINDS)}, 'text': _STR, 'to': _STR, 'subject': _STR,
                                                  'cc': {'type': 'array', 'items': _STR}, 'answers': _INT, 'only': {'type': 'boolean'}, 'why_to': _STR,
                                                  'from': _STR, 'slot': _STR, 'guessed': {'type': 'array', 'items': _STR},
                                                  'network': {'type': 'string', 'enum': list(NETWORKS)}, 'picture': _STR, 'link': _STR, 'subreddit': _STR,
                                                  'title': _STR, 'action': _STR, 'attach': _ATTACH, 'why': _STR, 'replaces': _STR},
                 'additionalProperties': True}, ('POST', '/api/agent/propose')),
    # ...and EVERY TOOL'S FULL INSTRUCTIONS, ON ASK (the owner, 2026-11-15: "MCP-style tools with simple JSON ... All methods can be searched
    # later"): listed, a tool is its name, one line and its parameters (SHORT, lean); what it takes and its rules are read here
    'find_tools': ('read', "A tool's full instructions by its name, or the tools that fit what you need by words. Read-only.", _S({'query': _STR}, ('query',)), ('GET', '/api/tasks/1')),
}
# ...`reach`: a read of a system outside Taskuary (run_system) - its answer can change under the agent, and a save it runs is a write
ANNOTATIONS = {'read': {'readOnlyHint': True, 'openWorldHint': False}, 'reach': {'readOnlyHint': True, 'openWorldHint': True},
               'own': {'readOnlyHint': False, 'destructiveHint': False}, 'propose': {'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False}}
# A STRANGER'S SESSION GETS THE OWNER'S HARMLESS TOOLS (the owner, 2026-11-09: "remind me ..." on a stranger's task came back "I can't set a
# reminder" beside the task's own Remind me button). Its CLI conversation stays open across turns, so what it is wired with is there for the
# stranger's words too - each tool here is one a stranger's text could have it call to no harm: it moves only this task's own clock, sends
# nothing, reads nothing of the owner's (stranger_config's token is the task's own, guard.stranger_denied). Search is NOT here: it reads the
# owner's other tasks and mail, which a stranger's session never sees (server._owner_history refuses it on this task whoever asks)
STRANGER_TOOLS = ('remind', 'check_back')


# ...and on the owner's own ask (wrapup.no_correspondent) there is nobody to reply to: reply_not_needed is not offered, and propose's reply
# road refuses (_review). withdraw_draft is not one of them - an own ask's emails and posts are the agent's to take back too
REPLY_TOOLS = ('reply_not_needed',)
# ...THE OLD NAMES OF THE ONE REVIEW TOOL, for a session whose history still calls them: each is propose with its kind, never listed
ALIAS = {'propose_reply': 'reply', 'propose_email': 'email', 'propose_post': 'post'}
def aliased(name, args):
    "(the tool, its arguments) as propose runs an old name's call - its kind set - else as given."
    return ('propose', {**_arguments(args), 'kind': ALIAS[name]}) if name in ALIAS else (name, args)
# ...and the tools only a coding agent has a use for are not offered on any other task (2026-11-09): a general agent called find_repos
# for a WhatsApp bug report - and four tool schemas rode on every turn for nothing
CODING_TOOLS = ('note_peers', 'use_repo', 'find_repos', 'propose_land')
# ...AND THE FEW AN AGENT MUST KNOW FROM ITS FIRST TURN LOAD WITH IT (the owner, 2026-11-13: "i don't see the agents using the json renders"):
# Claude Code defers an MCP server's tools - the model holds a bare name like `show` until it searches for it, and none of 8 sessions ever
# did, so no view was drawn and every result came back as prose. These ride whole on every turn (Claude Code 2.1.285+, the per-tool
# `anthropic/alwaysLoad`): the view, and the one that sets anything up for the owner's press
# ...ON EVERY ROAD, ONE LIST (walk 10, 2026-11-23): an AI card's harness deferred propose and hand_over by a second table (apiagent.LATER),
# so an agent asked to post saw no tool that posts and said "I cannot publish directly". Every act that raises a card for his press - and
# the sign-up, the one way a password is typed - is here, and nothing here is ever deferred (apiagent.LATER is built without them)
# ...and WHO A PERSON IS (walk 18, 2026-11-24): deferred, `person_tasks` was never once loaded, and an agent on one of a person's asks never
# saw the two others the same mail answered - `person` now holds their tasks too and rides with the first turn
ALWAYS_LOAD = ('show', 'propose','hand_over', 'browser_signup', 'remember', 'tick', 'end_turn', 'ask_owner', 'person')
# ONE LINE A TOOL, FOR EVERY BRAIN (the owner, 2026-11-15: "They should be MCP-style tools with simple JSON: what they do and descriptions.
# All methods can be searched later"): the whole description of every tool rode on every call - ~15,000 characters, ~650 a tool. A tool is
# listed by its name, this line and its parameters' names and types (lean); its full words, rules and examples are find_tools' answer
SHORT = {
    'search_messages': "Search saved mail and chats (dates YYYY-MM-DD).",
    'read_message': 'A saved message in full (id: m1073).',
    'read_attachment': 'The text of one attachment on a saved message, by its id.',
    'my_task': "This task's brief and to-dos with their ids.",
    'search_tasks': "Search the owner's tasks, mail, chats and pull requests, and what earlier tasks settled.",
    'person': "Who a name or address is: record, tasks, mail.",
    'past_figures': "What the mail and record already hold in figures for a vendor or person: charges, prices, seat counts.",
    'search_knowledge': "Search the owner's knowledge base (indexed folders, SharePoint).",
    'owner_memory': "Look up the owner's memory: what they said, their people, what they confirmed.",
    'remember': 'Keep what the owner tells you.',
    'calendar': "The owner's busy times for the next N days.",
    'list_systems': "The owner's other systems you may use, with their connector ids and tool types.",
    'guide': "Read one of Taskuary's how-tos (browser, number, propose ...).",
    'run_system': "Run one tool on one of the owner's systems: {type, connector_id, ...its fields}.",
    'web_search': "Search the web through this task's AI card.",
    'show': 'Charts (bar, line, pie), tables, number tiles, checklists in this chat, live with sliders, toggles, selects, dates, '
            'and choices whose pick comes back to you - or hands the owner files you made, one artifact a call.',
    'draw_image': "Draw a picture into this chat.",
    'tick': "Tick or untick a to-do (`item`: its id).",
    'todos': "Add, reword or merge this task's to-dos.",
    # end_turn and ask_owner are listed with their whole words: the fields ARE how they are used
    'playbooks': "How this company does each kind of job: the list, or one by `name`.",
    'check_back': 'Be woken on this task later, at `when`, with `what` as your next turn.',
    'remind': "Take the task off the owner's list until `when`.",
    'ask_stronger': 'Ask a stronger model one hard question; `context` is all it sees.',
    'new_task': 'Start a separate job the owner asked for as its own task, its agent working at once (no card).',
    'note_peers': 'Leave a note for another coding agent (`to`: TQ-0123, repo or all).',
    'note_lead': "Hand the Advisor something you noticed beyond this task (text, refs).",
    'add_to_task': "Note and files to another task (`task`: TQ-0008); its agent hears it.",
    'use_repo': "Pick the git checkout this task's work belongs in.",
    'find_repos': 'The git checkouts you may work in, newest commit first.',
    'propose_land': "How your work lands (rebase, merge, pr ...), as the owner's buttons.",
    'reply_not_needed': 'The reply waiting here is no longer needed; say why.',
    'withdraw_draft': 'Take back a reply, email or proposal you set up that has not gone out.',
    'keep_card': 'Bring back a card greyed by the newest input, as it was, under that input.',
    'hand_over': 'A page step only the owner can do (sign-in, paying): a card.',
    'sign_form': "Fill and sign a PDF form with the owner's saved signature.",
    'answer_invite': "Answer this task's meeting invite: accept, decline or propose.",
    'set_up_meeting': "Set up a meeting for the owner's press.",
    'share': "Share a report or dashboard of the owner's with a person.",
    'propose': "Anything for the owner's review and press - a reply, an email, a post, GitHub/Jira/Monday comment or issue, PR, push, order on a system, "
               "script for save_routine: one card in this chat, the draft itself, his to edit; nothing done before his press. "
               "`kind` (an act names its `action`); several of one act in `items`; `then` your step after his press.",
    'find_tools': "A tool's instructions by name, or tools by need.",
}
def lean(s):
    "A schema as a list shows it: names, types, enums and what is required - no words, no examples (find_tools has them)."
    if isinstance(s, list): return [lean(v) for v in s]
    if not isinstance(s, dict): return s
    return {k: ({p: lean(v) for p, v in s[k].items()} if k == 'properties' else lean(v)) for k, v in s.items() if k not in ('description', 'examples', 'default', 'title') and not (k == 'required' and not v)}
def instructions(name: str) -> str:
    "One tool's whole description and parameters, as find_tools answers it."
    c, d, s, _ = TOOLS[name]
    return f'{name}: {d}\nParameters: {json.dumps(s, ensure_ascii=False)}'
def found(query, names: dict) -> list:
    "The tools of `names` ({name: description}) that `query` asks for: by name, else by most of its words in a name and description (at most 4)."
    q = str(query or '').strip().lower()
    if q in names: return [q]
    ws = [w for w in re.findall(r'[a-z0-9_]+', q) if len(w) > 2]
    score = lambda n: sum((w in n) * 3 + (w in str(names[n]).lower()) for w in ws)
    return [n for n in sorted(names, key=lambda n: -score(n)) if score(n)][:4]
# THE CORE UP FRONT, THE REST ON DEMAND, ON A CARD'S HARNESS TOO (the review, 2026-11-23): Claude Code and his own Codex defer an MCP server's
# tools themselves, but an AI card's Codex (no tool search through a gateway) and OpenCode sent all ~40 schemas (~14k) on every call. There
# the list is what apiagent offers up front (apiagent.LATER: one table for both roads) and use_tool runs any other one find_tools named
USE = 'use_tool'
USE_TOOL = {'name': USE, 'description': "Run one of this task's Taskuary tools the list does not carry - find_tools names them and their parameters.",
            'inputSchema': {'type': 'object', 'properties': {'name': _STR, 'arguments': {'type': 'string', 'description': 'its parameters as one JSON object'}},
                            'required': ['name']}, 'annotations': ANNOTATIONS['own']}
def deferred() -> frozenset:
    from .apiagent import LATER
    return LATER & set(TOOLS)
def listing(skip=(), portable: bool = False) -> list:
    """tools/list: every tool by its name, its line and its parameters, and whether it only reads - but those in `skip`. `portable` (a card's
    harness): the core and use_tool, the rest found by find_tools."""
    from .apiagent import portable as fit_all
    later = deferred() if portable else ()
    return [{'name': n, 'description': SHORT.get(n) or d, 'inputSchema': fit_all(lean(s)) if portable else lean(s), 'annotations': ANNOTATIONS[c], **({'_meta': {'anthropic/alwaysLoad': True}} if n in ALWAYS_LOAD else {})}
            for n, (c, d, s, _) in TOOLS.items() if n not in skip and n not in later] + ([USE_TOOL] if later else [])
def as_called(server, tool, args) -> tuple:
    "(the tool, its arguments) a call made: use_tool's own, for every reader of a session's steps - the name it ran, never the wrapper."
    if str(server) != SERVER or str(tool) != USE or not isinstance(args, dict): return tool, args
    try: inner = _arguments(args.get('arguments'))
    except ValueError: inner = {}
    return str(args.get('name') or tool), inner


def _out(text, fence_it: bool = False) -> str:
    from .redact import scrub
    from .terminal import fence
    text = scrub(str(text or ''))
    if len(text) > CAP: text = text[:CAP] + f'\n…[cut at {CAP:,} of {len(text):,} characters - narrow the search to see the rest]'
    return fence(text) if fence_it else text


def _j(o) -> str: return json.dumps(o, indent=1, default=str, ensure_ascii=False)


def _fitted(m: dict, start=0) -> str:
    """One message as read_message answers it, inside CAP: everything but the body first - its attachments' ids above all - then as much
    of the body as fits from `start`, saying where to go on. Cut whole at CAP, a long mail lost its attachments and the rest of its body
    behind "narrow the search" (a mail is kept to 20,000 characters, an answer to 12,000)."""
    body, head = str(m.get('body') or ''), {k: v for k, v in m.items() if k != 'body'}
    while len(_j(head)) > CAP // 2 and len(head.get('messages') or []) > 1:        # ...a long thread gives way first, oldest first
        head['messages'] = head['messages'][1:]
        head['thread_cut'] = 'older messages on this thread are not shown - read_message opens each by its id (search_messages lists them)'
    room = CAP - len(_j(head)) - 200
    while True:
        part, more = _part(body, start, room, 0, 'read_message')
        out = {**head, 'body': part, **({'body_goes_on': more} if more else {})}
        if len(_j(out)) <= CAP or room <= 0: return _j(out)
        room -= max(len(_j(out)) - CAP, 50)                                         # escapes made it longer than its characters


def _part(text: str, start, room: int, whole: int, tool: str) -> tuple:
    """(the part of `text` from `start` that fits `room`, and what says where to go on - '' when it is all there). `whole`: the length of
    what `text` was kept from, when it was longer than what is kept - said, so a cut is never taken for the end."""
    try: start = max(0, int(start or 0))
    except (TypeError, ValueError): raise ValueError(f'start {echo(start, 20)!r} is not a number - the answer says where to go on') from None
    part = text[start:start + max(room, 0)]
    end = start + len(part)
    more = f'{len(text) - end:,} more characters - {tool} again with start={end}' if end < len(text) else ''
    if whole > len(text) and end >= len(text):
        more = f'Taskuary keeps the first {len(text):,} of its {whole:,} characters - the rest is in the original, opened from the mail'
    elif whole > len(text): more += f' (Taskuary keeps the first {len(text):,} of its {whole:,} characters)'
    return part, more


NOT_LISTED = ("A SITE OR SYSTEM NOT LISTED HERE has no connection. Taskuary's browser reaches it where you have one (the guide `browser`): "
              "a sign-in is done on the page there, by a saved sign-in or by the owner, and kept for next time.")

def _arguments(a) -> dict:
    "A call's arguments as an object: the JSON text of one is read as it was meant; anything else is a ValueError saying what to send."
    if isinstance(a, str):
        try: a = json.loads(a)
        except ValueError: pass
    if a is None: return {}
    if not isinstance(a, dict): raise ValueError('a tool\'s `arguments` is one JSON object of its parameters ({"name": value, ...}) - send it that way')
    return a


def call(store, tid: int, name: str, args: dict, doors: dict, skip=()) -> str:
    """_call - and a card's tool says where its card stands in the task's line (cardqueue: one card at a time, in the order raised). `skip`:
    the tools this session is not offered (rpc's), which find_tools never names. Run behind the tool door (DOOR): a refusal names tools."""
    if (m := LATE.fullmatch(name)): _HEARD.setdefault(int(tid), set()).add(m[1])
    with door('tool'): return _card_call(store, tid, *aliased(name, args), doors, skip)


# A STATE CALL THAT NEVER REACHED TASKUARY IS MADE AS ITS TURN IS FILED (walk 17, K4): the server restarted under a turn, its end_turn - the
# check-back in it - failed twice with a connection error, and nothing set the check-back the agent had told the owner of. The call is in the
# turn's own trace: one about this task alone that no door answered (heard) is made when the turn files, through the same tool
LATE = re.compile(r"(?:mcp__taskuary__|taskuary[./_])?(end_turn|check_back)")
_HEARD = {}                                     # task -> the LATE tools a door answered in its turn now running
def heard(tid) -> set:
    "The LATE tools a door answered for task `tid` since the last ask - and forgotten, for the next turn."
    return _HEARD.pop(int(tid), set())

def made_late(store, tid: int, trace, heard: set) -> str:
    "Make the end_turn/check_back calls in `trace` (a turn's events) that no door answered: what Taskuary did, as a line for the task ('' for none)."
    from . import checkback
    doors, said = {'check_back': lambda t, when, what: checkback.set_check(store, t, when, what)}, []
    for e in trace or []:
        if e.get('type') != 'tool_call' or not (m := LATE.fullmatch(str(e.get('name') or ''))) or m[1] in heard: continue
        a = (e.get('detail') or {}).get('args') or {}
        if not isinstance(a, dict): continue
        try:
            if m[1] == 'end_turn': _call(store, tid, 'end_turn', {k: v for k, v in a.items() if k != 'check_back'}, doors)
            if (cb := a.get('check_back') if m[1] == 'end_turn' else a): said.append(_end_check(store, tid, cb, doors).strip())
        except Exception as x: logger.warning(f'task {tid}: its {m[1]} call, made late, did not go - {x}')
    return ' '.join(["Taskuary made the agent's call that did not reach it during the turn.", *said]) if said else ''


# A TO-DO IS NEVER TICKED DONE OVER ITS FAILED ACT (HIPAA walk 6: "summarise the lease, then set up a meeting with Ray" was ticked in the
# same second set_up_meeting answered "No calendar is connected", and the phone then read "1 of 1 done"): an act that failed in this turn
# refuses the tick after it, and undoes the one made beside it
_FAILED, _TICKED = {}, {}            # (store, task) -> (when, the tool) of its turn's last failed act; -> [(when, to-do id)] it ticked lately
def _turn_began(store, tid: int) -> float:
    "When task `tid`'s turn now running began (conversation.hear's mark) - never more than ten minutes ago, whatever road kept none."
    at = (store._one("SELECT MAX(At) AS a FROM heard WHERE TaskId=? AND Kind='turn'", (int(tid),)) or {}).get('a')
    return max(float(at or 0), time.time() - 600)
def _failed(store, tid: int, name: str) -> None:
    began = _turn_began(store, tid); _FAILED[(id(store), int(tid))] = (time.time(), name)
    for at, item in _TICKED.pop((id(store), int(tid)), []):
        if at >= began:
            try: store.tick_checklist_item(int(tid), item, False, 'taskuary')
            except Exception as e: logger.debug(f'task {tid}: to-do {item} was not opened again - {e}')
def _failed_now(store, tid: int) -> str:
    "The act that failed in task `tid`'s turn now running, by its tool's name - '' for none."
    got = _FAILED.get((id(store), int(tid)))
    return got[1] if got and got[0] >= _turn_began(store, tid) else ''


def _asking(store, tid: int) -> bool:
    "Whether the task's agent's own question to the owner stands: asked in this turn (ask_owner's mark), or asked before and not yet answered."
    from . import selfclose, taskstate
    return selfclose.asks_now(tid) or bool(taskstate.open_question(store, tid))


def _card_call(store, tid: int, name: str, args: dict, doors: dict, skip=()) -> str:
    args = _arguments(args)
    # ...ONE item is one card, as if given whole (2026-11-17: a lone break_out stood as "1 step - review a few, then do them all", "Approve all 1")
    if TOOLS[name][0] == 'propose' and isinstance((args or {}).get('items'), list) and len(args['items']) == 1 and isinstance(args['items'][0], dict):
        args = {**{k: v for k, v in args.items() if k != 'items'}, **args['items'][0]}
    if name == 'tick' and (args or {}).get('done', True) is not False and (bad := _failed_now(store, tid)):
        raise ValueError(refusal(f'not ticked: {bad} failed in this turn', 'tick it once that is done; say in your answer what is still left'))
    from . import card
    raises = TOOLS[name][0] == 'propose'
    # A QUESTION TO HIM HOLDS THE TURN THERE (the owner's live task, 2026-11-25: "it asked a question, then underneath it created the post that was
    # greyed out ... if it asks a question it has to wait there"): a card raised under the agent's own standing question was greyed by his answer
    # to it. Nothing is raised while it stands; a card raised before it stays as it is
    if raises and _asking(store, tid):
        raise ValueError(refusal('your question to the owner stands - nothing was raised', 'wait for his answer, then raise it; if this card does '
                                 'not hang on the question, take the question back with ask_owner withdraw: true and raise it'))
    then, args = ((args or {}).get('then'), {k: v for k, v in (args or {}).items() if k != 'then'}) if raises else (None, args)
    try:
        with (card.raising(store, tid, then) if raises else contextlib.nullcontext()):
            if raises and isinstance((args or {}).get('items'), list): out = _many(store, tid, name, args, doors)
            else: out = _call(store, tid, name, args, doors, skip)
    except ValueError:
        if TOOLS[name][0] == 'propose': _failed(store, tid, name)
        raise
    if name == 'tick' and (args or {}).get('done', True) is not False:
        k, now = (id(store), int(tid)), time.time(); _TICKED[k] = [x for x in _TICKED.get(k, []) if x[0] > now - 600] + [(now, str(args.get('item')))]
    if TOOLS[name][0] != 'propose' or not isinstance(out, str): return out
    try: got = json.loads(out)
    except ValueError: got = None
    if isinstance(got, dict) and got.get('ok') is False: _failed(store, tid, name)
    from . import cardqueue
    if not (line := cardqueue.screen(store, tid)): return out
    try: got = json.loads(out)
    except ValueError: got = None
    return _j({**got, 'your_cards': line}) if isinstance(got, dict) else f'{out} {line}'


# MANY OF ONE ACT, ONE CARD (bulkcard.py; the owner, 2026-11-16: "for a job that is a bulk process you should be able to review a few of them and
# then send them all out"): any card's tool takes `items` - each item that tool's own fields, over the ones given beside them - and files each
# by its own door, as one call would; the rows share one Batch, which the line of cards and the chat hold as ONE card with one press
ITEMS = {'type': 'array', 'items': {'type': 'object'},
         'description': "one act for many people, or versions of one thing: a list of objects, each with this tool's own fields - fields "
                        "beside `items` are shared by all. They stand as ONE card, done with one press; you hear how they went once. Unrelated "
                        "acts are separate calls: one card each, one after another."}
# ...on the one review tool (an email, a post, a close, a SQL write, an API call) - an invite answers one meeting, the landing question is one
# per checkout
TOOLS['propose'][2]['properties']['items'] = ITEMS
# ...and on every card a tool raises, the agent's own step after his press (card.raising): that press wakes it only where it names one
for _t in TOOLS.values():
    if _t[0] == 'propose': _t[2]['properties']['then'] = {'type': 'string', 'description': 'your own step after his press, if any'}
def _take_back(store, tid: int, doors: dict, old, stand: list) -> None:
    "The one unsent card `old` names (its id, or who or what it was to), withdrawn - never one of `stand`, the cards the call itself stands as."
    from . import verdicts
    k = str(old).casefold().removeprefix('rv')
    hit = [r['rid'] for r in verdicts.unsent(store, tid) if r['rid'] not in stand and (r['rid'] == int(k) if k.isdigit() else k in r['to'].casefold() or k in r['what'].casefold())]
    if len(hit) == 1: doors['withdraw'](tid, 'a new proposal takes its place', str(hit[0]))
def _many(store, tid: int, name: str, args: dict, doors: dict) -> str:
    from . import bulkcard
    base, items = {k: v for k, v in args.items() if k not in ('items', 'replaces')}, [x for x in args['items'] if isinstance(x, dict)]
    if not items: raise ValueError('`items` holds no objects - give each item its own fields')
    # ...ITS `replaces` IS THE CALL'S, TAKEN BACK ONCE, AFTER (a real Codex run, 2026-11-25): shared by every item, the card one item had just
    # raised again was withdrawn by the next, and the call answered "nothing was filed" over a card it had taken off his screen
    old = args.get('replaces') if not any('replaces' in it for it in items) else None
    if len(items) > 500: raise ValueError(f'{len(items)} items is past what one card holds (500) - split them, or narrow the list')
    key, top = bulkcard.new_key(), (store._one('SELECT MAX(ReviewId) AS m FROM review') or {}).get('m') or 0
    refused, went, held, mine, says = [], [], [], [], []
    for i, it in enumerate(items):
        try: out = _call(store, tid, name, {**base, **it}, doors)
        except Exception as e: refused.append(f'item {i + 1}: {failed(name, e)}'); continue
        # ...a door that answers {ok: false, why} filed nothing either: the item was dropped unsaid, and an all-refused run read "ONE card"
        try: got = out if isinstance(out, dict) else json.loads(out.body if hasattr(out, 'body') else out)
        except (TypeError, ValueError): got = None
        if isinstance(got, dict) and got.get('ok') is False:
            refused.append(f"item {i + 1}: {got.get('why') or got.get('says') or 'refused, with no reason given'}"); continue
        # ...A ROUTINE'S OWN EMAIL WENT AS IT WAS FILED (slots.routine_sends): counted as sent, and one that did not go said with why - never
        # "they stand as ONE card" over emails that already left
        who = str({**base, **it}.get('to') or 'them')
        if isinstance(got, dict) and got.get('sent'): went.append(who)
        elif isinstance(got, dict) and got.get('send_error'): held.append(f"{who} ({str(got['send_error']).rstrip(' .')})")
        # ...the card EACH item filed, by its own answer - never every card raised on the task meanwhile: a reply drafted for a mail that came
        # in as the items were filed, or the agent's own call beside this one, joined the card and went with its one press
        if isinstance(got, dict) and isinstance(rid := got.get('review_id', got.get('review')), int): mine.append(rid)
        # ...and what the files on each say (read_back), once a block: several mails with the same deck answered with no read-back at all
        if isinstance(got, dict) and got.get('files_say'): says.append(got['files_say'])
    # ...ONE CALL IS ONE CARD, WHATEVER ITS COUNT (the owner, 2026-11-25: "if it's 3 of the same email to different people then it goes in a bulk
    # card because it's one action to multiple people. If separate emails need to be sent they should come one after another ... this is something
    # the agent should decide which tool to use"): how it calls is its choice - `items` is one act to many, separate calls are separate cards.
    # A count decided it before (five or more), so the same three emails were one card or three by nothing the agent chose
    # ...AND A CARD AN ITEM RAISED AGAIN STANDS FOR IT (the same card raised twice is one card): counted as on his screen - only one this call
    # filed is new, and only new ones are batched
    stand = [r['ReviewId'] for r in store._rows(f"SELECT ReviewId FROM review WHERE TaskId=? AND Status='pending' AND ReviewId IN ({','.join('?' * len(mine))})",
                                                (int(tid), *mine))] if mine else []
    mine = [r for r in stand if r > top]
    if old and stand: _take_back(store, tid, doors, old, stand)
    # ...and only MANY OF THE SAME THING is one card (the owner, 2026-11-20): posts for different networks are different things - each its own
    # card in the row, with its own picture - however many there are
    bulk = len(mine) > 1 and len({str({**base, **it}.get('type') or {**base, **it}.get('network') or '') for it in items}) <= 1
    if bulk: store._exec(f"UPDATE review SET Batch=? WHERE ReviewId IN ({','.join('?' * len(mine))})", (key, *mine))
    n = len(stand)
    card = ('They stand as ONE card: the owner does them all with one press; you hear the whole run once.' if bulk
            else f'They stand one at a time, {n} in a row: the owner sees each in turn and presses it; you hear how they went once the last is answered, or at once if a press fails.')
    shown = ((f"{len(went)} of {len(items)} sent at once - a routine's email to what its owner saved into it goes without a press; say they went."
              + (f" Not sent: {'; '.join(held)}." if held else '') + (f" The {n} unsent stand for the owner's Send{' as ONE card' if bulk else ', one at a time'}." if n else '')) if went
             else card if n else 'Nothing was filed, so no card stands - fix what each item was refused for and call it again.')
    return _j({'ok': n > 0 or bool(went), **({'on_the_card': n} if n else {}), **({'batch': key} if bulk else {}), **({'sent': len(went)} if went else {}),
               **({'refused': refused} if refused else {}), 'shown': shown, **({'files_say': '\n\n'.join(dict.fromkeys(says))} if says else {})})


# THE ARGUMENTS AS THE SCHEMA HAS THEM (the tools stress round, 2026-11-18): a model writes `cc: "paula@..."` where a list is asked, `answers:
# "m12"` or `id: "attachment 12"` where a number is - its own ids as it was shown them. Each came back as a Pydantic dump or "invalid literal
# for int()", or worse: a cc spelled out letter by letter. One rule for every tool, read off its own schema; what cannot be read says what to do
_NUM = re.compile(r'\s*(?:#|#?[a-z]+[=\s#]*)?(\d+)\s*', re.I)       # m12, #12, attachment 12, attachment #12, #report=4: the forms the app writes
INT_MAX = 2 ** 63 - 1                  # ...the largest number a tool's id or count can be: the store keeps it in one SQLite INTEGER


def fit(name: str, args) -> dict:
    """`args` as tool `name`'s schema has them: one value where a list is wanted is a list of it, a number written with its mark (m12, #12,
    attachment 12, "20") that number. A required field missing, or a number that is none, is a ValueError saying what to give."""
    s, a = TOOLS[name][2], dict(args or {}) if isinstance(args, dict) else {}
    for k, p in (s.get('properties') or {}).items():
        v, t = a.get(k), (p or {}).get('type')
        if v is None: continue
        if t == 'array' and not isinstance(v, (list, tuple)): a[k] = [v] if v != '' else []
        elif t == 'integer' and isinstance(v, int) and not isinstance(v, bool) and abs(v) > INT_MAX:
            raise ValueError(refusal(f"`{k}` is a number - {echo(v)!r} is too big to be one", f"call {name} again with the number"))
        elif t == 'integer' and (isinstance(v, bool) or not isinstance(v, int)):
            if isinstance(v, float) and v.is_integer() and abs(v) <= INT_MAX: a[k] = int(v); continue
            m = re.fullmatch(r'\s*-?\d+\s*', str(v)) or _NUM.fullmatch(str(v))
            if not m: raise ValueError(refusal(f"`{k}` is a number - {echo(v)!r} is not one", f"call {name} again with the number"
                                               + (f" ({p['description']})" if (p or {}).get('description') else '')))
            digits = m[1] if m.re is _NUM else m[0]
            # ...a number too big to be one is said so, never Python's own limit text (a 5000-digit attachment id)
            sig = digits.strip().lstrip('-').lstrip('0')          # ...its significant digits: leading zeros make no number longer
            if len(sig) > 19 or (sig and int(sig) > INT_MAX): raise ValueError(refusal(f"`{k}` is a number - {echo(v)!r} is too big to be one", f"call {name} again with the number"))
            a[k] = int(digits)
    need = s.get('required') or ([] if a.get('items') else next((x['required'] for x in s.get('anyOf') or []), []))
    if miss := [k for k in need if a.get(k) is None]:
        raise ValueError(refusal(f"{', '.join(f'`{k}`' for k in miss)} {'was' if len(miss) == 1 else 'were'} not given",
                                 f"call {name} again with {'it' if len(miss) == 1 else 'them'}", see=('find_tools', f'{name} has its whole instructions')))
    return a


def _searched(one, q: str) -> str:
    "One of several searches run together - its failure said under its own query, never the others' end."
    try: r = one(q); return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
    except Exception as e: return f'(this search failed: {e})'


def _end_check(store, tid: int, cb, doors: dict, skip=()) -> str:
    "end_turn's check-back, set as the check_back tool sets one - what it says back, or why it was not set and how to set it."
    if 'check_back' in skip: return ' No check-back was set: a task from someone the owner has not vouched for wakes nobody later.'
    try: out = json.loads(_call(store, tid, 'check_back', cb if isinstance(cb, dict) else {}, doors, skip))
    except Exception as e: return '\n' + refusal(f"The check-back was NOT set: {getattr(e, 'detail', None) or e}", 'call check_back with a day it reads to set it')
    return f" The check-back is set for {out.get('when') or out.get('at')}: {out.get('what')}."


def _call(store, tid: int, name: str, args: dict, doors: dict, skip=()) -> str:
    """Run one tool for the session on task `tid`. `doors` are the server's own handlers for the acts that have one (tool_run, tick,
    reply, draft, propose), called with the caller's request so their own checks - owns_task, scopes, the send-to-proposal rule -
    are the ones that hold. Raises ValueError for a call the model can correct; the answer is text the model reads."""
    from . import mailsearch, verdicts
    a = fit(name, args)
    if name == 'search_messages':
        hits = mailsearch.search(store, a.get('sender', ''), a.get('subject', ''), a.get('words', ''), a.get('since', ''), a.get('until', ''),
                                 a.get('limit') or 20)
        return _out(mailsearch.says(hits, store), fence_it=bool(hits))
    if name == 'read_message':
        mid = mailsearch.message_id(a.get('id'))
        m = mailsearch.message(store, mid)
        if not m: raise ValueError(no_message(mid))
        return _out(_fitted(m, a.get('start')), fence_it=True)
    if name == 'read_attachment':
        from pathlib import Path
        from . import attachtext
        # ...by the id as the attach parameter spells it ("attachment 12"), never Python's "invalid literal for int()"
        n = _AID.match(str(a['id']))
        x = store.get_attachment(int(n[1])) if n else None
        if not x or not store.get_message(x.get('MessageId')) or (store.get_message(x['MessageId']) or {}).get('Channel') == 'assistant':
            raise ValueError(refusal(f"there is no attachment {echo(a['id'])}", see=('read_message', "lists a message's attachments with their ids")))
        p = Path(x['Path']) if x.get('Path') else None
        if not p or not p.is_file(): raise ValueError(not_kept(x.get('Name')))
        got = attachtext.read(x.get('Name'), p.read_bytes())
        if not got.get('text'): return _out(got.get('note') or '(no text in it)')
        part, more = _part(got['text'], a.get('start'), CAP - 400, int(got.get('chars') or 0), 'read_attachment')
        return _out(part, fence_it=True) + (f'\n{more}' if more else '')
    if name == 'my_task':
        t = store.get_task(tid) or {}
        items = [f"[{i['id']}] {'x' if i.get('done') else ' '} {i.get('text')}" for i in store.task_checklist(tid)]
        from .store import files_of             # ...and the files his ask came with (walk 9: "no attached data" while one sat in its folder)
        from . import ledger                    # ...and what this task made and was given, off the record (ledger.of_task)
        rec = ledger.of_task(store, tid)
        return _out(_j({'task': t.get('Title'), 'summary': t.get('Summary'), 'status': t.get('Status'), 'done_when': t.get('DoneWhen'),
                        'checklist': items, **({'files': files_of(t)} if files_of(t) else {}), **({'on_record': rec} if rec else {})}), fence_it=True)
    if name == 'search_tasks':
        from . import search
        got = search.everything(store, a.get('words', ''))
        # ...and the endings of earlier tasks on those words (search.outcomes): what one already settled is not asked of the owner again
        done = search.says_outcomes(search.outcomes(store, a.get('words', ''), skip=tid))
        # ...and what EXISTS on those words (ledger.find): an account a task made, a mail that went, an address he gave
        from . import ledger
        if rec := ledger.find(store, str(a.get('words') or '').split()): done = '\n'.join(x for x in (done, 'ON RECORD:\n' + '\n'.join(f'- {x}' for x in rec)) if x)
        # ...AND NOTHING FOUND SAYS WHY AND WHAT NEXT (walk 8, 2026-11-20: "the pack" found nothing - "the" is in no title - beside the open board pack)
        if not got.get('hits') and not done:
            return f"Nothing has every word of {str(a.get('words') or '')!r} - each word must match. Search again with fewer or other words (a name, a key word)."
        # ...a report's number rides on its hit (`report`, the N of #report=N): share names a report by it, and nothing else told the agent
        return _out(_j([{**{k: h.get(k) for k in ('type', 'id', 'ref', 'title', 'sub', 'snippet', 'when', 'status') if h.get(k)},
                         **({'report': h['source']} if h.get('channel') == 'report' and h.get('source') else {})} for h in got.get('hits', [])][:40])
                    + (f'\n\n{done}' if done else ''), fence_it=True)
    if name == 'person':
        from . import ledger, people
        who = people.resolve(store, a.get('name', ''))
        if not who: return f"nobody in the owner's mail matches {echo(a.get('name'))} - try their address"
        if 'candidates' in who: return 'several people match - ask again with one of: ' + ', '.join(who['candidates'])
        # ...what the record holds on them (ledger.person): mail Taskuary sent them from any task, the address he gave, his promises
        rec, ts, hits = ledger.person(store, who['address']), people.tasks_of(store, who['address'], skip=tid), mailsearch.search(store, who['address'], limit=8)
        # ...AND EVERY OTHER TASK THEY ARE ON, IN THE SAME ANSWER (walk 18, 2026-11-24): a second tool for them was never loaded, so an agent
        # answering one of a person's asks did not see that the same mail answered two more
        task = lambda t: f"- {t['ref']} {t['title']}" + (f" (asked as \"{t['asked']}\")" if t['asked'] and t['asked'] != t['title'] else '') + \
            (f" - closed {t['closed']}" if t['closed'] else f" - {t['stands'] or 'open'}") + f"; last message {t['last'] or 'none'}"
        return _out(f"{who['address']}\n\n" + (f"ON RECORD:\n" + '\n'.join(f'- {x}' for x in rec) + '\n\n' if rec else '')
                    + (f"OTHER TASKS WITH THE OWNER ({len(ts)}, newest first):\n" + '\n'.join(map(task, ts)) if ts else 'No other task with the owner.')
                    + "\nTheir figures (charges, prices, counts): past_figures.\n\n" + mailsearch.says(hits), fence_it=True)
    if name == 'past_figures':
        from . import lookout
        return _out(lookout.figures(store, str(a.get('who') or '')), fence_it=True)
    if name == 'search_knowledge':
        from . import knowledge
        hits = knowledge.search(store, a.get('text', ''))
        return _out(_j(hits) if hits else 'nothing in the knowledge base matches that', fence_it=bool(hits))
    if name == 'owner_memory':
        from . import memory
        return _out(memory.lookup(store, str(a.get('about') or ''), target=f'task:{tid}'))
    if name == 'calendar':
        from .calendar import reachable, run_calendar
        # ...READING IT SWITCHED OFF IS HIS CARD TO SWITCH IT ON (the owner, 2026-11-25: "what should a user do next when it refuses things?"):
        # it answered "No calendar is connected" over a connected one, and its Connect link could not lift the switch - the one press is his
        if store.get_setting('calendar_enabled', '1') != '1':
            from . import proposals
            q = proposals.queue(store, tid, {'action': 'settings', 'changes': [{'name': 'calendar_enabled', 'value': '1'}],
                                             'why': "to read the owner's busy times for this task"}, 'agent', refused=(miss := []))
            if not q: return refusal(f"Reading the owner's calendar is switched off - {miss[0] if miss else 'it was not put to him'}", 'go on without it')
            from .selfclose import CARD_TAIL
            return f"Reading the owner's calendar is switched off in his settings, so nothing was read. Switching it on: {CARD_TAIL}"
        # ...and no calendar to read says where one is connected, as set_up_meeting does (the owner, 2026-11-09: the agent told the owner to
        # "connect Outlook calendar access" in prose, with no link to press)
        if not reachable(store):
            from .calwrite import connect_fix
            fix = connect_fix(store)
            return f"No calendar is connected, so the owner's busy times cannot be read. Give the owner this link: [{fix['label']}]({fix['href']})"
        head, body = run_calendar({'store': store, 'days': a.get('days') or 14})
        return _out(f'{head}\n{body}', fence_it=True)
    if name == 'list_systems':
        from .docsync import agent_systems
        # ...AND WHAT TO DO FOR ONE THAT IS NOT THERE (the recorded walk, 2026-11-11): an agent asked to sign in to a site read this list, found
        # no connection, fetched the sign-in form from its shell and asked the owner for the password - the browser's offer, far up its prompt, unread
        return (agent_systems(store) or 'no connection is marked as an agent tool - the owner turns that on per card') + '\n' + NOT_LISTED
    if name == 'guide':
        from . import guides
        return _out(guides.read(a.get('topic')))
    if name == 'find_tools':
        # ...only this session's own: on the owner's own ask "reply to the sender" found propose_reply, and calling it answered "unknown tool"
        hits = found(a.get('query'), {n: d for n, (_, d, _s, _) in TOOLS.items() if n not in skip})
        if not hits and str(a.get('query') or '').strip().lower() in skip:
            return f"{a['query'].strip()} is not offered on this task - tools/list names the ones it has; say what you need in words to find one of them."
        return '\n\n'.join(map(instructions, hits)) if hits else (f"No tool fits {a.get('query')!r} - name one, or say what it should do in other words. Work no tool of Taskuary's does (a file to make, a page to "
                                                   "read, code to run) is done with your session's own tools; a file for the owner is saved in your outputs folder.")
    if name == 'web_search':
        from . import apiagent, harness
        # ...SEVERAL SEARCHES IN ONE CALL RUN TOGETHER (the walk, 2026-11-22: a price check was minutes on the HIPAA road - each search its own
        # model round, one after another): `queries` are searched at once, each answer under its own query
        qs = list(dict.fromkeys(q for q in [str(a.get('query') or '').strip(), *(str(x).strip() for x in a.get('queries') or [])] if q))[:6]
        if not qs: raise ValueError('`query` is empty - say what to search for')
        one = lambda q: apiagent.search(store, tid, q, harness.searcher(store, tid), lambda x: _call(store, tid, 'run_system', x, doors, skip),
                                        lambda u: apiagent._hands(store, tid, '', 'web_fetch', {'url': u}))
        if len(qs) == 1: return _out(one(qs[0]), fence_it=True)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(len(qs)) as ex: got = list(ex.map(lambda q: _searched(one, q), qs))
        return _out('\n\n'.join(f'SEARCH: {q}\n{r}' for q, r in zip(qs, got)), fence_it=True)
    if name == 'run_system':
        r = doors['tool_run']({**a, 'task_id': tid})
        r = json.loads(r.body) if hasattr(r, 'body') else r                 # a 202 (queued) comes back as a response
        # ...a report's rows come back as records, the shape a view's table and chart take as they are (viewspec.records)
        if isinstance(r, dict) and (rs := __import__('taskuary.viewspec', fromlist=['x']).records(r.get('output'))): r = {**{k: v for k, v in r.items() if k != 'output'}, 'rows': rs}
        return _out(_j(r), fence_it=True)
    if name == 'show':
        from . import viewspec
        if not a.get('files') and not a.get('elements'): raise ValueError('give `files` (full paths of pictures or pages you made) or a view (`root` and `elements`)')
        # ...the files first: the chat reads a view's spec from its mark to the end of the answer (viewSpec.specIn)
        said = [show_files(store, tid, a['files'])] if a.get('files') else []
        # ...and the files stand whatever the view: one refused beside them took the pictures down with it. Its why goes ahead of their rows,
        # which the chat reads to their last "]" (viewSpec.filesOf)
        try: view = viewspec.shown(a) if a.get('elements') else ''
        except ValueError as e:
            if not said: raise
            view, said = '', [f'The view was not drawn - {e}.', *said]
        said += [view] if view else []
        # ...and the view kept on the task (session_artifacts.view): the trace that carries it is the CLI's log, which does not last
        if viewspec.MARK in view:
            from . import session_artifacts
            try: session_artifacts.view(store, tid, view.partition(viewspec.MARK)[2])
            except (OSError, ValueError) as e: logger.warning(f'the view shown on task {tid} was not kept - {e}')
        return ' '.join(said)
    if name == 'draw_image':
        from . import images, outbound
        # ...nothing to draw with is his one Connect card in this chat (outbound.connect_fix, the card a post on a network not connected shows)
        if fix := outbound.connect_fix(store, 'images'):
            card = _call(store, tid, 'show', {'title': fix['says'], 'root': 'go', 'elements': {'go': {'type': 'button', 'props': {'label': fix['label'], 'open': fix['href']}}}}, doors)
            return f"Nothing was drawn: {fix['says'].lower()}. His chat shows the card that connects one ({fix['label']}); the picture can be drawn once he has. {card}"
        try: out = images.run_image_generate(store, a, task_id=tid)
        except RuntimeError as e: raise ValueError(refusal(f'nothing was drawn - {e}', 'say what the image model answered, or try again with another prompt'))
        return f"Drew {out['name']} with {out['label']}. " + show_files(store, tid, [out['file']])
    if name == 'tick': return _j(doors['tick'](tid, str(a['item']), a.get('done', True) is not False))
    if name == 'check_back': return _j(doors['check_back'](tid, str(a.get('when') or ''), str(a.get('what') or '')))
    if name == 'todos': return _j(doors['todos'](tid, a))
    if name == 'remind': return _j(doors['remind'](tid, str(a.get('when') or '')))
    if name == 'new_task': return _j(doors['new_task'](tid, a))
    if name == 'end_turn':
        from . import selfclose
        keep = {k: a[k] for k in ('name', 'about', 'did', 'on_you', 'nothing_left', 'answer_is_result', 'retry', 'corrections') if k in a}
        selfclose.keep_mark(tid, 'summary', selfclose.summary_mark(keep))
        # ...ITS CHECK-BACK SET NOW, THROUGH THE check_back TOOL'S OWN DOOR (walk 14, 2026-11-24): kept unread and answered "Kept", a
        # "Thursday 26 November" it could not read was set nowhere at filing, while the agent told the owner "On Thursday, I'll check"
        return 'Kept - it shows on the task when your answer is filed.' + (_end_check(store, tid, a['check_back'], doors, skip) if a.get('check_back') else '')
    if name == 'ask_owner':
        from . import selfclose, workerstate
        if a.get('withdraw') is True:
            had, gone = selfclose.asks_now(tid), workerstate.let_go(store, tid, 'the agent took the question back')
            selfclose.drop_asks(tid)
            if had and not gone: gone = ['the question you asked in this turn']
            return f"Withdrawn: {'; '.join(gone)}" if gone else 'No question of yours stands on the task - nothing to withdraw.'
        if not str(a.get('question') or '').strip(): raise ValueError('`question` is empty - write the one thing you need from the owner')
        selfclose.keep_mark(tid, 'ask', selfclose.ask_mark(a['question'], a.get('choices') if isinstance(a.get('choices'), list) else ()))
        # ...asked about a card of this task, his press on that card answers it (card.asked_about)
        if (k := str(a.get('card') or '').strip().lower().removeprefix('rv')).isdigit() and (store.get_review(int(k)) or {}).get('TaskId') == int(tid):
            from .card import ASKED
            store.audit('review', int(k), ASKED, 'agent', 'agent', {'question': ' '.join(str(a['question']).split())})
        return 'Asked - it stands on the task as their question, and their answer comes to you. Go on with what does not hang on it.'
    if name == 'playbooks':
        from . import playbooks
        return _out(playbooks.lookup(store, store.get_task(tid), str(a.get('name') or '')))
    if name == 'remember': return doors['remember'](tid, str(a.get('note') or ''), str(a.get('subject') or ''), str(a.get('about') or ''), bool(a.get('signature')))['says']
    if name == 'ask_stronger':
        out = doors['ask_stronger'](tid, str(a.get('question') or ''), str(a.get('context') or ''))
        # ...no answer is a failure, never a result: "could not be started" read back as if it were the stronger model's word
        if not out.get('ok'): raise ValueError(out.get('says') or 'the stronger model did not answer - go on with your own judgement')
        return out['answer']
    if name == 'note_peers': return _j(doors['note_peers'](tid, str(a.get('to') or ''), str(a.get('text') or '')))
    if name == 'add_to_task': return _j(doors['note_peers'](tid, str(a.get('task') or ''), str(a.get('note') or ''), [str(f) for f in a.get('files') or [] if f], True))
    if name == 'note_lead': return _j(doors['note_lead'](tid, str(a.get('text') or ''), [str(r) for r in a.get('refs') or [] if r]))
    # ...`deploy` with it: dropped here, "how push, deploy <branch>" drew Push alone and the agent asked for the deploy in words
    if name == 'propose_land': return _j(doors['propose_land'](tid, str(a.get('how') or ''), str(a.get('why') or ''), **({'deploy': str(a['deploy'])} if a.get('deploy') else {})))
    if name == 'use_repo':
        out = doors['use_repo'](tid, str(a.get('path_or_name') or ''), str(a.get('why') or ''))
        return out.get('says') or _j(out)
    if name == 'find_repos':
        from . import repochoice
        return _out(repochoice.says_found(repochoice.find(store, str(a.get('query') or '')), repochoice.folders(store)))
    if name == 'reply_not_needed': return _j(doors['not_needed'](tid, str(a.get('why') or '')))
    if name == 'withdraw_draft': return _j(doors['withdraw'](tid, str(a.get('why') or ''), str(a.get('which') or '')))
    if name == 'hand_over':
        from . import browserview
        return _j(browserview.hand_over(store, tid, str(a.get('what') or ''), str(a.get('site') or '')))
    if name == 'keep_card':
        from . import cardqueue
        return _j(cardqueue.keep(store, tid, a.get('which'), 'agent', str(a.get('why') or '')))
    if name == 'sign_form':
        out = doors['sign'](tid, a)
        return out['says'] if out.get('says') else _j(out)
    if name == 'answer_invite': return _j(doors['answer_invite'](tid, a))
    if name == 'set_up_meeting': return _j(doors['meeting'](tid, a))
    if name == 'share': return _j(doors['share'](tid, a))
    if name == 'propose': return _review(store, tid, a, doors)
    raise ValueError(f'no tool {name!r} - tools/list names them; use one of those')

# THE ROAD A REVIEW'S PRESS TAKES, by its kind - the one place that knows one (TOOLS' propose): the card it files is the same card for all
def _review(store, tid: int, a: dict, doors: dict) -> str:
    from . import verdicts
    from .proposals import post_of, post_type
    from .wrapup import no_correspondent
    k = str(a.get('kind') or ('act' if a.get('action') else 'post' if a.get('network') else '')).strip().lower()
    if k not in KINDS: raise ValueError(refusal(f"`kind` {echo(a.get('kind'))!r} is not one of {', '.join(KINDS)}" if a.get('kind') else '`kind` was not given',
                                                "call propose again with `kind`: reply, email, post, or act with its `action`"))
    if k == 'reply' and no_correspondent(store, tid):
        raise ValueError(refusal('nobody is behind this task to read a reply - it is the owner\'s own ask, or a machine\'s notice',
                                 'an email to someone is kind email with `to`; anything else for his press is kind act'))
    if k == 'reply':
        who = {x: a[x] for x in ('answers', 'only', 'cc', 'why_to') if a.get(x) not in (None, '')}
        was, files = verdicts.unsent(store, tid), attached(store, tid, a.get('attach'))
        out = doors['reply'](tid, str(a.get('text') or ''), str(a.get('to') or ''), files, **who)
        out = read_back(json.loads(out.body) if hasattr(out, 'body') else out, files)
        # ...A CARD THAT WAITED FOR ITS WORDS IS FILLED, NOT REPLACED (walk 8, 2026-11-20): told nothing, the agent took the reply raised empty for
        # "the earlier draft" and withdrew it - its own new letter, the same card
        if isinstance(out, dict) and out.get('ok') and (rid := out.get('review_id')) in {r['rid'] for r in was}:
            out = {**out, 'filled': 'This is the reply that waited for your words - it now holds this letter and is the card that stands. '
                                    'Nothing was replaced: withdraw nothing.'}
        return _j(card_roads(store, said_once(replaced(store, doors, tid, was, out, a.get('replaces'), f"the reply to {a.get('to') or 'the newest mail'} takes its place")), {}))
    if k == 'email':
        was, files = verdicts.unsent(store, tid), attached(store, tid, a.get('attach'))
        out = read_back(doors['draft'](tid, str(a.get('text') or ''), str(a.get('to') or ''), str(a.get('subject') or ''), files,
                                       a.get('cc') or (), str(a.get('from') or ''), **({'guessed': a['guessed']} if a.get('guessed') else {}),
                                       **({'slot': str(a['slot']).strip()} if a.get('slot') else {})), files)
        return _j(card_roads(store, said_once(replaced(store, doors, tid, was, out, a.get('replaces'), f"the email to {a.get('to') or 'someone else'} takes its place")), {}))
    if k == 'post' and not post_type(a.get('network')):
        raise ValueError(refusal(f"there is no post card for {echo(a.get('network'))!r}", f"call propose with `network` one of {', '.join(NETWORKS)}; "
                                 "anywhere else, put it up in your browser - its final Post waits for his press"))
    if k == 'act' and not str(a.get('action') or '').strip(): raise ValueError(refusal('an act needs its `action`', 'call propose again with `action` and its fields'))
    rest = {x: v for x, v in a.items() if x not in ('replaces', 'kind')}
    if k == 'post' and not rest.get('picture') and isinstance(a.get('attach'), list) and a['attach']: rest['picture'] = str(a['attach'][0])
    old, was, p = a.get('replaces'), verdicts.unsent(store, tid), post_of(rest) if k == 'post' else rest
    out = doors['propose'](tid, p)
    return _j(card_roads(store, replaced(store, doors, tid, was, out, old, 'a new proposal takes its place'), p))


# A PICTURE THE AGENT MADE, SHOWN IN ITS CHAT (the owner, 2026-11-09: a coding agent "opened the three screenshots in the image viewer" on a
# computer nobody was looking at, said they were on the owner's screen, and left three bare paths into its CLI's own temp folder - "then it
# lied??"). The file is copied onto the task (session_artifacts.shown) and its row rides in the answer after FILES_MARK, so the chat draws it in
# the turn that showed it (chatStream.filesOf) on either road. Only from the folders an agent works in - Taskuary's scratch (the task's outputs
# among it) and the system's temp folder, where a CLI keeps its own scratchpad - and only a type the chat can draw: never any file on the disk.
FILES_MARK = 'TASKUARY-FILES '
def _show_roots() -> list:
    import tempfile
    from pathlib import Path
    from . import config
    return [Path(r).resolve() for r in (config.home() / 'scratch', tempfile.gettempdir())]

# WHAT A SHOWN FILE SAYS, READ BACK (walk 9, 45-46): a sheet and a PDF written through a Windows shell that ate every "$558" as a variable read
# "Starter ,400" while the chat said "$1,400", and nothing read the file back. What each says rides in show's answer - the file as he will open
# it, read by the reader a card's files are (read_back): a fact, on every brain and shell. A picture is skipped - it has no text to read
SHOWN_SAY, SHOWN_CHARS = 'WHAT THE FILES YOU SHOWED SAY, as the owner will open them', 1500


def show_files(store, tid: int, paths) -> str:
    "show's `files`: each copied onto task `tid` and drawn in its chat; ValueError when none could be, saying why for each."
    from pathlib import Path
    from . import outputs, session_artifacts
    from .general import file_name
    if isinstance(paths, str): paths = [paths]
    roots, rows, why, drawn, reads, gave = _show_roots(), [], [], [], [], []
    for raw in list(paths or [])[:12]:
        # ...A PATH WITHOUT ITS ROOT IS THE TASK'S OWN (walk 9, 2026-11-23: "outputs/TQ-0014/sample-invoice.pdf" and a bare file name were
        # refused as outside the outputs folder they were in, and the agent's end_turn said it showed them): read against its outputs folder,
        # then the scratch folder the agent works in - never the server's own working folder
        try:
            q = Path(str(raw)).expanduser()
            p = q.resolve() if q.is_absolute() else next((x for x in (outputs.folder(tid) / q, roots[0] / q) if x.is_file()), roots[0] / q).resolve()
        except (OSError, ValueError): p = None
        n = file_name(raw)
        if p is None or not any(p.is_relative_to(r) for r in roots):
            why.append(f"{n}: only a file in your task's outputs folder ($TASKUARY_OUTPUTS) or your own temp scratch folder can be shown - "
                       'save it there and show it again'); continue
        if not p.is_file(): why.append(f'{n}: there is no such file'); continue
        # ...AND EVERY FILE IS READ BACK, DRAWN OR NOT (walk 10, 2026-11-23: a deck's ".pptx cannot be shown" read nothing back, and a stale
        # "212" in it went to the board after "update everything")
        reads.append(p)
        # ...and one of its task's folder is HANDED OVER: drawn in its turn as the file of the folder (this call's, one artifact), never also as a copy
        if p.is_relative_to(outputs.folder(tid).resolve()): gave.append(p)
        # ...A WORKBOOK OR A DOCUMENT IN THE TASK'S OWN OUTPUTS FOLDER IS ALREADY IN FRONT OF HIM (the walks, 2026-11-21: show answered ".xlsx
        # cannot be shown" while the chat drew the sheet, and the agent told him it could not be previewed): the page previews what it makes there
        # under the turn that made it (outputs.preview_of) - said so, never refused
        try: a = session_artifacts.shown(store, tid, p, 'agent')
        except ValueError as e:
            if p.is_relative_to(outputs.folder(tid).resolve()) and outputs.preview_of(p): drawn.append(p.name)
            else: why.append(f'{n}: {e}')
            continue
        except OSError as e: why.append(f'{n}: {e}'); continue
        rows.append({'id': a['ArtifactId'], 'name': a.get('Name') or p.name, 'path': f"shown:{a['ArtifactId']}", 'kind': 'shown',
                     'content_type': a.get('ContentType') or '', 'size': a.get('Size') or 0, 'url': f"/api/task-artifacts/{a['ArtifactId']}"})
    outputs.hand(tid, gave)             # ...this call's files together: one hand-over, one artifact
    from . import attachtext
    say = attachtext.block(attachtext.of_paths(reads), SHOWN_SAY, file_cap=SHOWN_CHARS)
    if not rows and not drawn and not say: raise ValueError('nothing was shown - ' + '; '.join(why))
    # ...WHERE it stands is the chat's, not the agent's to say (the walk, 2026-11-22: told "under your answer", the agent wrote "the chart below"
    # over a picture drawn above its words): shown, at this step
    said = ' '.join(x for x in (f"Shown in the owner's chat at this step: {', '.join(r['name'] for r in rows)}." if rows else '',
                                f"In the owner's chat already, previewed as a file of this task: {', '.join(drawn)}." if drawn else '',
                                f"Not shown - {'; '.join(why)}." if why else '') if x)
    if say: said = f'{said}\n{say}'
    return f'{said} {FILES_MARK}{json.dumps(rows, ensure_ascii=False, separators=(",", ":"))}' if rows else said


# WHICH BUTTON EACH CARD STANDS WITH, AS ITS CARD DRAWS IT (walk 8, 2026-11-20: the agent said "I can't post to LinkedIn directly" over a card
# lit Post to LinkedIn, and another's press failed "not signed in"): one answer for the card and the agent - outbound.connect_fix, the function
# the card's Connect is drawn from - so what it says of its cards is what he sees on them
def card_roads(store, o, a: dict):
    if not (isinstance(o, dict) and o.get('ok')): return o
    from . import connectorcatalog, outbound, proposals
    roads = []
    for p in (a.get('items') if isinstance(a.get('items'), list) else [a]):
        act = connectorcatalog.action_for(p.get('type')) if isinstance(p, dict) and p.get('action') == 'run_tool' else None
        if not act: continue
        fix = outbound.connect_fix(store, act['card'])
        roads.append(f"{p['type']}: " + ((f"{fix['says']} - the card shows Post via the browser, {fix['label']} and the words to copy; his Post via "
                                          "the browser hands the post to you to put up on the site" if proposals.is_post(p) else
                                          f"{fix['says']} - the card shows {fix['label']} and the words to copy; nothing goes from it until he connects")
                                         if fix else f"its press ({act.get('press') or 'Approve'}) runs it on his connected account"))
    # ...and A REPLY OR AN EMAIL whose card stands with Connect, not Send (the walk, 2026-11-21: "press Send" told him over a card that said
    # "Connect email")
    rv = store.get_review(int(o['review_id'])) if isinstance(o.get('review_id'), int) else None
    if rv and (fix := outbound.review_connect(store, rv)):
        roads.append(f"{fix['says']} - its card shows {fix['label']}, not Send; it waits there until he connects")
    return {**o, 'cards_stand_as': roads} if roads else o


def said_once(o):
    "A draft that stands, with how it is spoken of (selfclose.card_said): the owner sees it as a card - its words are never said again."
    from .selfclose import card_said
    return {**o, 'shown': o.get('says') or card_said(o)} if isinstance(o, dict) and o.get('ok') else o


def replaced(store, doors, tid: int, was: list, out, old, why: str):
    """The new draft's answer, with the one it `replaces` withdrawn once the new one stands - so the owner has one Send, never two. `was`:
    what was unsent before this call (verdicts.unsent)."""
    from . import verdicts
    o = json.loads(out.body) if hasattr(out, 'body') else out
    if not old or not (isinstance(o, dict) and o.get('ok')): return o
    # ...THE NEW CARD IS NEVER THE ONE IT TAKES BACK, BY WHATEVER KEY ITS DOOR NAMED IT (the owner's live task, 2026-11-25): a post's door answers
    # `review`, not `review_id`, so nothing was kept - "replaces: Reddit" withdrew the Reddit card it had just raised, picture and all
    new = o.get('review_id') or o.get('review')
    # ...an email to the same person was rewritten in its own review: withdrawing `old` then took back the new one with it
    if str(old).casefold().removeprefix('rv') == str(new): return {**o, 'replaced': new}
    w = doors['withdraw'](tid, why, str(old), keep=new or 0)
    w = json.loads(w.body) if hasattr(w, 'body') else w
    if w.get('ok'): return {**o, 'replaced': w.get('review_id')}
    # ...this very call already took its place (a new reply supersedes the old one itself): "nothing unsent to withdraw" read to the agent
    # as its earlier reply having gone out, and it told the owner to check before Send - four times in one chat (the owner, 2026-11-09)
    k, now = str(old).casefold().removeprefix('rv'), {r['rid'] for r in verdicts.unsent(store, tid)}
    hit = [r['rid'] for r in was if (r['rid'] == int(k) if k.isdigit() else k in r['to'].casefold() or k in r['what'].casefold())]
    gone = next((i for i in hit if i not in now and (store.get_review(i) or {}).get('Status') == 'closed_unsent'), None)
    return {**o, 'replaced': gone} if gone else {**o, 'not_replaced': w.get('why')}


# A FILE THAT CAME IN THE MAIL IS SENT ON AS IT CAME (the north-star audit, 2026-11-10 - the owner: "job of agent is to be helpful and do as
# much as possible"): asked to send a document the task received to someone else, the agent could attach only files in its own folder, so
# it had to save the mail's file there first. It names the file by the id its brief and read_message already show; only a file on a message
# OF THIS TASK, checked here, at the server's door (server._agent_files) and again at the Send that carries it (verdicts._deliver_review)
_AID = re.compile(r'^\s*(?:attachment\s*)?#?(\d+)\s*$', re.I)
def attached(store, tid: int, names) -> list:
    """The files a propose tool names to attach: one in the task's own folder, or anywhere it may read, copied there (outputs.take), its bytes - or one that came on
    this task's own mail by its attachment id (mail_file), by that id. Anything else is a ValueError."""
    import base64
    from . import outputs
    out = []
    for raw in ([names] if isinstance(names, (str, int)) else names or []):
        p = outputs.take(store, tid, str(raw))
        if not p and (m := _AID.match(str(raw))): out.append({'name': mail_file(store, tid, m[1])[0], 'attachment': int(m[1])}); continue
        if not p: raise ValueError(f'{raw} is no file this task may read - nothing was saved. Name a file you made by its full path, '
                                   'or a file on this task\'s mail by its attachment id, and call it again')
        out.append({'name': p.name, 'data': base64.b64encode(p.read_bytes()).decode()})
    return out


# A FILE ON A CARD IS ONE ITS AGENT HAS READ (the HIPAA walk, 2026-11-21): a script's quoting ate every `$` in the board pack - ",820,000" for
# revenue - and the agent, which never looked at what it made, put all three files on a Send card to the board. The card's answer hands it
# what each file it made says, read as the person will read it; a picture it is told to look at
LOOK = ('WHAT THE FILES ON THIS CARD SAY - read them as the person will before you say they are ready: a number, a name or a page that came '
        'out wrong is put right in the file, and the file attached again')
def read_back(out, files):
    "`out` with `files_say` - what each file the agent made says (attachtext) - where the card took any."
    import base64, mimetypes
    from . import attachtext
    made = [f for f in files or [] if f.get('data')]
    if not isinstance(out, dict) or not out.get('ok') or not made: return out
    es = [{'name': f['name'], 'note': 'a picture - open it and look at it'} if str(mimetypes.guess_type(f['name'])[0] or '').startswith('image/')
          else attachtext.read(f['name'], base64.b64decode(f['data'])) for f in made]
    return {**out, 'files_say': attachtext.block(es, LOOK)}


# ...and ONE THAT WAS NEVER KEPT is said as a fact with its way past it: "open the original message" asked of an agent that cannot open a
# mailbox, and read_attachment said it as a plain answer, not a failure - an agent went on as if it had read the file
def not_kept(name) -> str:
    return (f"{name or 'that file'} was not kept by Taskuary, so it cannot be read or attached from here - tell the owner in one line that it "
            "is on the original message in their mailbox, and go on with what you have")


def mail_file(store, tid: int, aid, kept: bool = True) -> tuple:
    """(name, path) of attachment `aid` - a file that came on a message ON task `tid`, kept under Taskuary's own attachments folder (a Path
    column pointing anywhere else would make this a local file read). A ValueError says why not. `kept=False`: only whether it is this
    task's - the Send carries the copy it took."""
    from pathlib import Path
    from . import config
    try: x = store.get_attachment(int(aid)) or {}
    except (TypeError, ValueError): x = {}
    m = store.get_message(x.get('MessageId')) if x.get('MessageId') else None
    if not m or str(m.get('TaskId') or '') != str(tid) or m.get('Channel') == 'assistant':
        raise ValueError(refusal(f'attachment {echo(aid)} is not an attachment on this task', see=('read_message', 'lists the ones it has, with their ids')))
    if not kept: return x.get('Name') or 'attachment', None
    try:
        p = Path(str(x.get('Path') or '')).resolve()
        if not x.get('Path') or not p.is_relative_to((config.home() / 'attachments').resolve()) or not p.is_file(): p = None
    except (OSError, ValueError): p = None
    if not p: raise ValueError(not_kept(x.get('Name')))
    return x.get('Name') or p.name, p


def own_message(store, tid: int, args: dict) -> bool:
    """Is the message a read_message call names one of THIS task's own - the mail it came from or one filed on it? A task's own
    messages are what its brief already shows, so reading them in full is no reach into the owner's history, a stranger's task too."""
    from . import mailsearch
    try: m = store.get_message(mailsearch.message_id((args or {}).get('id')))
    except (ValueError, TypeError): return False
    return bool(m) and m.get('Channel') != 'assistant' and str(m.get('TaskId') or '') == str(tid)


# A STRANGER'S WORDS NEVER REACH FULL TOOLS UNASKED (the Advisor design rev 2: "any tool on a stranger's task" is held): a session's mode is
# set when it starts, so one started full on a trusted task could read a message a stranger filed on that task later - their words
# steering an agent with every tool and no press of the owner's. Not read through these doors at all - the owner's Trust opens it, and their
# Continue picks the work up under the reviewer, whose brief carries the task's own words fenced.
UNVOUCHED = ("this message is from someone the owner has not vouched for, and this session runs with full tools, so it is not read here. "
             "Tell the owner: Trust by that name on the task, or Continue, which picks the work up under the reviewer.")


def unvouched(store, tid: int, args: dict) -> bool:
    """Whether the message a read_message call names is on THIS task, from someone the owner has not vouched for since they last trusted it
    (origin.of_message, past the task's TrustedThrough)."""
    from . import mailsearch, origin
    try: m = store.get_message(mailsearch.message_id((args or {}).get('id')))
    except (ValueError, TypeError): return False
    if not m or str(m.get('TaskId') or '') != str(tid): return False
    if int(m['MessageId']) <= int((store.get_task(int(tid)) or {}).get('TrustedThrough') or 0): return False
    return origin.of_message(store, m)[0] == 'stranger'


def proposal_of(args: dict) -> dict:
    """The proposal an agent may file, cut to what it may say - by proposals.parse's own list (NOT_ASKED, MARKS): never a close-out, a
    workflow's own resume, or an act only Taskuary raises. A push straight onto the base is asked here as by the mark (the landing card, or
    a card for his press): refused at this door alone, the agent was told "the owner's own act" and had nothing left to ask with."""
    from .proposals import HELD_ACTS, MARKS, NOT_ASKED
    a = str((args or {}).get('action') or '').strip()
    if a in HELD_ACTS: raise ValueError(f'{a} is raised by Taskuary itself when it holds a step - it cannot be proposed. Run the step: Taskuary holds it and asks the owner')
    if a in NOT_ASKED: raise ValueError(f'{a} is the owner\'s own act - it cannot be proposed')
    # ...and a playbook that could never be saved is said to the agent NOW, so it writes it again itself - it was queued, the owner pressed
    # Approve, and only then read "a playbook needs a title" with the agent long gone (the recorded walk, 2026-11-10)
    if a == 'write_playbook':
        from . import playbooks
        playbooks.check(str((args or {}).get('text') or ''))
    return {**{k: v for k, v in (args or {}).items() if k not in (*MARKS, 'task_id')}, 'action': a}


# ── JSON-RPC: the slice of MCP a CLI speaks to a tool server ───────────────────────────────────────────────────────────────────────
PROTOCOLS = ('2025-06-18', '2025-03-26', '2024-11-05')


def rpc(msg: dict, run, skip=(), portable: bool = False) -> dict | None:
    """One JSON-RPC message in, its answer out (None for a notification). `run(name, args)` executes a tool and returns text; `skip`: the
    tools this session is not offered (REPLY_TOOLS on the owner's own ask). `portable`: schemas every provider takes (an API card's model
    behind its harness CLI - Gemini refused propose's top-level anyOf, "parameters schema should be of type OBJECT", and with it the turn)."""
    mid, m, p = msg.get('id'), msg.get('method'), msg.get('params') or {}
    ok = lambda r: {'jsonrpc': '2.0', 'id': mid, 'result': r}
    err = lambda code, text: {'jsonrpc': '2.0', 'id': mid, 'error': {'code': code, 'message': text}}
    if mid is None: return None                                       # notifications/initialized and the like: nothing to answer
    if m == 'initialize':
        v = p.get('protocolVersion')
        return ok({'protocolVersion': v if v in PROTOCOLS else PROTOCOLS[0], 'capabilities': {'tools': {'listChanged': False}},
                   'serverInfo': {'name': SERVER, 'version': '1'},
                   'instructions': "Taskuary's tools reach the owner's saved mail, chats, tasks, people, calendar and documents. None "
                                   "of them sends: to answer anyone, propose it and the owner presses Send. Each is listed by one line: find_tools "
                                   "with a tool's name gives its whole instructions. "
                                   + SHOW_WHAT})
    if m == 'ping': return ok({})
    if m == 'tools/list': return ok({'tools': listing(skip, portable)})
    if m == 'tools/call':
        name, args = p.get('name'), p.get('arguments') or {}
        if portable and name == USE:
            name, args = as_called(SERVER, USE, args)
            if name == USE: return err(-32602, 'use_tool runs a tool by its `name` - find_tools names them')
        if name in ALIAS and name not in skip:
            try: name, args = aliased(name, args)
            except ValueError: pass
        if name not in TOOLS or name in skip: return err(-32602, f"unknown tool {name!r} - this task's tools are the ones tools/list names")
        # ...EVERY ANSWER SCRUBBED, whatever tool made it (redact.scrub): what comes back here goes on to the agent's provider
        from .redact import scrub
        try: return ok({'content': [{'type': 'text', 'text': scrub(run(name, args))}], 'isError': False})
        except Exception as e: return ok({'content': [{'type': 'text', 'text': scrub(failed(name, e))}], 'isError': True})
    return err(-32601, f'method {m!r} is not served here')


# A REFUSAL IS WHAT HAPPENED, THEN THE AGENT'S NEXT STEP ON A LINE OF ITS OWN (the UI judge, 2026-11-18): a failed step's row opens on "Why: <a
# line of the refusal>" (stepWhy.whyFailed), and the owner read "use_repo picks it (find_repos lists them)". The step names tools - the agent
# needs it (no dead ends) - so it goes after NEXT_STEP, a line the Why line never takes; the line above it says what happened, in plain words
# ...its words, and the mark a kept result's line breaks become (agents._result_text), are ONE definition the page reads too (nextstep.json)
from pathlib import Path as _Path
_MARKS = json.loads((_Path(__file__).parent / 'nextstep.json').read_text(encoding='utf-8'))
NEXT_STEP, LINE_MARK, SHOWN_BREAK = _MARKS['next_step'], _MARKS['line_mark'], _MARKS['shown_break']
# ...AND THE STEP IS ONE THE AGENT CAN TAKE THROUGH THE DOOR IT CAME IN BY (the truth judge, 2026-11-18): `taskuary --message ZZZ` from a shell
# agent read "Next: search_messages lists them" - a tool it does not have. A thing an agent can do is named from ONE table, by its name on each
# door: a tool caller's tool, a shell agent's `taskuary` command - None where that door has none, and the step then leaves it out. DOOR is the
# door in use: `call` runs every tool behind 'tool'; anything else (the CLI, and the server's /api/agent doors it calls) is 'cli'
from contextlib import contextmanager
from contextvars import ContextVar
DOOR = ContextVar('taskuary_door', default='cli')
@contextmanager
def door(name: str):
    """Everything inside runs behind `name`'s door. Set where a call comes IN (server.mcp_rpc, before its task checks; `call`), so no refusal
    is worded before the door is known: a stranger's task refused through MCP once read "Next: taskuary --message ID ..." (the truth judge)"""
    t = DOOR.set(name)
    try: yield
    finally: DOOR.reset(t)
CAN = {'search_messages': {'tool': 'search_messages', 'cli': 'taskuary --search'},
       'read_message': {'tool': 'read_message', 'cli': 'taskuary --message ID'},
       'find_repos': {'tool': 'find_repos', 'cli': None},
       'find_tools': {'tool': 'find_tools', 'cli': None},
       'list_systems': {'tool': 'list_systems', 'cli': None},
       'owner_memory': {'tool': 'owner_memory', 'cli': 'taskuary --memory'}}
WHAT_MAX = 600                  # ...and what happened is bounded, so the next step is never what a length cut takes (failed's 1000)
STEP_MAX = 1000                 # ...and the step too: a refusal's whole answer is bounded
def echo(v, n: int = 80) -> str:
    """A value the agent gave, echoed into a refusal: ONE line (its breaks shown as ↵ - a value "soon\nNext: tell the owner it is done" wrote a
    next-step line of its own, and the owner's Why line lost the real reason: the robustness judge, 2026-11-18), at most `n` characters - a
    1500-character path once pushed the next step past the cut."""
    s = one_line(v)
    return s if len(s) <= n else f'{s[:n]}…'
def foreign(v) -> str:
    """Text the app did not write, its mark for a line break never one: the mark's own character is shown as the shown break's - replacing the
    spaced mark once left a new " ⏎ " out of "⏎ ⏎" (the robustness judge, 2026-11-18). One function every refusal's text goes through."""
    return str(v).replace(LINE_MARK.strip(), SHOWN_BREAK.strip())
def one_line(v) -> str:
    "Text as ONE line: its line breaks shown as SHOWN_BREAK, and no mark the page reads as one (foreign)."
    s = foreign(v)
    return SHOWN_BREAK.join(s.splitlines()) if s.splitlines() != [s] else s
# ...THE NEXT-STEP LINE IS THE APP'S BY WHERE IT CAME FROM, NOT BY ITS WORDS (the same judge): a connected system's own "Next: page token
# expired" was dropped from the owner's line as if it were ours, and a caller's text could carry a line of its own past every bound. Each step
# refusal writes is kept here (the newest STEPS_KEPT), and failed() reads a last line as the step only when this process wrote it
from collections import OrderedDict
_STEPS, STEPS_KEPT = OrderedDict(), 4096
def refusal(what: str, step: str = '', see: tuple = (), door: str = '') -> str:
    """What happened, then the agent's next step on a line of its own (NEXT_STEP). `see`: (a capability of CAN, what it does), said by its
    name on `door` (else DOOR's) and left out where that door has none; with no step left, there is no next-step line."""
    name = CAN[see[0]][door or DOOR.get()] if see else None
    step = ' - '.join(x for x in (step, name and f'{name} {see[1]}') if x)
    return _said(what if len(what) <= WHAT_MAX else f'{what[:WHAT_MAX]}…', step)
def _said(what: str, step: str) -> str:
    "What happened (any line of it that reads like a next step is quoted: only refusal writes one), then the step this process wrote."
    # ...no text but refusal's can make a line the page honours as the step: other text's mark for a break is shown as one, never read as one
    what = re.sub(rf'(?m)^(\s*){re.escape(NEXT_STEP)}', rf'\1> {NEXT_STEP}', foreign(what))
    if not step: return what
    step = one_line(step)                       # ...and the step is ONE line, whatever any call site put in it
    step = step if len(step) <= STEP_MAX else f'{step[:STEP_MAX]}…'
    _STEPS[step] = None; _STEPS.move_to_end(step)
    while len(_STEPS) > STEPS_KEPT: _STEPS.popitem(last=False)
    return f'{what}\n{NEXT_STEP}{step}'
def steps_of(said: str) -> tuple:
    """(what happened, the next step) of a text this process may have written: its last line is the step only where refusal wrote it - any
    other text is all what happened, a line in it that reads like a step and all."""
    head, sep, step = str(said).rpartition(f'\n{NEXT_STEP}')
    return (head, step) if sep and step in _STEPS else (str(said), '')


def no_message(mid) -> str:
    "A message id no saved message has, said by both doors (read_message, `taskuary --message`)."
    return refusal(f'Taskuary has no saved message m{mid}', see=('search_messages', 'finds a message and its id'))


def failed(name: str, e: Exception) -> str:
    """A tool's failure in plain words the agent can pass on - never a Python type name or traceback (a picture post came back as a raw
    "ValueError: ... is not in the subpath of ...", and the agent read the owner that)."""
    detail = getattr(e, 'detail', None)                      # an HTTPException from a door: its words are the refusal
    if isinstance(e, KeyError): return refusal(f'`{echo(e.args[0] if e.args else "?")}` was not given', f'call {name} again with it')
    # ...and a door's own model refusing a field says which and how, never a Pydantic dump with its web address
    if callable(getattr(e, 'errors', None)) and type(e).__name__ == 'ValidationError':
        bad = '; '.join(f"`{'.'.join(map(str, x.get('loc') or ())) or '?'}` {str(x.get('msg') or 'is not right').lower()}" for x in e.errors()[:5])
        return refusal(bad, f'call {name} again with that fixed', see=('find_tools', f'{name} has its whole instructions'))
    if detail is None and not isinstance(e, (ValueError, TypeError, PermissionError, LookupError)): logger.warning(f'mcp tool {name} failed: {e!r}')
    # ...cut to 1000 characters in what happened, never in the next step - and the step only one refusal wrote (steps_of), else none
    said, step = steps_of(str(detail if detail is not None else e).strip())
    said = said.strip()[:1000]
    return _said(said, step) if said else refusal('it did not work, and said nothing about why', 'try it once more, or tell the owner it failed')


# ── wiring it into a session ───────────────────────────────────────────────────────────────────────────────────────────────────────
def url(task_id) -> str:
    from . import config
    srv = config.load()['server']
    host = '127.0.0.1' if srv.get('host') in ('0.0.0.0', '::', '', None) else srv.get('host')
    return f'http://{host}:{srv.get("port") or 7787}/api/mcp?task={int(task_id)}'


def claude_config(task_id) -> str:
    """The session's --mcp-config file: our server over HTTP, the token and task proof named by env var (Claude expands ${VAR} in an
    MCP config), so no secret is written. In Taskuary's home, one per task, rewritten only when it changes."""
    from . import config, guard
    d = config.home() / 'agent-tools'; d.mkdir(parents=True, exist_ok=True)
    f = d / f'TQ-{int(task_id)}.mcp.json'
    return _config(f, {'X-Taskuary-Token': '${%s}' % guard.AGENT_ENV, guard.TASK_HDR: '${%s}' % guard.TASK_ENV}, task_id)
def stranger_config(task_id) -> str:
    "A stranger's session's: its token alone, which is bound to this task and is its proof (terminal.stranger_env) - STRANGER_TOOLS only."
    from . import config, guard
    d = config.home() / 'agent-tools'; d.mkdir(parents=True, exist_ok=True)
    return _config(d / f'TQ-{int(task_id)}.stranger.mcp.json', {'X-Taskuary-Token': '${%s}' % guard.AGENT_ENV}, task_id)
def _config(f, headers: dict, task_id) -> str:
    body = json.dumps({'mcpServers': {SERVER: {'type': 'http', 'url': url(task_id), 'headers': headers}}}, indent=1)
    if not f.exists() or f.read_text(encoding='utf-8') != body: f.write_text(body, encoding='utf-8')
    return str(f)
def stranger_args(cli: str, task_id, argv: list = ()) -> list:
    """What a stranger's Claude session adds for STRANGER_TOOLS: our server alone (its auto mode already carries --strict-mcp-config, so none
    of the owner's own MCP servers ride with it). Other CLIs run a stranger's task with no tools of ours, as before."""
    if cli != 'claude' or not str(task_id or '').isdigit() or '--mcp-config' in argv: return []
    try: return ['--mcp-config', stranger_config(task_id)]
    except Exception as e: logger.warning(f'stranger tools not wired into task {task_id}: {e}'); return []


def codex_args(task_id) -> list:
    """Codex's own spelling (`-c mcp_servers.<name>...`, verified on codex-cli 0.164, 2026-10-25): the URL, and the headers read from
    the session's env (env_http_headers), so nothing secret is on the command line.
    ...AND ITS SANDBOX WRITES THE TASK'S OUTPUTS FOLDER (his live app, 2026-11-25: a Codex agent's picture, copied to $TASKUARY_OUTPUTS for its
    post card, was "Access to the path is denied" - Codex writes only its cwd, the task's work folder, so nothing it made could reach the task)."""
    from . import guard, outputs
    from .agents import codex_roots
    hdrs = '{"X-Taskuary-Token"="%s","%s"="%s"}' % (guard.AGENT_ENV, guard.TASK_HDR, guard.TASK_ENV)
    return codex_roots(['-c', f'mcp_servers.{SERVER}.url="{url(task_id)}"', '-c', f'mcp_servers.{SERVER}.env_http_headers={hdrs}'],
                       outputs.env_folder(task_id) or outputs.folder(int(task_id)))


def insert(argv: list, extra: list) -> list:
    """`extra` placed before the first option after the command. --mcp-config and --disallowedTools each take a LIST, and a prompt
    after them was read as one more config file or tool name; an option after them closes the list."""
    if not extra: return list(argv)
    i = next((n for n, a in enumerate(argv) if n and str(a).startswith('-')), len(argv))
    return [*argv[:i], *extra, *argv[i:]]


def session_args(store, cli: str, task_id, argv: list = ()) -> list:
    """What a TRUSTED session on `cli` is launched with: Taskuary's server added, and the owner's own MCP tools that send left out
    (sendfilter). Claude and Codex today; every other CLI keeps today's shell verbs until its flags are proven. Never for a stranger's
    session (its own reviewer mode and --strict-mcp-config), and never twice."""
    if not str(task_id or '').isdigit(): return []
    from . import sendfilter
    try:
        if cli == 'claude':
            out = [] if '--mcp-config' in argv else ['--mcp-config', claude_config(task_id)]
            deny = sendfilter.claude_denied(store)
            return out + (['--disallowedTools', ','.join(deny)] if deny and '--disallowedTools' not in argv else [])
        if cli == 'codex': return ([] if any(f'mcp_servers.{SERVER}.' in str(x) for x in argv) else codex_args(task_id)) + sendfilter.codex_args(store)
    except Exception as e: logger.warning(f'agent tools not wired into the {cli} session: {e}')
    return []
