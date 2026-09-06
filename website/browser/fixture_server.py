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
if not os.environ.get("TASKUARY_HOME") or os.environ.get("TASKUARY_DEMO") != "1":
    raise RuntimeError("the browser fixture requires an isolated demo home")

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind((HOST, PORT))
listener.listen(128)
listener.setblocking(False)

# Executing this file puts website/browser, rather than the checkout root, first
# on sys.path. Force the fixture to import the code under test from this checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class NoOutboundSocket(socket.socket):
    def connect(self, address):
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

    from taskuary.server import app, store
    from fixture_changes import install_processing_changes
    install_processing_changes(app, store)

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve(sockets=[listener])


if __name__ == "__main__":
    asyncio.run(run())
