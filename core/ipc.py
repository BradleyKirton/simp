import typing as t

import zmq
import zmq.asyncio


class SubscriberProtocol(t.Protocol):
    async def __call__(self) -> t.AsyncIterator[str]: ...


class Publisher:
    def __init__(self, addr: str) -> None:
        self._ctx = zmq.asyncio.Context.instance()
        self._socket = self._ctx.socket(zmq.PUB)
        self._socket.bind(addr)

    async def __call__(self, data: str) -> None:
        await self._socket.send_string(data)


class Subscriber:
    def __init__(self, addr: str, topics: list[str]) -> None:
        self._ctx = zmq.asyncio.Context.instance()
        self._socket = self._ctx.socket(zmq.SUB)
        self._socket.connect(addr)
        self._poller = zmq.asyncio.Poller()
        self._poller.register(self._socket, zmq.POLLIN)

        for topic in topics:
            self._socket.setsockopt_string(zmq.SUBSCRIBE, topic)

    async def __call__(self) -> t.AsyncIterator[str]:
        events = dict(await self._poller.poll(1000))

        for socket in events:
            yield await socket.recv_string()


publish = Publisher("ipc:///tmp/pubsub")
subscribe = Subscriber("ipc:///tmp/pubsub", topics=[""])
