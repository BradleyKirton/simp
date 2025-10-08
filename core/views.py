import asyncio
import dataclasses
import datetime
import random
import time
import typing as t
import uuid

import nats
import ollama
import psycopg
import psycopg_pool
import valkey.asyncio as valkey
from django import forms
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import lorem_ipsum
from django.views import View
from glide import GlideClient, GlideClientConfiguration, NodeAddress
from nats.js.errors import BucketNotFoundError

from core import ipc
from db import aconn
from db import models as db_models


def favicon_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-bold"><path d="M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"></path><path d="M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"></path></svg>',
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
            await client.close()
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


async def datastar_sse_view(request: HttpRequest) -> StreamingHttpResponse:
    async def event_stream() -> t.AsyncIterator[str]:
        yield "event: connected\n"
        yield "data:\n\n"

        while True:
            div_id = random.choice([1, 2, 3, 4, 5])
            colour = random.choice(["blue", "red", "green"])

            yield "event: datastar-patch-elements\n"
            yield "data: mode replace\n"
            yield "data: useViewTransition false\n"
            yield f'data: elements <div id="{div_id}" style="background: {colour}; width: 100px; height: 10px;"></div>\n\n'
            await asyncio.sleep(1.0 / 4.0)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["Connection"] = "keep-alive"
    return response


def datastar_view(request: HttpRequest) -> HttpResponse:
    action = request.GET.get("a", "")

    if action == "get_partial":
        message = random.choice(
            [
                "henlo world",
                "henlo mundo",
                "henlo monde",
                "хенло мир",
                "henlo wereld",
                "הנלו עולם",
                "henlo dünya",
            ]
        )
        return render(request, "core/datastar.html#get_partial", {"message": message})

    return render(request, "core/datastar.html", {})


class SpeculationRulesView(View):
    template_name: str = ""

    def __init__(self, template_name: str, **kwargs: t.Any) -> None:
        super().__init__(**kwargs)
        self.template_name = template_name

    def get(self, request: HttpRequest) -> HttpResponse:
        response = render(request, self.template_name, {})
        # response["Cache-Control"] = "public,max-age=31536000,immutable"
        return response


def service_worker_view(request: HttpRequest) -> HttpResponse:
    return render(request, "core/service_worker.html", {})


def service_worker_js_view(request: HttpRequest) -> HttpResponse:
    return render(request, "core/sw.js", {}, content_type="application/javascript")


CONWAY_GRID = {}
CONWAY_GRID_SIZE = 100


def is_top_row(index: int, size: int) -> bool:
    return index < size


def is_bottom_row(index: int, size: int) -> bool:
    length = size**2
    return (length - size) <= index < length


def is_left_row(index: int, size: int) -> bool:
    return index % size == 0


def is_right_row(index: int, size: int) -> bool:
    return (index + 1) % size == 0


def get_neighbour_indexes(index: int, size: int) -> list[int]:
    is_top = is_top_row(index, size)
    is_bottom = is_bottom_row(index, size)
    is_left = is_left_row(index, size)
    is_right = is_right_row(index, size)

    available_neigbors = ["T", "TR", "R", "BR", "B", "BL", "L", "TL"]
    available_neigbors_top = ["L", "R", "B", "BL", "BR"]
    available_neigbors_bottom = ["L", "R", "T", "TL", "TR"]
    available_neigbors_left = ["T", "R", "B", "TR", "BR"]
    available_neigbors_right = ["T", "L", "B", "TL", "BL"]

    neigbors = set(available_neigbors)

    if is_top:
        neigbors = neigbors & set(available_neigbors_top)
    if is_left:
        neigbors = neigbors & set(available_neigbors_left)
    if is_right:
        neigbors = neigbors & set(available_neigbors_right)
    if is_bottom:
        neigbors = neigbors & set(available_neigbors_bottom)

    neighbour_indexes = []
    for neigbor in neigbors:
        if neigbor == "T":
            neighbour_indexes.append(index - size)
        elif neigbor == "TR":
            neighbour_indexes.append(index - size + 1)
        elif neigbor == "R":
            neighbour_indexes.append(index + 1)
        elif neigbor == "BR":
            neighbour_indexes.append(index + size + 1)
        elif neigbor == "B":
            neighbour_indexes.append(index + size)
        elif neigbor == "BL":
            neighbour_indexes.append(index + size - 1)
        elif neigbor == "L":
            neighbour_indexes.append(index - 1)
        elif neigbor == "TL":
            neighbour_indexes.append(index - size - 1)

    # print("*" * 10)
    # print("index", index)
    # print("is_top", is_top)
    # print("is_bottom", is_bottom)
    # print("is_left", is_left)
    # print("is_right", is_right)
    # print(neigbors)
    # print(neighbour_indexes)
    # print("*" * 10)

    return neighbour_indexes


