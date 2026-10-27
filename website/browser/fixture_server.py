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
    if not FRESH:
        from fixture_changes import install_processing_changes
        install_processing_changes(app, store)

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve(sockets=[listener])


if __name__ == "__main__":
    asyncio.run(run())
