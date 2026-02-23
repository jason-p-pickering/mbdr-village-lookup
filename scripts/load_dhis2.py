#!/usr/bin/env python3
"""
Fetch townships, wards, and villages from DHIS2 and populate the database.

Data sources:
  - Option sets  → actual option data (name, code, Burmese translation)
  - Option groups → township linkage only ("Amarapura" / "Amarapura (Wards)")

Required environment variables (or .env file):
  DHIS2_BASE_URL          e.g. http://localhost:8080
  DHIS2_USERNAME
  DHIS2_PASSWORD
  TOWNSHIP_OPTIONSET_UID  YNtzjFwAJVU
  WARD_OPTIONSET_UID      tL47jSni11v
  VILLAGE_OPTIONSET_UID   IV5XD8XjxYl
  DATABASE_URL            postgresql+asyncpg://...
"""

import asyncio
import os
from collections import defaultdict

import httpx
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

load_dotenv()

DHIS2_BASE_URL = os.environ["DHIS2_BASE_URL"].rstrip("/")
DHIS2_USERNAME = os.environ["DHIS2_USERNAME"]
DHIS2_PASSWORD = os.environ["DHIS2_PASSWORD"]
TOWNSHIP_OPTIONSET_UID = os.environ["TOWNSHIP_OPTIONSET_UID"]
WARD_OPTIONSET_UID = os.environ["WARD_OPTIONSET_UID"]
VILLAGE_OPTIONSET_UID = os.environ["VILLAGE_OPTIONSET_UID"]
DATABASE_URL = os.environ["DATABASE_URL"]

BATCH_SIZE = 1000
WARDS_SUFFIX = " (Wards)"


def make_client() -> httpx.Client:
    return httpx.Client(
        base_url=DHIS2_BASE_URL,
        auth=(DHIS2_USERNAME, DHIS2_PASSWORD),
        timeout=180,
    )


def get_my_name(translations: list[dict]) -> str | None:
    for t in translations:
        if t.get("locale") == "my" and t.get("property") == "NAME":
            return t.get("value")
    return None


def fetch_options_with_translations(client: httpx.Client, optionset_uid: str, label: str) -> dict[str, dict]:
    """
    Fetch all options for an option set from the /api/options endpoint (includes translations).
    Returns {option_uid: {id, code, name, name_my}}.
    """
    print(f"Fetching {label} options ...", flush=True)
    params = {
        "filter": f"optionSet.id:eq:{optionset_uid}",
        "fields": "id,code,name,translations",
        "paging": "false",
    }
    resp = client.get("/api/options", params=params)
    resp.raise_for_status()
    raw = resp.json().get("options", [])
    result = {
        o["id"]: {
            "uid": o["id"],
            "code": o.get("code"),
            "name": o["name"],
            "name_my": get_my_name(o.get("translations", [])),
        }
        for o in raw
    }
    print(f"  → {len(result)} {label}")
    return result


def fetch_option_groups(client: httpx.Client) -> list[dict]:
    """Fetch all option groups with just enough to build the linkage map."""
    print("Fetching option groups (linkage) ...", flush=True)
    resp = client.get(
        "/api/optionGroups",
        params={"fields": "id,name,options[id]", "paging": "false"},
    )
    resp.raise_for_status()
    groups = resp.json().get("optionGroups", [])
    print(f"  → {len(groups)} option groups")
    return groups


