# Modelo de Dados

## Visão geral

Todo o armazenamento é em arquivos texto planos sob `tmsdata/`. Não há banco de dados. As rotas de escrita são:

- **Coleta** → `current/current.txt` (snapshot em tempo real) e `loom/<mac>.txt` (registro diário com histórico de paradas).
- **Agregação** (`TMSDATAfinal.pm`) → `shift/`, `operator/`, `shift-date`, `shift-week`, `shift-month`, `shift-shift` e derivados.
- **Índices** (`TMSDATAindex.pm`) → `index/` (uso em telas de seleção).

## Arquivos do diretório raiz

| Arquivo | Conteúdo | Escrito por |
|---|---|---|
| `collect_date.txt` | epoch da última coleta | `TMScollect::update_collect_date` / `extend_1hour` |
| `update.lock` | lock de atualização (`ip/level/timeout`) | `TMSlock::update_lockfile` |
| `restruction.req` | marcador de rebuild ("unfix") | `TMSrestruct` |
| `backup/*.zip` | backup do scanner | `getdata2.cgi` |

## 1. `current/current.txt` (snapshot real)

Uma linha por tear, `key value` separados por vírgula:

```
,mac_name <name>,mac_type <JAT|LWT>,ip_addr <ip>,shift <shift id>,get_time <y m d w H M S>,
sys_time <y m d w H M S>,style,beam,ubeam,s_beam,r_beam,s_ubeam,r_ubeam,cloth_len,cut_len,
doff_fcst,wout_fcst,uwout_fcst
```

## 2. `current/setting.txt`

Como `current.txt` + bloco de configuração:

- `rtc_time <y m d w H M S>`, `SHIFT_MODE <0..>`, `SIMPLE <n turnos> <hh:mm x n> <hh:mm x n>...`, `DAY_0..DAY_6 <n> <horários>`, `NAME_0..NAME_5 <nomes de operadores>`, `DAY_START_TIME <h:m>`.

> Observação real: `rtc_time` estava 4 h atrás de `sys_time` — relógios das máquinas errados (propósito do recurso setclock).

## 3. `loom/<mac>.txt` — registro diário do tear

Secções (marcadores no arquivo):

| Marcador | Conteúdo |
|---|---|
| linha 1 | `get_time <y m d w H M S>` (nota: wday no índice 3) |
| `JAT710-TMS-DATA current` | estado atual: `style beam *`, `MJ_current_sb` |
| `#"+"stop_history` | `MH_d0_hNNN_history HH:MM:SS HH:MM:SS <código>` por linha |
| `JAT700-MCARD-DATA file_info` | machine/style/beam/top_beam |
| `moni_monitor` (bloco principal) | `MJ_current_sb`, `MJ_sN_yN_seisan <4/conta>/rt/sc(40)/st(40)/to/tm/tapo1-6/tail1-6/sn/bn_b/bn_t/bt_use`, `MJ_t_sN_*` (shift atual 0=agora, 1=próximo, com `s0 live ...`, `s1 next ...`), `PM_t_p5_*` (pick ss0-ss2, eficiência, análise run/stop), `PM_i_now_p`, `PM_i_ctime`, `PM_i_ptime`, `PM_i_change 360`, `PM_i_who 5` |
| `shift` | `SHIFT_MODE`, `SIMPLE <n> <h:m>...`, `DAY 0..6`, `NAME 0..5`, `DAY_START_TIME` |

Exemplo real do arquivo `172017001001.txt` (2125 linhas):
- linha 1: `get_time 2026 9 17 4 13 58 9`
- linha 2: `JAT710-TMS-DATA current`
- linhas 23–436: `stop_history` (`#"+"stop_history`, linhas `HH:MM:SS HH:MM:SS code`)
- linhas 438–442: `JAT700-MCARD-DATA file_info`
- linhas 444–2106: `moni_monitor`
- linhas 2108–2124: `shift` — `SIMPLE 3 05:00 14:00 23:35 -1:-1 -1:-1`, `DAY 0..6`, `NAME 0..5 "..."`, `DAY_START_TIME 6:0`

## 4. `stop_history/<YYYY.MM.DD>/<NNNNNNNN>.txt`

- Linha 1 (metadados): `fixed|unfix,day 2026.09.17,ip_addr <ip>,mac_name <mac>,mac_type JAT710`
- Linhas seguintes: `<HH:MM:SS>,<HH:MM:SS>,<código>` — pares `stop_time,run_time,code`. Linha `-,HH:MM:SS,code` = segmento de rodagem.
- `index.txt`: `unfix,<NNNNNNNN>.txt,<mac_name>` por linha.
- `TMSstophist.pm` gera por tear CSV: linha 1 `YYYY/MM/DD,mac_name`, demais `stop_time,run_time,<texto da causa>`.

