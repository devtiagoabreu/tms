# Plano de Migração para Python + PostgreSQL

## 1. Princípios

- Backend **100% Python** (FastAPI recomendado) + **PostgreSQL** como única fonte de verdade.
- Coletor Python mantém o protocolo da máquina (JAT710/LW700 via HTTP, scanner, memcard) mas grava direto no banco.
- Relatórios nativos em web (tabelas/gráficos) **substituem** o fluxo TmsHelper→Excel; exportação para CSV/XLSX nativa via bibliotecas Python.
- Multilíngue mantido (pt, en, ja, zh-cn, zh-tw, ko) — strings vindas dos `str_*.pm` migradas para o banco/arquivos de tradução.
- Normalizar codificação **Shift-JIS → UTF-8** em todos os arquivos/código.
- Legado permanece intacto em `docs/legado/` como referência; o novo sistema nasce em `src/`.

## 2. Mapeamento de conceitos

| Legado | Alvo |
|---|---|
| `tmsdata/` (arquivos planos) | Schema PostgreSQL |
| `loom/<mac>.txt`, `current/current.txt` | tabela `machines`, `machine_snapshots` |
| `stop_history/<date>/<mac>.txt` | tabela `stop_events` |
| `shift/<data>.<n>.txt` (bruto por dia) | tabela `daily_raw` |
| agregados `shift-*`, `operator-*` | visões/tabelas agregadas (views materializadas por shift/date/week/month) |
| `index/` | consultas SQL dinâmicas |
| `setting/*.txt`, `selitem.txt` | tabela `settings`, `report_prefs` |
| CGI Perl | Endpoints FastAPI (`/api/...`) |
| `opestate/dashboard` (HTML+meta refresh) | Dashboard SPA/páginas com polling/WebSocket |
| TmsHelper.exe + `.xls` | Export CSV/XLSX nativo + grids web |
| `httpc.exe` | `httpx`/`aiohttp` |
| cron do Windows / CGI de agendamento | Scheduler (APScheduler) + coleta paralela |

## 3. Schema PostgreSQL proposto (rascunho)

```sql
-- Mestres
machines      (id, mac_name, mac_type, ip_addr, active, created_at, updated_at)
styles        (id, name, beam_type, unit)
operators     (id, code, name)
shifts        (id, code, name, day_start_time, schedule_json)
settings      (key, value, updated_at)                 -- language, expire, service, security_dir...
report_prefs  (id, key, value)                          -- selitem.txt

-- Runtime no tear
machine_snapshots (machine_id, shift_id, get_time, sys_time, rtc_time,
                   style_id, beam, ubeam, cloth_len, cut_len,
                   doff_fcst, wout_fcst, uwout_fcst, payload_json)

-- Eventos
stop_events   (machine_id, shift_id, day, stop_time, run_time, raw_code,
               stop_start, stop_end, fixed bool, duration_min)

-- Diários / agregação
daily_raw    (machine_id, day, raw_line_json, collected_at)
agg_shift    (machine_id, operator_id, shift_id, style_id, beam, ubeam,
              seisan_1, seisan_2, seisan_3, off_prod_1..3,
              run_tm, stop_ttm, effic,
              stop_ct int[12], stop_tm numeric[12],
              wf1_ct, wf1_tm, wf2_ct, wf2_tm, lh_ct, lh_tm)
```

> Visões agregadas (week/month) como `CREATE VIEW` ou tabelas materializadas recalculadas pelo mesmo pipeline do `TMSDATAfinal.pm`, mas em SQL/Python.

## 4. Fórmulas a portar (canônicas)

```
RPM          = seisan[0]*100 / (run_tm/60)
EFFIC %      = run_tm*100 / (run_tm + stop_ttm)
Production   = seisan[unit] + off_prod[unit]        -- unit 0=PICK 1=METER 2=YARD
warp_ct      = sum(stop_ct[0..4]) + stop_ct[11]      -- efficiency report
weft_ct      = stop_ct[5]
svs pick     = 1000 * seisan[0]
WARP_BOTTOM  = stop_ct[1]
False/CC     = stop_ct[2] + stop_ct[11]
Leno Total   = stop_ct[3] + stop_ct[4]
TOTAL        = soma das 12 categorias (com colapsos false/leno; exclui [0] se beam_type!=2)
TOTAL2       = somente fiação (warp+weft+false+leno)
```

