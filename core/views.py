import typing as t
import random
import ollama
import asyncio

from django.utils import lorem_ipsum
from django.views import View
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.template import Template, Context


def favicon_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse(b'<svg height="16" width="16" xmlns="http://www.w3.org/2000/svg"><text>E</text></svg>', content_type="image/svg+xml")


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
