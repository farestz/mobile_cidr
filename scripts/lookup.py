#!/usr/bin/env python3
"""Проверить, принадлежит ли IPv4-адрес мобильному оператору РФ.

Использование:
    ./scripts/lookup.py 217.118.83.42
    ./scripts/lookup.py 217.118.83.42 8.8.8.8 1.2.3.4
    echo "217.118.83.42" | ./scripts/lookup.py -

Источник: data/combined/all-mobile-ru.json (обновляется `scripts/fetch.py`).
Только IPv4. Зависимостей нет — стандартная библиотека.
"""
from __future__ import annotations

import ipaddress
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMBINED = ROOT / "data" / "combined" / "all-mobile-ru.json"


def load_index() -> list[tuple[ipaddress.IPv4Network, list[str], list[int]]]:
    doc = json.loads(COMBINED.read_text(encoding="utf-8"))
    idx = []
    for p in doc["prefixes"]:
        net = ipaddress.ip_network(p["cidr"], strict=False)
        if isinstance(net, ipaddress.IPv4Network):
            idx.append((net, p["operators"], p["asns"]))
    return idx


def lookup(ip_str: str, idx) -> list[tuple[ipaddress.IPv4Network, list[str], list[int]]]:
    try:
        ip = ipaddress.IPv4Address(ip_str)
    except (ipaddress.AddressValueError, ValueError) as e:
        raise SystemExit(f"{ip_str!r}: невалидный IPv4 ({e})")
    return [(net, ops, asns) for net, ops, asns in idx if ip in net]


def format_match(ip: str, matches) -> str:
    if not matches:
        return f"{ip}\tNOT_MOBILE"
    # Самый специфичный — последний при сортировке по prefixlen
    matches = sorted(matches, key=lambda m: m[0].prefixlen, reverse=True)
    net, ops, asns = matches[0]
    extra = ""
    if len(matches) > 1:
        extra = f"  (also: {', '.join(str(m[0]) for m in matches[1:])})"
    return f"{ip}\t{','.join(ops)}\tAS{','.join(str(a) for a in asns)}\t{net}{extra}"


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    if argv == ["-"]:
        ips = [line.strip() for line in sys.stdin if line.strip()]
    else:
        ips = argv

    idx = load_index()
    for ip in ips:
        print(format_match(ip, lookup(ip, idx)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
