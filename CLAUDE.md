# mobile_cidr

Сбор и поддержка актуальных CIDR-списков мобильных операторов РФ для использования в правилах роутинга (xray-core, Keenetic, happ-конфиги в соседнем `../routing/`).

## Зачем

Мобильные операторы РФ выдают абонентам IP из своих AS. Нужен инструмент, который:

1. По списку AS-номеров операторов собирает все анонсируемые префиксы.
2. Сохраняет их в воспроизводимом виде (plain CIDR + JSON с метаданными).
3. Поддерживает регулярное обновление (источники меняются: новые префиксы появляются, старые отзываются).

## Операторы и AS-номера

Канонический список — в `data/sources.yaml`. Кратко:

| Оператор | Основные ASN | Примечание |
|----------|--------------|------------|
| МТС | AS8359, AS29497, AS8003, AS35728 | AS8359 — backbone, AS29497 — mobile |
| МегаФон | AS31133, AS25159 | Yota — внутри AS31133 (MVNO) |
| Билайн (ВымпелКом) | AS3216, AS8402 | AS3216 — backbone |
| T2 (Tele2) | AS41330, AS31213, AS50543 | Tinkoff Mobile, SberMobile — MVNO на T2 |

> Перед обновлением списка ASN — сверяться с RIPE: операторы реструктуризируются, появляются новые AS.

## Источники данных

В порядке приоритета:

