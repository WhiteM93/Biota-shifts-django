# Заметки по производительности MetaBase / Biota-shifts-django

Дата: 2026-07-09. Только анализ и план — без обязательства выполнить всё сразу.

---

## Короткий вывод

Сайт «тяжёлый» не из‑за дизайна, а из‑за архитектуры: каждая страница тащит много лишнего на сервере и в браузере. На телефоне это часто выглядит как «не грузится» (белый экран, таймаут, падение вкладки).

Сравнение с [metawork.work-shifts.ru](https://metawork.work-shifts.ru): похожий UI, но один минифицированный CSS (~236 KB → ~40–60 KB gzip), service worker, page-specific JS. У нас — монолиты без сборки и кэша.

---

## Симптомы на телефоне

| Симптом | Вероятная причина |
|---------|-------------------|
| Белый экран 20–40 сек, потом ошибка | `/home/` или `/graph/` — сервер/БД не успевает (TTFB) |
| Открылась, потом зависла / закрылась вкладка | Десктопный график (тысячи DOM-узлов) или `/products/` с 24× WebGL |
| Иногда грузится, иногда нет | Нестабильная сеть + много HTTP-запросов без кэша |
| Логин долго «молчит» | Blocking JS + `biota_global.css` на каждой странице |

---

## Бэкенд (TTFB)

### Главная `/home/` (точка входа после логина)

До первого байта HTML:
- `load_employees()` из внешней БД Biota (без LRU-кэша)
- `load_schedule_table()` на месяц
- `late_early_minutes_per_employee_month()` по всем сотрудникам
- context processor: `_load_users_store()` — JSON с диска **2 раза** без кэша

### Склад `/inventory/` (любая вкладка)

Один view ~1900 строк. Даже `?panel=purchases` гоняет:
- ~37 запросов `_distinct_*` для фильтров
- историю, выдачи, каталог инструментов, заявки (300), брак

### Карточка изделия

- N+1 по `ProductNote` на каждую установку
- чтение файлов программ с диска в цикле
- `plan_material_suggestions()` — полный скан `Product` + `ProductSetup`

### График `/graph/`

- pandas + внешняя PostgreSQL
- DOM: сотрудник × день = тысячи `<input>`
- ~900 строк inline JS + html2canvas (CDN)

### Инфраструктура (проверить на проде)

- `DEBUG=True` по умолчанию, если не `DJANGO_DEBUG=0`
- нет `CACHES` в settings
- `CONN_MAX_AGE=0` — новое PG-подключение на запрос
- конфигов nginx/gunicorn **нет в репозитории**
- media/STL через Django (`DJANGO_SERVE_MEDIA=1`) — медленно

---

## Фронтенд

### Крупнейшие файлы (без минификации)

| Файл | ~Размер |
|------|---------|
| `product_detail.js` | 196 KB |
| `product_detail.css` | 133 KB |
| `machines.js` | 110 KB |
| `inventory.js` | 96 KB |
| `biota_global.css` | 54 KB (на **каждой** странице) |

Нет webpack/vite, нет `.min.js`/`.min.css`, нет service worker.

### Вкладка «Закупки»

- `inventory.js` (96 KB) — логика всего склада
- JSON `#inv-options` в HTML — ~30 массивов enum'ов инструмента (не нужны на закупках)

### График на телефоне

- Мобильная версия **есть**: `/graph/mobile/`
- `is_mobile_user_agent()` написана, но **не подключена** к auto-redirect
- Меню ведёт на `/graph/` (десктоп) → OOM / зависание

### Наладки `/products/`

- Three.js с jsdelivr
- до 24 одновременных WebGL-превью + STL с `/media/`
- лимит WebGL на мобильном ~8–16 контекстов

### Blocking-скрипты

- inline JS в `<head>` `base.html`
- `biota_delete_btn.js` без `defer`
- html2canvas в `graph.html` без defer

---

## Metawork vs Biota

| | Biota | Metawork |
|---|-------|----------|
| CSS | 5–8 файлов, без minify | 1× `.min.css` + content-hash |
| JS | монолиты 96–196 KB | маленькие page-specific (login.js ~8 KB) |
| Кэш | `?v=45` вручную | SW + hashed filenames |
| PWA | manifest без SW | manifest + service-worker.js |
| 3D | Three.js + 24 WebGL | нет |

---

## План оптимизации (приоритет)

### Быстрые wins

1. ~~Убрать склад с главной~~ (сделано 2026-07-09)
2. ~~Пакет A (feature flags)~~ — ветка `perf/package-a`, см. ниже
3. Auto-redirect телефонов `/graph/` → `/graph/mobile/` — **BIOTA_PERF_MOBILE_GRAPH**
4. `defer` на `biota_delete_btn.js` — **BIOTA_PERF_DEFER_SCRIPTS**
5. Кэш `_load_users_store()` — **BIOTA_PERF_USERS_STORE_CACHE_SEC**
6. Не грузить `inventory.js` + `#inv-options` на `panel=purchases`

### Средний эффект

6. Облегчить `/home/` — кэш сводки или lazy-таблицы
7. 3D на `/products/` только по клику
8. Minify + gzip на nginx

### Структурные

9. Разделить `inventory_view` по вкладкам
10. Vite/esbuild + content-hash
11. Service worker / HTTP cache headers
12. Виртуализация таблицы графика

---

## Проверка на проде

```bash
# DJANGO_DEBUG=0, nginx отдаёт /static/ и /media/, gzip on
curl -I https://<сайт>/static/css/biota_global.css
```

На телефоне:
1. TTFB `/home/` после логина
2. `/graph/` vs `/graph/mobile/`
3. Падает ли `/products/`

Деплой после правок статики:
```bash
git pull origin master
python manage.py collectstatic --noinput
sudo systemctl restart <django-сервис>
# Ctrl+F5 в браузере
```

---

## Пакет A — включение и откат (ветка `perf/package-a`)

**По умолчанию всё выключено** — поведение сайта не меняется, пока не задана переменная.

### Включить на сервере для теста

```bash
git fetch origin
git checkout perf/package-a   # или git pull origin perf/package-a
# В .env:
BIOTA_PERF_PACKAGE_A=1
sudo systemctl restart <django-сервис>
```

Что делает `BIOTA_PERF_PACKAGE_A=1`:
- телефоны с `/graph/` автоматически на `/graph/mobile/` (cookie `graph_prefer_desktop=1` — полная таблица);
- `defer` на `biota_delete_btn.js`;
- кэш JSON прав пользователей 60 сек (сброс при сохранении users store).

### Откат без git (мгновенно)

```bash
# В .env:
BIOTA_PERF_PACKAGE_A=0
sudo systemctl restart <django-сервис>
```

### Откат по частям

```env
BIOTA_PERF_MOBILE_GRAPH=0
BIOTA_PERF_DEFER_SCRIPTS=0
BIOTA_PERF_USERS_STORE_CACHE_SEC=0
```

### Откат через git

```bash
git checkout master
sudo systemctl restart <django-сервис>
```

После проверки — merge `perf/package-a` → `master`.
