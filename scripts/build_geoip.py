#!/usr/bin/env python3
"""Собрать xray-core-совместимый geoip.dat из CIDR-списков.

Читает data/cidrs/<slug>.txt и data/combined/all-mobile-ru.txt,
пишет data/geoip/mobile-ru.dat с entries:
  MTS, MEGAFON, BEELINE, TELE2, MOBILE

Формат — Protocol Buffers GeoIPList, как у v2ray-rules-dat:

    message CIDR      { bytes ip = 1; uint32 prefix = 2; }
    message GeoIP     { string country_code = 1; repeated CIDR cidr = 2;
                        bool reverse_match = 3; }
    message GeoIPList { repeated GeoIP entry = 1; }

Reverse-match: для каждого основного тега (MTS, MEGAFON, …) пишется
парный тег с суффиксом `_NOT` и `reverse_match=true`. xray матчит такой
тег как «всё, чего НЕТ в списке» — нужно для правил «весь трафик кроме
мобильного». Это дешевле, чем считать комплемент CIDR-набора.

Использование в xray-конфиге (DirectIp / ProxyIp / BlockIp):
    "ext:/path/to/mobile-ru.dat:mobile"      # любой мобильный IP
    "ext:/path/to/mobile-ru.dat:mobile_not"  # всё, кроме мобильных
    "ext:/path/to/mobile-ru.dat:mts"

Или, если файл подменяет основной geoip.dat (Geoipurl в happ-конфиге),
ссылаться как обычно:
    "geoip:mobile", "geoip:mobile_not", "geoip:mts"

Зависимостей нет — wire format кодируется руками (5 строк varint).
"""
from __future__ import annotations

import ipaddress
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CIDRS = DATA / "cidrs"
COMBINED = DATA / "combined"
GEOIP = DATA / "geoip"


def varint(n: int) -> bytes:
    out = bytearray()
    while n > 0x7f:
        out.append((n & 0x7f) | 0x80)
        n >>= 7
    out.append(n & 0x7f)
    return bytes(out)


def tag(field_number: int, wire_type: int) -> bytes:
    return varint((field_number << 3) | wire_type)


def length_delim(field_number: int, payload: bytes) -> bytes:
    """Закодировать поле wire_type=2 (length-delimited): bytes / string / nested."""
    return tag(field_number, 2) + varint(len(payload)) + payload


def encode_cidr(cidr_str: str) -> bytes:
    net = ipaddress.ip_network(cidr_str, strict=False)
    if net.version != 4:
        raise ValueError(f"only IPv4 supported: {cidr_str}")
    ip_bytes = net.network_address.packed  # 4 bytes для IPv4
    return length_delim(1, ip_bytes) + tag(2, 0) + varint(net.prefixlen)


def encode_geoip(country_code: str, cidrs: list[str], reverse_match: bool = False) -> bytes:
    payload = length_delim(1, country_code.encode("ascii"))
    for c in cidrs:
        payload += length_delim(2, encode_cidr(c))
    if reverse_match:
        payload += tag(3, 0) + varint(1)
    return payload


def encode_geoip_list(entries: list[tuple[str, list[str], bool]]) -> bytes:
    payload = b""
    for code, cidrs, reverse in entries:
        payload += length_delim(1, encode_geoip(code, cidrs, reverse))
    return payload


def read_cidr_file(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    GEOIP.mkdir(parents=True, exist_ok=True)

    base: dict[str, list[str]] = {}
    for slug in ("mts", "megafon", "beeline", "tele2"):
        f = CIDRS / f"{slug}.txt"
        if not f.exists():
            print(f"skip {slug}: {f} not found", file=sys.stderr)
            continue
        base[slug.upper()] = read_cidr_file(f)

    base["MOBILE"] = read_cidr_file(COMBINED / "all-mobile-ru.txt")

    # Каждый базовый тег + парный _NOT с reverse_match=true.
    entries: list[tuple[str, list[str], bool]] = []
    for code, cidrs in base.items():
        entries.append((code, cidrs, False))
        entries.append((f"{code}_NOT", cidrs, True))

    blob = encode_geoip_list(entries)
    out = GEOIP / "mobile-ru.dat"
    out.write_bytes(blob)

    print(f"wrote {out.relative_to(ROOT)} ({len(blob):,} bytes)")
    for code, cidrs, reverse in entries:
        marker = "(reverse)" if reverse else ""
        print(f"  geoip:{code.lower():<14} {len(cidrs):>5} CIDR  {marker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
