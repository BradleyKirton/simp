import time
import zmq.asyncio
import zmq
import asyncio


async def subber(shutdown, poller):
    while not shutdown.is_set():
        events = dict(await poller.poll(1000))

        for socket in events:
            data = await socket.recv_string()
            print("received", data)


async def pubber(shutdown, publisher):
    counter = 0
    while counter < 10:
        await publisher.send_string("HELLO")
        await asyncio.sleep(1)
        print("publishing")
        counter += 1

    shutdown.set()


async def main():
    ctx = zmq.asyncio.Context()
    publisher = ctx.socket(zmq.PUB)
    # publisher.bind("inproc://pubsub")
    publisher.bind("ipc:///tmp/pubsub")

    subscriber = ctx.socket(zmq.SUB)
    # subscriber.connect("inproc://pubsub")
    subscriber.connect("ipc:///tmp/pubsub")
    subscriber.setsockopt_string(zmq.SUBSCRIBE, "")

    poller = zmq.asyncio.Poller()
    poller.register(subscriber, zmq.POLLIN)

    shutdown = asyncio.Event()
    await asyncio.gather(subber(shutdown, poller), pubber(shutdown, publisher))


asyncio.run(main())

# import time
# import zmq
# import threading


# ctx_pub = zmq.Context()
# publisher = ctx_pub.socket(zmq.PUB)
# publisher.bind("inproc://pubsub")
# publisher.bind("ipc:///tmp/pubsub")
# # publisher.bind("tcp://localhost:9000")

# ctx_sub = zmq.Context()
# subscriber = ctx_sub.socket(zmq.SUB)
# subscriber.connect("inproc://pubsub")
# subscriber.connect("ipc:///tmp/pubsub")
# subscriber.setsockopt_string(zmq.SUBSCRIBE, "")
# # subscriber.setsockopt(zmq.RCVTIMEO, 1000)
# # subscriber.connect("tcp://localhost:9000")

# poller = zmq.Poller()
# poller.register(subscriber, zmq.POLLIN)


# shutdown = threading.Event()


# def subber():
#     while not shutdown.is_set():
#         events = dict(poller.poll(1000))

#         for socket in events:
#             data = socket.recv_string()
#             print("received", data)


# thread = threading.Thread(target=subber)
# thread.start()

# counter = 0
# while counter < 3:
#     publisher.send_string("HELLO")
#     time.sleep(1)
#     print("publishing")
#     counter += 1

# shutdown.set()
# thread.join()
