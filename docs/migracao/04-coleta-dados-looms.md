# Coleta de Dados e Telas de Tear

## Protocolo de coleta

As máquinas (JAT710 — tecido a ar; LWT700 — tecido a água) são consultadas via HTTP:

- **JAT710**: `httpc.exe <ip> "/cgi-bin/ext.cgi?func=tms_get_monitor_data&data1=current&data2=monitor&data3=shift&data4=history"` — concorrência `PIPE_MAX=10`, 1 retry em `ERR__START_TIME_DIFF`. Dados de status: `func=get_stat`.
- **Scanner (TmsScanner)**: teares virtuais `S1-`…`S5-`; POST multipart (`boundary=----------mget-boundary-strings----------`, campo `mac_id=`) para `/TmsScanner/cgi-bin/mget.cgi`; resposta por tear em blocos `file`. `MGET_MAX=10` por pipe.
- **Memcard** (`mcdata*.cgi`): leitura de arquivos de card de memória (upload do PC do cliente), parser de seções `JAT700-/LW700-MCARD-DATA moni_monitor/shift`.

Arquivos têm `#! C:\Perl\bin\perl.exe` (Perl do Windows), dados mediante pipe para `bin/httpc.exe`.

## Fases pós-coleta (idênticas em getdata2.cgi:216–249 e mcdata2.cgi:156–185)

1. `make_newdata(1)` — grava `loom/<mac>.txt`
2. `merge_data(2)` — mescla
3. `make_final(3)` — agrega
4. `make_index(4)` — índices
5. `make_stophist_csv(5)` — CSV de histórico por tear

Cada fase guardada por `TMSlock::update_lockfile`; o dispositivo (tear/PC) bloqueia até o pipeline inteiro terminar (lock de arquivo + refresh a cada 10 s).

## Gates

- `TMSrestruct::check_restruction()` — true se `tmsdata/restruction.req` existe OU `tmsdata/shift` existe sem `tmsdata/shift-shift` (TMSrestruct.pm:92–103). Aciona rebuild completo + `clr_restruction_request()`.
- `TMScollect::check_collect_date` (TMScollect.pm:89–115) — falha sem `collect_date.txt` ou se o tempo decorrido > `selitem_expire` (padrão 26 h); `update_collect_date`/`extend_1hour` gravam epoch.

## getdata2.cgi (703 linhas) — fluxo completo

- `get_jat710_tms_data`: `httpc.exe $ip "/cgi-bin/ext.cgi?func=tms_get_monitor_data&data1=current&data2=monitor&data3=shift&data4=history" > tmpdatNN.tmp |`, 1 retry em `ERR__START_TIME_DIFF`.
- `check_monitor_data` (517–637): exige 5 linhas de cabeçalho (shift_start_time + operator_start_time [+ history_start_time]); compara sentinelas head/tail (descarta se diff → `ERR__START_TIME_DIFF` 1001); extrai `ip_addr`; grava `loom/octeto-octeto-octeto-octeto.txt` com prefixo `get_time <y m d w H M S>`; `WARN__CLOCK_DIFF` 1100 se `sys_time` difere > 600 s; parse de `sys_time` com `timelocal($d[7],$d[6],$d[5],$d[3],$d[2]-1,$d[1]-1900)` (ordem do token `Y M D W H M S`).
- `get_result_msg` (655–701): OK → `str_SUCCEED`; `WARN__CLOCK_DIFF` → relógio errado (link `http://$ip/`); ERRs → Desligada/Network/Socket/HTTP/Not Support/Data/System; linhas em `getdata3.dat`.
- Backup do scanner: `httpc.exe $scan_ip "/TmsScanner/backup.zip"` → `tmsdata\backup\scannerNN.zip`.

## mcdata.cgi / mcdata2.cgi (memcard)

- `mcdata.cgi` (332): somente localhost; seletor de pastas registradas em `datadir.txt` (drive maiúsculo, máx. 10); filtra ocultos/sistema (Win32::File) → POST para mcdata2.
- `mcdata2.cgi` (439): limpa `tmsdata\loom\*.*` (:91), auto-redireciona a mcdata3 após 2 s; contadores + `mcdata3.dat`.
- `mcdata_check` (199–307): exige `shift_start_time`+`operator_start_time` [+`history_start_time`]; compara head/tail (`ERR_DIFF_TIME`=5); `sys_time`→prefixo get_time; grava `loom/<fname>.txt` (espaços→underscores, sem `.txt`), sanidade de relógio (`WARN_FUTURE_DATA`=1 se futuro >600 s; `WARN_TOO_OLD_DATA`=2 se >7 dias).
- `service_mcdata_check` (315–437): parser de memcard JAT700/LW700 (`moni_monitor`/`shift`); determina turno atual por `MJ_t_sN_tm/rt/st` (rst = rt + Σ st, o primeiro não-zero vence); monta cabeçalho `current` `ip_addr <mac_name>/mac_name/shift/#end_of_data`; despeja seções verbatim. Erros: `ERR_CANT_OPEN`=3, `ERR_NOT_SUPPORT`=4, `ERR_DATA_ERROR`=6, `ERR_DIFF_TIME`=5.

## Estado do tear (opestate_cel.cgi:430–577 `make_status_data`)

Idêntico em opestate/opestate_all/dashboard_beta:

