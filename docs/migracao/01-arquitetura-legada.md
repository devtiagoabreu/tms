# Arquitetura Legada

## Visão geral do fluxo

```
Máquinas (JAT710/LW700 via rede, TmsScanner, memcards)
   │  httpc.exe / getdata.cgi / mcdata.cgi
   ▼
tmsdata/loom/<mac>.txt        (registro diário por tear, com stop_history)
   │  TMSDATAfinal.pm (make_data.cgi) + TMSDATAindex.pm (make_index.cgi)
   ▼
Arquivos agregados por período + arquivos de índice (tmsdata/index/)
   │  Report CGI (lê index + agregados, grava CSV + .tmshlp)
   ▼
TmsHelper.exe  →  mescla CSV em template .xls  →  Excel
```

## Componentes

| Camada | Arquivos | Papel |
|---|---|---|
| Porta de entrada | `index.cgi` (raiz `tms/`) | Menu principal, versão 7.0, gating por subsistema presente, rotação de logs `check/access.log` |
| Coleta | `loom/getdata.cgi`, `getdata2.cgi`, `getdata3.cgi`, `loom/mcdata*.cgi` | Busca dados das máquinas via rede (`httpc.exe`) ou memcard |
| Processamento | `common/TMSDATAnew.pm`, `TMSDATAmerge.pm`, `TMSDATAfinal.pm`, `TMSDATAindex.pm`, `TMScollect.pm`, `TMSrestruct.pm` | Cria/atualiza agregados e índices |
| Relatórios | `shift/*.pm`, `shift/*.cgi`, `operator/*_p.cgi`, `shift2/svsreport.cgi` | Geram CSV + protocolo TmsHelper |
| Configuração | `setting/*.cgi`, `scanset/*.cgi`, `scanloom/*.cgi` | Telas de ajustes que gravam arquivos em `tmsdata/setting` |
| Edição | `edit/*.cgi`, `edit2/*.cgi`, `TMSedit.pm`, `TMSswitchdata.pm` | Editar/renomear/excluir/exportar dados |
| Telas de tear | `loom/opestate*.cgi`, `dashboard*.cgi`, `teares.cgi`, `apistate*.cgi` | Monitoramento em tempo real |
| Helper | `bin/httpc.exe`, `TmsHelper-1.10.msi`, `xlsfile/<lang>/*.xls` | Comunicação com máquinas e popup Excel |

## Protocolo TmsHelper (exportação Excel)

Cada CGI de relatório:
1. Grava o CSV dos dados via `TMScommon::get_xlsdata_file_name(<name>,"csv")` (padrão `tmsdata/csv/`).
2. Emite protocolo TmsHelper:
   ```
   method POPUP_EXCEL
   version 1.0
   xlsfile <url do template .xls>
   csvfile1 <caminho ou url do csv>
   ```
   — caminho local se o cliente é `127.0.0.1`, URL se remoto.
3. O helper local mescla o CSV no template XML/`xlsfile/<lang>/<nome>.xls` e abre no Excel.

Templates: `stylereport, stophistory, stopanalysis, statushistory, showstyle, shiftreport, production, forecast, efficiency` (`svsreport.xls` apenas ja/en).

> As células **EFFIC/RPM/RATE_\*** ficam **em branco no CSV** — são *fórmulas do template Excel*. A reescrita deve computar o servidor: `RPM = seisan[0]*100/(run_tm/60)`, `EFFIC% = run_tm*100/(run_tm+stop_ttm)`.

## Gates (bloqueios/pós-condições) em todo CGI de relatório

1. **`TMScollect::check_collect_date()`** — `tmsdata/collect_date.txt`, expira em `expire` (padrão 26 h); redireciona para coleta se vencido. `extend=on` chama `extend_1hour`. Pulado quando não há coleta configurada (sem `ipaddress.txt` e sem `scanner_ip.txt`).
2. **`TMSrestruct::check_restruction()`** — estado "unfix" (rebuild em andamento) bloqueia relatórios a menos que `force=on`. Acionado quando existe `tmsdata/restruction.req` OU `tmsdata/shift` existe sem `tmsdata/shift-shift`.
3. **`TMSlock::check_lockfile('../../tmsdata/update.lock',...)`** — página `data_updating_page` se há update em andamento. Formato `ip <ip>\nlevel <level>\ntimeout <timeout>`; locks obsoletos são descartados.

## Idioma

- `TMSstr::get_lang_set()` lê `setting/language.txt` (padrão `en`; suporta `ja,zh-cn,zh-tw,ko,pt`).
- Strings por idioma: `common/str_<lang>.pm` (`load_str_file` → `get_str`, `load_stop_cause_str_jat710`, `load_stop_cause_str_lwt710`).
- `get_stop_cause` retorna a própria chave se a tradução não existe (fallback i18n).

## Períodos e tipos de dados

- Período: `shift=0`, `date=1`, `week=2`, `month=3`.
- Tipo: `shift=0`, `operator=1`.

## Unidades e precisão

| Campo | Bruto (`loom/`, `shift/<data>`) | Agregado |
|---|---|---|
| `run_tm`, `stop_ttm`, `stop_tm` | segundos (int) | minutos com 3 casas = `seg/60` |
| `seisan[0..2]`, `off_prod[0..2]` | contagens cruas | `/10` (kilopicks/km...) — `svsreport` multiplica por 1000 |
| `stop_ct` | contagem (int) | contagem (int) |

## Diretório do código legado

- Código: `docs/legado/htdocs/tms/` → `bin, check, common, debug, disablepw, edit, edit2, image, loom, operator, scanloom, scanset, setting, shift, shift2, xlsfile`.
- Dados: `docs/legado/htdocs/tmsdata/` → `current, index, loom, operator, setting, shift, shift-date, shift-week, shift-month, shift-shift, stop_history, backup, logs, check, csv`.