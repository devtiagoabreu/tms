# Configuração e Edição de Dados

## 1. `current/setting.txt` (config mestre)

Escrito por `common/TMSDATAnew.pm` → `write_current()` (:487–507), uma linha por tear, par chave/valor separado por vírgula:

```
,mac_name <nome>,mac_type <JAT|LWT>,ip_addr <ip>,get_time <..>,
sys_time <Y M D h m s>,rtc_time <..>,SHIFT_MODE <..>,SIMPLE <..>,
DAY_0 .. DAY_6 <..>,NAME_0 .. NAME_5 <..>,DAY_START_TIME <..>
```

`current.txt` (mesmo diretório) é o registro runtime: `mac_name, mac_type, ip_addr, shift, get_time, sys_time, style, beam, s_beam, r_beam, ubeam, s_ubeam, r_ubeam, cloth_len, cut_len, doff_fcst, wout_fcst, uwout_fcst`.

Fonte dos dados: `tmsdata/loom/*.txt` parseado por marcadores: `JAT710-TMS-DATA current`, `JAT700-MCARD-DATA moni_monitor`, `JAT700-MCARD-DATA shift`, `JAT710-TMS-DATA stop_history` (e equivalentes LW700).

Retenção (`TMSDATAmerge.pm`): current mantém 1 mês; shift e operator 11 meses; mais antigos removidos.

## 2. Telas de configuração e arquivos que gravam

Convenção: `X.cgi` = formulário, `X2.cgi` = aplicar, `X3.cgi` = sucesso. Todas as páginas de aplicar usam `update.lock` (`TMSlock`) e restringem a `REMOTE_ADDR eq '127.0.0.1'`.

| Tela | Grava em | Notas |
|---|---|---|
| `setting/selitem.cgi` | `tmsdata/setting/selitem.txt` | Itens de relatório; módulo `TMSselitem.pm`; defaults `@item2` (Top Beam 0, Beam 0, RPM 1, Efficiency 1, Run Time 1, Stop Time 1, Production 1), `@item`, `@item3` (CC Front, CC Rear, Leno Total), `@detail` (WF1, WF2, LH), `@color` (Color1–6); escalares beam_type=1, unit=0, period='shift', week=0, effic=0, run_tm=0, expire=26 |
| `setting/otherset.cgi` | `memcard.txt` (`use_memcard ari`) + `scanner_ip.txt` | via `TMSscanner::save_scan1_ip_set` |
| `setting/langset.cgi` | `language.txt`, `mac_type.txt` | Força `$lang="en"`; `TMSstr::save_language`, `TMSselitem::save_mac_type` |
| `setting/ipset.cgi` | `tmsdata/setting/ipaddress.txt` | `TMSipset.pm`; valida octetos 0–255, mescla/ordena sub-redes, expande faixas |
| `setting/passwd.cgi` | `passwd.txt`, `setting/.htaccess` | `AuthUserFile .../tmsdata/setting/passwd.txt`; `bin/htpasswd.exe -nbm TMS`; localhost-only |

## 3. Dados mestre do scanner (`scanset/`, `scanloom/`)

- `scanset/styleset.cgi` → `set/style_mst.txt` (`get_loom_setting("style")`); exibição + aplicar em uma página.
- `scanset/shiftset.cgi`/`2` → linhas de escala: `shift_schedule_is_week`, `shift_schedule_simple`, `shift_schedule_week 0..6`.
- `scanset/unitset.cgi`/`2` → `set/system_set.txt` via `TMSscanner::upload_scanner_file("all",…)`; `length_unit` (pick/meter/yard), `density_unit` (cm/inch).
- `scanset/loomspecset.cgi` → nome do tear/spec (`get_loom_setting("mac_name","ubeam_ari")`), ordenado por ID de tear.
- `scanset/passwd.cgi`/`2` → `passwd/scanloom_passwd.txt` + `passwd/scanloom/.htaccess`.
- `scanloom/clothbeamset.cgi` (`LOOM_DISP_MAX=20`), `clothbeammainte.cgi`/`2`/`3` (params `mac_id, style, use_doff_length, doff_length, beam, beam_set, beam_shrinkage, ubeam, ubeam_set, ubeam_shrinkage, correct_cloth, cloth_length, correct_beam, beam_remain, correct_ubeam, ubeam_remain`), `scanloom/otherset.cgi` (`get_loom_setting("mac_name","forecast_effic","cloth_correction")`).

## 4. Camada de edição (`edit/`, `edit2/`)

- `select.cgi`, `apply.cgi`, `delete/2`, `rename/2`, `hist_delete/2`, `hist_rename/2`, `setstyle/2`, `showstyle/2`, `exportcsv/2/3`, `TMSedit.pm`.
- `apply.cgi` → `TMSDATAfinal::update_all_request()`, `TMSDATAfinal::make_final(1)`, `TMSDATAindex::make_index(2)`.
- `edit2/switchdata.cgi`/`2` (TMSswitchdata.pm): alterna/renomeia/cria/apaga conjuntos de dados renomeando `tmsdata` ↔ `tmsdata.<nome>`.
- Export usa `TMScommon::http_header_tmsinf()` (protocolo TmsHelper, `POPUP_EXCEL` v1.0, `csvfile1`/`xlsfile`).
- Dados intermediários mantidos: `stop_history/<YYYY.MM.DD>/<NNNNNNNN>.txt` com header `fixed|unfix,day,ip_addr,mac_name,mac_type` e linhas `stoptime(HH:MM:SS),runtime(HH:MM:SS),stop_cause_code`.