- Entrada: linhas `KEY=VALUE` de `get_stat` (JAT710) ou arquivos de status do scanner. Flags: `Stop/Warp_top/Warp/False_selvage/…/Power_off` (14 JAT / 15 LWT); dados: `Rpm/Shift_efficiency/24h_efficiency/Shift_stops/24h_stops/Stop_time/Run_time/Cloth_change_forecast/time/Beam_out_forecast/time/Top_beam_out_forecast/time`; `Style_name/Top_beam_use`.
- Precedência do status (:533–551): **Run** se `Stop==0`; senão última flag vencedora: `Manual → Weft → Leno_R → Leno_L → CatchCode_rear → CatchCode_front → False_selvage → Warp → Warp_top → Power_off → Cloth_mending → Machine_failure → Cloth_doffing → Warp_out → Out_of_product`.
- Duração = `Stop_time` se parado, senão `Run_time` (seg). Eficiência limitada a "100".
- `make_error_status` (600–617): ERR → Power_off (timeout de ping) / Comm_error / Not_support / Data_error / System_error.
- `get_scan_loom_status` (621–722): POST `/TmsScanner/cgi-bin/mget.cgi` (`boundary=` + `&file=..\data\status\<NN><NNN>.txt`), chunks por boundary → make_status_data por tear; ausentes → erro.
- `get_jat710_loom_status` (732–836): `PIPE_MAX=5` concorrente `httpc.exe $ip "/cgi-bin/ext.cgi?func=get_stat"`, resposta de 20 linhas ou "Not supported"/"func command not found" → Not_support.

### Renderização

- `opestate_cel.cgi` (272–320): tabela TEAR / ARTIGO / STATUS (cor de fundo) / PARADAS 24h / EFICIENCIA 24h / RPM; meta-refresh 60 s; paginação de 100.
- `opestate_all.cgi` (1274): dashboard de KPIs em português — mapas de status/fonte/cor (:46–89), `LOOM_DISP_MAX=150`, **OEE = disponibilidade%**, eficiência média turno/24h/horas custom (1–168), downtime pela soma de durações, filtros (status/eficiência/paradas), CSS + FontAwesome.
- `dashboard_beta.cgi` (996): grade de cards com toggle claro/escuro, por tear (barras de eficiência, contagens de parada trama/urdume).

Helpers: `print_duration`, `percent_bar`, `min_to_hhmm`.

## JSON / stubs

- `teares.cgi?json=1`: `encode_json(\@teares)` — vetor hardcoded.
- `apistate_.cgi` (80): sempre `Content-type: application/json`, JSON manual com 4 teares fixos em português (artigo/status/eficiencia/rpm) — **stub estático, não dados reais**.

## Setclock (ajuste de relógio das máquinas)

- `setclock.cgi` (148): relógio do PC via JS (`ShowPcClock`), alvo `Y/M/D H:M:S`, multi-seleção de teares (`ipaddress.txt`) + scanners 1–5 → posta em setclock2.
- `setclock2.cgi` (442): códigos de erro 100/200/201/210/220/300/400/410/900/1000/1001; lock `setclock.lock`; por tear: `diff_loom_clock` (GET `func=tms_get_monitor_data&data1=current`, valida 5 linhas, parse `sys_time` com `timelocal($d[7]…)`) — `|diff|≤30s` → `str_NOT_NEED_ADJUST`; senão `set_loom_clock` (GET `func=tms_set_date&data=Y+M+D+H+M+S`, espera `OK`). Por scanner: `diff_scanner_clock` (GET `cgi-bin/scanset.cgi?func=systime`, resposta `Y M D h m s`) → `set_scanner_clock` (+`&set_time=…`). Logs OK/SAME/POFF/ERR em `setclock3.dat`; cancelamento via `cancel.txt` (pop-up).

## TMSscanner.pm (719 linhas)

- Caches de config em `tmsdata/setting/`: `scanner_ip.txt` (get_scan1_ip_set), `scan_member.txt`, `ltb3_id.txt`, `loom_set.txt`, `system_set.txt`.
- `get_scanner_file($scan_no,$file)` (289–339): `httpc.exe $scan_ip "/TmsScanner/$file"`, 1 retry em 220 (não encontrado), `disp_scanner_error` em falha.
- `get_loom_setting(@items)` (365–431): defaults por máquina de `loom_set.txt` — mac_name, ubeam_ari=0, style, beam, beam_set, beam_shrinkage "0.0", ubeam, ubeam_set, ubeam_shrinkage, use_doff_length, doff_length, forecast_effic=95, cloth_correction "100.0"; remove duplicados registrados em ltb3_id.
- `update_loom_setting` (435–491): reescreve via `upload_scanner_file`.
- Unidades: `get_str_length_unit` = ("kpick","m","yard"), `/cm|/inch`.

## Formatos de armazenamento (amostras reais)

- `index/shift_shift.txt`: `<shift-id> <seq>` (ex.: `2026.09.17.0 4`); `index/current_loom.txt`: um mac por linha.
- `stop_history/<date>/<NNNNNNNN>.txt`: `unfix,day 2026.09.17,ip_addr 172.17.1.1,mac_name 00001,mac_type JAT710` então `START,END,CODE` (`-,07:06:54,0004` = segmento rodando); `index.txt`: `unfix,00000039.txt,00001`.
- `TMSstophist.pm` (178): fase 5 lê `*.update` (linhas `^\d{4}\.\d{2}\.\d{2}$`); cria `\TMSDATA\yyyy-mm\stop_history\yyyy-mm-dd\` CSV por tear; linha 1 `YYYY/MM/DD,mac_name`; demais `stop_time,run_time,<texto da causa>` (get_stop_cause).