# Biota Shifts Django — памятка разработчика

Документ для онбординга: что это за приложение, из чего состоит, где «тонкости» при доработках. Предполагается, что ты один продолжаешь разработку и должен понимать не только код, но и окружение/данные вокруг него.

## Назначение проекта

Внутреннее веб-приложение на **Django 5.2**, которое объединяет:

- **Спланированные графики** из Excel (`schedule_<год>_<месяц>.xlsx`).
- **Фактические данные из PostgreSQL системы учёта (Biota / ZKBioTA)**: справочник сотрудников, табель/`att_payloadtimecard`, события СКУД в `iclock_transaction`.
- **Операционные модули на ORM Django** (склад инструмента, закупки, брак, расчётные профили ЗП по сотрудникам, каталог изделий и технологических наладок).
- **«Регламенты перерывов»** как отдельное приложение `regulations` с интерактивной шкалой и экспортами.

Целевая аудитория — производство и офисные роли с разной видимостью данных (отделы/участки, пункты меню, роли manager/executor).

## Структура репозитория (главное)

| Путь | Что здесь |
|------|-----------|
| `biota_site/` | Корень Django-проекта: `settings.py`, `urls.py`, `wsgi.py`. |
| `shifts/` | Основное приложение: маршруты, почти все бизнес-страницы, ORM-модели, представления. |
| `regulations/` | Регламенты перерывов: модели, API сохранения, страница и экспорты. |
| `biota_shifts/` | **Разделяемое ядро** логики/БД Excel/вычислений. Исторически совместимо с Streamlit-приложением: часть `auth.py` опционально тянет `streamlit`; в Django основной вход — через сессии. |
| `templates/` | Шаблоны; базовый каркас — `templates/base.html`. |
| `static/` | Статические файлы, `STATIC_ROOT` после `collectstatic` — `staticfiles/`. |
| `schedules/` (или путь из `BIOTA_SCHEDULE_DIR`) | Каталог с Excel графиками. Создаётся автоматически при старте, если используется путь по умолчанию в `biota_shifts.config`. |

## Две базы данных — ключевая идея

### 1) «Биота PostgreSQL» (read-only источник)

Подключение и SQL в **`biota_shifts/db.py`**. Конфиг из переменных `BIOTA_DB_*`, с опциональным переключателем профиля через `BIOTA_DB_PROFILE` (см. `.env.example`).

Ожидаемые основные таблицы (ориентир — ZKBioTA):

- `personnel_employee`, `personnel_department`, `personnel_position`, `personnel_area`, `personnel_employee_area`
- `att_payloadtimecard` (план/факт по дням)
- `iclock_transaction` (сырые отметки СКУД)

**Тонкости:**

- **Кэш LRU** на тяжёлых выборках (`functools.lru_cache`). Справочник сотрудников намеренно **без кэша**, чтобы правки в Biota сразу отражались. Сброс кэша: view `refresh_cache` (POST) и `biota_db.clear_biota_db_cache()`.
- При недоступности Biota по умолчанию включён **локальный fallback** на пустые датафреймы (`BIOTA_DB_LOCAL_FALLBACK`, по умолчанию разрешён). UI «живой», но данные пустые — не путать с «всё сломалось на SQL».
- Фильтр уволенных: по умолчанию `personnel_employee.is_active = true` (см. `employee_active_where_suffix()`). Переопределения через `BIOTA_INCLUDE_DISMISSED_EMPLOYEES` или `BIOTA_EMPLOYEE_ACTIVE_SQL`.
- Таймзона **Europe/Moscow** в настройках Django; в SQL для СКУД часто явное приведение `punch_time at time zone 'Europe/Moscow'`.

### 2) «Сайт БД» Django (`default`)

В `biota_site/settings.py`:

- Если **пустой** `SITE_DB_HOST` → **SQLite** `db.sqlite3` в корне проекта.
- Если задан хост → **PostgreSQL** для Django (сессии, админка, ORM-модели `shifts`, `regulations`).

**Тонкости:**

