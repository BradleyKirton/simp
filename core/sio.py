import socketio


sio = socketio.AsyncServer(async_mode="asgi")


@sio.event
async def connect(sid, environ, auth):
    await sio.emit("connected", {"sid": sid})


@sio.event
async def disconnect(sid, reason):
    await sio.emit("disconnected", {"sid": sid})


@sio.event
async def mousemove(sid, data):
    await sio.emit(
        "mousemove_pub",
        {"sid": sid, "clientX": data["clientX"], "clientY": data["clientY"]},
    )
