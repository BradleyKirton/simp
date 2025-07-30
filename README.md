## Build

Run the build script if you are using podman. Otherwise just port to docker.

## Run

Run the build run if you are using podman. Otherwise just port to docker.

## Managing Unit

```console
curl -X GET --unix-socket /var/run/control.unit.sock  \
      http://localhost/control/applications/django/restart

curl -X PUT -d '"/var/log/access.log"' \
      --unix-socket /var/run/control.unit.sock \
      http://localhost/config/access_log
```
 
 
## 🔥 Hot Reloading Hack 🔥

```console
uv run watchfiles 'podman-compose restart server' .
```

## Meilisearch

```
https://github.com/meilisearch/meilisearch/releases/tag/v1.15.2
```

## DB Setup

```console
initdb -D .db
PGPORT=1000 postgres -D .db
psql -U postgres
```

```sql
CREATE DATABASE simp;
CREATE USER simp;
GRANT USAGE ON SCHEMA public TO simp;
GRANT ALL PRIVILEGES ON simp TO simp;
```

## Issues

[https://github.com/nginx/unit/issues/1561](https://github.com/nginx/unit/issues/1561)