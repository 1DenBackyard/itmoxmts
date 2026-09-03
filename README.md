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
- хранение оригиналов в локальном storage для разработки или в приватном Cloud.ru Object Storage;
- хранение в БД только ссылки на объект, hash, метаданных проверки и замечаний.

## Логическая архитектура

```mermaid
flowchart LR
    USER["Сотрудник"] --> LK["Личный кабинет<br/>Streamlit"]
    LK --> INPUT["Загрузка ТЗ"]
    INPUT --> PREP["Разбор документа<br/>и карта фактов"]
    INPUT --> OBJECTS[("Хранилище оригиналов<br/>local / Cloud.ru S3")]
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

## HLD для первого деплоя в Cloud.ru

```mermaid
flowchart LR
    DEV["Команда"] --> GH["GitHub<br/>исходный код и версии"]
    GH --> DEPLOY["git pull +<br/>docker compose up"]

    USER["Сотрудник"] -->|HTTPS| PROXY

    subgraph VM["Cloud.ru VM · Ubuntu"]
        PROXY["Caddy / Nginx<br/>TLS и reverse proxy"] --> APP["Streamlit<br/>ЛК + review engine"]
        APP --> PG[("PostgreSQL<br/>пользователи · проверки · ошибки")]
    end

    APP --> S3[("Cloud.ru Object Storage<br/>приватный бакет · оригиналы ТЗ")]
    APP --> FM["Cloud.ru Foundation Models<br/>OpenAI-compatible API"]
