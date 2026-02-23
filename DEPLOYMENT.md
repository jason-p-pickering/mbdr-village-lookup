# Deployment Notes

## Infrastructure

```
Host machine
├── proxy          (172.19.2.2)   — nginx reverse proxy
├── dhis           (172.19.2.11)  — DHIS2 (Tomcat, port 8080)
├── postgres       (172.19.2.20)  — PostgreSQL
├── monitor        (172.19.2.30)  — monitoring
└── village-lookup (172.19.2.45)  — this microservice (port 8000)
```

---

## 1. Create the LXC container

Run on the host:

```bash
lxc launch ubuntu:22.04 village-lookup
```

Verify it got 172.19.2.45:

```bash
lxc list village-lookup
```

---

## 2. Set up PostgreSQL access

### Create the database and user

Run on the host (executes inside the postgres container):

```bash
lxc exec postgres -- sudo -u postgres psql -c "CREATE USER village WITH PASSWORD 'choose-a-password';"
lxc exec postgres -- sudo -u postgres psql -c "CREATE DATABASE village_lookup OWNER village;"
```

### Allow the village-lookup container in pg_hba.conf

On the postgres container, add this line to `/etc/postgresql/*/main/pg_hba.conf`:

```
host  village_lookup  village  172.19.2.45/32  scram-sha-256
```

Then reload:

```bash
lxc exec postgres -- sudo systemctl reload postgresql
```

### Open the firewall on the postgres container

```bash
lxc exec postgres -- ufw allow from 172.19.2.45 to any port 5432 comment "village-lookup"
```

Verify:

```bash
lxc exec postgres -- ufw status
```

---

## 3. Allow microservice to reach DHIS2

On the **dhis** container, open port 8080 to the village-lookup container:

```bash
lxc exec dhis -- ufw allow from 172.19.2.45 to any port 8080 comment "village-lookup"
```

Verify:

```bash
lxc exec dhis -- ufw status
```

---

## 4. Get the code onto the container

```bash
# Option A: copy from dev machine
scp -r village-lookup/ user@host:/tmp/village-lookup
lxc file push -r /tmp/village-lookup host:/opt/village-lookup

# Option B: git clone inside the container
lxc exec village-lookup -- git clone <repo-url> /opt/village-lookup
```

---

## 5. Install dependencies

```bash
lxc exec village-lookup -- apt update
lxc exec village-lookup -- apt install -y python3 python3-pip python3-venv python3-dev libpq-dev
lxc exec village-lookup -- bash -c "cd /opt/village-lookup && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
```

> `python3-dev` and `libpq-dev` are required to compile `asyncpg` during `pip install`.

---

## 6. Configure the environment

```bash
lxc exec village-lookup -- bash -c "cp /opt/village-lookup/.env.example /opt/village-lookup/.env"
lxc exec village-lookup -- nano /opt/village-lookup/.env
```

Fill in `.env`:

```
DATABASE_URL=postgresql+asyncpg://village:choose-a-password@172.19.2.20:5432/village_lookup
DHIS2_BASE_URL=http://172.19.2.11:8080
DHIS2_USERNAME=admin
DHIS2_PASSWORD=
TOWNSHIP_OPTIONSET_UID=YNtzjFwAJVU
WARD_OPTIONSET_UID=tL47jSni11v
VILLAGE_OPTIONSET_UID=IV5XD8XjxYl
ICD10_OPTIONSET_UID=MDNwHnWn2Ik
```

Lock down the file:

```bash
lxc exec village-lookup -- chmod 600 /opt/village-lookup/.env
```

---

## 7. Run database migrations

```bash
lxc exec village-lookup -- bash -c "cd /opt/village-lookup && .venv/bin/alembic upgrade head"
```

---

## 8. Load data from DHIS2

This takes a few minutes (65k villages):

```bash
lxc exec village-lookup -- bash -c "cd /opt/village-lookup && .venv/bin/python scripts/load_dhis2.py"
```

Expected output:

```
Fetching townships options ...   → 331 townships
Fetching wards options ...       → 3486 wards
Fetching villages options ...    → 64960 villages
Fetching ICD10 codes options ... → 10616 ICD10 codes
...
Done.
  Townships  : 331
  Wards      : 3381
  Villages   : 63081
  ICD10 codes: 10616
```

> **Note:** 37 option groups could not be matched to a township due to naming
> inconsistencies in DHIS2 (e.g. `"Aungmyaythasan (Wards)"` vs township name
> `"Aungmyaythazan"`). These have been logged and passed back to the data team.
> The affected wards/villages will appear once the names are corrected in DHIS2
> and the loader is re-run.

---

## 9. Run as a systemd service

Create `/etc/systemd/system/village-lookup.service` inside the container:

