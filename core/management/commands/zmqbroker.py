import zmq
import zmq.asyncio
import asyncio

from django.core.management.base import BaseCommand


async def proxy(socket_from, socket_to):
    poller = zmq.asyncio.Poller()
    poller.register(socket_from, zmq.POLLIN)
    poller.register(socket_to, zmq.POLLIN)

    while True:
        events = await poller.poll()
        events = dict(events)

        if socket_from in events:
            print("from")
            msg = await socket_from.recv_multipart()
            await socket_to.send_multipart(msg)

        elif socket_to in events:
            print("to")
            msg = await socket_to.recv_multipart()
            await socket_from.send_multipart(msg)


async def xpub_xsub_proxy() -> None:
    ctx = zmq.asyncio.Context()
    frontend = ctx.socket(zmq.XSUB)
    backend = ctx.socket(zmq.XPUB)

    frontend.bind("ipc:///tmp/ipcsub")
    backend.bind("ipc:///tmp/ipcpub")

    print("Starting broker")
    await proxy(frontend, backend)



class Command(BaseCommand):
    help = "ZMQ pub sub broker."

    def handle(self, *args: object, **options: object) -> None:
        asyncio.run(xpub_xsub_proxy())
