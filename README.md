# NET SpecGuard

NET SpecGuard — прототип мультиагентной системы предварительного ревью технических заданий на потоки и витрины данных. Система проверяет документ глазами аналитика, data engineer, архитектора и тестировщика, перепроверяет найденные замечания и формирует персональные рекомендации сотруднику.

## Зачем нужен продукт

Большая часть возвратов ТЗ в разработке связана не с отсутствием документа, а с разрывом контекста: неоднозначными формулировками, противоречиями между разделами, пропущенными правилами расчёта и неописанными edge cases. NET SpecGuard помогает найти такие места до передачи документа разработчику.

Система не заменяет ручное ревью. LLM-замечание становится ошибкой сотрудника только после подтверждения или фактического исправления. Отклонённые замечания учитываются как обратная связь для качества агента, но не ухудшают профиль сотрудника.

## Возможности MVP

- личный кабинет сотрудника;
- загрузка PDF, DOCX, TXT и Markdown или вставка текста;
- параллельное ревью несколькими специализированными агентами;
- rule-based проверки, работающие без подключения LLM;
- подключение Cloud.ru Foundation Models через OpenAI-совместимый API;
- критик и судья для фильтрации и дедупликации замечаний;
- доказательное замечание: цитата, влияние, вопрос и рекомендация;
- подтверждение, отклонение и закрытие найденной проблемы;
- персональная статистика по подтверждённым категориям ошибок;
- хранение метаданных проверки без сохранения полного текста ТЗ.

## Логическая архитектура

```mermaid
flowchart LR
    USER["Сотрудник"] --> LK["Личный кабинет<br/>Streamlit"]
    LK --> INPUT["Загрузка ТЗ"]
    INPUT --> PREP["Разбор документа<br/>и карта фактов"]
    PREP --> ORCH["Оркестратор"]

    ORCH --> A1["Аналитик"]
    ORCH --> A2["Data Engineer"]
    ORCH --> A3["Архитектор"]
    ORCH --> A4["QA"]

    A1 --> CONTROL["Критик и судья"]
    A2 --> CONTROL
    A3 --> CONTROL
    A4 --> CONTROL

    KB[("Шаблоны · Правила<br/>Примеры правок")] -. контекст .-> ORCH
    CONTROL --> REPORT["Единый отчёт"]
    REPORT --> LK

    LK --> DECISION["Принять · Отклонить<br/>Исправить"]
    DECISION --> HISTORY[("История ошибок")]
    HISTORY --> PROFILE["Персональные<br/>рекомендации"]
    PROFILE --> LK
```

## HLD для Cloud.ru

```mermaid
flowchart LR
    GH["GitHub<br/>исходный код"] --> CI["GitHub Actions<br/>tests · build"]
    CI --> AR["Cloud.ru<br/>Artifact Registry"]
    AR --> APP["Cloud.ru Container Apps<br/>Streamlit + review engine"]

    USER["Пользователь"] --> APP
    APP --> PG[("Managed PostgreSQL<br/>пользователи · проверки · ошибки")]
    APP --> FM["Foundation Models<br/>OpenAI-compatible API"]
    APP -. следующий этап .-> S3[("Object Storage<br/>документы с TTL")]

    ADMIN["Администратор"] --> APP
```

Для MVP приложение разворачивается одним контейнером в **Container Apps**. Docker-образ хранится в **Artifact Registry**, структурированные данные — в **Managed PostgreSQL**, а вызовы агентов выполняются через **Foundation Models**. Endpoint Foundation Models совместим с OpenAI API и задаётся конфигурацией. Полные тексты документов в текущем MVP не сохраняются: в БД попадают hash документа, метаданные и найденные замечания.

Официальная документация Cloud.ru:

