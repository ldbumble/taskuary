"""THE CARD GALLERY'S STAND-INS (browser/card-gallery.mjs; TASKUARY_FIXTURE_GALLERY=1 - a dev tool, never set in CI).

The gallery raises every shape a chat can draw the way an agent does - its own tools over /api/mcp - so what is here is only what an agent
has and a fixture lacks: a task to work on with the headers its CLI would send, the files it would have made in its folder, the end of its
turn, a session whose browser is on a page, and the far ends its presses land on (nothing leaves the machine). The people are invented."""
import json, os, subprocess, time
from pathlib import Path
from types import SimpleNamespace

MD = """# Expense tools for a 40-person team

Three tools compared for **Northwind** - what each costs and where it falls short.

| Plan | Per month | Approval flow |
|---|---:|---|
| Spendly Free | $0 | one approver |
| Payworth Basic | $200 | two steps |
| Payworth Pro | $540 | any number, by amount |

## What I would pick

1. **Payworth Basic** - the cheapest with a real approval flow.
2. Move to Pro only if finance asks for limits by amount.

> Erin's budget covers either. `Spendly Free` has no export.

- [x] Prices checked on each vendor's page
- [ ] Ask Ray about the bus quote
"""


def _png(p: Path, title: str, hue: int, size=(1200, 628)):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, (245, 247, 244)); d = ImageDraw.Draw(im)
    for i, v in enumerate((0.35, 0.6, 0.45, 0.8, 0.7, 0.95)):
        x = 90 + i * (size[0] - 180) // 6; h = int((size[1] - 220) * v)
        d.rectangle([x, size[1] - 90 - h, x + (size[0] - 180) // 8, size[1] - 90], fill=((hue * 37) % 200, 120 + (hue * 53) % 100, 110 + (hue * 91) % 120))
    d.rectangle([60, size[1] - 90, size[0] - 60, size[1] - 86], fill=(60, 70, 60))
    d.text((60, 40), title, fill=(30, 40, 30)); im.save(p)


def _pdf(p: Path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(p), pagesize=letter)
    for n, (head, lines) in enumerate((("Northwind - offsite budget", ["Bus for 40 people, March 12: $1,400", "Venue deposit: $1,500", "Catering: $2,100", "Total: $5,000"]),
                                       ("Page 2 - approvals", ["Erin Blake approves the budget.", "Ray Colton books the bus.", "Paula Vance pays the deposit."])), 1):
        c.setFont("Helvetica-Bold", 20); c.drawString(72, 700, head); c.setFont("Helvetica", 12)
        for i, l in enumerate(lines): c.drawString(72, 660 - 22 * i, l)
        c.drawString(72, 60, f"Page {n} of 2"); c.showPage()
    c.save()


def _pptx(p: Path):
    from pptx import Presentation
    d = Presentation()
    for title, body in (("Ledger portal launch", "Northwind - what goes live Monday"), ("Why now", "Invoices in one place\nApprovals in two steps\nExports to the ledger"),
                        ("Next steps", "Erin: budget\nRay: bus quote\nGail: announce")):
        s = d.slides.add_slide(d.slide_layouts[1]); s.shapes.title.text = title; s.placeholders[1].text = body
    d.save(str(p))


def _xlsx(p: Path, region="North"):
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Invoices"
    ws.append(["Vendor", "Invoice", "Due", "Amount", "Status"])
    for i, v in enumerate(("Payworth", "Trainly", "Spendly", "PhishGuard", "Payworth", "Trainly"), 1): ws.append([v, f"{region[:1]}-{1000 + i}", f"2026-12-{i:02d}", 250.5 * i, "open" if i % 2 else "paid"])
    ws.append(["Total", "", "", "=SUM(D2:D7)", ""])
    s2 = wb.create_sheet("By vendor"); s2.append(["Vendor", "Open"]); [s2.append([v, n]) for v, n in (("Payworth", 2), ("Trainly", 1), ("Spendly", 1))]
    wb.save(str(p))


def _mp4(p: Path):
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=4:size=640x360:rate=24", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(p)], check=True, capture_output=True)


def make(p: Path):
    "One file as an agent's own script would have left it in its folder, by its extension."
    ext = p.suffix.lower()
    if ext == ".md": p.write_text(MD, encoding="utf-8")
    elif ext == ".csv": p.write_text("Vendor,Invoice,Due,Amount\n" + "".join(f"{v},N-{1000 + i},2026-12-{i:02d},{250.5 * i}\n" for i, v in enumerate(("Payworth", "Trainly", "Spendly", "PhishGuard"), 1)), encoding="utf-8")
    elif ext == ".pdf": _pdf(p)
    elif ext == ".pptx": _pptx(p)
    elif ext == ".xlsx": _xlsx(p, p.stem.title())
    elif ext == ".mp4": _mp4(p)
    elif ext == ".png": _png(p, p.stem.replace("-", " "), sum(p.stem.encode()), (1080, 1350) if "tall" in p.stem else (1200, 628))
    elif ext == ".html": p.write_text("<!doctype html><title>Offsite plan</title><h1>Offsite plan</h1><p>March 12 - 40 people - bus at 8:00.</p>", encoding="utf-8")
    else: p.write_text("Northwind offsite: bus at 8:00, 40 people.\n", encoding="utf-8")


def install(app, store):
    from fastapi import Body
    from taskuary import browserview, config, general, guard, outputs, selfclose, terminal, workerstate as ws
    from taskuary import store as store_mod

    @app.post("/api/fixture/gallery/task")
    def gallery_task(body: dict = Body(...)):
        """A task its agent is at work on: the owner's ask (`ask`), a colleague's mail it came from (`mail`: its words; `channel`), where it
        points (`source`). Answers with the headers the agent's CLI posts its tool calls with, and its outputs folder."""
        store_mod.set_owner(store, "Alex Doyle", "alex@northwind.example", "owner")
        tid = store.create_task({"Title": body["title"], "Kind": "general", "Status": "open", "OriginBase": "owner", "SourceRef": body.get("source") or None,
                                 "Summary": body.get("ask") or ""}, "owner")
        mid = body.get("mail") and store.add_message({"TaskId": tid, "ExternalId": f"fx-gallery-{tid}", "Channel": body.get("channel") or "email", "FromName": "Erin Blake",
            "FromEmail": "erin@northwind.example", "ToEmail": "alex@northwind.example", "Subject": body.get("subject") or "Vendor plans", "SentAt": "2026-11-24 08:00:00",
            "BodyText": body["mail"], "Status": "routed"})
        store.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, body.get("ask") or "Set it up for my press.")
        f = outputs.folder(tid); f.mkdir(parents=True, exist_ok=True)
        srv = config.load()["server"]
        return {"taskId": tid, "messageId": mid, "folder": str(f), "headers": {"X-Taskuary-Token": srv["agent_token"], guard.TASK_HDR: guard.task_proof(srv, tid)}}

    @app.post("/api/fixture/gallery/files")
    def gallery_files(body: dict = Body(...)):
        "The files the agent made in its folder (`names`), each real - a PDF of two pages, a deck, a workbook, a clip: their full paths."
        f = outputs.folder(int(body["taskId"])); f.mkdir(parents=True, exist_ok=True)
        for n in body["names"]: make(f / n)
        return {"paths": [str(f / n) for n in body["names"]]}

    @app.post("/api/fixture/gallery/end")
    def gallery_end(body: dict = Body(...)):
        """The agent's turn ends with `text`: each question it asked by its tool is filed as his open question, as the turn's one reader files
        it, and the turn is filed as a chat turn is (general.send_prompt) - its answer, and under it the steps of its trace: each tool call and
        what it was answered (`trace`), which is where the chat reads a view's spec and a shown file's row from."""
        from taskuary import sessionrecord
        tid = int(body["taskId"])
        _said, asks = selfclose.ask_markers(selfclose.take_marks(tid))
        for q, ch in asks: ws.record(store, tid, f"gal{tid}", "input_needed", request_id=ws.request_id_for(q), text=q, choices=ch, source="api")
        rid = store.add_comment(tid, "assistant", general.ASSISTANT_TYPE, body["text"])
        sessionrecord.keep_turn(tid, rid, [e for i, c in enumerate(body.get("trace") or []) for e in (
            {"type": "tool_call", "name": f"mcp__taskuary__{c['name']}", "detail": {"args": c.get("args") or {}, "tool_call_id": f"call{i}"}},
            {"type": "tool_result", "name": f"mcp__taskuary__{c['name']}", "detail": {"tool_call_id": f"call{i}", "result": c.get("result") or "", "is_error": bool(c.get("err"))}})])
        return {"ok": True, "asked": [q for q, _ in asks]}

    # ...the agent itself is the one far end with nobody behind it: every wake of a task's agent - a press with its `then`, an answer - is kept
    # (GET woken) where a model would have taken it, whatever road it would have gone by
    PAGES, WOKEN = {}, []
    general.to_agent = lambda st, t, said="", actor="owner", heard=None, **k: WOKEN.append({"taskId": (t or {}).get("TaskId") if isinstance(t, dict) else t,
                                                                                            "said": str(said)[:400]}) or (heard and heard("woke")) or "woke"

    @app.post("/api/fixture/gallery/session")
    def gallery_session(body: dict = Body(...)):
        "The task's agent as a session at rest (the real class, no CLI started under it), its browser on `url` - what hand_over hands a step over on."
        tid = int(body["taskId"]); sid = f"gal{tid}"
        s = terminal.SESSIONS[sid] = general.GeneralSession(store, tid, sid=sid); s.spoke = True
        if body.get("url"): PAGES[sid] = body["url"]
        if not getattr(browserview.state, "gallery", False):
            real = browserview.state
            def state(s, fresh=False): return {"open": True, "url": PAGES[str(s)], "port": 0} if str(s) in PAGES else real(s, fresh)
            state.gallery = True; browserview.state = state
        return {"ok": True, "sid": sid}

    @app.get("/api/fixture/gallery/woken")
    def gallery_woken(): return {"woken": WOKEN}

    @app.post("/api/fixture/gallery/hold")
    def gallery_hold(body: dict = Body(...)):
        "A shell command of the agent's, heard by the gate its CLI's hook asks (shellgate.check): held as a step for his press, or let run."
        from taskuary import shellgate
        tid = int(body["taskId"])
        return {"answer": shellgate.check(store, tid, f"gal{tid}", body["command"], "Bash", body.get("cwd") or os.environ["TASKUARY_HOME"], about=body.get("about") or "")}

    @app.post("/api/fixture/gallery/world")
    def gallery_world(body: dict = Body(...)):
        """The far ends: `connect` connections made (their type), each write tool of theirs answered by a stand-in that says where it landed;
        `refuse` tools whose press fails, with the words they fail with; `github` a GitHub that takes a comment and a new issue."""
        from taskuary import reports
        ids = {}
        for t in body.get("connect") or []:
            c = store.get_connector_by_type(t)
            ids[t] = store.save_connector({**({"ConnectorId": c["ConnectorId"]} if c else {"Type": t, "Name": f"Northwind {t}"}), "Active": 1, "Secret": "fixture-token", "Roles": "tool",
                                           "ConfigJson": json.dumps({"base_url": f"https://{t}.northwind.example", "email": "alex@northwind.example", "member_name": "Alex Doyle"})}, "owner")
        for tool in body.get("lands") or []:
            reports.REGISTRY[tool] = lambda cfg, tool=tool: (time.sleep(float(body.get("delay") or 0)), {"rows": [{"url": f"https://{tool.split('_')[0]}.example/alex/1"}], "columns": ["url"]})[1]
        for tool, why in (body.get("refuse") or {}).items():
            def refused(_cfg, why=why): raise RuntimeError(why)
            reports.REGISTRY[tool] = refused
        if body.get("github"):
            from taskuary import ci, github
            github.comment_issue = lambda *a, **k: "https://github.example/northwind/ledger/issues/12#issuecomment-1"
            ci._conn = lambda *a, **k: {"Secret": "fixture-token"}
        return {"ok": True, "connectors": ids}

    @app.post("/api/fixture/gallery/checkout")
    def gallery_checkout(body: dict = Body(...)):
        """His checkout, with a remote of its own to push to (a bare one beside it): its folder. With `repo`, the agent's commit made in it -
        after the task that names the checkout began, since a task's own commits are the ones made there since it did (landing.own)."""
        from taskuary import spawn
        G = body.get("git") or "git"
        git = lambda cwd, *a, env=None: subprocess.run([G, "-C", str(cwd), "-c", "user.name=Alex Doyle", "-c", "user.email=alex@northwind.example", *a], check=True, capture_output=True, env=env)
        if body.get("repo"):
            repo, later = Path(body["repo"]), str(int(time.time()) + 5)
            if body.get("branch"): git(repo, "checkout", "-q", "-b", body["branch"])
            (repo / "totals.py").write_text("def total(a): return round(sum(a), 2)\n", encoding="utf-8"); git(repo, "add", ".")
            git(repo, "commit", "-qm", "Keep cents in totals", env={**os.environ, "GIT_COMMITTER_DATE": f"{later} +0000", "GIT_AUTHOR_DATE": f"{later} +0000"})
            return {"repo": str(repo)}
        top = Path(spawn.own_temp("tq-gallery-")); repo, bare = top / "ledger", top / "ledger-origin.git"
        repo.mkdir(exist_ok=True); (repo / "totals.py").write_text("def total(a): return round(sum(a))\n", encoding="utf-8")
        git(repo, "init", "-q", "-b", "master"); git(repo, "add", "."); git(repo, "commit", "-qm", "start")
        git(top, "init", "-q", "--bare", str(bare)); git(repo, "remote", "add", "origin", str(bare)); git(repo, "push", "-q", "origin", "master")
        return {"repo": str(repo)}
