# Логика сохранения графика смен

## Полный процесс

### 1. КЛИЕНТ (шаблон + JavaScript)

#### Рендеринг таблицы (templates/shifts/graph.html)

```
{% for row in table_rows %}  <!-- row.i = 0, 1, 2, 3, ... -->
  {% for cell in row.day_cells %}
    <input name="cell_{{ row.i }}_{{ cell.key }}" value="{{ cell.val }}">
    <!-- Пример: cell_0_01, cell_0_02, ..., cell_1_01, cell_1_02, ... -->
  {% endfor %}
{% endfor %}
```

**Ключевой момент**: `row.i` — это индекс в ОТФИЛЬТРОВАННОМ И ПЕРЕСОРТИРОВАННОМ DataFrame (0, 1, 2, 3, ...)

#### Фильтрация (клиент)

На странице есть два состояния фильтров:
1. **Filter form** (`#graph-filter-form`) — текущие фильтры пользователя (GET параметры)
2. **Save form** (`#graph-save-form`) — скрытые поля для передачи фильтров при сохранении

#### Сохранение (saveNow функция)

```javascript
function saveNow() {
  // 1. Синхронизируем dep_mode и pos_mode из filter-формы в save-форму
  hiddenDepMode.value = currentDepMode.value
  hiddenPosMode.value = currentPosMode.value

  // 2. Копируем все dep и pos checkboxes из filter-формы в save-форму
  // Удаляем старые, добавляем новые из текущего состояния фильтра

  // 3. Отправляем POST с FormData(save-form)
  fetch(window.location.href, {
    method: "POST",
    body: new FormData(form)  // Содержит все cell_i_d inputs
  })
}
```

**Критически важно**: Фильтры синхронизируются перед отправкой!

---

### 2. СЕРВЕР (GET обработка)

#### graph_views.py, GET ветвь

```python
# 1. Загружаем ВСЕ сотрудников (employees_df)
employees_df = _employees_for_user(request)

# 2. Загружаем ВСЕ данные из файла графика
schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)

# 3. Добавляем столбцы "Отдел", "Должность"
schedule_df = _schedule_with_department(schedule_df, employees_df)
# Индексы в schedule_df совпадают с исходными индексами в DataFrame (0, 1, 2, ...)

# 4. Получаем ВСЕ уникальные отделы и должности
all_deps = sorted(schedule_df["Отдел"].unique())  # ["1", "2", "3"]
all_positions = sorted(schedule_df["Должность"].unique())  # ["Нач", "Опер", ...]

# 5. Извлекаем ТЕКУЩИЕ выбранные фильтры из GET параметров
selected_deps, dep_mode = _extract_selected_deps(request, all_deps, from_post=False)
selected_positions, pos_mode = _extract_selected_positions(request, all_positions, from_post=False)

# 6. Создаём маппинг для сортировки (rank = порядок в списке all_deps)
dep_rank = {"1": 0, "2": 1, "3": 2}  # Зависит от порядка в all_deps
pos_rank = {"Нач": 0, "Опер": 1}

# 7. ФИЛЬТРУЕМ и СОРТИРУЕМ
schedule_df = schedule_df[
    schedule_df["Отдел"].isin(selected_deps)
    & schedule_df["Должность"].isin(selected_positions)
].copy()
# Теперь schedule_df содержит ТОЛЬКО нужные строки
# Индексы могут быть: [5, 2, 8, 1, ...] (в порядке исходного DataFrame)

schedule_df = _sort_graph_rows(schedule_df, dep_rank, pos_rank).reset_index(drop=True)
# После sort_values: строки переупорядочены
# После reset_index: индексы становятся 0, 1, 2, 3, ...

# 8. Генерируем table_rows с i = 0, 1, 2, 3, ...
for i in range(len(schedule_df)):
    row = schedule_df.iloc[i]
    table_rows.append({"i": i, ...})  # i это 0, 1, 2, 3, ...
```

**Результат на клиенте**: inputs вроде `cell_0_01`, `cell_1_01`, где i это 0, 1, 2, 3, ...

---

### 3. СЕРВЕР (POST обработка)

#### graph_views.py, POST ветвь — КРИТИЧЕСКАЯ ЛОГИКА