- [Container Apps](https://cloud.ru/docs/container-apps-evolution/ug/index)
- [Artifact Registry: загрузка Docker-образа](https://cloud.ru/docs/artifact-registry-evolution/ug/topics/guides__artifact-push)
- [Managed PostgreSQL](https://cloud.ru/docs/paas-postgresql/ug/doc-contents)
- [Foundation Models API](https://cloud.ru/docs/foundation-models/ug/topics/api-ref)

## Структура проекта

```text
.
├── app.py                         # Streamlit UI
├── src/specguard/
│   ├── auth.py                    # Демо-аутентификация
│   ├── config.py                  # Конфигурация окружения
│   ├── database.py                # SQLAlchemy и репозиторий
│   ├── documents.py               # PDF/DOCX/TXT extraction
│   └── review/
│       ├── agents.py              # Специализированные агенты
│       ├── llm.py                 # Cloud.ru Foundation Models
│       ├── pipeline.py            # Оркестратор, критик, судья
│       └── schemas.py             # Контракты результатов
├── tests/                         # Автоматические проверки
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Быстрый запуск

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
streamlit run app.py
```

Откройте `http://localhost:8501`.

Демо-пользователь:

```text
email: analyst@example.com
password: demo1234
```

Пароль можно изменить через `DEMO_PASSWORD`. Демо-аутентификация предназначена только для прототипа; перед промышленным использованием её нужно заменить на корпоративный OIDC/SSO.

## Запуск через Docker Compose

```bash
docker compose up --build
```

Приложение будет доступно на `http://localhost:8501`, PostgreSQL — только внутри compose-сети.

## Подключение Foundation Models

В Cloud.ru создайте API-ключ Foundation Models и задайте:

```dotenv
LLM_ENABLED=true
LLM_BASE_URL=https://foundation-models.api.cloud.ru/v1
LLM_API_KEY=replace-me
LLM_MODEL=ai-sage/GigaChat3-10B-A1.8B
```

Модель является конфигурацией: перед деплоем выберите актуальную модель с поддержкой Structured Output в каталоге Cloud.ru. Без ключа приложение остаётся работоспособным и запускает встроенные детерминированные проверки.

## Переменные окружения

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///data/specguard.db` |
| `DEMO_PASSWORD` | Пароль демо-аккаунтов | `demo1234` |
| `LLM_ENABLED` | Включить LLM-агентов | `false` |
| `LLM_BASE_URL` | Endpoint модели | Cloud.ru Foundation Models |
| `LLM_API_KEY` | API-ключ | пусто |
| `LLM_MODEL` | ID модели | `ai-sage/GigaChat3-10B-A1.8B` |
| `MAX_DOCUMENT_CHARS` | Лимит текста для MVP | `120000` |

Для Cloud.ru Managed PostgreSQL используйте URL вида:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

## Деплой в Cloud.ru

1. Создать Managed PostgreSQL и пользователя приложения.
2. Создать реестр в Artifact Registry.
3. Собрать Linux-образ:

   ```bash
   docker build --platform linux/amd64 -t <registry>.cr.cloud.ru/net-specguard:<tag> .
   ```

4. Авторизоваться и отправить образ:

   ```bash
   docker login <registry>.cr.cloud.ru
   docker push <registry>.cr.cloud.ru/net-specguard:<tag>
   ```

5. Создать Container Service из образа, открыть порт `8080` и добавить health check `/_stcore/health`.
6. Передать секретами `DATABASE_URL`, `LLM_API_KEY` и `DEMO_PASSWORD`.
7. Передать обычными переменными `LLM_ENABLED`, `LLM_BASE_URL` и `LLM_MODEL`.

## Проверки

```bash
pytest
python -m compileall app.py src
docker build -t net-specguard:local .
```

## Ближайшие этапы

1. Заменить демо-аутентификацию на OIDC/SSO.
2. Добавить версионируемый registry шаблонов и правил.
3. Подключить Object Storage с TTL и шифрованием для исходных документов.
4. Добавить исторические пары «ТЗ → комментарий разработчика» в RAG.
5. Создать закрытый eval-набор и измерять precision, weighted recall и accepted issue rate.
6. Разделить синхронное UI-приложение и фоновые review jobs при росте нагрузки.