1. **RIPEstat Data API** (https://stat.ripe.net/docs/02.data-api/announced-prefixes.html) — основной источник.
   `GET https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS<N>`
   Возвращает список анонсируемых префиксов с временными метками. Free, без авторизации, лимиты щадящие.

2. **BGPView API** (https://bgpview.docs.apiary.io/) — резервный.
   `GET https://api.bgpview.io/asn/<N>/prefixes`
   Free, есть rate-limit (~1 req/s).

3. **RIPE WHOIS REST** (https://rest.db.ripe.net/) — для перекрёстной проверки `inetnum` и принадлежности префикса.

4. **bgp.tools** (https://bgp.tools/) — UI для ручной верификации, API требует регистрации.

Hurricane Electric (bgp.he.net) **не использовать** для автоматизации — только UI без API.

## Структура

```
mobile_cidr/
├── CLAUDE.md
├── .github/workflows/build.yml  # CI: ежедневный сбор → release `latest`
├── data/
│   └── sources.yaml             # ЕДИНСТВЕННЫЙ источник в git (operator → ASN)
├── scripts/
│   ├── fetch.py                 # RIPEstat → raw/, cidrs/, combined/
│   ├── build_geoip.py           # cidrs/ → geoip/mobile-ru.dat (xray-core)
│   └── lookup.py                # IP → оператор / NOT_MOBILE
└── data/                        # всё ниже — .gitignore, генерируется
    ├── raw/<asn>.json           # сырой ответ RIPEstat (для отладки)
    ├── cidrs/<slug>.{txt,json}  # CIDR на оператора
    ├── combined/all-mobile-ru.{txt,json}
    └── geoip/mobile-ru.dat
```

**В git хранится только вход (`sources.yaml`) и код.** Все артефакты —
плод запуска `scripts/fetch.py && scripts/build_geoip.py`. В CI
GitHub Actions запускает их ежедневно в 04:17 UTC и обновляет
rolling-релиз `latest` со всеми файлами.

## Релизы и стабильные URL

CI публикует артефакты в [Releases](../../releases/tag/latest):

| Файл | Стабильный URL |
|---|---|
| `mobile-ru.dat` | `https://github.com/<owner>/mobile_cidr/releases/latest/download/mobile-ru.dat` |
| `all-mobile-ru.txt` | `…/releases/latest/download/all-mobile-ru.txt` |
| `all-mobile-ru.json` | `…/releases/latest/download/all-mobile-ru.json` |
| `<operator>.txt` | `…/releases/latest/download/<operator>.txt` |

Эти URL подставляются в happ-конфиги (`Geoipurl`) и любые другие потребители.

## Использование

**Обновить списки:**
```bash
./scripts/fetch.py
```

**Проверить IP:**
```bash
./scripts/lookup.py 95.84.128.1
./scripts/lookup.py 95.84.128.1 178.176.0.1 8.8.8.8     # несколько за раз
echo "95.84.128.1" | ./scripts/lookup.py -              # из stdin
```
Формат вывода (TSV): `<ip>\t<operator(s)>\tAS<n>\t<matched-cidr>` или `<ip>\tNOT_MOBILE`.

**Собрать xray-core geoip.dat:**
```bash
./scripts/build_geoip.py
# → data/geoip/mobile-ru.dat (~50 KB)
```
Внутри пять тегов:

| Тег | Что матчит |
|-----|------------|
| `geoip:mts` | МТС (все ASN из `sources.yaml`) |
| `geoip:megafon` | МегаФон |
| `geoip:beeline` | Билайн |
| `geoip:tele2` | T2 (Tele2) |
| `geoip:mobile` | union всех четырёх (= `data/combined/all-mobile-ru.txt`) |
| `geoip:<X>_not` | Парный reverse-вариант для каждого тега выше (всё, чего НЕТ в X) |

Reverse-варианты — это копии CIDR-наборов с флагом `reverse_match=true`
в protobuf-сообщении `GeoIP`. xray-core при матчинге инвертирует
результат. Это намного дешевле, чем считать комплемент CIDR-набора
(который дал бы ~миллион CIDR на ~весь IPv4-простор).

Проверка валидности: `V2RAY_LOCATION_ASSET=$PWD/data/geoip v2ray test -c <config>`.

**Использование в xray/happ-конфиге** (см. `../routing/`):

Если файл подменяет основной `geoip.dat` (через `Geoipurl`):
```json
"DirectIp": ["geoip:mobile"]
"ProxyIp":  ["geoip:mts", "geoip:megafon"]
```

Если используется как дополнительный (не подменяя `geoip.dat`):
```json
"DirectIp": ["ext:mobile-ru.dat:mobile"]
```
Файл должен лежать в asset-директории xray (`V2RAY_LOCATION_ASSET` / `XRAY_LOCATION_ASSET`).

## Формат хранения

**`data/cidrs/<operator>.txt`** — один CIDR на строку, отсортировано, IPv4 и IPv6 раздельно или в одном файле (договоримся при первом запуске):
```
2.60.0.0/15
5.16.0.0/13
...
```

**`data/cidrs/<operator>.json`** — структурированно, для трекинга изменений:
```json
{
  "operator": "mts",
  "asns": [8359, 29497, 8003, 35728],
  "updated_at": "2026-05-12T18:00:00Z",
  "source": "RIPEstat",
  "prefixes": [
    {"cidr": "2.60.0.0/15", "asn": 8359, "family": 4},
    {"cidr": "2a00:1370::/32", "asn": 29497, "family": 6}
  ]
}
```

**`data/combined/all-mobile-ru.txt`** — финальный артефакт для подстановки в `DirectIp`/`ProxyIp` xray-конфигов.

## Обновление

Запуск фетчера обновляет `data/raw/`, `data/cidrs/`, `data/combined/`. Изменения коммитятся, чтобы diff показывал, какие префиксы появились/исчезли — это полезно для аудита.

Расписание — пока вручную; позже можно повесить cron/GitHub Action.

## Правила

- **Не дедуплицировать вслепую.** Если один и тот же CIDR анонсируется двумя операторами через разные AS — фиксируем оба факта в JSON, а в `.txt` оставляем один.
- **Не фильтровать по «mobile-only».** RIPEstat возвращает все анонсы AS — и магистраль, и сотовые подсети. Разделить их без приватных данных оператора невозможно; в роутинге это обычно не критично, но факт нужно держать в голове.
- **Только IPv4.** Потребители (xray/Keenetic роутинг-конфиги) IPv6 не используют — фильтруем в `fetch.py` на этапе парсинга RIPEstat.
- **Сырые ответы API хранить в `data/raw/`** — нужны для аудита и для отслеживания «когда префикс пропал».

## Связанное

- `../routing/` — xray/happ конфиги, потребители этого списка
- `[[mobile_cidr]]` MOC в `knowledge/Projects/personal/mobile_cidr/`