```python
# 1. Загружаем ПОЛНЫЙ файл графика
full_schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
# Индексы: [0, 1, 2, 3, ...]

# 2. Добавляем столбцы "Отдел", "Должность"
schedule_df = _schedule_with_department(full_schedule_df, employees_df)
# Индексы в schedule_df совпадают с full_schedule_df: [0, 1, 2, 3, ...]

# 3. Получаем ВСЕ уникальные отделы и должности (КАК И НА GET!)
all_deps = sorted(schedule_df["Отдел"].unique())
all_positions = sorted(schedule_df["Должность"].unique())

# 4. ВАЖНО: Извлекаем фильтры ИЗ POST (которые клиент синхронизировал!)
selected_deps, _dep_mode = _extract_selected_deps(request, all_deps, from_post=True)
selected_positions, _pos_mode = _extract_selected_positions(request, all_positions, from_post=True)

# 5. Создаём маппинг (ДОЛЖЕН БЫТЬ ИДЕНТИЧЕН GET!)
dep_rank = _dept_rank_map(all_deps)
pos_rank = _pos_rank_map(all_positions)

# 6. ФИЛЬТРУЕМ и СОРТИРУЕМ (ТОЧНО КАК НА GET!)
filtered = schedule_df[
    schedule_df["Отдел"].isin(selected_deps)
    & schedule_df["Должность"].isin(selected_positions)
].copy()
filtered = _sort_graph_rows(filtered, dep_rank, pos_rank)

# ⭐ КРИТИЧЕСКАЯ СТРОКА: Сохраняем индексы ДО reset_index
# Это индексы в schedule_df, которые совпадают с индексами в full_schedule_df!
filtered_indices = filtered.index.tolist()  # Например: [5, 2, 8, 1, ...]

filtered = filtered.reset_index(drop=True)
# Теперь индексы в filtered: 0, 1, 2, 3, ...
# Но мы помним старые индексы в filtered_indices!

# 7. ОБНОВЛЯЕМ ДАННЫЕ В ПОЛНОМ DATAFRAME
for i in range(len(filtered)):
    full_idx = filtered_indices[i]  # Индекс в full_schedule_df
    for d in day_columns:
        key = f"cell_{i}_{d}"  # Соответствует INPUT с клиента
        if key not in request.POST:
            continue
        raw = request.POST.get(key)
        # Обновляем ПРАВИЛЬНУЮ строку в full_schedule_df!
        full_schedule_df.at[full_idx, d] = raw

# 8. Сохраняем в файл
biota_schedule.save_schedule_table(full_schedule_df, y, m)
```

---

## Почему это работает

### Сопоставление индексов

| Шаг | Что происходит | Индексы |
|-----|---|---|
| GET: Фильтруем | `schedule_df[condition]` | `[5, 2, 8, 1]` |
| GET: Сортируем | `_sort_graph_rows()` | `[5, 2, 8, 1]` (переупорядочены, но индексы те же) |
| GET: Reset | `reset_index(drop=True)` | `[0, 1, 2, 3]` |
| GET: table_rows | `{"i": 0}, {"i": 1}, ...` | Клиент получает inputs `cell_0_d`, `cell_1_d`, ... |
| | | |
| POST: Фильтруем | `schedule_df[condition]` | `[5, 2, 8, 1]` |
| POST: Сортируем | `_sort_graph_rows()` | `[5, 2, 8, 1]` |
| POST: Сохраняем | `filtered_indices = [5, 2, 8, 1]` | Помним индексы! |
| POST: Reset | `reset_index(drop=True)` | `[0, 1, 2, 3]` |
| POST: Обновляем | `full_idx = filtered_indices[i]` | Используем сохранённые индексы `[5, 2, 8, 1]` |
| | `full_schedule_df.at[full_idx, d] = raw` | Обновляем правильные строки! |

### Почему индексы совпадают между GET и POST

1. **all_deps и all_positions одинаковые**: оба вычисляются из `sorted(schedule_df.unique())`
2. **dep_rank и pos_rank одинаковые**: оба создаются через `_dept_rank_map(all_deps)`
3. **Фильтрация одинаковая**: обе используют `isin()` с selected_deps и selected_positions
4. **Сортировка одинаковая**: обе используют `_sort_graph_rows()` с одинаковыми рангами
5. **selected_deps и selected_positions одинаковые**: клиент синхронизирует их перед отправкой!

---

## Потенциальные проблемы и их предотвращение

### ❌ Проблема 1: Разные фильтры на GET и POST

**Как это происходит**: Клиент не синхронизирует фильтры, POST отправляет старые фильтры

**Решение**: `saveNow()` копирует текущие фильтры из filter-формы перед POST

### ❌ Проблема 2: Разный порядок строк на GET и POST

**Как это происходит**: Разное количество строк в selected_deps/selected_positions или разная сортировка

**Решение**: Используем `_sort_graph_rows()` с одинаковыми рангами на GET и POST

### ❌ Проблема 3: Индексы не совпадают после сортировки

**Как это происходит**: reset_index() на GET но не на POST (или наоборот)

**Решение**: На POST сохраняем индексы ДО reset_index, потом используем их при обновлении

### ❌ Проблема 4: Неправильные строки обновляются

**Как это происходит**: Использование enumerate индекса вместо сохранённого индекса

**Решение**: `full_idx = filtered_indices[i]` гарантирует обновление правильной строки в full_schedule_df

---

## Отладка

Если сохранение не работает:

1. **Проверить логи**: server logs должны показать какие фильтры используются
2. **Проверить POST данные**: DevTools → Network → график POST запрос
3. **Проверить cell_i_d**: inputs вроде `cell_0_01`, `cell_1_02` должны быть в POST данных
4. **Проверить порядок строк**: убедиться, что на GET и POST один и тот же порядок (по отделу → должности → фамилии)
5. **Проверить индексы**: `filtered_indices` должны соответствовать индексам в full_schedule_df

---

## Краткая суть

**На клиенте**: inputs именуются как `cell_0_d`, `cell_1_d`, где 0, 1 — это позиция в отфильтрованной и отсортированной таблице

**На сервере при GET**: создаём table_rows с i = 0, 1, 2, после reset_index, чтобы совпадать с клиентскими индексами

**На сервере при POST**: сохраняем настоящие индексы из full_schedule_df ДО reset_index, потом используем их для обновления, чтобы данные сохранились в правильные строки

**Критическое условие**: GET и POST должны использовать ОДИНАКОВЫЕ фильтры, сортировку и сопоставление индексов
