import asyncio
import random

from django.utils import lorem_ipsum
from django.views import View
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.template import Template, Context


def favicon_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse(b"E")


class IndexView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        template_raw = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Experiments</title>
        </head>
        <body>
            <h1>Hello World</h1>
            <div id="stream"></div>
            <script>
                const evtSource = new EventSource("{% url 'sse' %}", { withCredentials: true });
                const streamElement = document.getElementById("stream");

                evtSource.addEventListener("token", (e) => {
                    let span = document.createElement("span");
                    let space = document.createElement("span");
                    space.innerText = " ";
                    span.innerText = e.data;
                    streamElement.appendChild(span);
                    streamElement.appendChild(space);
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
    async def event_stream():
        paragraphs = lorem_ipsum.paragraphs(2)

        for paragraph in paragraphs:
            tokens = paragraph.split()

            for index, token in enumerate(tokens):
                yield "event: token\n"
                yield f"id: {index}\n"
                yield f"data: {token}\n\n"

                await asyncio.sleep(get_sleep_time())

        yield "event: end\n"
        yield "data: Stream complete\n\n"

    return StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