```

Для хакатонного MVP используем одну **Cloud.ru VM** и Docker Compose: так проще развернуть и диагностировать прототип. Streamlit и PostgreSQL работают в отдельных контейнерах на VM. Исходные документы сохраняются в приватном бакете **Cloud.ru Object Storage**, а в PostgreSQL находятся только ключ объекта, hash, размер, MIME-тип, результаты проверок и персональная статистика. Публичный доступ к бакету не требуется.

Когда появится нагрузка, без изменения прикладной логики можно вынести PostgreSQL в Managed PostgreSQL, образ — в Artifact Registry, а приложение — в Container Apps.

Официальная документация Cloud.ru:

- [Container Apps](https://cloud.ru/docs/container-apps-evolution/ug/index)
- [Artifact Registry: загрузка Docker-образа](https://cloud.ru/docs/artifact-registry-evolution/ug/topics/guides__artifact-push)
- [Managed PostgreSQL](https://cloud.ru/docs/paas-postgresql/ug/doc-contents)
- [Foundation Models API](https://cloud.ru/docs/foundation-models/ug/topics/api-ref)
- [Object Storage](https://cloud.ru/docs/s3e/ug/doc-contents)
- [Object Storage через Python SDK boto3](https://cloud.ru/docs/s3e/ug/topics/tools__sdk-python)

## Структура проекта

```text
.
├── app.py                         # Streamlit UI
├── src/specguard/
│   ├── auth.py                    # Демо-аутентификация
│   ├── config.py                  # Конфигурация окружения
│   ├── database.py                # SQLAlchemy и репозиторий
│   ├── documents.py               # PDF/DOCX/TXT extraction
│   ├── storage.py                 # Local/S3 adapter исходных документов
│   └── review/
│       ├── agents.py              # Специализированные агенты
│       ├── llm.py                 # Cloud.ru Foundation Models
│       ├── pipeline.py            # Оркестратор, критик, судья
│       └── schemas.py             # Контракты результатов
├── tests/                         # Автоматические проверки
├── Dockerfile
├── Caddyfile                      # HTTPS и reverse proxy
├── docker-compose.yml
├── Makefile                       # Команды локальной разработки
└── .github/workflows/ci.yml
```

## Быстрый запуск

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
make run
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

## Подключение Cloud.ru Object Storage

Cloud.ru предоставляет S3-совместимый API и официально поддерживает Python SDK `boto3`. Создайте приватный бакет и ключ доступа к Object Storage, затем задайте:

```dotenv
DOCUMENT_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://s3.cloud.ru
S3_REGION=ru-central-1
S3_BUCKET=net-specguard-documents
S3_ACCESS_KEY_ID=<tenant_id>:<key_id>
S3_SECRET_ACCESS_KEY=<key_secret>
S3_PREFIX=documents
```

Секреты не коммитятся и на VM находятся только в `.env`. Бакет приложение автоматически не создаёт. Объекты размещаются по ключу `documents/<user_id>/<YYYY>/<MM>/<DD>/<uuid>-<filename>`. Для удаления старых тестовых документов настройте Lifecycle rule в бакете; рекомендуемый срок для демо — 30 дней.

По умолчанию используется `DOCUMENT_STORAGE_BACKEND=local`, поэтому localhost работает без облачных ключей и сохраняет файлы в `data/documents`.

## Подключение Foundation Models

В Cloud.ru создайте API-ключ Foundation Models и задайте:

```dotenv
LLM_ENABLED=true
LLM_BASE_URL=https://foundation-models.api.cloud.ru/v1
LLM_API_KEY=replace-me
LLM_MODEL=ai-sage/GigaChat3-10B-A1.8B
LLM_TIMEOUT_SECONDS=45
LLM_MAX_RETRIES=0
```

Модель является конфигурацией: перед деплоем выберите актуальную модель с поддержкой Structured Output в каталоге Cloud.ru. Без ключа приложение остаётся работоспособным и запускает встроенные детерминированные проверки.

## Переменные окружения

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///data/specguard.db` |
| `APP_BIND_ADDRESS` | Адрес публикации Docker-порта | `127.0.0.1` |
| `APP_PORT` | Порт приложения на хосте | `8501` |
| `APP_DOMAIN` | Публичный домен для автоматического HTTPS | `aitalenthack.cloudru-edu.ru` |
| `DEMO_PASSWORD` | Пароль демо-аккаунтов | `demo1234` |
| `LLM_ENABLED` | Включить LLM-агентов | `false` |
| `LLM_BASE_URL` | Endpoint модели | Cloud.ru Foundation Models |
| `LLM_API_KEY` | API-ключ | пусто |
| `LLM_MODEL` | ID модели | `ai-sage/GigaChat3-10B-A1.8B` |
| `LLM_TIMEOUT_SECONDS` | Максимальное ожидание одного LLM-агента | `45` |
| `LLM_MAX_RETRIES` | Число повторов зависшего LLM-запроса | `0` |
| `MAX_DOCUMENT_CHARS` | Лимит текста для MVP | `120000` |
| `DOCUMENT_STORAGE_BACKEND` | `local` или `s3` | `local` |
| `DOCUMENT_STORAGE_PATH` | Каталог локальных оригиналов | `data/documents` |
| `S3_ENDPOINT_URL` | Endpoint Object Storage | `https://s3.cloud.ru` |
| `S3_REGION` | Регион подписи AWS SigV4 | `ru-central-1` |
| `S3_BUCKET` | Приватный бакет документов | пусто |
| `S3_ACCESS_KEY_ID` | `<tenant_id>:<key_id>` | пусто |
| `S3_SECRET_ACCESS_KEY` | Секрет ключа Object Storage | пусто |
| `S3_PREFIX` | Префикс ключей документов | `documents` |
| `S3_SERVER_SIDE_ENCRYPTION` | Опциональный режим SSE бакета | пусто |

Для Cloud.ru Managed PostgreSQL используйте URL вида:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

## Деплой MVP на Cloud.ru VM

1. Создать Ubuntu VM, назначить публичный IP и разрешить входящие `22`, `80`, `443`.
2. Установить Docker Engine и Docker Compose plugin.
3. Клонировать GitHub-репозиторий на VM.
4. Создать приватный бакет Object Storage и API-ключ с доступом только к этому бакету.
5. Создать `.env` из `.env.example` и задать как минимум:

   ```dotenv
   DEMO_PASSWORD=<strong-password>
   DOCUMENT_STORAGE_BACKEND=s3
   S3_BUCKET=<bucket>
   S3_ACCESS_KEY_ID=<tenant_id>:<key_id>
   S3_SECRET_ACCESS_KEY=<key_secret>
   ```

