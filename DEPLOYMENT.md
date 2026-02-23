# Deployment Notes

## Prerequisites

- Python 3.10+
- PostgreSQL 12+ with `pg_trgm` extension (included in `postgresql-contrib`)
- Access to the DHIS2 server from the deployment host

```bash
# Install contrib if not already present
sudo apt install postgresql-contrib
```

---

## 1. Get the code onto the server

```bash
# Option A: copy from dev
scp -r village-lookup/ user@server:/opt/village-lookup

# Option B: git clone (if you've pushed to a repo)
git clone <repo-url> /opt/village-lookup
```

---

## 2. Create a virtualenv and install dependencies

```bash
cd /opt/village-lookup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Create the database

```bash
sudo -u postgres psql -c "CREATE USER village_lookup WITH PASSWORD 'choose-a-password';"
sudo -u postgres psql -c "CREATE DATABASE village_lookup OWNER village_lookup;"
```

---

## 4. Configure the environment

```bash
cp .env.example .env
nano .env
```

Fill in `.env`:

```
DATABASE_URL=postgresql+asyncpg://village_lookup:choose-a-password@localhost/village_lookup
DHIS2_BASE_URL=https://your-dhis2-server
DHIS2_USERNAME=admin
DHIS2_PASSWORD=
TOWNSHIP_OPTIONSET_UID=YNtzjFwAJVU
WARD_OPTIONSET_UID=tL47jSni11v
VILLAGE_OPTIONSET_UID=IV5XD8XjxYl
```

Lock down the file:

```bash
chmod 600 .env
```

---

## 5. Run database migrations

```bash
source .venv/bin/activate
alembic upgrade head
```

---

## 6. Load data from DHIS2

This takes a few minutes (65k villages):

```bash
source .venv/bin/activate
python scripts/load_dhis2.py
```

Expected output:
```
Fetching townships options ...  → 331 townships
Fetching wards options ...      → 3486 wards
Fetching villages options ...   → 64960 villages
...
Done.
  Townships : 331
  Wards     : 3381
  Villages  : 63081
```

> **Note:** 37 option groups could not be matched to a township due to naming
> inconsistencies in DHIS2 (e.g. `"Aungmyaythasan (Wards)"` vs township name
> `"Aungmyaythazan"`). These have been logged and passed back to the data team.
> The affected wards/villages will appear once the names are corrected in DHIS2
> and the loader is re-run.

---

## 7. Run as a systemd service

Create `/etc/systemd/system/village-lookup.service`:

```ini
[Unit]
Description=Village Lookup Microservice
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/village-lookup
EnvironmentFile=/opt/village-lookup/.env
ExecStart=/opt/village-lookup/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> Adjust `User=` to whichever system user you want the process to run as.
> Make sure that user can read `/opt/village-lookup/.env`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable village-lookup
sudo systemctl start village-lookup
sudo systemctl status village-lookup
```

---

## 8. Nginx reverse proxy

nginx sits in front of both DHIS2 (port 8080) and the microservice (port 8081).
It intercepts `POST /api/tracker` and routes it through the microservice for
validation. All other traffic goes straight to DHIS2.

```nginx
server {
    listen 80;
    server_name your-server;

    # Synchronous tracker submissions → microservice (validates, then relays)
    location = /api/tracker {
        proxy_pass          http://127.0.0.1:8081/proxy/tracker;
        proxy_pass_header   Cookie;
        proxy_set_header    Host $host;
        proxy_set_header    X-Real-IP $remote_addr;
        proxy_read_timeout  60s;
    }

    # Everything else → DHIS2 directly
    location / {
        proxy_pass          http://127.0.0.1:8080;
        proxy_set_header    Host $host;
        proxy_set_header    X-Real-IP $remote_addr;
    }
}
```

**How the proxy route works:**

- `async=true` or no `async` param → microservice relays straight to DHIS2,
  no validation (async jobs are not intercepted)
- `async=false` + program != `cUjoGJK4gPL` → relayed straight through
- `async=false` + program `cUjoGJK4gPL` + inconsistent address → **409** returned
  to client, submission blocked
- `async=false` + program `cUjoGJK4gPL` + valid (or empty) address → relayed to
  DHIS2, DHIS2 response returned to client unchanged

---

## 9. Verify the deployment

```bash
# Health check
curl http://localhost:8080/health

