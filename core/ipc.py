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
    def __init__(self, addr: str, topics: list[str], timeout: int) -> None:
        self._ctx = zmq.asyncio.Context.instance()
        self._addr = addr
        self._topics = topics
        self._timeout = timeout
        self._socket = self._ctx.socket(zmq.SUB)
        self._socket.connect(self._addr)
        self._socket.setsockopt(zmq.RCVTIMEO, self._timeout)

        for topic in self._topics:
            self._socket.setsockopt_string(zmq.SUBSCRIBE, topic)

    async def __call__(self) -> str:
        try:
            return await self._socket.recv_string()
        except zmq.error.Again:
            raise TimeoutError("Socket timeout.")


publish = Publisher("ipc:///tmp/pubsub")
subscribe = Subscriber("ipc:///tmp/pubsub", topics=[""], timeout=5000)