6. Запустить приложение:

   ```bash
   docker compose up -d --build
   ```

7. Добавить Caddy или Nginx перед Streamlit, выпустить TLS-сертификат и не публиковать порт PostgreSQL.
8. Проверить `/_stcore/health`, вход, загрузку ТЗ и появление объекта в бакете.

В текущем Compose Caddy уже настроен: он слушает `80/443`, автоматически получает TLS-сертификат для `APP_DOMAIN` и проксирует запросы в Streamlit. Для домена должна существовать DNS `A`-запись на публичный IP VM, а группа безопасности Cloud.ru должна разрешать входящий TCP-трафик на `80` и `443`.

## CI/CD из GitHub в production

Workflow `.github/workflows/ci.yml` работает так:

- Pull Request: установка зависимостей, Ruff, Pytest, compileall и сборка Docker-образа;
- push/merge в `main`: те же проверки, затем синхронизация точного commit на VM, установка production `.env`, `docker compose up -d --build` и health check;
- ручной повтор: **GitHub → Actions → CI/CD → Run workflow** на ветке `main`.

Деплой использует GitHub Environment `production` и два Actions Secret:

| Secret | Содержимое |
|---|---|
| `VM_SSH_PRIVATE_KEY_B64` | Отдельный приватный ключ GitHub Actions в однострочном Base64 |
| `PROD_ENV_FILE` | Полное содержимое production `.env`, включая FM/S3 credentials |

Первичная настройка в GitHub:

1. Открыть **Settings → Secrets and variables → Actions → New repository secret**.
2. Добавить secrets `VM_SSH_PRIVATE_KEY_B64` и `PROD_ENV_FILE`.
3. Опционально открыть **Settings → Environments**, создать `production` и включить доступные для тарифа protection rules. Для приватного репозитория на GitHub Free environment secrets и required reviewers могут быть недоступны, поэтому базовая схема использует repository secrets.
4. Создать Pull Request из рабочей ветки в `main` и дождаться зелёного CI.
5. Merge Pull Request автоматически запустит production deploy.

IP, пользователь и каталог VM сейчас зафиксированы в workflow: `176.123.165.124`, `denbackyard`, `/home/denbackyard/net-specguard`. Приложение остаётся привязано к `127.0.0.1:8501`; внешний доступ должен идти через reverse proxy с HTTPS.

Секреты нельзя добавлять в Git, workflow-файлы или логи. Чтобы изменить FM-токен, пароль или S3-ключи, обновите только `PROD_ENV_FILE` в GitHub Environment и повторно запустите workflow.

На macOS значение для `VM_SSH_PRIVATE_KEY_B64` можно скопировать без вывода ключа в терминал:

```bash
openssl base64 -A -in ~/.ssh/itmoxmts_github_actions | pbcopy
```

Base64 используется только как безопасный для многострочной вставки формат, а не как шифрование. GitHub Actions декодирует ключ во временный файл runner и проверяет его через `ssh-keygen` перед подключением.

## Проверки

```bash
make test
make lint
python -m compileall app.py src
docker build -t net-specguard:local .
```

## Ближайшие этапы

1. Заменить демо-аутентификацию на OIDC/SSO.
2. Добавить версионируемый registry шаблонов и правил.
3. Настроить Lifecycle/TTL и политику шифрования бакета исходных документов.
4. Добавить исторические пары «ТЗ → комментарий разработчика» в RAG.
5. Создать закрытый eval-набор и измерять precision, weighted recall и accepted issue rate.
6. Разделить синхронное UI-приложение и фоновые review jobs при росте нагрузки.
