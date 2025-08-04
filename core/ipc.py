import typing as t

import zmq
import zmq.asyncio


class SubscriberProtocol(t.Protocol):
    async def __call__(self) -> t.AsyncIterator[str]: ...


class Publisher:
    def __init__(self, addr: str) -> None:
        self._ctx = zmq.asyncio.Context.instance()
        self._socket = self._ctx.socket(zmq.PUB)
        self._socket.connect(addr)

    async def __call__(self, data: str) -> None:
        await self._socket.send_multipart([b"", data.encode()])


class Subscriber:
    def __init__(self, addr: str, topics: list[str], timeout: int) -> None:
        self._ctx = zmq.asyncio.Context.instance()
        self._addr = addr
        self._topics = topics
        self._timeout = timeout
        self._socket = self._ctx.socket(zmq.SUB)
        self._socket.connect(self._addr)
        self._socket.setsockopt(zmq.RCVTIMEO, self._timeout)
        self._socket.setsockopt(zmq.SUBSCRIBE, b"")

    async def __call__(self) -> str:
        try:
            _, data = await self._socket.recv_multipart()
            return data.decode()
        except zmq.error.Again:
            raise TimeoutError("Socket timeout.")


publish = Publisher("ipc:///tmp/ipcpub")
subscribe = Subscriber("ipc:///tmp/ipcsub", topics=[""], timeout=5000)
