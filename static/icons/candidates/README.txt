SVG-кандидаты из Figma для страницы /cabinet/icons/preview/

Быстрый старт без экспорта:
  Кнопка «Применить набор Hugeicons» на странице превью (CDN, Stroke Rounded).

Кастомные правки из Figma:
  Имя файла = ключ иконки + .svg
  Примеры:
    cabinet.notifications.svg
    action.upload.svg
    nav.home.svg

  Набор: Hugeicons 4000+ free, стиль Stroke Rounded, 24×24.
  Slug для поиска — в таблице «Инвентарь» на странице превью (upload-01 и т.д.).

  Источник SVG: npm-пакет @hugeicons/static (тот же набор, что в Figma Hugeicons).
  Пример: npx npm pack @hugeicons/static && tar -xzf hugeicons-static-*.tgz
  Файлы лежат в package/icons/*.svg — копируйте в static/icons/hugeicons/svg/
  или сюда как action.quick_edit_save.svg для колонки «Figma SVG».

  Экспорт: SVG, outline/stroke, без фона.
  После копирования файлов обновите превью в браузере (Ctrl+F5).
