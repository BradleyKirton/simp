import urllib3
from concurrent.futures import ThreadPoolExecutor


def loadtest():
    http = urllib3.PoolManager()
    resp = http.request(
        "GET",
        "http://localhost:8000/sse/?t=lorem",
        preload_content=False,
        headers={"Accept": "text/stream"},
    )

    for event in resp:
        print(event, end="\r")


with ThreadPoolExecutor(10) as pool:
    for _ in range(10):
        pool.submit(loadtest)