## 5. `operator/<YYYY.MM.DD>.txt`

Uma linha por (tear × operador):

```
unfix,mac_name <mac>,mac_type JAT,ip_addr <ip>,day,start 2026 9 17 4 6 0 0,ope_num 5,
ope_name girlande,style 1210,beam 123219,ubeam None,seisan <4>,run_tm <sec>,stop_ttm <sec>,
s_ct <40>,s_tm <40>
```

## 6. `shift/<YYYYMMDD>.<n>.txt` — dados brutos por dia

Uma linha por tear, `key value` em pares:

```
mac_name, mac_type, ope_name, style, beam, ubeam, seisan(4), off_prod(3),
run_tm(sec int), stop_ttm(sec int), <arrays de parada por código> (40/31 valores)
```

## 7. `shift-shift/<shift>.txt` — agregado por turno

```
shift 2026.09.17.0,mac_name…,mac_type,ope_name,style,beam,ubeam,seisan 311.8 239.8 262.3,
off_prod,run_tm 484.883,stop_ttm 47.333,stop_ct/tm <12 cada>,wf1_ct/tm <6|4>,wf2_ct/tm,lh_ct/tm
```

- `run_tm`/`stop_ttm`/`stop_tm` em **minutos com 3 casas**.
- `seisan`/`off_prod` = valores crus /10 (kilopicks...).

## 8. Arquivos de índice (`index/`)

- `shift_shift.txt`, `shift_date.txt`: `<periodo> <wday>` ordenados reversamente (ex.: `2026.09.17.0 4`).
- `shift_week.txt`, `shift_month.txt`: períodos.
- `loom_{s,d,w,m}.txt`, `style_{s,d,w,m}.txt`: nomes de teares/estilos únicos.
- `opedata_date.txt`, `opedata_week.txt`, `opedata_month.txt`, `operator_{d,w,m}.txt` (dados de operador).
- `current_style.txt`, `current_loom.txt` (snapshot).
- `history_date.txt` (com subpastas por wday), `history_loom.txt` (nomes de máquina).
- O diretório é limpo com `del /Q /F` e reconstruído por `make_index`.

## Pipeline de agregação (`TMSDATAfinal.pm`)

1. `make_*_update_list` → diretórios `newdata`.
2. `make_shift_tmp_file` → arquivo temporário.
3. `make_tmp_data` = soma das linhas brutas por dia.
4. `split_tmp_file` agrupa por `periodo, mac_name, mac_type, ope_name, style, beam, ubeam` (chave de período a partir da data ou do arquivo de turno).
5. `make_final_data` (linhas 839–843): aplica o mapeamento 40→12 categorias, converte seg→min (3 casas), divide `seisan`/`off_prod` por 10, calcula `effic = run*100/(run+stop)` e **descarta linhas abaixo de `min_run_tm`/`min_effic`** (configuráveis em selitem).
6. Retenção: apaga arquivos mais antigos que `old_03/06/12_ym` (2/5/11 meses atrás do raw mais novo).

`merge_shift_data`/`merge_operator_data`/`merge_current_data` persistem com dedup + ordenação.

## Mapeamento dos códigos de parada (40 → 12) — `<código> → <categoria>`

Fonte: `common/TMScommon.pm` — `get_detail_stop_jat` (:264), `get_detail_stop_lwt` (:306). 12 categorias e 12 timed arrays (`stop_ct`, `stop_tm`) + `wf1/wf2/lh` (colunas de trama por cor).

### JAT — 40 códigos (índice no array cru)
`[0] Warp miss, [1] False selvage, [2] Leno(R), [3] Leno(L), [4] Manual check, [5-10] WF1 color 1-6, [11-16] WF2 color 1-6, [17] Warp top miss, [18-23] LH color 1-6, [24] Warp out, [25] Cloth doffing, [26-38] Other(13), [39] Power off`

| Categoria final | Fonte JAT |
|---|---|
| 0 Warp(Top) | `[17]` |
| 1 Warp | `[0]` |
| 2 False selvage | `[1]` |
| 3 Leno(L) | `[3]` |
| 4 Leno(R) | `[2]` |
| 5 Weft | Σ `[5..16]` + Σ `[18..23]` |
| 6 Warp out | `[24]` |
| 7 Cloth doffing | `[25]` |
| 8 Manual | `[4]` |
| 9 Power off | `[39]` |
| 10 Other | Σ `[26..38]` |
| 11 CC Back | **0 no JAT** |