def build_linkage(
    township_options: dict[str, dict],
    option_groups: list[dict],
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Walk option groups to build:
      ward_uid_to_township_uid[option_uid]    = township_uid
      village_uid_to_township_uid[option_uid] = township_uid
    """
    name_to_uid = {v["name"]: k for k, v in township_options.items()}

    ward_uid_to_township_uid: dict[str, str] = {}
    village_uid_to_township_uid: dict[str, str] = {}
    unmatched: list[str] = []

    for group in option_groups:
        gname: str = group["name"]
        opt_uids = [o["id"] for o in group.get("options", [])]

        if gname.endswith(WARDS_SUFFIX):
            township_name = gname[: -len(WARDS_SUFFIX)]
            t_uid = name_to_uid.get(township_name)
            if t_uid:
                for uid in opt_uids:
                    ward_uid_to_township_uid[uid] = t_uid
            else:
                unmatched.append(gname)
        else:
            t_uid = name_to_uid.get(gname)
            if t_uid:
                for uid in opt_uids:
                    village_uid_to_township_uid[uid] = t_uid
            else:
                unmatched.append(gname)

    if unmatched:
        print(f"  WARNING: {len(unmatched)} option group(s) did not match any township:")
        for name in unmatched[:10]:
            print(f"    - {name}")
        if len(unmatched) > 10:
            print(f"    ... and {len(unmatched) - 10} more")

    return ward_uid_to_township_uid, village_uid_to_township_uid


async def upsert_townships(session, options: dict[str, dict]) -> dict[str, int]:
    """Upsert townships; return {dhis2_uid → db_id}."""
    for opt in options.values():
        await session.execute(
            text(
                """
                INSERT INTO townships (uid, code, name, name_my)
                VALUES (:uid, :code, :name, :name_my)
                ON CONFLICT (uid) DO UPDATE
                  SET code    = EXCLUDED.code,
                      name    = EXCLUDED.name,
                      name_my = EXCLUDED.name_my
                """
            ),
            opt,
        )
    await session.commit()

    result = await session.execute(text("SELECT uid, id FROM townships"))
    return {row.uid: row.id for row in result}


async def upsert_in_batches(session, table: str, rows: list[dict]) -> None:
    total = len(rows)
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        await session.execute(
            text(
                f"""
                INSERT INTO {table} (uid, code, name, name_my, township_id)
                VALUES (:uid, :code, :name, :name_my, :township_id)
                ON CONFLICT (uid) DO UPDATE
                  SET code        = EXCLUDED.code,
                      name        = EXCLUDED.name,
                      name_my     = EXCLUDED.name_my,
                      township_id = EXCLUDED.township_id
                """
            ),
            batch,
        )
        await session.commit()
        done = min(i + BATCH_SIZE, total)
        print(f"  {table}: {done}/{total}", end="\r", flush=True)
    print()


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    with make_client() as client:
        township_opts = fetch_options_with_translations(client, TOWNSHIP_OPTIONSET_UID, "townships")
        ward_opts = fetch_options_with_translations(client, WARD_OPTIONSET_UID, "wards")
        village_opts = fetch_options_with_translations(client, VILLAGE_OPTIONSET_UID, "villages")
        option_groups = fetch_option_groups(client)

    print("Building township linkage from option groups ...")
    ward_link, village_link = build_linkage(township_opts, option_groups)
    print(f"  {len(ward_link)} wards linked, {len(village_link)} villages linked")

    print("Upserting townships ...")
    async with Session() as session:
        uid_to_db_id = await upsert_townships(session, township_opts)
    print(f"  {len(uid_to_db_id)} townships saved.")

    ward_rows = [
        {**ward_opts[uid], "township_id": uid_to_db_id[ward_link[uid]]}
        for uid in ward_link
        if uid in ward_opts and ward_link[uid] in uid_to_db_id
    ]

    village_rows = [
        {**village_opts[uid], "township_id": uid_to_db_id[village_link[uid]]}
        for uid in village_link
        if uid in village_opts and village_link[uid] in uid_to_db_id
    ]

    print(f"Upserting {len(ward_rows)} wards ...")
    async with Session() as session:
        await upsert_in_batches(session, "wards", ward_rows)

    print(f"Upserting {len(village_rows)} villages ...")
    async with Session() as session:
        await upsert_in_batches(session, "villages", village_rows)

    await engine.dispose()
    print("\nDone.")
    print(f"  Townships : {len(uid_to_db_id)}")
    print(f"  Wards     : {len(ward_rows)}")
    print(f"  Villages  : {len(village_rows)}")


if __name__ == "__main__":
    asyncio.run(main())