```bash
lxc exec village-lookup -- bash -c "cat > /etc/systemd/system/village-lookup.service" << 'EOF'
[Unit]
Description=Village Lookup Microservice
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/village-lookup
EnvironmentFile=/opt/village-lookup/.env
ExecStart=/opt/village-lookup/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start:

```bash
lxc exec village-lookup -- systemctl daemon-reload
lxc exec village-lookup -- systemctl enable village-lookup
lxc exec village-lookup -- systemctl start village-lookup
lxc exec village-lookup -- systemctl status village-lookup
```

---

## 10. Configure nginx on the proxy container

Edit the nginx site config on the proxy container. Two changes are needed:

### 1. Add a `map` block in `http{}`

Outside the `server{}` block, add:

```nginx
map $request_method $tracker_upstream {
    POST    http://172.19.2.45:8000/proxy/tracker;
    default http://172.19.2.11:8080/dhis/api/tracker;
}
```

This routes POST submissions through the microservice for validation and passes
all other methods (GET, etc.) straight to DHIS2.

### 2. Add location blocks inside `server{}`

```nginx
# Tracker submissions — POST goes to microservice, everything else to DHIS2
location = /dhis/api/tracker {
    proxy_pass     $tracker_upstream$is_args$args;
    include        /etc/nginx/proxy_params;
    proxy_redirect off;
}

# Village/ward/township lookup
location /lookup/ {
    proxy_pass     http://172.19.2.45:8000/;
    include        /etc/nginx/proxy_params;
    proxy_redirect off;
}

```

Test and reload:

```bash
lxc exec proxy -- nginx -t
lxc exec proxy -- systemctl reload nginx
```

---

## 11. Verify the deployment

```bash
# Health check (from host or proxy container)
curl http://172.19.2.45:8000/health

# Townships (should return 331)
curl http://172.19.2.45:8000/townships | python3 -c "import json,sys; t=json.load(sys.stdin); print(len(t), 'townships')"

# Ward search (Amarapura)
curl "http://172.19.2.45:8000/wards?township_uid=hMKEafGDKdQ&q=hman"

# Village search (Amarapura)
curl "http://172.19.2.45:8000/villages?township_uid=hMKEafGDKdQ&q=gyo"
```

---

## 12. Re-loading data after DHIS2 changes

When option sets or option groups are updated in DHIS2, re-run the loader.
It uses `ON CONFLICT ... DO UPDATE` so it is safe to run repeatedly — no need
to wipe the database first.

```bash
lxc exec village-lookup -- bash -c "cd /opt/village-lookup && .venv/bin/python scripts/load_dhis2.py"
lxc exec village-lookup -- systemctl restart village-lookup   # refresh in-memory townships cache
```

---

## API Reference

### `GET /health`
```bash
curl http://172.19.2.45:8000/health
# {"status": "ok"}
```

### `GET /townships`
Returns all 331 townships. Use the returned UIDs for the other endpoints.
```bash
curl http://172.19.2.45:8000/townships
```

### `GET /wards`

| Param | Required | Description |
|---|---|---|
| `township_uid` | yes | DHIS2 UID from `/townships` |
| `q` | no | Name search (fuzzy, case-insensitive) |
| `limit` | no | Default 50, max 200 |

```bash
curl "http://172.19.2.45:8000/wards?township_uid=hMKEafGDKdQ"
curl "http://172.19.2.45:8000/wards?township_uid=hMKEafGDKdQ&q=shwe"
```

### `GET /villages`
Same params as `/wards`.

```bash
curl "http://172.19.2.45:8000/villages?township_uid=hMKEafGDKdQ"
curl "http://172.19.2.45:8000/villages?township_uid=hMKEafGDKdQ&q=gyo"
```

**Response fields** (wards/villages): `uid`, `code`, `name`, `name_my`

---

### `GET /icd10`

External URL (via nginx): `/lookup/icd10`

| Param | Required | Description |
|---|---|---|
| `q` | no | Search term — matches ICD10 code (e.g. `A00`) or description (e.g. `cholera`), case-insensitive |
| `page` | no | Page number, default 1 |
| `limit` | no | Default 50, max 200 |

```bash
curl "http://172.19.2.45:8000/icd10?q=cholera"
curl "http://172.19.2.45:8000/icd10?q=A00"
curl "http://172.19.2.45:8000/icd10?page=2&limit=100"
```

**Response:**
```json
{
  "page": 1,
  "limit": 50,
  "total": 6,
  "results": [
    {"uid": "...", "code": "100.9", "icd_code": "A00.9", "name": "A00.9 Cholera, unspecified"}
  ]
}
```

Interactive docs available at `http://172.19.2.45:8000/docs`.