# Townships (should return 331)
curl http://localhost:8080/townships | python3 -c "import json,sys; t=json.load(sys.stdin); print(len(t), 'townships')"

# Ward search
curl "http://localhost:8080/wards?township_uid=hMKEafGDKdQ&q=hman"

# Village search
curl "http://localhost:8080/villages?township_uid=hMKEafGDKdQ&q=gyo"

# Validation
curl -s -X POST http://localhost:8080/validate \
  -H "Content-Type: application/json" \
  -d '{"events":[{"event":"test","dataValues":[
    {"dataElement":"QcFEXzah0f1","value":"Amarapura"},
    {"dataElement":"hQnTVzOd0m9","value":"Urban"},
    {"dataElement":"ZT3zBscjD24","value":"Lut Lat Yay Ward - Ahlone"}
  ]}]}'
# Expected: {"valid":false,...}
```

---

## 10. Re-loading data after DHIS2 changes

When option sets or option groups are updated in DHIS2, re-run the loader.
It uses `ON CONFLICT ... DO UPDATE` so it is safe to run repeatedly — no need
to wipe the database first.

```bash
cd /opt/village-lookup
source .venv/bin/activate
python scripts/load_dhis2.py
sudo systemctl restart village-lookup   # refresh the in-memory townships cache
```

---

## Port note

The dev DHIS2 instance runs on port 8080. If you deploy this service on the
**same host** as DHIS2, change the uvicorn port in the systemd unit (e.g. 8081)
and update the nginx proxy accordingly.

## API Usage

---                                                                                                                                                                                        
  GET /health                                                                                                                                                                                
                                                                                                                                                                                             
  Simple liveness check.                                                                                                                                                                     
  curl http://localhost:8000/health                                                                                                                                                          
  Response: {"status": "ok"}

  ---
  GET /townships

  Returns all townships (loaded from DB into memory at startup). Use these UIDs for the other endpoints.
  curl http://localhost:8000/townships
  Response: [{"uid": "hMKEafGDKdQ", "code": "...", "name": "Amarapura"}, ...]

  ---
  GET /wards

  Search urban wards within a township.

  ┌──────────────┬──────────┬──────────────────────────────────────────────┐
  │    Param     │ Required │                 Description                  │
  ├──────────────┼──────────┼──────────────────────────────────────────────┤
  │ township_uid │ yes      │ DHIS2 UID from /townships                    │
  ├──────────────┼──────────┼──────────────────────────────────────────────┤
  │ q            │ no       │ Name search string (fuzzy, case-insensitive) │
  ├──────────────┼──────────┼──────────────────────────────────────────────┤
  │ limit        │ no       │ Default 50, max 200                          │
  └──────────────┴──────────┴──────────────────────────────────────────────┘

  # All wards for Amarapura
  curl "http://localhost:8000/wards?township_uid=hMKEafGDKdQ"

  # Search within Amarapura
  curl "http://localhost:8000/wards?township_uid=hMKEafGDKdQ&q=shwe"

  # With limit
  curl "http://localhost:8000/wards?township_uid=hMKEafGDKdQ&q=shwe&limit=10"

  ---
  GET /villages

  Search rural villages within a township. Same params as /wards.

  # All villages for Amarapura
  curl "http://localhost:8000/villages?township_uid=hMKEafGDKdQ"

  # Search within Amarapura
  curl "http://localhost:8000/villages?township_uid=hMKEafGDKdQ&q=gyo"
