"""Data Dragon: static champion data. Public CDN, no API key and no rate limit."""

import json
import sqlite3

import requests

BASE = "https://ddragon.leagueoflegends.com"


def latest_version(session: requests.Session | None = None) -> str:
    http = session or requests
    response = http.get(f"{BASE}/api/versions.json", timeout=15)
    response.raise_for_status()
    return response.json()[0]


def fetch_champions(version: str, session: requests.Session | None = None) -> list[dict]:
    http = session or requests
    response = http.get(f"{BASE}/cdn/{version}/data/en_US/champion.json", timeout=15)
    response.raise_for_status()
    return [
        {
            "champion_id": int(c["key"]),
            "champion_key": c["id"],
            "name": c["name"],
            "tags": c["tags"],
        }
        for c in response.json()["data"].values()
    ]


def store_champions(conn: sqlite3.Connection, champions: list[dict], version: str) -> None:
    conn.execute("DELETE FROM champions")
    conn.executemany(
        "INSERT INTO champions (champion_id, champion_key, name, tags, ddragon_version) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (c["champion_id"], c["champion_key"], c["name"], json.dumps(c["tags"]), version)
            for c in champions
        ],
    )


def known_champion_ids(conn: sqlite3.Connection) -> set[int]:
    return {row[0] for row in conn.execute("SELECT champion_id FROM champions")}
