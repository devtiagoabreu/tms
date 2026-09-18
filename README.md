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
| `GET /api/reports/{day\|week\|month}.csv` | idem, exporta CSV (12 categorias + totais) |
| `GET /api/monitor` | `offline_after_s`, `lang`, `live`, `stored`, `timeout` — estado atual por tear |
| `GET /api/live-status` | último status ao vivo persistido por tear |
| `GET /api/settings` | todas as chaves/valores (`settings`) |
| `GET\|PUT /api/settings/ip-ranges` | faixas de IP (`ipaddress.txt`; faz merge das sub-redes) |
| `GET\|PUT /api/settings/styles` | estilos (`style_mst.txt`: nome/densidade/comprimento) |
| `GET\|PUT /api/settings/shift` | escala de turnos (`system_set.txt`) |
| `GET\|PUT /api/settings/report-prefs` | itens de relatório (`selitem.txt`) |
| `GET\|PUT /api/settings/value/{key}` | chave avulsa (`language`, `scanner_ip`, `memcard`…) |
| `GET /api/screens/{efficiency\|production\|stop-analysis}` | `period`, `mode`, `key`, `mac_name`, `day_from`, `day_to`, `week_start`, `min_run_tm`, `min_effic` (+ `unit`/`beam_type`) |
| `GET /api/screens/{efficiency\|production\|stop-analysis}.csv` | idem; stop-analysis usa `value=count\|time` |
| `GET /monitor` | dashboard HTML que consome `/api/monitor` (auto-refresh 30s) |

Datas no formato legado `YYYY.MM.DD` (ex.: `2025.10.01`). OpenAPI em `/docs`.

Relatórios agregam `agg_shift` por `(mac_name, mac_type, style, beam, ubeam)` —
**soma** contadores/tempos e **recomputa** EFFIC/RPM/total (nunca média de
taxas), como `TMSDATAfinal.pm`. A semana usa início configurável
(`week_start`, 0=domingo), não ISO. Período `shift` agrupa por `shift_id`
(`YYYY.MM.DD.n`); modo `operator` (`mode=operator`) agrega `operator_daily`
por nome do operador e não tem granularidade de turno.

## Retenção e reprocessamento (Fase 1)

```bash
# aplicar a política em camadas (1/3/12 meses); sem --reference usa a data mais nova do banco
PYTHONPATH=src python -m tms.maintenance retention --dry-run
PYTHONPATH=src python -m tms.maintenance retention --reference 2026.09.17

# contar (sem apagar) o que sairia da retenção até 2024.12.31
PYTHONPATH=src python -m tms.maintenance purge --to 2024.12.31 --dry-run

# apagar stop_events/daily_raw de um período
PYTHONPATH=src python -m tms.maintenance purge --to 2024.12.31 --sources stop_events,daily_raw

# recalcular agg_shift a partir de daily_raw (após mudar stopcodes/fórmulas)
PYTHONPATH=src python -m tms.maintenance rebuild-agg --from 2025.01.01 --to 2025.12.31
```

`retention` espelha a política do legado (`old_03/06/12_ym`): `machine_snapshots`
1 mês; `daily_raw`/`stop_events` 3 meses; `agg_shift`/`operator_daily` 12 meses.
Os períodos de semana/mês são calculados a partir de `agg_shift`, que sobrevive
ao descarte do bruto — `report(...)` usa `source="agg"` por default
(`source="raw"` usa `daily_raw`).

`purge` exige ao menos `--from` ou `--to` (nunca apaga tudo por acidente).
`rebuild-agg` reaproveita o `raw_line` guardado, então novos mapeamentos de
parada entram em vigor sem reingerir arquivos.

## Monitoramento (Fase 2)

Dashboard em `/monitor` (cards coloridos, refresh 30s) alimentado por
`GET /api/monitor`. O estado de cada tear é inferido de:

- frescura do último snapshot (`get_time`) → `offline` (default 15 min);
- parada em aberto no `stop_history` (última parada sem `run_time`) → `stopped`
  (com código/causa e duração);
- caso contrário → `run`; sem snapshot → `no_data`.

### Coleta ao vivo

`core/live.py` reproduz `loom/apistate.cgi::make_status_data`: parseia as linhas
`Chave=valor` do tear (`ext.cgi?func=get_stat`), valida a completude
(JAT710 `scnt>=14`, LWT710 `scnt>=15`, `dcnt>=13`, `vcnt>=2`) e deriva o status
pelos bits na mesma precedência do legado. Códigos de erro de coleta (`100`
ping, `220`/`300` HTTP, `400` socket, `1000` não suportado, `1001` dados) viram
`offline`/`no_data` em `live_to_monitor_state`.

