import asyncio
import random
import typing as t

import ollama
from django import forms
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.template import Context, Template
from django.utils import lorem_ipsum
from django.views import View
from core import models as core_models


def favicon_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        b'<svg height="16" width="16" xmlns="http://www.w3.org/2000/svg"><text>E</text></svg>',
        content_type="image/svg+xml",
    )


class IndexView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        template_raw = """
        <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Experiments</title>
                <link rel="icon" href="{% url 'favicon' %}" type="image/x-icon">
                <script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.6/dist/htmx.min.js"></script>
            </head>
            <body>
                <h1>Hello World</h1>
                <p>This project contains some experiments with:</p>
                <ul>
                    <li>Nginx Unit for serving Django ASGI applications</li>
                    <li>SSE and LLM integration</li>
                    <li>UV for package management within containerized builds</li>
                    <li>Multi stage container builds</li>
                    <li>Django template partials and HTMX</li>
                    <li>
                        <a href="https://github.com/nearform/temporal_tables/blob/master/versioning_function.sql">Temporal tables</a>
                    </li>
                </ul>
                <a href="{% url 'fact' %}">Fact over sse</a>
            </body>
        </html>
        """
        template = Template(template_raw)
        context = Context({})
        content = template.render(context=context)
        return HttpResponse(content.encode())


class RandomFactView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        template_raw = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link rel="icon" href="{% url 'favicon' %}" type="image/x-icon">
            <title>Experiments</title>
        </head>
        <body>
            <h1>Random Fact Generator</h1>
            <div id="stream"></div>
            <script>
                const evtSource = new EventSource("{% url 'sse' %}", { withCredentials: true });
                const streamElement = document.getElementById("stream");

                var thinking = false;
                var containerElement = streamElement;
                evtSource.addEventListener("llm", (e) => {
                    let span = document.createElement("span");

                    if ( e.data == "<think>" ) {
                        thinking = true;
                        containerElement = document.createElement("div");
                        containerElement.style = 'border: 1px solid black; padding: 1px;';
                        streamElement.appendChild(containerElement);
                        span.innerText = "🤔";
                        containerElement.appendChild(span);
                    } else if ( e.data == "</think>" ) {
                        thinking = false;
                        span.innerText = "🤔";
                        containerElement.appendChild(span);
                        containerElement = streamElement;
                    } else {                    
                        span.innerText = e.data;
                        containerElement.appendChild(span);
                    }
                })
                evtSource.addEventListener("lorem", (e) => {
                    let span = document.createElement("span");
                    let space = document.createElement("span");
                    space.innerText = " ";
                    span.innerText = e.data;
                    containerElement.appendChild(span);
                    containerElement.appendChild(space);
                })
                evtSource.addEventListener("end", (e) => {
                    evtSource.close();
                })
                evtSource.addEventListener("error", (e) => {
                  console.error(e);
                });
            </script>
        </body>
        </html>
        """
        template = Template(template_raw)
        context = Context({})
        content = template.render(context=context)
        return HttpResponse(content.encode())


def get_sleep_time() -> float:
    return random.randint(0, 5) / 100


async def stream_view(request: HttpRequest) -> StreamingHttpResponse:
    async def llm_event_stream() -> t.AsyncIterator:
        client = ollama.AsyncClient(host="http://localhost:11434")
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
        print(action)
        if action == "create":
            customer_form = CustomerAddForm(request.POST)
            template_name = "core/index.html#create_customer"
        elif action == "edit":
            customer_form = CustomerEditForm(request.POST)
            template_name = "core/index.html#edit_customer"
        elif action == "delete":
            customer_form = CustomerDeleteForm(request.POST)
            template_name = "core/index.html#delete_customer"
        else:
            raise Exception(":(")

        if not customer_form.is_valid():
            context = {"customer_form": customer_form}
            return render(request, template_name, context)

        if action == "create":
            name = customer_form.cleaned_data["name"]
            address = customer_form.cleaned_data["address"]
            core_models.Customer.new(name=name, address=address)
            event_name = "CustomerCreated"
        elif action == "edit":
            pk = customer_form.cleaned_data["id"]
            name = customer_form.cleaned_data["name"]
            address = customer_form.cleaned_data["address"]
            customer = get_object_or_404(core_models.Customer, pk=pk)
            customer.update(name=name, address=address)
            event_name = "CustomerUpdated"
        elif action == "delete":
            pk = customer_form.cleaned_data["id"]
            customer = get_object_or_404(core_models.Customer, pk=pk)
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
            template_name = "core/index.html#create_customer"
        elif action == "edit":
            customer = get_object_or_404(
                core_models.Customer, pk=request.GET.get("customer_id", 0)
            )
            initial = {
                "id": customer.pk,
                "name": customer.name,
                "address": customer.address,
            }
            customer_form = CustomerEditForm(initial=initial)
            template_name = "core/index.html#edit_customer"
        elif action == "delete":
            customer = get_object_or_404(
                core_models.Customer, pk=request.GET.get("customer_id", 0)
            )
            initial = {
                "id": customer.pk,
                "name": customer.name,
                "address": customer.address,
            }
            customer_form = CustomerEditForm(initial=initial)
            template_name = "core/index.html#delete_customer"
        elif action == "list":
            template_name = "core/index.html#customers"
            customer_form = None
        else:
            template_name = "core/index.html"
            customer_form = None

        customers = core_models.Customer.objects.all().order_by("name")
        context = {
            "customer_form": customer_form,
            "customers": customers,
        }
        return render(request, template_name, context)
