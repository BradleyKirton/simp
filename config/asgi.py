"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import mimetypes
import os

import socketio
from asgiref import typing as t
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.asgi import ASGIHandler, get_asgi_application
from core.sio import sio

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


class PathSendApp:
    def __init__(self, app: ASGIHandler) -> None:
        self.app = app

    async def _handle_websocket(
        self,
        scope: t.WebSocketScope,
        receive: t.ASGIReceiveCallable,
        send: t.ASGISendCallable,
    ) -> None:
        await self.app(
            scope=scope,
            receive=receive,
            send=send,
        )

    async def _handle_http(
        self,
        scope: t.HTTPScope,
        receive: t.ASGIReceiveCallable,
        send: t.ASGISendCallable,
    ) -> None:
        path = scope["path"]

        if not path.startswith(settings.STATIC_URL):
            await self.app(
                scope=scope,
                receive=receive,
                send=send,
            )
        else:
            file_path: str = finders.find(path.removeprefix(settings.STATIC_URL))  # type: ignore

            if file_path:
                content_type, _ = mimetypes.guess_type(file_path)

                if not content_type:
                    content_type = "text/plain"

                content_length = os.path.getsize(file_path)

                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            [b"content-type", f"{content_type}".encode()],
                            [b"content-length", f"{content_length}".encode()],
                            [b"x-served-by", b"PathSend"],
                        ],
                    }  # type: ignore
                )
                await send(
                    {
                        "type": "http.response.pathsend",
                        "path": file_path,
                    }  # type: ignore
                )
            else:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [
                            [b"content-type", b"text/plain"],
                        ],
                    }  # type: ignore
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"404 Not Found",
                        "more_body": False,
                    }  # type: ignore
                )

    async def __call__(
        self,
        scope: t.Scope,
        receive: t.ASGIReceiveCallable,
        send: t.ASGISendCallable,
    ) -> None:
        match scope["type"]:
            case "http":
                await self._handle_http(scope=scope, receive=receive, send=send)
            case "websocket":
                await self._handle_websocket(scope=scope, receive=receive, send=send)
            case unhandled:
                raise ValueError(f"Unhandled ASGI scope {unhandled}")


application = get_asgi_application()
application = PathSendApp(app=application)
application = socketio.ASGIApp(sio, application)
