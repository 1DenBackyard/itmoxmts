# МТС · Прототип анализа ТЗ (Streamlit)

Прототип UI + контрактов для мультиагентного ревью документации объектов данных.

## Что внутри

1. **Работа с документом** — загрузка PDF/TXT, mock multi-agent анализ, карточки правок с прожаркой (Well done / Medium / Medium rare / Rare), статусы.
2. **Дашборд самообучения** — статистика только по статусу «Исправлено».

Приоритет замечания: `score = P(проблема) × Impact`.

## Быстрый старт

Рекомендуется Python из Anaconda (уже содержит streamlit/pandas/plotly/pypdfium2):

```bash
cd prototype
cp .env.example .env
/Applications/anaconda3/bin/streamlit run app.py
```

Или в любом venv:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Откройте http://localhost:8501

## Демо на датасете

В сайдбаре страницы документа выберите, например:

- `Тестовые данные для Хакатона-7-9.pdf` (витрина-агрегат)
- тип документа: «Описание витрины-агрегата»
- роль: Разработчик / Тестировщик / Аналитик

Нажмите **Запустить анализ** → пройдитесь по карточкам → **Исправлено** → смотрите дашборд.

## LLM

По умолчанию `LLM_MODE=mock` (детерминированный чеклист + ролевые агенты).

Чтобы подключить лёгкую модель:

```env
LLM_MODE=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

или OpenAI-compatible endpoint (`LLM_MODE=openai_compatible`).

Если модель недоступна, UI не падает и остаётся в demo mode.

## Контракты для бэкенда

- Findings: `data/findings_store.json`
- Learning events: `data/learning_events.json`
- Логи LLM: `data/llm_logs/`

Схема полей — в корневом `ТЗ_прототип_Streamlit.md`.

## Структура

```
prototype/
  app.py
  pages/
    1_Работа_с_документом.py
    2_Дашборд_самообучения.py
  src/
    analyzer/     # checklist + orchestrator
    llm/          # LLMClient abstraction
    models.py
    storage.py
    pdf_extract.py
    scoring.py
    ui_components.py
  data/
```
