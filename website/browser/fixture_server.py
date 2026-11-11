"""Start Taskuary's synthetic demo backend with outbound network fail-closed.

The listener is created before the socket guard is installed.  Uvicorn may accept
fixture browser connections, but application code cannot open a TCP connection to
a connector, model provider, owner server, or local bridge.
"""
from __future__ import annotations

import asyncio
import os
import socket
import sys
from pathlib import Path


HOST = "127.0.0.1"
PORT = int(os.environ["TASKUARY_PORT"])
if PORT in (7787, 7790):
    raise RuntimeError("the browser fixture may not use Taskuary's live ports")
# FRESH: a first start on a machine with nothing set up - not the demo world, still a disposable home and no outbound sockets
FRESH = os.environ.get("TASKUARY_FIXTURE_FRESH") == "1"
if not os.environ.get("TASKUARY_HOME") or (os.environ.get("TASKUARY_DEMO") != "1" and not FRESH):
    raise RuntimeError("the browser fixture requires an isolated demo home")
if FRESH and os.environ.get("TASKUARY_DEMO"):
    raise RuntimeError("a fresh fixture is not the demo")

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind((HOST, PORT))
listener.listen(128)
listener.setblocking(False)

# Executing this file puts website/browser, rather than the checkout root, first
# on sys.path. Force the fixture to import the code under test from this checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _pty_own(address) -> bool:
    """pywinpty reads a Windows pty through a loopback socket it opened itself (ptyprocess._read_in_thread): a coding agent's terminal,
    not a connection out. Only winpty's own call, only to loopback - every other connect stays blocked (browser/agent-presses)."""
    host = address[0] if isinstance(address, tuple) else ""
    return host in ("127.0.0.1", "localhost") and sys._getframe(2).f_globals.get("__name__", "").startswith("winpty")


class NoOutboundSocket(socket.socket):
    def connect(self, address):
        if _pty_own(address): return super().connect(address)
        raise RuntimeError(f"browser fixture blocked outbound socket connection to {address!r}")

    def connect_ex(self, address):
        raise RuntimeError(f"browser fixture blocked outbound socket connection to {address!r}")


