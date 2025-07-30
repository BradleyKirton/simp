import re
import uuid
import random
import time
import threading
import urllib3
from urllib3.util import Timeout
from urllib3.exceptions import ReadTimeoutError
from concurrent.futures import ThreadPoolExecutor


def loadtest_lorem(http: urllib3.PoolManager):
    resp = http.request(
        "GET",
        "http://localhost:8000/sse/?t=lorem",
        preload_content=False,
        headers={"Accept": "text/stream"},
    )

    for event in resp:
        print(event, end="\r")


def loadtest_chat(http: urllib3.PoolManager):
    chats = [
        "Hey",
        "Hi there",
        "How are you?",
        "I am good, how are you?",
        "Good, bye.",
    ]

    shutdown = threading.Event()

    def sse_request():
        timeout = Timeout(read=5)
        sse_resp = http.request(
            "GET",
            "http://localhost:8000/chat/sse/",
            preload_content=False,
            headers={"Accept": "text/stream"},
            timeout=timeout,
        )
        while not shutdown.is_set():
            try:
                event = next(sse_resp, None)

                if not event:
                    continue

                print("SSE:", event)
            except ReadTimeoutError:
                continue

    thread = threading.Thread(target=sse_request)
    thread.start()

    guid = uuid.uuid4()
    username = guid.hex

    resp = http.request("GET", "http://localhost:8000/chat/")
    set_cookie = resp.headers["Set-Cookie"]
    html = resp.data.decode()
    match = re.search(
        '<input type="hidden" name="csrfmiddlewaretoken" value="(.*)">', html
    )
    csrf_token = match.groups()[0]

    for _ in range(10):
        time.sleep(random.random() / 3)
        content = random.choice(chats)
        print("posting", content)
        http.request(
            "POST",
            "http://localhost:8000/chat/",
            fields={
                "user": username,
                "content": content,
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"Cookie": set_cookie},
        )

    shutdown.set()
    thread.join()

http = urllib3.PoolManager()
loadtest_chat(http)

with ThreadPoolExecutor(10) as pool:
    http = urllib3.PoolManager()
    for _ in range(10):
        pool.submit(loadtest_chat, http)
