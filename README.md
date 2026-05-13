# mobile_cidr

CIDR-списки IPv4-префиксов мобильных операторов России — **МТС, МегаФон, Билайн, T2 (Tele2)**.

Источник: [RIPEstat announced-prefixes](https://stat.ripe.net/docs/02.data-api/announced-prefixes.html) по списку ASN операторов в [`data/sources.yaml`](data/sources.yaml). GitHub Actions ежедневно пересобирает артефакты и обновляет [release `latest`](https://github.com/farestz/mobile_cidr/releases/latest).

## Стабильные URL

Подставлять в скрипты, конфиги xray/Keenetic, `Geoipurl` happ-конфигов и т.п. URL **не меняется** между обновлениями — `releases/latest/` это GitHub-алиас, всегда указывающий на самый свежий релиз.

| Файл | URL |
|------|-----|
| **xray-core geoip.dat** | <https://github.com/farestz/mobile_cidr/releases/latest/download/mobile-ru.dat> |
| Объединённый CIDR | <https://github.com/farestz/mobile_cidr/releases/latest/download/all-mobile-ru.txt> |
| Объединённый CIDR + метаданные | <https://github.com/farestz/mobile_cidr/releases/latest/download/all-mobile-ru.json> |
| МТС | <https://github.com/farestz/mobile_cidr/releases/latest/download/mts.txt> |
| МегаФон | <https://github.com/farestz/mobile_cidr/releases/latest/download/megafon.txt> |
| Билайн | <https://github.com/farestz/mobile_cidr/releases/latest/download/beeline.txt> |
| T2 (Tele2) | <https://github.com/farestz/mobile_cidr/releases/latest/download/tele2.txt> |

Скачать всё одним `curl`:

```bash
BASE=https://github.com/farestz/mobile_cidr/releases/latest/download
curl -fLO "$BASE/mobile-ru.dat"
curl -fLO "$BASE/all-mobile-ru.txt"
```

## Использование в xray-core / v2ray / happ

`mobile-ru.dat` — Protocol Buffers `GeoIPList`, тот же формат, что у [v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat). Внутри пять тегов:

| Тег | Что внутри |
|-----|------------|
| `geoip:mts` | Все CIDR МТС |
| `geoip:megafon` | МегаФон |
| `geoip:beeline` | Билайн |
| `geoip:tele2` | T2 |
| `geoip:mobile` | Объединённый список (МТС + МегаФон + Билайн + T2) |

В happ-конфиге (раздел `Geoipurl`):

```json
{
  "Geoipurl": "https://github.com/farestz/mobile_cidr/releases/latest/download/mobile-ru.dat",
  "DirectIp": ["geoip:mobile"]
}
```

Или, если файл подкладывается рядом с основным `geoip.dat` (xray читает его из `XRAY_LOCATION_ASSET`):

```json
"DirectIp": ["ext:mobile-ru.dat:mobile"]
```

В Keenetic / OPNsense / pf — заливать `<operator>.txt` или `all-mobile-ru.txt` (по одной CIDR на строку).

## Что покрывается

Сейчас в `sources.yaml` 44 ASN всех четырёх операторов. **В сборку включаются только сотовые ASN**: облачные подразделения (MTS-CLOUD, MTS-NGCLOUD), стриминговые (MTS-STREAM/KION) и фиксированно-широкополосные «дочки» (МГТС) сознательно исключены, чтобы lookup на «мобильный?» не давал ложных срабатываний. Список и обоснование — в комментариях `data/sources.yaml`.

MVNO (Yota, Tinkoff Mobile, СберМобайл, ВТБ Мобайл, Газпромбанк Мобайл) собственных ASN не имеют — их IP выдаются из пулов хост-операторов (МегаФон / T2) и автоматически попадают в покрытие.

Только **IPv4**. IPv6 не используется потребителями (xray/Keenetic роутинг-конфиги).

## Локально

```bash
# Сборка артефактов из RIPEstat (нужен uv для inline-script зависимостей)
./scripts/fetch.py

# xray-core geoip.dat
./scripts/build_geoip.py

# Проверить, чей IP (stdlib only)
./scripts/lookup.py 95.84.128.1
./scripts/lookup.py 95.84.128.1 178.176.0.1 8.8.8.8
echo "95.84.128.1" | ./scripts/lookup.py -
```

Формат вывода `lookup.py`:

```
95.84.128.1   megafon   AS31133   95.84.128.0/19
8.8.8.8       NOT_MOBILE
```

## Гарантии корректности

- `fetch.py` при каждом запуске сверяет реальный RIPE `holder` каждого ASN с заявленным в `sources.yaml`. Если кто-то «переехал» между операторами — печатается `MISMATCH` с предупреждением.
- В `sources.yaml` ведётся блок «ИСКЛЮЧЕНО» с пояснением, почему ASN был удалён — чтобы случайно не вернулся.
- Источник — публичные RIPE BGP-анонсы, обновляются непрерывно. Релиз пересобирается каждую ночь.

## Лицензия

Списки сами по себе — публичные данные RIPE. Скрипты — без ограничений.
