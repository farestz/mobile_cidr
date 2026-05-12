#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6", "httpx>=0.27"]
# ///
"""Сбор CIDR-префиксов мобильных операторов РФ.

Источник: RIPEstat Data API (announced-prefixes).
Читает data/sources.yaml, для каждого ASN получает список анонсируемых
префиксов, складывает в:
  data/raw/AS<N>.json          — сырой ответ
  data/cidrs/<slug>.txt        — plain CIDR на оператора
  data/cidrs/<slug>.json       — с метаданными
  data/combined/all-mobile-ru.txt   — объединённый plain
  data/combined/all-mobile-ru.json  — объединённый с разметкой
"""
from __future__ import annotations

import ipaddress
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCES = DATA / "sources.yaml"
RAW = DATA / "raw"
CIDRS = DATA / "cidrs"
COMBINED = DATA / "combined"

RIPESTAT_PREFIXES = "https://stat.ripe.net/data/announced-prefixes/data.json"
RIPESTAT_OVERVIEW = "https://stat.ripe.net/data/as-overview/data.json"
USER_AGENT = "mobile_cidr/0.1 (https://github.com/farestz)"


def fetch_asn(client: httpx.Client, asn: int) -> dict:
    """Получить announced-prefixes для одного ASN."""
    r = client.get(RIPESTAT_PREFIXES, params={"resource": f"AS{asn}"}, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"AS{asn}: status={payload.get('status')} messages={payload.get('messages')}")
    return payload


def fetch_holder(client: httpx.Client, asn: int) -> str:
    """Holder из RIPE — для сверки с заявленным в sources.yaml."""
    r = client.get(RIPESTAT_OVERVIEW, params={"resource": f"AS{asn}"}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", {}).get("holder", "")


def prefixes_from_payload(payload: dict) -> list[str]:
    """Только IPv4 — IPv6 не используется в потребляющих роутинг-конфигах."""
    out = []
    for p in payload.get("data", {}).get("prefixes", []):
        cidr = p["prefix"]
        if ipaddress.ip_network(cidr, strict=False).version == 4:
            out.append(cidr)
    return out


def family(cidr: str) -> int:
    return ipaddress.ip_network(cidr, strict=False).version


def sort_key(cidr: str):
    net = ipaddress.ip_network(cidr, strict=False)
    return (net.version, int(net.network_address), net.prefixlen)


def write_operator(slug: str, asns: list[int], asn_to_prefixes: dict[int, list[str]]) -> dict:
    """Сохранить cidrs/<slug>.{txt,json}, вернуть запись для combined."""
    seen: dict[str, list[int]] = {}
    for asn in asns:
        for cidr in asn_to_prefixes.get(asn, []):
            seen.setdefault(cidr, []).append(asn)

    sorted_cidrs = sorted(seen.keys(), key=sort_key)

    (CIDRS / f"{slug}.txt").write_text("\n".join(sorted_cidrs) + "\n", encoding="utf-8")

    doc = {
        "operator": slug,
        "asns": asns,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "RIPEstat",
        "prefixes": [
            {"cidr": c, "asns": seen[c]}
            for c in sorted_cidrs
        ],
    }
    (CIDRS / f"{slug}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return doc


def main() -> int:
    for d in (RAW, CIDRS, COMBINED):
        d.mkdir(parents=True, exist_ok=True)

    sources = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    operators = sources["operators"]

    asn_to_prefixes: dict[int, list[str]] = {}

    holder_mismatches: list[str] = []

    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for op in operators:
            slug = op["slug"]
            for entry in op["asns"]:
                asn = entry["asn"]
                expected_holder = entry.get("holder", "")
                actual_holder = fetch_holder(client, asn)
                marker = "OK" if actual_holder == expected_holder else "MISMATCH"
                print(f"[{slug}] AS{asn} holder={actual_holder!r} [{marker}]", flush=True)
                if marker == "MISMATCH":
                    holder_mismatches.append(
                        f"  AS{asn} ({slug}): expected {expected_holder!r}, got {actual_holder!r}"
                    )

                payload = fetch_asn(client, asn)
                (RAW / f"AS{asn}.json").write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                prefixes = prefixes_from_payload(payload)
                asn_to_prefixes[asn] = prefixes
                print(f"  → {len(prefixes)} prefixes", flush=True)
                time.sleep(0.3)  # вежливый rate-limit

    operator_docs = []
    for op in operators:
        slug = op["slug"]
        asns = [e["asn"] for e in op["asns"]]
        doc = write_operator(slug, asns, asn_to_prefixes)
        operator_docs.append(doc)
        print(f"[{slug}] total {len(doc['prefixes'])} prefixes", flush=True)

    all_seen: dict[str, dict] = {}
    for doc in operator_docs:
        for p in doc["prefixes"]:
            entry = all_seen.setdefault(p["cidr"], {"cidr": p["cidr"], "operators": [], "asns": set()})
            entry["operators"].append(doc["operator"])
            entry["asns"].update(p["asns"])

    sorted_all = sorted(all_seen.keys(), key=sort_key)
    (COMBINED / "all-mobile-ru.txt").write_text("\n".join(sorted_all) + "\n", encoding="utf-8")

    combined_doc = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "RIPEstat",
        "operators": [op["slug"] for op in operators],
        "prefixes": [
            {
                "cidr": c,
                "operators": sorted(set(all_seen[c]["operators"])),
                "asns": sorted(all_seen[c]["asns"]),
            }
            for c in sorted_all
        ],
    }
    (COMBINED / "all-mobile-ru.json").write_text(
        json.dumps(combined_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"\ncombined: {len(sorted_all)} unique CIDR (IPv4 only)")

    if holder_mismatches:
        print("\nWARNING: RIPE holder ≠ заявленный в sources.yaml:", file=sys.stderr)
        for line in holder_mismatches:
            print(line, file=sys.stderr)
        print("Проверьте, что AS не переехал к другому оператору. "
              "Если переехал — поправьте sources.yaml. Если просто переименован "
              "и принадлежит тому же оператору — обновите поле holder.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
