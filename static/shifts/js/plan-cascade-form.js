/**
 * Plan Cascade Form Manager
 *
 * Управляет каскадной видимостью полей в форме планирования изделия.
 * Реализует сложную логику показа/скрытия полей в зависимости от выбора:
 * - Тип изделия (Изделие, Сборка, ПКИ)
 * - Вид заготовки (Ленточная пила, Лазерная резка, ПКИ)
 * - Специфичные параметры для каждого пути
 */

class PlanCascadeFormManager {
  /**
   * Инициализация менеджера формы
   * @param {HTMLElement} containerElement - контейнер с форм ой
   */
  constructor(containerElement) {
    this.container = containerElement;
    this.state = {
      product_type: '',
      workpiece_type: '',
      laser_thickness: '',
      material: '',
      workpiece_size: '',
      workpiece_type_enum: ''
    };
    this.fieldElements = {};
    this.selectElements = {};
    this.inputElements = {};

    this.init();
  }

  /**
   * Инициализация: поиск элементов и подключение слушателей
   */
  init() {
    this.cacheFieldElements();
    this.cacheSelectElements();
    this.cacheInputElements();
    this.attachEventListeners();
    this.syncStateFromDOM();
    this.updateFieldVisibility();
    this._onInlineEditMode = this._onInlineEditMode.bind(this);
    window.addEventListener("setup-inline-edit-mode", this._onInlineEditMode);
    this.setFormEnabled(document.body.classList.contains("setup-inline-edit-enabled"));
  }

  /**
   * Включить/выключить поля (только в режиме «Быстрое редактирование»).
   */
  setFormEnabled(enabled) {
    this.container.classList.toggle("is-plan-readonly", !enabled);
    this.container.querySelectorAll("select, input").forEach(function (el) {
      el.disabled = !enabled;
    });
  }

  _onInlineEditMode(ev) {
    var enabled = !!(ev && ev.detail && ev.detail.enabled);
    this.setFormEnabled(enabled);
  }

  /**
   * Кэширование все field контейнеров по data-field атрибуту
   */
  cacheFieldElements() {
    const fields = this.container.querySelectorAll('.form-field[data-show-when]');
    fields.forEach(field => {
      const dataField = field.getAttribute('data-field');
      if (dataField) {
        this.fieldElements[dataField] = field;
      }
    });

    // Кэшировать также всегда видимые поля
    const alwaysVisible = this.container.querySelectorAll('.form-field--always-visible');
    alwaysVisible.forEach(field => {
      const dataField = field.getAttribute('data-field');
      if (dataField) {
        this.fieldElements[dataField] = field;
      }
    });
  }

  /**
   * Кэширование всех select элементов
   */
  cacheSelectElements() {
    const selects = this.container.querySelectorAll('select[data-field]');
    selects.forEach(select => {
      const dataField = select.getAttribute('data-field');
      this.selectElements[dataField] = select;
    });
  }

  /**
   * Кэширование всех input элементов
   */
  cacheInputElements() {
    const inputs = this.container.querySelectorAll('input[data-field]');
    inputs.forEach(input => {
      const dataField = input.getAttribute('data-field');
      this.inputElements[dataField] = input;
    });
  }

  /**
   * Подключение слушателей событий на селекты и inputs
   */
  attachEventListeners() {
    // Слушатели для select элементов
    Object.entries(this.selectElements).forEach(([fieldName, select]) => {
      select.addEventListener('change', (e) => {
        this.setState(fieldName, e.target.value);
      });
    });

    // Слушатели для input элементов
    Object.entries(this.inputElements).forEach(([fieldName, input]) => {
      input.addEventListener('change', (e) => {
        this.setState(fieldName, e.target.value);
      });

      // Для текстовых inputs также обновлять при вводе (для валидации)
      if (input.type === 'text' || input.type === 'number') {
        input.addEventListener('input', (e) => {
          this.state[fieldName] = e.target.value;
        });
      }
    });
  }

  /**
   * Синхронизировать state из текущих значений DOM
   */
  syncStateFromDOM() {
    Object.entries(this.selectElements).forEach(([fieldName, select]) => {
      this.state[fieldName] = select.value;
    });

    Object.entries(this.inputElements).forEach(([fieldName, input]) => {
      this.state[fieldName] = input.value;
    });
  }

  /**
   * Сбросить фокус с активного поля формы и синхронизировать state (перед отправкой).
   */
  prepareForSubmit() {
    const active = document.activeElement;
    if (active && this.container.contains(active)) {
      const tag = (active.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'select' || tag === 'textarea') {
        active.blur();
      }
    }
    this.syncStateFromDOM();
  }

  /**
   * Обновить состояние и пересчитать видимость полей
   * @param {string} key - имя поля
   * @param {string} value - новое значение
   */
  setState(key, value) {
    this.state[key] = value;

    // Очистить зависимые поля при изменении
    if (key === 'product_type') {
      this.clearDependentFields(['workpiece_type', 'laser_thickness', 'material', 'workpiece_size', 'workpiece_type_enum']);
    } else if (key === 'workpiece_type') {
      this.clearDependentFields(['laser_thickness', 'material', 'workpiece_size', 'workpiece_type_enum']);
    }

    this.updateFieldVisibility();
  }