def _install_fresh_routes(app, store):
    """The starts no API press makes, shaped as triage makes them (browser/agent-starts-at-once): a quick call that holds the task opening
    for `hold` seconds with no session, then hands it to the agent (quickwork.escalate); or a start queued behind full agent slots."""
    import threading, time
    from fastapi import Body
    from taskuary import general, ingest

    @app.post("/api/fixture/general/start")
    def fixture_general_start(body: dict = Body(...)):
        tid = int(body["taskId"])
        if body.get("queue"):
            store.enqueue_dispatch(tid, None, "assistant", "2 agents are already running")
            store.add_comment(tid, "router", "agent", "Waiting its turn: 2 agents are already running, and it starts by itself when there is room.")
            return {"queued": True}
        general.OPENING.add(tid)
        def escalate():
            try: time.sleep(float(body.get("hold") or 0)); ingest._auto_general(store, tid, deep=True)
            finally: general.OPENING.discard(tid)
        threading.Thread(target=escalate, daemon=True).start()
        return {"opening": True}

    @app.post("/api/fixture/coding")
    def fixture_coding(body: dict = Body(...)):
        """A coding task on a repository of the home's own, its agent the stand-in ACP adapter (tests/fake_acp_server.py), Developer mode on -
        what the Connections and New screens would make, without driving them (browser/coding-line-timeline)."""
        import json, subprocess
        from taskuary import agents
        repo = Path(os.environ["TASKUARY_HOME"]) / "ledger"; repo.mkdir(exist_ok=True)
        (repo / "totals.py").write_text("def total(a, tax):\n    return a + tax\n", encoding="utf-8")
        git = lambda *a: subprocess.run([body.get("git") or "git", "-C", str(repo), *a], check=True, capture_output=True)
        git("init", "-q"); git("config", "user.name", "Alex Doyle"); git("config", "user.email", "alex@northwind.example"); git("add", "."); git("commit", "-qm", "start")
        store.set_setting(agents.DEV_MODE, "1", "owner")
        fake = str(Path(__file__).resolve().parents[2] / "tests" / "fake_acp_server.py")
        # ...under the CLI's own name too: a conversation reopened after a restart starts its session by the name it kept (waitroom.reopen_coding)
        for name in ("coding", "claude"): store.upsert_agent(name, "coding", "cli", json.dumps({"cmd": "claude", "acp_cmd": [sys.executable, fake], "cwd": str(repo)}))
        tid = store.create_task({"Title": body.get("title") or "Comment the ledger totals", "Kind": "coding", "Status": "in_progress"}, "owner")
        return {"taskId": tid, "repo": str(repo)}

    @app.post("/api/fixture/mail-task")
    def fixture_mail_task(body: dict = Body(...)):
        """A task from a mail of Erin Blake's with a reply already drafted for it - the arrival road's draft, waiting (browser/cards-in-their-turn).
        `kind`: the task's kind (general by default; `coding` on the stand-in ACP agent, after /api/fixture/coding)."""
        # ...the owner named, so a colleague on his own domain is no stranger (senders.own_domains)
        store.set_setting("owner_name", "Alex Doyle", "owner"); store.set_setting("owner_email", "alex@northwind.example", "owner")
        tid = store.create_task({"Title": "Vendor review for Erin", "Kind": body.get("kind") or "general", "Status": "open",
                                 "Summary": "Erin Blake asks for our review of the vendor tool"}, "owner")
        mid = store.add_message({"TaskId": tid, "ExternalId": f"fx-{tid}", "Channel": "email", "FromName": "Erin Blake", "FromEmail": "erin@northwind.example",
                                 "ToEmail": "alex@northwind.example", "Subject": "Your review of the tool?", "SentAt": "2026-11-10 08:00:00",
                                 "BodyText": "Hi Alex, could you send me your review of the tool? Thanks, Erin", "Status": "routed"})
        rid = store.add_review({"TaskId": tid, "MessageId": mid, "Kind": "draft_reply", "Status": "pending", "Channel": "email",
                                "DraftText": body.get("draft") or "Hi Erin, here is a long review of every flaw we found in the tool, one by one. Alex"})
        return {"taskId": tid, "reviewId": rid, "messageId": mid}

    @app.post("/api/fixture/session")
    def fixture_session(body: dict = Body(...)):
        "The task's live session put where time would put it: `ended` (closed, forgotten) or `idled` (closed quietly, the next line wakes it)."
        from taskuary import terminal
        tid = int(body["taskId"]); t = general._live_of(tid)
        if t is None: return {"ok": False, "why": "no live session"}
        if body.get("state") == "idled":
            t.last -= 10 ** 6; was = general.idle_for; general.idle_for = lambda: 0
            try: ok = t.idle_out()
            finally: general.idle_for = was
            return {"ok": ok, "why": t.idle_why()}
        t.close(); general.drop_session(tid); terminal.SESSIONS.pop(t.sid, None)
        return {"ok": True}


async def run() -> None:
    # asyncio's Windows wakeup socket exists by the time this coroutine runs. The
    # pre-bound listener above remains the real socket; only later outbound sockets
    # created by application code receive the fail-closed subclass.
    import uvicorn
    socket.socket = NoOutboundSocket
    loop = asyncio.get_running_loop()

    async def no_outbound_connection(*args, **kwargs):
        target = kwargs.get("host") or (args[1] if len(args) > 1 else "unknown")
        raise RuntimeError(f"browser fixture blocked event-loop connection to {target!r}")

    loop.create_connection = no_outbound_connection
    for operation in ("connect", "connect_ex"):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            getattr(probe, operation)((HOST, PORT))
        except RuntimeError as error:
            if "blocked outbound socket" not in str(error):
                raise
        else:
            raise RuntimeError(f"browser fixture socket.{operation} guard is not active")
        finally:
            probe.close()
    try:
        await loop.create_connection(asyncio.Protocol, HOST, PORT)
    except RuntimeError as error:
        if "blocked event-loop connection" not in str(error):
            raise
    else:
        raise RuntimeError("browser fixture event-loop connection guard is not active")
    print("PHASE0_FIXTURE_NETWORK_GUARD=blocked", flush=True)

    if FRESH:
        # the registry's PATH is this box's, never a fresh machine's: the fixture's PATH is all a CLI can be found on
        from taskuary import agents
        agents._fresh_path = lambda: os.environ.get("PATH", "")
    from taskuary.server import app, store
    if FRESH: _install_fresh_routes(app, store)
    if not FRESH:
        from fixture_changes import install_processing_changes
        install_processing_changes(app, store)

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve(sockets=[listener])


if __name__ == "__main__":
    asyncio.run(run())