`tms.collector` busca o payload de cada tear (stdlib `urllib`, sem dependências)
por dois caminhos do legado: JAT710 via `ext.cgi?func=get_stat` no IP do tear e
LWT710 via scanner (`mget.cgi`, corpo `boundary=…&file=..\data\status\NNMMM.txt`).
Pode ser usado como CLI — `--host NOME=IP` (repetível) ou, sem hosts, lê os IPs
de `machines.ip_addr` no banco:

```bash
# uma coleta
PYTHONPATH=src python -m tms.collector --host 00001=10.0.0.11 --timeout 5

# LWT via scanner
PYTHONPATH=src python -m tms.collector --scanner-ip 10.0.0.9 --scan-id S1-00001.1

# grava em live_status e coleta a cada 60s
PYTHONPATH=src python -m tms.collector --persist --loop --interval 60
```

`GET /api/monitor?live=true` faz a coleta (lenta) e usa o estado ao vivo;
`?stored=true` usa o último status gravado em `live_status` (endpoint
`GET /api/live-status`). Em ambos, `source="live"` e os bits/dados vêm em `live`.
Sem nenhum deles, o estado é inferido do banco: frescura do snapshot →
`offline`; parada em aberto no `stop_history` → `stopped`; senão `run`; sem
snapshot → `no_data`.

## Relatórios — exportação CSV (Fase 3)

`GET /api/reports/{period}.csv` gera um layout estável: identidade
(`period,key,mac_name,mac_type,style,beam,ubeam`), métricas (`rpm,effic,
run_tm,stop_ttm`), produção (`seisan_1..3,off_prod_1..3,production,pick`) e as
12 categorias de parada como `ct_<CATEGORIA>`/`tm_<CATEGORIA>` + `total_ct`/
`total2_ct`/`wf1*/wf2*/lh*` (arrays separados por `;`). Os nomes das categorias
seguem `core.stopcodes.CATEGORY_KEYS`. Os endpoints agregam a partir de
`agg_shift` (`report(...)`, fonte retida por 12 meses).

## Configuração e edição (Fase 4)

`tms.config_service` substitui os arquivos de configuração do legado por tabelas,
com parser/serializador do formato original em cada caso:

| Arquivo legado | Tabela / serviço |
|---|---|
| `setting/ipaddress.txt` | `ip_ranges` — `parse/merge/expand/replace_ip_ranges` |
| `set/style_mst.txt` | `styles.density/doff_len` — `parse/replace_styles` |
| `set/system_set.txt` (shift) | `shift_schedules` — `parse/replace/get_shift_schedule` |
| `setting/selitem.txt` | `report_prefs` — `parse/format/get/replace_report_prefs` |
| `setting/{language,scanner_ip,memcard}.txt` | `settings` — `get/set_setting` |

O merge de sub-redes (`ipset2.cgi`) é mantido: faixas da mesma sub-rede que se
tocam são unidas e ordenadas. Os endpoints `GET|PUT /api/settings/*` expõem
leitura/escrita; `GET /api/settings/ip-ranges` devolve também a lista de IPs
expandida. Exemplo: as 3 faixas reais de `ipaddress.txt` expandem para 26 IPs.

## Telas de relatório (Fase 3)

`tms.reporting.screens` reproduz os layouts do legado em modo tear/estilo —
`mode=shift` (default) — e modo operador — `mode=operator`, que agrega
`operator_daily` por operador e troca LOOM/STYLE por OPERATOR —, nos períodos
`shift`/`day`/`week`/`month`, expostos em `/api/screens/*` (JSON e `.csv`):

| Tela | Origem | Colunas |
|---|---|---|
| `efficiency` | `shift/efficiency.pm` | LOOM, STYLE, EFFIC%, RUN, STOP, WARP count + rate cph/cpday, WEFT count + rate cph/cpday |
| `production` | `shift/production.pm` | LOOM, STYLE, PRODUCT (`seisan[unit]+off_prod[unit]`) |
| `stop-analysis` | `shift/stopanalysis.cgi` | colunas escolhidas pelo `report_prefs` (selitem) + `UNSELECT` |

No `stop-analysis`, `count_rows`/`time_rows` (JSON) e `value=count|time` (CSV)
dão, respectivamente, contagem e minutos. O `UNSELECT` soma tudo o que não foi
selecionado, e `WARP_TOP` só aparece quando configurado no selitem. As taxas de
parada são recalculadas por hora de operação (`cph`) e por dia (`cph × 24`).
`mode=operator` + `period=shift` é rejeitado (`operator_daily` não tem turno).