@dataclasses.dataclass(slots=True, eq=False, repr=False)
class ConwayCell:
    index: int
    value: int
    class_value: str


def process_cell(cell: ConwayCell, neighbours: list[ConwayCell]) -> tuple[int, str]:
    """
    Any live cell with fewer than two live neighbours dies, as if by underpopulation.
    Any live cell with two or three live neighbours lives on to the next generation.
    Any live cell with more than three live neighbours dies, as if by overpopulation.
    Any dead cell with exactly three live neighbours becomes a live cell, as if by reproduction.
    """
    neighbour_live_count = sum(neighbour.value for neighbour in neighbours)
    is_alive = cell.value == 1

    if is_alive and neighbour_live_count < 2:
        return 0, ""
    elif is_alive and neighbour_live_count in (2, 3):
        return 1, "alive"
    elif is_alive and neighbour_live_count > 3:
        return 0, ""
    elif not is_alive and neighbour_live_count == 3:
        return 1, "alive"
    else:
        return 0, ""


async def conway_see_view(request: HttpRequest) -> StreamingHttpResponse:
    async def event_stream() -> t.AsyncIterator[str]:
        global CONWAY_GRID

        yield "event: connected\n"
        yield "data:\n\n"

        tick_counter = 0

        try:
            while True:
                tick_counter += 1
                changes_for_publishing = []

                start_time = time.monotonic()
                for index in range(CONWAY_GRID_SIZE**2):
                    cell_lookup = CONWAY_GRID[index]
                    cell = cell_lookup["self"]
                    neighbours = cell_lookup["neighbours"]

                    new_value, new_class_value = process_cell(cell, neighbours)
                    changes_for_publishing.append((index, new_value, new_class_value))

                total_seconds = time.monotonic() - start_time
                total_milliseconds = total_seconds * 1000
                print("total_milliseconds", f"{total_milliseconds:0.4f}")

                if changes_for_publishing:
                    yield "event: datastar-patch-elements\n"
                    yield "data: mode outer\n"

                    for index, new_value, new_class_value in changes_for_publishing:
                        cell_lookup = CONWAY_GRID[index]
                        cell = cell_lookup["self"]
                        cell.value = new_value
                        cell.class_value = new_class_value

                        element = (
                            f'<div id="{index}" class="cell {new_class_value}"></div>'
                        )
                        yield f"data: elements {element}\n"
                    yield "\n"

                await asyncio.sleep(1 / 5)
        except Exception as ex:
            yield "event: disconnected\n"
            yield "data:\n\n"
            raise ex

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["Connection"] = "keep-alive"
    return response


class ConwayView(View):
    template_name: str = ""

    def get(self, request: HttpRequest) -> HttpResponse:
        global CONWAY_GRID

        CONWAY_GRID = {}
        cells = []
        length = CONWAY_GRID_SIZE**2
        for index in range(length):
            if random.random() < 0.2:
                value = 1
                class_value = "alive"
            else:
                value = 0
                class_value = ""

            cell = ConwayCell(
                index=index,
                value=value,
                class_value=class_value,
            )
            cells.append(cell)
            CONWAY_GRID[index] = {"self": cell}

        for index in range(length):
            neighbour_indexes = get_neighbour_indexes(index, CONWAY_GRID_SIZE)
            neighbours = [
                CONWAY_GRID[neighbour_index]["self"]
                for neighbour_index in neighbour_indexes
            ]
            CONWAY_GRID[index]["neighbours"] = neighbours

        return render(
            request,
            "core/conway.html",
            {"cells": cells, "size": CONWAY_GRID_SIZE},
        )


async def bucket_view(request: HttpRequest) -> HttpResponse:
    nc = await nats.connect(servers=["nats://localhost:4222"])
    js = nc.jetstream()
    try:
        object_store = await js.object_store("stuff")
    except BucketNotFoundError:
        object_store = await js.create_object_store("stuff")

    bucket_status = await object_store.status()

    data = bytes(10000000)
    name = uuid.uuid4()
    info = await object_store.put(f"{name}", data)

    entries = await object_store.list()

    return render(
        request,
        "core/bucket.html",
        {"bucket_status": bucket_status, "info": info, "entries": entries},
    )
