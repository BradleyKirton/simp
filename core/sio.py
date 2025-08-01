import socketio
from django.core.handlers.wsgi import get_str_from_wsgi
from django.contrib.sessions.backends.db import SessionStore
from django.http.request import QueryDict
from django.conf import settings
from http.cookies import SimpleCookie

sio = socketio.AsyncServer(async_mode="asgi")


def get_session(environ):
    """
    session = get_session(environ=environ)
    username = await session.aget("username", "")
    """
    session_cookie_name = settings.SESSION_COOKIE_NAME
    raw_cookie = get_str_from_wsgi(environ, "HTTP_COOKIE", "")
    cookie = SimpleCookie()
    cookie.load(raw_cookie)
    session_key = cookie.get(session_cookie_name)
    return SessionStore(session_key)


@sio.event
async def connect(sid, environ):
    """
    from django.core.handlers.wsgi import get_str_from_wsgi, get_path_info, get_script_name
    path = get_path_info(environ)
    script_name = get_script_name(environ)
    print(script_name)
    print(path)
    print(environ.keys())
    print(environ["RAW_URI"])
    raw_query_string = get_str_from_wsgi(environ, "QUERY_STRING", "")
    print(raw_query_string)
    query_params = QueryDict(raw_query_string)
    print(query_params)
    """
    raw_query_string = get_str_from_wsgi(environ, "QUERY_STRING", "")
    query_params = QueryDict(raw_query_string)
    username = query_params.get("username", "<unknown>")
    await sio.save_session(sid, {"username": username})
    await sio.enter_room(sid, "tracker")

    participants = sio.manager.get_participants("/", "tracker")
    connected_sids = []

    for sio_sid, _ in participants:
        connected_sids.append(sio_sid)

    await sio.emit(
        "connected",
        {"sid": sid, "username": username, "connectedSids": connected_sids},
    )


@sio.event
async def disconnect(sid, reason):
    session = await sio.get_session(sid)
    username = session["username"]
    await sio.leave_room(sid, "tracker")

    participants = sio.manager.get_participants("/", "tracker")
    connected_sids = []

    for sio_sid, _ in participants:
        connected_sids.append(sio_sid)

    await sio.emit(
        "disconnected",
        {"sid": sid, "username": username, "connectedSids": connected_sids},
    )


@sio.event
async def mousemove(sid, data):
    session = await sio.get_session(sid)
    username = session["username"]
    await sio.emit(
        "mousemove_pub",
        {
            "sid": sid,
            "username": username,
            "clientX": data["clientX"],
            "clientY": data["clientY"],
        },
    )
