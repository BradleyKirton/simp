## Build

Run the build script if you are using podman. Otherwise just port to docker.

## Run

Run the build run if you are using podman. Otherwise just port to docker.

## Restart

curl -X GET --unix-socket /var/run/control.unit.sock  \
      http://localhost/control/applications/django/restart

curl -X PUT -d '"/var/log/access.log"' \
      --unix-socket /var/run/control.unit.sock \
      http://localhost/config/access_log

 uv run watchfiles 'podman container exec simp curl -X GET --unix-socket /var/run/control.unit.sock http://localhost/control/applications/django/restart' .