- В проде обычно нужен отдельный PostgreSQL (`SITE_DB_*`), иначе SQLite остаётся узким местом и риском по бэкапам/конкуренции записи.
- Проверка здоровья подключения и прав на запись — `shifts/db_health.py` (используется в ЛК).

## Excel-графики

Логика в **`biota_shifts/schedule.py`**.

- Имя файла: `schedule_<YYYY>_<MM>.xlsx` в `SCHEDULE_DIR` (`BIOTA_SCHEDULE_DIR` или `<project>/schedules`).
- Колонки дней: `p1,p2,p3` (хвост предыдущего месяца) + числовые `1..N` для текущего.
- Функции нормализации/сортировки колонок и привязки к датам — см. `is_schedule_day_column`, `schedule_column_to_date`.

Если график не найден или битый Excel, часть экранов покажет понятную ошибку; при отладке сначала проверяй **наличие файла** и **год/месяц** в UI.

## Аутентификация и права (важно для любых новых view)

### Модель пользователей

**Не** стандартный `django.contrib.auth.User` для бизнес-логики. Реальные пароли и профили лежат в JSON-файле:

- Путь: `BIOTA_USERS_STORE` или по умолчанию **`.biota_users.json`** в корне проекта (`biota_shifts.config.USERS_STORE_PATH`).
- Админ: логин из `BIOTA_ADMIN_USERNAME` (по умолчанию `admin`), пароль из `BIOTA_ADMIN_PASSWORD` (в `.env.secrets`).
- Регистрация создаёт запись с `approved: false` до подтверждения в ЛК.

**Тонкости:**

- Файл пользователей читается с **`utf-8-sig`** (BOM в начале иначе ломает первый ключ).
- Подписанные cookies для Streamlit (`biota_auth`) в Django **не заменяют** сессию; для веба источник истины — `request.session["biota_username"]`.

### Декораторы и middleware

- `shifts/auth_utils.biota_login_required` — доступ только после логина; неутверждённых пользователей выкидывает на login.
- `nav_permission_required` / спец-обработка `inventory_route_nav_access_required` — мелкая сетка прав по пунктам меню и панелям `/inventory/?panel=...`.
- `write_permission_required` — блокирует POST для роли «исполнитель» не-админов (сообщение + редирект).
- **`ExecutorReadOnlyMiddleware`** (`shifts/middleware.py`) — второй контур для «исполнителя»: на небезопасных методах отдаёт **403**; для AJAX с `X-Requested-With: XMLHttpRequest` вернёт JSON с `{"error":"read_only",...}` вместо HTML-форbidden.

При добавлении форм/API:

- Если это изменение данных — решай, нужен ли `write_permission_required` и учитывай AJAX-поведение middleware.
- Не добавляй «скрытые» POST без CSRF-токена в шаблонах — стандартный Django CSRF включён.

### Контекст шаблонов

`shifts/context_processors.biota_session` пробрасывает:

- отображаемое имя (для админа может браться из `session["admin_display_name"]`),
- `biota_nav` — доступные разделы,
- `biota_is_executor`, `biota_can_edit`.

## Маршрутизация (`shifts/urls.py`, `biota_site/urls.py`)

Корень сайта ведёт в приложение `shifts` (`"" -> include("shifts.urls")`). Отдельный префикс:

- `/regulations/...` — регламенты.

Полезные endpoints:

- `POST /refresh-cache/` — сброс LRU-кэша Biota (см. форму в `templates/base.html`), требует логина и проходит через `write_permission_required`.
- СКУД и отчёты: `/skud/` + выгрузки `.csv`/`.xlsx`/`.pdf` (не меняй расширения в URL без необходимости — ниже про nginx).

## Доменные области в ORM (`shifts/models.py`)

Кратко по сущностям:

- **Склад:** `ToolItem` + спеки (`EndMillSpec`, `TapSpec`, …), движения `StockMovement`, заявки `PurchaseRequest`.
- **Брак и ЗП:** `EmployeeDefectRecord`, `EmployeePayrollProfile`, `EmployeePayrollSettlement`, `EmployeePayrollMonthStatus`, `EmployeeDefectPayrollAdjustment`.
- **Изделия:** `Product`, `ProductSetup` (+ файлы УП, фото, строки инструмента в наладке).

