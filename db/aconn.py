import psycopg_pool
import psycopg
from django.conf import settings


default_db = settings.DATABASES["default"]
dbname = default_db["NAME"]
user = default_db["USER"]
passwd = default_db["PASSWORD"]
host = default_db["HOST"]
port = default_db["PORT"]
conn_str = f"dbname={dbname} user={user} password={passwd} host={host} port={port}"

_pool = psycopg_pool.AsyncConnectionPool[psycopg.AsyncConnection](
    conn_str,
    open=False,
    kwargs={"autocommit": True},
)


async def get_connection_pool() -> psycopg_pool.AsyncConnectionPool:
    if not _pool._opened:
        await _pool.open()
    return _pool