Preenchimento trama: `wf1[i]=all[5+i]`, `wf2[i]=all[11+i]`, `lh[i]=all[18+i]` (i=0..5).

### LWT — 31 códigos
`[0] Warp miss, [1] False selvage, [2] CC Back, [3] Leno(R), [4] Leno(L), [5] Manual, [6-9] WF1 color 1-4, [10] Warp top miss, [11-14] LH color 1-4, [15] Warp out, [16] Cloth doffing, [17-19] Other(3), [20-23] WF2 color 1-4, [24-29] Other(6), [30] Power off`

| Categoria final | Fonte LWT |
|---|---|
| 0 Warp(Top) | `[10]` |
| 1 Warp | `[0]` |
| 2 False selvage | `[1]` |
| 3 Leno(L) | `[4]` |
| 4 Leno(R) | `[3]` |
| 5 Weft | Σ `[6..9]` + Σ `[11..14]` + Σ `[20..23]` |
| 6 Warp out | `[15]` |
| 7 Cloth doffing | `[16]` |
| 8 Manual | `[5]` |
| 9 Power off | `[30]` |
| 10 Other | Σ `[17..19]` + Σ `[24..29]` |
| 11 CC Back | `[2]` |

Preenchimento trama: `wf1[i]=all[6+i]`, `wf2[i]=all[20+i]`, `lh[i]=all[11+i]` (i=0..3).

> JAT = 6 cores; LWT = 4 cores.

## Rótulos das 12 categorias (`str_en.pm`, mesmas chaves em todos os idiomas)

`WARP_TOP_MISS 'Warp(Top)'`, `WARP_MISS 'Warp'`, `FALSE_SELVAGE_MISS 'False selvage'`, `LENO_L_MISS 'Leno(Left)'`, `LENO_R_MISS 'Leno(Right)'`, `WEFT_MISS 'Weft'`, `WARP_OUT 'Warp out'`, `CLOTH_DOFFING 'Cloth doffing'`, `MANUAL_STOP 'Manual'`, `POWER_OFF 'Power off'`, `OTHER_STOP 'Other'`, + `WF1/WF2/LH`, `COLOR1-6`, unidades `PICK/METER/YARD`.

## Exemplos de códigos crus (bloco JAT, `str_en.pm` :448–861; LWT :866–~1133)

- JAT: `0000 WARP STOP`, `0001 WASTE-SELVAGE STOP`, `0002/0003 FULL-LENO SELVAGE STOP (RIGHT/LEFT-HAND)`, `0004-0009 WEFT STOP BY WF1 COLOR 1-6`, `0010-0015 WEFT STOP BY WF2 COLOR 1-6`, `0016-0021 WEFT SUPPLY STOP BY LH FEELER COLOR 1-6`, `0025 CLOTH BEAM TO BE DOFFED`, `0027 [STOP] SWITCH PRESSED`, `0028 EMERGENCY STOP BUTTON PRESSED`, `1502-1504 (TAPO)`, `2101 REMOTE CONTROL STOP`, `2150/2151/2153/2154/2155 DECLARE(...)`.
- LWT: `0000 WARP STOP`, `0001/0002 WASTE-SELVAGE STOP (FRONT/REAR)`, `0003/0004 FULL-LENO SELVAGE STOP (RIGHT/LEFT-HAND)`, `0005-0008 / 0009-0012 WEFT (COLOR 1-4) / SUPPLY`, `0013 CLOTH BEAM TO BE DOFFED`, `0014/0015 STOP SWITCH / EMERGENCY STOP`, `2100 REMOTE CONTROL LOCK`, `2150-2155 DECLARE`.

> O arquivo `common/str_en.pm` contém ~400 códigos por máquina; os **primeiros 40 (JAT) / 31 (LWT)** são o mapeamento canônico acima; o restante (equipamento/falha, ex.: `2470 MAIN CONTROL: TUCKER BELT BREAK`, `4500-4510 SELVAGE`) é exibido por texto livre no histórico de paradas.

## Estrutura de arquivo agregado (linha consumida pelos relatórios)

```
mac_name, mac_type, ope_name, style, beam, ubeam, seisan(3), off_prod(3),
run_tm(min), stop_ttm(min), stop_ct(12), stop_tm(12),
wf1_ct(6|4), wf1_tm, wf2_ct, wf2_tm, lh_ct, lh_tm
```

## Chaves de dados

- `shift/...`: por `mac_name`.
- `operator/...`: por `"$mac_name $ope_num"`.
- `current.txt`/`setting.txt`: por `mac_name`.

## Compatibilidade pré-V3

- Arrays `stop_ct` com menos de 12 → `stop_ct[11] = 0`.
- `off_prod` ausente → `(0,0,0)`.