Mapeamento de códigos brutos → 12 categorias JAT/LWT em `02-modelo-de-dados.md` §"Mapeamento dos códigos de parada".

## 5. Módulos do projeto proposto

```
src/tms/
  app/                # FastAPI app, rotas, templates
    api/              # endpoints (coleta, status, relatórios, config, admin)
    reports/          # shift, efficiency, production, style, stopanalysis,
                      # stophistory, statushistory, forecast, svs, operator, showstyle
  collector/          # coleta JAT710/LW700 (httpx), scanner, memcard
  ingest/             # parser dos arquivos de máquina (secções current/monitor/shift/history)
  models/             # ORM (SQLAlchemy) + migrações (Alembic)
  aggregate/          # pipeline 40→12, turno/data/semana/mês, retenção
  i18n/               # tabelas de strings p/ pt, en, ja, zh-cn, zh-tw, ko
  services/           # setclock, scanloom, ipset, passwd, switchdata, restruct, lock
tests/                # testes unitários (fórmulas, mapeamentos) + integração
```

## 6. Cronograma sugerido (fases)

1. **Fase 0 — Fundação**: repo `src/`, FastAPI + SQLAlchemy + Alembic, schema inicial, migração das strings i18n, testes das fórmulas.
2. **Fase 1 — Ingestão e coleta**: parser de `loom/*.txt`/memcard/scanner, escrita em PostgreSQL, snapshot `machine_snapshots`, pipeline de agregação (shift/date/week/month) com as mesmas regras de retenção (2/5/11 meses).
3. **Fase 2 — Monitoramento**: dashboard de teares com cálculo de estado (precedência Run→Manual→…→Out_of_product), OEE, eficiência shift/24h/custom, polling.
4. **Fase 3 — Relatórios**: todas as telas com as fórmulas do §4; exportação CSV/XLSX.
5. **Fase 4 — Configuração e edição**: selitem, shiftset, styleset, loomspec, clothbeam, ipset, passwd, switchdata, edição de dados com histórico (fix/unfix e cancelamento).
6. **Fase 5 — Extras**: setclock (ajuste de relógio por rede), backup/restauração, TDM/wnet (formatos MCARD, tabela de IP) — conforme necessidade.
7. **Fase 6 — Migração de dados**: importador dos arquivos legados `tmsdata` existentes para PostgreSQL.

## 7. Decisões pendentes (a validar com o cliente/usuário)

- **Framework web**: FastAPI + server-side templates (Jinja) vs SPA (React/Vue). Recomendação: FastAPI + Jinja para começar (simples, acompanha o legado), SPA numa fase posterior se necessário.
- **Correção de bugs legados** em `03-camada-relatorios.md` §6: reproduzir fielmente (para comparação visual) ou corrigir deliberadamente (recomendado: corrigir, com flag de compatibilidade nos testes).
- **Autenticação**: manter modelo do legado (senha opcional, localhost-trust) ou introduzir login robusto?
- **Deployment**: local na fábrica (Windows prefixado) ou Linux/container? Isso afeta a operação do coletor e horários.

## 8. Riscos

| Risco | Mitigação |
|---|---|
| Protocolo JAT710/LW700 proprietário | Reaproveitar strings/contratos documentados; validar em laboratório com máquina real |
| Formatos binários MCARD (TDM) | Documentar layout; manter ferramenta de conversão isolada |
| Relógios das máquinas errados | Portar setclock; logs de diff sys/rtc |
| Volumetria de histórico longo | Particionar por período; views materializadas com refresher agendado |
| Perda de fideliidade dos relatórios | Suite de testes comparando saídas legadas (fixtures) × novas saídas