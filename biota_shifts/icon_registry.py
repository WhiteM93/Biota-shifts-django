"""Каталог семантических иконок сайта (значения по умолчанию)."""
from __future__ import annotations

# kind: emoji | flaticon | text | partial
DEFAULT_ICON_REGISTRY: dict[str, dict] = {
    # —— Кабинет администратора ——
    "cabinet.django_admin": {
        "label": "Django Admin",
        "group": "Кабинет",
        "kind": "emoji",
        "value": "⚙",
    },
    "cabinet.schedule_backups": {
        "label": "Резервные копии графиков",
        "group": "Кабинет",
        "kind": "emoji",
        "value": "📅",
    },
    "cabinet.inventory_backups": {
        "label": "Резервные копии склада",
        "group": "Кабинет",
        "kind": "emoji",
        "value": "📦",
    },
    "cabinet.regulations_backups": {
        "label": "Резервные копии регламентов",
        "group": "Кабинет",
        "kind": "emoji",
        "value": "📋",
    },
    "cabinet.perf_diagnostics": {
        "label": "Медленные загрузки",
        "group": "Кабинет",
        "kind": "emoji",
        "value": "⏱",
    },
    "cabinet.notifications": {
        "label": "Уведомления",
        "group": "Кабинет",
        "kind": "emoji",
        "value": "🔔",
    },
    "cabinet.icons": {
        "label": "Справочник иконок",
        "group": "Кабинет",
        "kind": "emoji",
        "value": "🎨",
    },
    # —— Flaticon (действия) ——
    "action.upload": {
        "label": "Загрузить",
        "group": "Действия",
        "kind": "flaticon",
        "value": "fi fi-rr-upload",
    },
    "action.search": {
        "label": "Поиск / предпросмотр",
        "group": "Действия",
        "kind": "flaticon",
        "value": "fi fi-rr-search",
    },
    "action.add_document": {
        "label": "Добавить документ",
        "group": "Действия",
        "kind": "flaticon",
        "value": "fi fi-rr-add-document",
    },
    "action.add": {
        "label": "Добавить",
        "group": "Действия",
        "kind": "flaticon",
        "value": "fi fi-rr-add",
    },
    "action.camera": {
        "label": "Камера / фото",
        "group": "Действия",
        "kind": "flaticon",
        "value": "fi fi-rr-camera",
    },
    "action.copy": {
        "label": "Копировать",
        "group": "Действия",
        "kind": "flaticon",
        "value": "fi fi-rr-copy",
    },
    "action.plus": {
        "label": "Плюс (жирный)",
        "group": "Действия",
        "kind": "flaticon",
        "value": "fi fi-br-plus",
    },
    "action.calendar": {
        "label": "Календарь",
        "group": "Действия",
        "kind": "flaticon",
        "value": "fi fi-rr-calendar",
    },
    "action.picture": {
        "label": "Изображение",
        "group": "Действия",
        "kind": "flaticon",
        "value": "fi fi-rr-picture",
    },
    # —— Навигация (SVG-шаблоны) ——
    "nav.home": {
        "label": "Главная",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_home_icon.html",
    },
    "nav.inventory": {
        "label": "Склад",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_inventory_icon.html",
    },
    "nav.user": {
        "label": "Кабинет",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_user_icon.html",
    },
    "nav.forms": {
        "label": "Формы",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_forms_icon.html",
    },
    "nav.calendar": {
        "label": "График",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_calendar_icon.html",
    },
    "nav.hours_skud": {
        "label": "Часы / СКУД",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_hours_skud_icon.html",
    },
    "nav.hr_payroll": {
        "label": "Зарплата",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_hr_payroll_icon.html",
    },
    "nav.machines": {
        "label": "Станки",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_machines_icon.html",
    },
    "nav.setups": {
        "label": "Наладки",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_setups_icon.html",
    },
    "nav.calculator": {
        "label": "Калькулятор",
        "group": "Навигация",
        "kind": "partial",
        "value": "shifts/includes/nav_calculator_icon.html",
    },
    # —— Прочие SVG ——
    "action.delete": {
        "label": "Удалить",
        "group": "Действия",
        "kind": "partial",
        "value": "shifts/includes/biota_delete_icon.html",
    },
    "action.quick_edit": {
        "label": "Быстрое редактирование",
        "group": "Действия",
        "kind": "partial",
        "value": "shifts/includes/quick_edit_edit_icon.html",
    },
    "action.quick_edit_save": {
        "label": "Сохранить (быстрое редактирование)",
        "group": "Действия",
        "kind": "svg_static",
        "value": "icons/hugeicons/svg/floppy-disk.svg",
    },
    "pdf.export_specs": {
        "label": "PDF — спецификация",
        "group": "PDF",
        "kind": "partial",
        "value": "shifts/includes/pdf_export_specs_icon.html",
    },
    "pdf.export_photos": {
        "label": "PDF — фото",
        "group": "PDF",
        "kind": "partial",
        "value": "shifts/includes/pdf_export_photos_icon.html",
    },
    "setup.load_to_machine": {
        "label": "Загрузить инструмент в станок",
        "group": "Наладка",
        "kind": "partial",
        "value": "shifts/includes/setup_load_to_machine_icon.html",
    },
    "setup.tool_note_view": {
        "label": "Примечание (просмотр)",
        "group": "Наладка",
        "kind": "partial",
        "value": "shifts/includes/setup_tool_note_view_icon.html",
    },
    # —— Текстовые символы ——
    "ui.lock": {
        "label": "Заблокировано",
        "group": "Интерфейс",
        "kind": "svg_static",
        "value": "icons/hugeicons/svg/square-lock-01.svg",
    },
    "ui.unlock": {
        "label": "Разблокировано",
        "group": "Интерфейс",
        "kind": "svg_static",
        "value": "icons/hugeicons/svg/square-unlock-01.svg",
    },
    "ui.close": {
        "label": "Закрыть",
        "group": "Интерфейс",
        "kind": "text",
        "value": "×",
    },
    "ui.refresh": {
        "label": "Обновить",
        "group": "Интерфейс",
        "kind": "text",
        "value": "↻",
    },
}

ICON_KINDS = ("emoji", "flaticon", "text", "partial", "svg_static", "hugeicons")
