# tms

Toyota loom monitoring system (TMS). This repository holds the legacy system (for reference) and the Python rewrite (in progress).

## Documentação

- [docs/migracao/00-visao-geral.md](docs/migracao/00-visao-geral.md) — visão geral da migração
- [docs/migracao/01-arquitetura-legada.md](docs/migracao/01-arquitetura-legada.md)
- [docs/migracao/02-modelo-de-dados.md](docs/migracao/02-modelo-de-dados.md)
- [docs/migracao/03-camada-relatorios.md](docs/migracao/03-camada-relatorios.md)
- [docs/migracao/04-coleta-dados-looms.md](docs/migracao/04-coleta-dados-looms.md)
- [docs/migracao/05-configuracoes-edicao.md](docs/migracao/05-configuracoes-edicao.md)
- [docs/migracao/06-subsistemas.md](docs/migracao/06-subsistemas.md)
- [docs/migracao/07-plano-migracao-python.md](docs/migracao/07-plano-migracao-python.md)

## Conteúdo

- `src/tms/` — reescrita em Python (FastAPI + SQLAlchemy + Alembic, PostgreSQL)
- `alembic/` — migrações do banco
- `tests/` — testes (fórmulas e mapeamentos de parada)
- `docs/legado/` — código legado (não versionado; só referência local)

## Como rodar (Fase 0)

```bash
# 1. criar banco (uma vez)
psql -U postgres -c "CREATE ROLE tms LOGIN PASSWORD 'tms';"
psql -U postgres -c "CREATE DATABASE tms OWNER tms;"

export TMS_DATABASE_URL=postgresql+psycopg://tms:tms@localhost:5432/tms

# 2. migrar e rodar
pip install -e ".[dev]"
alembic upgrade head
PYTHONPATH=src uvicorn tms.app.main:app --reload

# 3. testar
pytest
```

API: `GET /api/health` · OpenAPI: `/docs`

## Ingestão dos dados legados (Fase 1)

Lê um diretório `tmsdata/` (com `current/`, `shift/`, `stop_history/`) e faz
upsert idempotente no PostgreSQL. A URL do banco vem de `TMS_DATABASE_URL`.

```bash
# contar o que seria ingerido, sem escrever no banco
PYTHONPATH=src python -m tms.ingest docs/legado/htdocs/tmsdata --dry-run

# ingerir tudo (ou restringir com --sources current,setting,shift,operator,stophistory,loom)
PYTHONPATH=src python -m tms.ingest docs/legado/htdocs/tmsdata
```

## API de leitura (Fase 1)

Somente leitura, paginada (`limit` ≤ 1000, `offset`) e filtrável por tear/dia/turno.

| Endpoint | Filtros principais |
| --- | --- |
| `GET /api/machines` | — |
| `GET /api/machines/{mac_name}` | — |
| `GET /api/machines/{mac_name}/snapshot` | último snapshot do tear |
| `GET /api/snapshots` | `mac_name`, `shift_id`, `day_from`, `day_to` |
| `GET /api/daily-raw` | `mac_name`, `day`, `shift_id`, `day_from`, `day_to` |
| `GET /api/agg-shift` | `mac_name`, `shift_id`, `day_from`, `day_to` |
| `GET /api/stop-events` | `mac_name`, `day`, `shift_id`, `raw_code`, `day_from`, `day_to` |
| `GET /api/operator-daily` | `mac_name`, `operator_code`, `day`, `day_from`, `day_to` |
| `GET /api/reports/{day\|week\|month}` | `key`, `mac_name`, `day_from`, `day_to`, `week_start`, `min_run_tm`, `min_effic`, `unit`, `beam_type` |

Datas no formato legado `YYYY.MM.DD` (ex.: `2025.10.01`). OpenAPI em `/docs`.

Relatórios agregam `daily_raw` por `(mac_name, mac_type, style, beam, ubeam)` —
**soma** contadores/tempos e **recomputa** EFFIC/RPM/total (nunca média de
taxas), como `TMSDATAfinal.pm`. A semana usa início configurável
(`week_start`, 0=domingo), não ISO.
