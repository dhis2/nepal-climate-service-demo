# Nepal Climate Service demo: agent notes

Operating rules for AI coding assistants maintaining the hosted demo at
<https://ocs-demo-nepal.dhis2.org/>. The README explains the setup; this file lists what to
do and what not to do. Read both before changing anything on the deploy host.

## Access

SSH access to the deploy host comes from DHIS2 DevOps. Nothing here grants it, and host
details stay out of this repository. The host runs two Compose projects that share one data
directory:

| Project | Role | Reachable |
| --- | --- | --- |
| public (`compose.yml` + `compose.override.yml`) | `read_only: true`, serves visitors | via the reverse proxy |
| worker | `read_only: false`, scheduler on, ingestion credentials | `127.0.0.1:8013` on the host, via an SSH tunnel |

## Rules

- **The public container stays read-only.** Never set `read_only: false` in
  `climate-service.yaml`, and never route or publish the worker's port. All writes go
  through the worker.
- **Only the worker runs schedules.** Open Climate Service allows one scheduling process per
  data directory.
- **Credentials live in `worker.env`, owner-only, never in `.env`.** Compose reads `.env`
  automatically and passes it into the public container. Never print `worker.env`; to check
  it, show key names only: `sed -E 's/=.+/=<set>/' worker.env`. Let the operator write the
  values themselves.
- **Do not edit `compose.override.yml`.** It is host-specific and owned by DevOps.
- **Do not restart the worker while an ingestion runs.** A synchronous ingestion dies with
  the process, and its HTTP request ends with an empty reply. Check the worker's recent logs
  for downloads or writes first. If one was killed, re-run it with `"overwrite": true`.
- **Ingest a whole range in one call.** Extending a dataset with an adjacent ingestion fails
  the coverage check; use sync for that.

## Updating to the current upstream build

```bash
# public project
git pull
docker compose build --pull
docker compose up -d
# worker project, so both run the same image (only when no ingestion is running)
docker compose up -d
# from anywhere
make verify BASE=https://ocs-demo-nepal.dhis2.org
```

`make verify` must report `read_only: True` and `ingest 403 : yes`. If it does not, stop the
public container and report it; do not leave a writable public instance running.

Tag the running image before rebuilding (`docker tag <image>:latest <image>:pre-YYYY-MM-DD`)
so a bad build can be rolled back.

## Keeping the data current

The monthly CHIRPS3 and ERA5-Land datasets are extended by sync schedules on the worker.
To check them:

1. `GET /schedules/sync/{dataset_id}` on the worker for the last run and its result.
2. `GET https://ocs-demo-nepal.dhis2.org/datasets` for each dataset's temporal extent. A new
   month normally appears in the first half of the following month.
3. If a source advanced but its anomaly datasets did not, re-derive the anomalies for the
   current year with `"overwrite": true`.

A published store appears on the public instance without a restart.

## Where to look

- Worker logs: `docker compose logs --since 30m` in the worker project. Icechunk warnings
  about concurrent commits on a local filesystem are expected.
- Public health: `GET /health` and `GET /info`.
- What can be ingested: `GET /data-sources` on the worker.
