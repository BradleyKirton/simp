import asyncio


async def show_task_lifecycle():
    print(len(asyncio.all_tasks()))

    task = asyncio.create_task(asyncio.sleep(1))

    # Task is in all_tasks()
    print(len(asyncio.all_tasks()))
    print(f"Task in all_tasks: {task in asyncio.all_tasks()}")

    await task  # Wait for task completion

    # Task is now removed
    print(len(asyncio.all_tasks()))
    print(f"Task in all_tasks after completion: {task in asyncio.all_tasks()}")


asyncio.run(show_task_lifecycle())
