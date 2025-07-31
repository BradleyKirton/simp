import asyncio
import random
import typing as t
import uuid

import ollama
import psycopg
import psycopg_pool
from django import forms
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import lorem_ipsum
from django.views import View

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
    async def stream_events(
        self, pool: psycopg_pool.AsyncConnectionPool[psycopg.AsyncConnection]
    ) -> t.AsyncGenerator:
        yield "event:connected\n"
        yield "data:\n\n"

        async with pool.connection() as conn:
            await conn.execute("LISTEN messages;")

            async for notify in conn.notifies():
                if notify.payload == "stop":
                    break

                yield "event:message\n"
                yield "data:created\n\n"

        yield "event: close\n"
        yield "data:\n\n"

    async def get(self, request: HttpRequest) -> StreamingHttpResponse:
        pool = await aconn.get_connection_pool()
        return StreamingHttpResponse(
            self.stream_events(pool=pool),
            content_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
            },
        )


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
            request, template_name, {"user": username, "messages": messages[::-1]}
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