## 5. Senha / licença / helper / modo serviço

- Desabilitação de senha: `disablepw/disable.cgi` + `index.cgi`; `tmsdata/setting/security_dir.txt`; `TMSdeny::is_demo_mode()` retorna 0 (variante demo retorna 1 e desabilita botões de submit).
- Download do TmsHelper: `index.cgi:209` → `<A href="TmsHelper-1.10.msi">` somente se `REMOTE_ADDR ne '127.0.0.1'`; MSI em `htdocs/tms/TmsHelper-1.10.msi` (229.376 bytes).
- Modo serviço: `index.cgi:62–72` lê `setting/service.txt`; se conteúdo `1`, `$SERVICE_MODE` ativo (adiciona Service Report, Language Setting, Data Switch) senão o arquivo é removido. Também em `loom/mcdata2.cgi` (~:120).
- Gating do menu (`index.cgi`): `$JAT710_ARI` = existe `ipaddress.txt`; `$MEMCARD_ARI` = existe `memcard.txt`; `$SCANNER_ARI` = existe `scanner_ip.txt`; URLs do scanner: `http://<scan1_ip>/TmsScanner/passwd/{scanloom,scanset}/redir.cgi?url=…`.
- Versão: `index.cgi:10` `my $version = "Version 7.0";`.
- `index.cgi:258–279` roda rotação de `logs/access.log`/`error.log` em 200 KB para `.1/.2/.3`.

## 6. Strings em português (`common/str_pt.pm`)

`load_str()` (:13–441): chaves comuns/menu/setting/loom/IP/service/scanner/LWT/Vista. Exemplos: `MAIN_MENU='Menu Principal'`, `SHIFT_REPORT='Relatorio de Turno'`, `SETTING='Ajuste'`, `DATA_EDIT='Editar Dados'`, `EXPORT_CSV_FILE='Exportar arquivo CSV'`, `BACK='Voltar'`.

Categorias: `WARP_TOP_MISS='Urdume(Superior)'`, `WARP_MISS='Urdume'`, `FALSE_SELVAGE_MISS='Ourela Falsa'`, `LENO_L_MISS='Giro(Esq)'`, `LENO_R_MISS='Giro(Dir)'`, `WEFT_MISS='Trama'`, `WARP_OUT='Troca de rolo de urdume'`, `CLOTH_DOFFING='Troca de rolo de tecido'`, `MANUAL_STOP='Manual'`, `POWER_OFF='Desligada'`, `OTHER_STOP='Outro'`; LWT: `CC_FRONT_MISS='Ourela Falsa(Frente)'`, `CC_REAR_MISS='Ourela Falsa(Atras)'`, `LENO_MISS='Giro Ingles'`.

`load_stop_cause_str_jat710()` (:448–862): ~400 códigos JAT (os 40 principais em :452–491; o restante são códigos de equipamento/falha, muitos com acentos mojibake/`?`). `load_stop_cause_str_lwt710()` (:866+): mapa LWT em inglês.

## 7. Rótulos de parada — os "40 códigos" em inglês (`str_en.pm` :448–491)

```
0000 WARP STOP
0001 WASTE-SELVAGE STOP
0002 FULL-LENO SELVAGE STOP, RIGHT-HAND
0003 FULL-LENO SELVAGE STOP, LEFT-HAND
0004..0009  WEFT STOP BY WF1 (COLOR 1..6)
0010..0015  WEFT STOP BY WF2 (COLOR 1..6)
0016..0021  WEFT SUPPLY STOP BY LH FEELER (COLOR 1..6)
0025 CLOTH BEAM TO BE DOFFED
0027 [STOP] SWITCH PRESSED
0028 EMERGENCY STOP BUTTON PRESSED
1502 TAPO:INOPERABLE (NO MISSED WEFT)
1503 TAPO:PROCESSING FAILURE (TOO SHORT MISSED WEFT)
1504 TAPO:PROCESSING FAILURE (TOO LONG MISSED WEFT)
2101 REMOTE CONTROL STOP
2150 DECLARE(M/C TROUBLE)
2151 DECLARE(MENDING)
2153 DECLARE(WARP OUT)
2154 DECLARE(CLOTH DOFFING)
2155 DECLARE(FOREMAN CALL ON)
2414 WARP STOP ( GROUND )
2415 WARP STOP ( PILE )
2420 CLOTH BEAM TO BE DOFFED( COUNTER STOP )
2421 CLOTH BEAM TO BE DOFFED( FRINGE STOP )
2422 CLOTH BEAM TO BE DOFFED( CUTTING STOP )
2430 STOP LOT NUMBER
```

Os "12 rótulos de categoria" são as categorias configuráveis (`OPST__*`/`*_MISS` em `str_pt.pm`): Urdume topo, Urdume, Ourela falsa, CC frente, CC atrás, Giro esq, Giro dir, Trama, Urdume fora, Troca de tecido, Manual, Desligada (+ Outro).