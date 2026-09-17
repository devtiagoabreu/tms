# Migração do TMS Legado — Visão Geral

## Propósito

Este documento é a base de referência para a reescrita do **TMS (Toyota Loom Monitoring System)** legado — hoje um sistema de **CGI em Perl** com dados em **arquivos texto planos** — em uma solução moderna **100% Python (backend + frontend)** com **PostgreSQL**.

O código legado está em `docs/legado/htdocs/tms` (código) e `docs/legado/htdocs/tmsdata` (dados de exemplo). O sistema também conta com subsistemas auxiliares em `docs/legado/htdocs/{wnet,jat,lwt,tdm,tdmdata,quiz,Catalogs,TStyleSheets}`.

## Objetivos da migração

| Critério | Legado | Alvo |
|---|---|---|
| Backend | CGI Perl (`#! C:\Perl\bin\perl.exe`) | Python (FastAPI/Flask/Django — a definir) |
| Frontend | HTML gerado por CGI + popup **TmsHelper.exe** que abre `.xls` | Frontend web nativo (a definir: templates/server-side ou SPA) |
| Persistência | Arquivos texto planos em `tmsdata/` | PostgreSQL |
| Idioma | 6 idiomas (`en, ja, zh-cn, zh-tw, ko, pt`) | Manter multilíngue |
| Exibição de relatórios | Excel `.xls` via helper local | Tabelas/gráficos web + export |
| Coleta de dados | HTTP para as máquinas (`httpc.exe`) + leitura de memcards | Coletor Python (a manter protocolo JAT710/LW700) |

## Escopo

- **Pleno**: subsistema `tms` (coleta, monitoramento de teares, relatórios, configurações, edição de dados).
- **Documentar, portar somente formatos**: `tdm`, `tdmdata`, `jat`, `lwt` (binários/compilados — documentar formatos MCARD, `.set`, `exchange.dat/.inf`).
- **Portar lógica real**: `wnet` (menus, i18n, geração de tabela de IPs).
- **Descartar**: `quiz` (app de terceiros, não relacionado) e `Catalogs` (apenas placeholder).

## Sumário do documento

| Doc | Conteúdo |
|---|---|
| [01-arquitetura-legada](01-arquitetura-legada.md) | Arquitetura, fluxo, TmsHelper/Excel, locks/gates, idiomas, períodos, unidades |
| [02-modelo-de-dados](02-modelo-de-dados.md) | Formato dos arquivos de dados, agregação, código de paradas 40→12, fórmulas |
| [03-camada-relatorios](03-camada-relatorios.md) | Cada tela de relatório e suas fórmulas exatas |
| [04-coleta-dados-looms](04-coleta-dados-looms.md) | Coleta de dados das máquinas, protocolo, telas de status |
| [05-configuracoes-edicao](05-configuracoes-edicao.md) | Camadas de configuração e edição de dados |
| [06-subsistemas](06-subsistemas.md) | wnet, jat, lwt, tdm, tdmdata, quiz, Catalogs, CSS |
| [07-plano-migracao-python](07-plano-migracao-python.md) | Proposta de arquitetura Python + PostgreSQL e cronograma |

## Notas críticas para a reescrita

1. **Sem runtime real no repositório** — `tmsdata/` nesta cópia contém apenas amostras (`shift-shift`, `loom`, `stop_history`, `operator`, `current`). Os contratos de formato foram extraídos do código.
2. **Bug legados devem ser decididos caso a caso** (ver `03-camada-relatorios.md` §6) — reescrever exatamente ou corrigir deliberadamente.
3. **Arquivos Shift-JIS** — `.cgi`/`.pm` têm comentários em Shift-JIS; strings de idioma são ASCII. Na reescrita, normalizar tudo para UTF-8.
4. **TmsHelper.exe** é o elo com o Excel — a reescrita substitui isso por relatórios web e exportação nativa; as **fórmulas** (RPM, EFFIC, taxas) ficam do lado do servidor.