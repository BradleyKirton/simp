import asyncio
import datetime
import random
import typing as t
import uuid
import ollama
import psycopg
import psycopg_pool
import valkey.asyncio as valkey
from valkey.asyncio.client import PubSub
from django import forms
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import lorem_ipsum
from django.views import View
from glide import GlideClientConfiguration, NodeAddress, GlideClient
from core import ipc
from db import aconn
from db import models as db_models


def favicon_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        b'<svg height="16" width="16" xmlns="http://www.w3.org/2000/svg"><text>E</text></svg>',
        content_type="image/svg+xml",
    )


class IndexView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "core/index.html", {})


class RandomFactView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "core/llm.html", {})


def get_sleep_time() -> float:
    return random.randint(0, 5) / 100


async def stream_view(request: HttpRequest) -> StreamingHttpResponse:
    async def llm_event_stream() -> t.AsyncIterator:
        client = ollama.AsyncClient(
            host=f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}"
        )
        stream: t.AsyncIterator[ollama.ChatResponse] = await client.chat(
            model="qwen3:0.6b",
            messages=[
                {
                    "role": "user",
                    "content": "Generate a random fact.",
                }
            ],
            stream=True,
        )
        async for resp in stream:
            token = resp.message.content
            yield "event: llm\n"
            yield f"data: {token}\n\n"

        yield "event: end\n"
        yield "data:\n\n"

    async def lorem_event_stream() -> t.AsyncIterator:
        paragraphs = lorem_ipsum.paragraphs(2)

        for paragraph in paragraphs:
            tokens = paragraph.split()

            for index, token in enumerate(tokens):
                yield "event: lorem\n"
                yield f"id: {index}\n"
                yield f"data: {token}\n\n"

                await asyncio.sleep(get_sleep_time())

        yield "event: end\n"
        yield "data:\n\n"

    if request.GET.get("t", "") == "lorem":
        event_stream = lorem_event_stream()
    else:
        event_stream = llm_event_stream()

    return StreamingHttpResponse(
        event_stream,
        content_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


class CustomerAddForm(forms.Form):
    name = forms.CharField()
    address = forms.CharField(widget=forms.Textarea())


class CustomerEditForm(forms.Form):
    id = forms.IntegerField(widget=forms.HiddenInput())
    name = forms.CharField()
    address = forms.CharField(widget=forms.Textarea())


class CustomerDeleteForm(forms.Form):
    id = forms.IntegerField()


class SPVIew(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        action = request.POST.get("a", "")
        event_name = ""

        if action == "create":
            customer_form = CustomerAddForm(request.POST)
            template_name = "core/spi.html#create_customer"
        elif action == "edit":
            customer_form = CustomerEditForm(request.POST)
            template_name = "core/spi.html#edit_customer"
        elif action == "delete":
            customer_form = CustomerDeleteForm(request.POST)
            template_name = "core/spi.html#delete_customer"
        else:
            raise Exception(":(")

        if not customer_form.is_valid():
            context = {"customer_form": customer_form}
            return render(request, template_name, context)

        if action == "create":
            name = customer_form.cleaned_data["name"]
            address = customer_form.cleaned_data["address"]
            db_models.Customer.new(name=name, address=address)
            event_name = "CustomerCreated"
        elif action == "edit":
            pk = customer_form.cleaned_data["id"]
            name = customer_form.cleaned_data["name"]
            address = customer_form.cleaned_data["address"]
            customer = get_object_or_404(db_models.Customer, pk=pk)
            customer.update(name=name, address=address)
            event_name = "CustomerUpdated"
        elif action == "delete":
            pk = customer_form.cleaned_data["id"]
            customer = get_object_or_404(db_models.Customer, pk=pk)
            customer.delete()
            event_name = "CustomerDeleted"

        context = {"customer_form": None}
        response = render(request, template_name, context)
        response["HX-Trigger-After-Swap"] = event_name
        return response

    def get(self, request: HttpRequest) -> HttpResponse:
        action = request.GET.get("a", "")

        if action == "create":
            customer_form = CustomerAddForm()
            template_name = "core/spi.html#create_customer"
        elif action == "edit":
            customer = get_object_or_404(
                db_models.Customer, pk=request.GET.get("customer_id", 0)
            )
            initial = {
                "id": customer.pk,
                "name": customer.name,
                "address": customer.address,
            }
            customer_form = CustomerEditForm(initial=initial)
            template_name = "core/spi.html#edit_customer"
        elif action == "delete":
            customer = get_object_or_404(
                db_models.Customer, pk=request.GET.get("customer_id", 0)
            )
            initial = {
                "id": customer.pk,
                "name": customer.name,
                "address": customer.address,
            }
            customer_form = CustomerEditForm(initial=initial)
            template_name = "core/spi.html#delete_customer"
        elif action == "list":
            template_name = "core/spi.html#customers"
            customer_form = None
        else:
            template_name = "core/spi.html"
            customer_form = None

        customers = db_models.Customer.objects.all().order_by("name")
        context = {
            "customer_form": customer_form,
            "customers": customers,
        }
        return render(request, template_name, context)


class ChatEventView(View):
    async def event_stream(
        self, pool: psycopg_pool.AsyncConnectionPool[psycopg.AsyncConnection]
    ) -> t.AsyncGenerator:
        yield "event:connected\n"
        yield "data:\n\n"

        async with pool.connection() as conn:
            await conn.execute("LISTEN messages;")

            async for notify in conn.notifies():
                if notify.payload == "stop":
                    break

                task_count = len(asyncio.all_tasks())
                yield "event:message\n"
                yield f"data:{task_count}\n\n"

        yield "event: close\n"
        yield "data:\n\n"

    async def get(self, request: HttpRequest) -> StreamingHttpResponse:
        pool = await aconn.get_connection_pool()
        response = StreamingHttpResponse(
            self.event_stream(pool=pool), content_type="text/event-stream"
        )
        response["Cache-Control"] = "nocache"
        response["Connection"] = "keep-alive"
        return response


class ChatForm(forms.Form):
    user = forms.CharField()
    content = forms.CharField()


class ChatView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        messages = db_models.Message.objects.all().order_by("-created_at")[:13]
        is_htmx_request = request.headers.get("HX-Request", "false") == "true"

        if is_htmx_request:
            template_name = "core/chat.html#messages"
        else:
            template_name = "core/chat.html"

        if "username" not in request.session:
            guid = uuid.uuid4()
            username = request.session["username"] = guid.hex
        else:
            username = request.session["username"]

        return render(
            request,
            template_name,
            {"user": username, "messages": messages[::-1]},
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        form = ChatForm(data=request.POST)

        if form.is_valid():
            user = form.cleaned_data["user"]
            content = form.cleaned_data["content"]
            db_models.Message.objects.create(user=user, content=content)
            request.session["username"] = user

            with connection.cursor() as cursor:
                cursor.execute("NOTIFY messages")

        return HttpResponse(b"")


class SioView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if "username" not in request.session:
            username = f"{uuid.uuid4()}"
            request.session["username"] = username
        else:
            username = request.session["username"]
        return render(request, "core/sio.html", {"username": username})


class ZmqIpcStreamView(View):
    async def stream_events(self) -> t.AsyncGenerator:
        yield "event:connected\n"
        yield "data:\n\n"

        should_subscribe = True

        while should_subscribe:
            try:
                data = await ipc.subscribe()

                if data == "break":
                    should_subscribe = False
                    break

                yield "event:current_time\n"
                yield "data:current_time\n\n"
            except TimeoutError:
                yield "event:ping\n"
                yield "data:ping\n\n"

        yield "event:disconnected\n"
        yield "data:\n\n"

    async def get(self, request: HttpRequest) -> StreamingHttpResponse:
        return StreamingHttpResponse(
            self.stream_events(),
            content_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )


class ZmqIpcView(View):
    async def get(self, request: HttpRequest) -> HttpResponse:
        if request.GET.get("p", "") == "current_time":
            template_name = "core/zmq_pubsub.html#current_time"
        else:
            template_name = "core/zmq_pubsub.html"

        current_time = datetime.datetime.now()

        return render(
            request, template_name, {"current_time": current_time.isoformat()}
        )

    async def post(self, request: HttpRequest) -> HttpResponse:
        await ipc.publish("SUCCESS")
        return HttpResponse(b"")


async def task_count_sse(request: HttpRequest) -> StreamingHttpResponse:
    async def event_stream() -> t.AsyncGenerator:
        yield "event: connected\n"
        yield "data: connected\n\n"

        while True:
            await asyncio.sleep(1)

            yield "event: ping\n"
            yield "data: ping\n\n"

    stream = event_stream()
    response = StreamingHttpResponse(stream, content_type="text/event-stream")
    response["Connection"] = "keep-alive"
    response["Cache-Control"] = "no-cache"
    return response


class TaskCountSSEView(View):
    async def event_stream(self, client: GlideClient) -> t.AsyncGenerator:
        try:
            yield "event: connected\n"
            yield "data: connected\n\n"

            while True:
                guid = uuid.uuid4()
                yield "event: message\n"
                yield f"data: {guid.hex}\n\n"

                await asyncio.sleep(1)
        finally:
            await client.close()

    async def get(self, request: HttpRequest) -> StreamingHttpResponse:
        addresses = [NodeAddress("localhost", 6379)]
        config = GlideClientConfiguration(addresses, request_timeout=500)
        client = await GlideClient.create(config)
        stream = self.event_stream(client)
        response = StreamingHttpResponse(stream, content_type="text/event-stream")
        response["Connection"] = "keep-alive"
        response["Cache-Control"] = "no-cache"
        return response


class TaskCountView(View):
    async def get(self, request: HttpRequest) -> HttpResponse:
        task_count = len(asyncio.all_tasks())
        return render(
            request,
            "core/task_count.html",
            {"task_count": task_count},
        )


class ValKeyIpcStreamView(View):
    async def event_stream(self, client: GlideClient) -> t.AsyncGenerator:
        try:
            yield "event:connected\n"
            yield "data:\n\n"

            while True:
                data = await client.get_pubsub_message()

                if data.message == b"break":
                    break

                yield "event:current_time\n"
                yield "data:current_time\n\n"

            yield "event:disconnected\n"
            yield "data:\n\n"

        finally:
            await client.close()

    async def get(self, request: HttpRequest) -> StreamingHttpResponse:
        _ = await request.session.aget("username")  # type: ignore
        addresses = [NodeAddress("localhost", 6379)]
        PubSubSubscriptions = GlideClientConfiguration.PubSubSubscriptions
        PubSubChannelModes = GlideClientConfiguration.PubSubChannelModes
        pubsub_subscriptions = PubSubSubscriptions(
            {PubSubChannelModes.Exact: set(["ipc"])},
            callback=None,
            context=None,
        )
        config = GlideClientConfiguration(
            addresses, request_timeout=500, pubsub_subscriptions=pubsub_subscriptions
        )
        client = await GlideClient.create(config)
        response = StreamingHttpResponse(
            self.event_stream(client),
            content_type="text/event-stream",
        )
        response["Connection"] = "keep-alive"
        response["Cache-Control"] = "no-cache"
        return response


class ValKeyIpcView(View):
    async def get(self, request: HttpRequest) -> HttpResponse:
        if request.GET.get("p", "") == "current_time":
            username = await request.session.aget("username")  # type: ignore
            template_name = "core/valkey_pubsub.html#current_time"
        elif request.GET.get("p", "") == "pong":
            addresses = [NodeAddress("localhost", 6379)]
            config = GlideClientConfiguration(addresses, request_timeout=500)
            client = await GlideClient.create(config)
            ponged_at = datetime.datetime.now(datetime.UTC)
            username = await request.session.aget("username")  # type: ignore
            await client.publish(ponged_at.isoformat(), f"username:{username}")
            return HttpResponse(b"")
        else:
            username = uuid.uuid4()
            template_name = "core/valkey_pubsub.html"
            await request.session.aset("username", f"{username.hex}")  # type: ignore

        task_count = len(asyncio.all_tasks())
        current_time = datetime.datetime.now()
        return render(
            request,
            template_name,
            {
                "current_time": current_time.isoformat(),
                "username": username,
                "task_count": task_count,
            },
        )

    async def post(self, request: HttpRequest) -> HttpResponse:
        addresses = [NodeAddress("localhost", 6379)]
        config = GlideClientConfiguration(addresses, request_timeout=500)
        client = await GlideClient.create(config)
        await client.publish("", "ipc")
        await client.close()
        return HttpResponse(b"")


valkey_pool = valkey.ConnectionPool(host="localhost", port=6379)


async def valkey_stream(request: HttpRequest) -> StreamingHttpResponse:
    async def event_stream() -> t.AsyncIterator:
        yield "event: connected\n"
        yield "data:\n\n"

        conn = valkey.Valkey.from_pool(valkey_pool)
        async with conn.pubsub() as pubsub:
            await pubsub.subscribe("channel:ipc")

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True)

                if message is None:
                    continue

                data = message["data"].decode()

                if data == "break":
                    break

                current_time = datetime.datetime.now()
                current_time_serialized = current_time.isoformat()
                yield "event: current_time\n"
                yield f"data: {current_time_serialized}\n\n"

        yield "event:disconnected\n"
        yield "data:\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["Connection"] = "keep-alive"
    return response


async def valkey_view(request: HttpRequest) -> HttpResponse:
    task_count = len(asyncio.all_tasks())
    return render(request, "core/pyvalkey_pubsub.html", {"task_count": task_count})