  /**
   * Очистить значения зависимых полей
   * @param {string[]} fieldNames - массив имен полей
   */
  clearDependentFields(fieldNames) {
    fieldNames.forEach(fieldName => {
      if (this.selectElements[fieldName]) {
        this.selectElements[fieldName].value = '';
        this.state[fieldName] = '';
      }
      if (this.inputElements[fieldName]) {
        this.inputElements[fieldName].value = '';
        this.state[fieldName] = '';
      }
    });
  }

  /**
   * Получить список видимых полей для текущего состояния
   * @returns {string[]} - массив имен видимых полей
   */
  getVisibleFieldsForState() {
    const visible = new Set();
    const { product_type, workpiece_type } = this.state;

    // Всегда видимое поле: Тип изделия
    visible.add('product_type');

    if (product_type === 'made') {
      // Вид заготовки видна для Изделия
      visible.add('workpiece_type');

      if (workpiece_type === 'laser') {
        // Путь: Лазерная резка
        visible.add('laser_thickness');
        visible.add('material');
      } else if (workpiece_type === 'preparatory') {
        // Путь: Ленточная пила
        visible.add('material');
        visible.add('workpiece_size');
        visible.add('workpiece_type_enum');
      } else if (workpiece_type === 'pki') {
        // Путь: ПКИ (в виде заготовки)
        visible.add('material');
        visible.add('workpiece_size');
      }
    } else if (product_type === 'assembly') {
      visible.add('material');
      visible.add('workpiece_size');
    } else if (product_type === 'pki') {
      // Путь: ПКИ (в типе изделия)
      visible.add('material');
      visible.add('workpiece_size');
    }

    return Array.from(visible);
  }

  /**
   * Обновить видимость всех полей на основе текущего состояния
   */
  updateFieldVisibility() {
    const visibleFields = this.getVisibleFieldsForState();

    // Обновить видимость каскадных полей
    Object.entries(this.fieldElements).forEach(([fieldName, fieldElement]) => {
      const isVisible = visibleFields.includes(fieldName);
      const isCascadeField = fieldElement.classList.contains('form-field--cascade');

      if (isCascadeField) {
        if (isVisible) {
          fieldElement.classList.add('is-visible');
        } else {
          fieldElement.classList.remove('is-visible');
        }
      }
    });
  }

  /**
   * Получить payload формы для отправки на сервер
   * @returns {Object} - объект с текущими значениями формы
   */
  getFormPayload() {
    return { ...this.state };
  }

  /**
   * Валидировать форму для текущего состояния
   * @returns {Object} - {valid: boolean, errors: string[]}
   */
  validateForm() {
    this.prepareForSubmit();
    const errors = [];
    const visible = new Set(this.getVisibleFieldsForState());
    const { product_type, workpiece_type, laser_thickness, material, workpiece_size, workpiece_type_enum } =
      this.state;

    if (visible.has('product_type') && !product_type) {
      errors.push('Выберите тип изделия');
      return { valid: false, errors };
    }

    if (visible.has('workpiece_type') && !workpiece_type) {
      errors.push('Выберите вид заготовки');
      return { valid: false, errors };
    }

    if (visible.has('laser_thickness')) {
      const thick = parseFloat(String(laser_thickness || '').replace(',', '.'));
      if (!laser_thickness || Number.isNaN(thick) || thick <= 0 || thick >= 500) {
        errors.push('Укажите толщину листа от 0 до 500 мм');
      }
    }

    if (visible.has('material') && !String(material || '').trim()) {
      errors.push('Укажите материал');
    }

    if (visible.has('workpiece_size') && !String(workpiece_size || '').trim()) {
      errors.push('Укажите размер заготовки');
    }

    if (visible.has('workpiece_type_enum') && !String(workpiece_type_enum || '').trim()) {
      errors.push('Выберите тип заготовки (плита / круг / пруток)');
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  /**
   * Применить данные с сервера к форме
   * @param {Object} data - данные из ответа сервера (plan_inline_state)
   */
  syncFromServer(data) {
    if (!data) return;
    if (!data.product_type && data.plan_product_type) {
      data = Object.assign({}, data, { product_type: data.plan_product_type });
    }

    Object.entries(data).forEach(([key, value]) => {
      if (key in this.state) {
        this.state[key] = value;

        // Обновить DOM элементы
        if (this.selectElements[key]) {
          this.selectElements[key].value = value;
        }
        if (this.inputElements[key]) {
          this.inputElements[key].value = value;
        }
      }
    });

    this.updateFieldVisibility();
  }

  /**
   * Получить объект с информацией о видимых полях
   * (полезно для дебага и логирования)
   * @returns {Object}
   */
  getDebugInfo() {
    return {
      state: this.state,
      visibleFields: this.getVisibleFieldsForState(),
      validation: this.validateForm(),
      fieldElements: Object.keys(this.fieldElements),
      selectElements: Object.keys(this.selectElements),
      inputElements: Object.keys(this.inputElements)
    };
  }
}

// Глобально для product_detail.js (обычный <script defer>, не bundler)
if (typeof window !== 'undefined') {
  window.PlanCascadeFormManager = PlanCascadeFormManager;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PlanCascadeFormManager;
}