Медиа-файлы изделий: `MEDIA_ROOT` (по умолчанию `<project>/media`). В dev Django может отдавать `/media/`; в проде обычно nginx, либо `DJANGO_SERVE_MEDIA=1` для gunicorn без nginx (см. комментарии в `settings.py`).

## Приложение `regulations`

- Модель `RegulationPlan` хранит план на дату, смену, окна перерывов и JSON `breaks` для динамических ползунков.
- URL-ы экспорта **намеренно без** суффиксов `.pdf/.xlsx` в пути (`regulations/urls.py`), чтобы reverse-proxy не отдал статику вместо ответа Django.

## Локальный запуск (минимум)

1. Python 3.11+ (ориентир — версия, на которой ставятся зависимости из `requirements.txt`).
2. `pip install -r requirements.txt`
3. Скопировать `.env.example` → `.env`, `.env.secrets.example` → `.env.secrets`, заполнить пароли.
4. `python manage.py migrate`
5. `python manage.py runserver`

Если Biota PostgreSQL недоступен, приложение частично «оживёт» на пустых данных (fallback), но разделы, завязанные на факт, будут пустыми.

## Продакшен-заметки

- Запуск через **gunicorn** (зависимость есть). Настрой `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`.
- `collectstatic` → `staticfiles/`, раздача через nginx.
- `X_FRAME_OPTIONS = "SAMEORIGIN"` — сознательно для PDF в `<iframe>/<object>` на том же домене.
- Большое число полей на формах табеля: `DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000`.

## Что почти не покрыто тестами

`shifts/tests.py` и `regulations/tests.py` — заготовки без кейсов. Регресии ловятся ручным прогоном сценариев и здравым смыслом вокруг SQL/Excel. Если проект живёт долго — первые кандидаты на автотесты:

- нормализация `emp_code` (`biota_shifts/emp_codes.py`),
- построение сетки часов из графика и отметок (`biota_shifts/logic.py`),
- права доступа (`auth_utils`, middleware).

## Типичные проблемы при доработке

- **«Пустые сотрудники» после логина** — проверь `approved`, `access_scope`, `nav`, `nav_dep_filters` у пользователя в `.biota_users.json` и связку `employees_df_for_nav` в представлениях.
- **Данные Biota не обновляются** — LRU-кэш; нажми «Обновить данные из БД» или вызови `clear_biota_db_cache()` в коде после осознанной мутации на стороне Biota *в этом же процессе* (на практике Biota read-only).
- **Расхождение времён СКУД** — следи за TZ в SQL (`Europe/Moscow`) и за тем, как pandas интерпретирует `timezone-aware` datetime.
- **Сломался первый ключ в `.biota_users.json`** — BOM; читать/писать только с корректной кодировкой (`utf-8-sig`).
- **Конфликт nginx и динамических отчётов** — см. паттерн URL в `regulations`; не вешай голые `.pdf` в путь без настройки `location`.

## Где искать код по задаче

| Задача | Стартовые файлы |
|--------|----------------|
| Новый экран или правка роутинга | `shifts/urls.py`, соответствующий `*_views.py` |
| Запрос к Biota | `biota_shifts/db.py`, агрегаты/`merge` — `biota_shifts/logic.py` |
| Excel-график | `biota_shifts/schedule.py` |
| Права/роли | `biota_shifts/auth.py`, `shifts/auth_utils.py`, `shifts/middleware.py`, ЛК — `shifts/cabinet_views.py` |
| Шаблон/навигация | `templates/base.html`, `shifts/context_processors.py` |
| Модель/админка | `shifts/models.py`, `shifts/admin.py` |
| Регламенты | `regulations/views.py`, `regulations/models.py`, `static/regulations/timeline.js` |

Этого достаточно, чтобы не гадать при первом билде после долгого перерыва или при переносе на новый сервер.
