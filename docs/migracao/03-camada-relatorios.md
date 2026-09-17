# Camada de Relatórios

Análise de cada tela, parâmetros e fórmulas exatas. Fonte: `tms/shift`, `tms/shift2`, `tms/operator`, `tms/edit/exportcsv*`.

## Fórmulas canônicas (usadas em todos os relatórios)

Computadas pelo lado do Excel (template) ou pelo `exportcsv2.cgi`:

- **`RPM = seisan[0] * 100 / (run_tm / 60)`**
- **`EFFIC% = run_tm * 100 / (run_tm + stop_ttm)`**
- **`Production(unit) = seisan[unit] + off_prod[unit]`** (unit: 0=PICK, 1=METER, 2=YARD)

nos relatórios, células `RPM`/`EFFIC`/`RATE_*` saem em branco e o Excel calcula.

---

## 1. Relatório de Turno — `shift/shiftreport_s.cgi` + `shift/shiftreport.pm`

**Seleção** (mode=shift/operator, period, sel=loom ou style): `item2` (Top Beam, Beam, RPM, Effic, Run, Stop, Production), `item` (11 categorias), `item3` (CC Front, CC Back, Leno Total), `detail` (WF1, WF2, LH), `color` (1–6), `unit` (PICK/METER/YARD), `beam_type` (2 = tear de urdume superior).

**Título** (make_shiftreport_title :34–195):
`SORTKEY,{SHIFT|DATE|WEEK|MONTH}[,OPERATOR]{,LOOM,STYLE|,STYLE,LOOM}[,MAC_TYPE se jat_ari&&lwt_ari]{,TopBeam}{,Beam}{,RPM}{,Effic},Run&MINUTE,Stop&MINUTE,Production&PICK[,Production&unit]` + colunas por item selecionado. `Run,Stop,Production&PICK` são emitidos incondicionalmente.

**Dados** (make_shiftreport_data :200–379):
- `Production&unit` = `seisan[unit] + off_prod[unit]` (:276).
- Itens de parada de máquina (WarpOut, ClothDoff, ManualStop, PowerOff, Other — i=6..10): `&COUNT,&MINUTE` (:284–288). Não selecionados → somados em `UNSELECT&COUNT,MINUTE`.
- Itens de fiação de urdume/trama (WarpTop i=0, Warp i=1, Weft i=5, False/CC Total, Leno Total): `&COUNT,&MINUTE,&RATE_PH,&RATE_PDAY,&RATE_PP` (taxas em branco):
  - **False/CC Total = `stop_ct[2] + stop_ct[11]`** (CC Front + CC Back) (:323–329).
  - **Leno Total = `stop_ct[3] + stop_ct[4]`** (Leno(L)+Leno(R)) (:332–338).
  - `WarpTop` é **omitido quando `beam_type != 2`** (:97, :297).
- `TOTAL&COUNT` = `total_ct`, `TOTAL&MINUTE` = `total_tm`, `TOTAL2&COUNT` = `total2_ct` (:347): `total_ct` soma as 12 categorias (`[2]+[11]` colapsado em false, `[3]+[4]` em leno; `[0]` excluído se `beam_type≠2`); `total2_ct` = só fiação (warp+weft+false+leno).
- Detalhe: `WF1/WF2/LH &COUNT,&MINUTE` por cor selecionada de `wf1_ct/tm, wf2_ct/tm, lh_ct/tm` (:351–365); CC Front=`stop_ct[2]` (:368), CC Back=`stop_ct[11]` (:371), Leno(L)=`stop_ct[3]`, Leno(R)=`stop_ct[4]` (:374–376).
- `PARAM->` retorna `data_type, period_type, jat_ari, lwt_ari, sort_col, rpm, effic, run, stop, production, mac_stop, yarn_stop, unselect, unselect2, main_col, detail`.

## 2. Relatório de Eficiência — `shift/efficiency_s.cgi` + `shift/efficiency.pm`

Colunas (:34–36): `PERIOD[,OPERATOR],LOOM,STYLE,EFFIC&PERCENT,RUN&MINUTE,STOP&MINUTE,WARP&COUNT,WARP_RATE&CPH,WARP_RATE&CPDAY,WEFT&COUNT,WEFT_RATE&CPH,WEFT_RATE&CPDAY`.

Dados (:78–96): **`warp_ct = stop_ct[0]+[1]+[2]+[3]+[4]+[11]`**, **`weft_ct = stop_ct[5]`**. `EFFIC` e taxas em branco (Excel). Compatibilidade pré-V3: `if $#stop_ct < 11 { $stop_ct[11]=0 }`.

## 3. Relatório de Produção — `shift/production_s.cgi` + `shift/production.pm`

Colunas: `PERIOD[,OPERATOR],LOOM,STYLE,PRODUCT&{PICK|METER|YARD}`.
Dados (:79): **`product = seisan[unit] + off_prod[unit]`** (off_prod default `(0,0,0)`). Não usa `jat_ari/lwt_ari`.

## 4. Previsão de Fiação (forecast) — `shift/forecast.cgi`

- Período + horizonte `$doff_fcst`; data-hora prevista = `localtime(get_date + doff_fcst*60)` formatado `YYYY/MM/DD HH:MM:00`.
- Lê dados agregados de operador/turno; template `xlsfile/<lang>/forecast.xls`.

## 5. Análise de Paradas — `shift/stopanalysis.cgi`

- Params: period, sel_mode (loom/style), season (FIXED/UNFIX), beam_type, `doff_fcst`.
- Combina `stop_ct/stop_tm` (12) com detalhe por parada dos arquivos `stop_history`; `season` seleciona rodagens fixed ou unfix.

## 6. Relatório de Estilo — `shift/stylereport.cgi`

Agrupa os agregados por estilo (uma linha por estilo) sobre períodos selecionados, ciente JAT/LWT. Mesma estrutura de 12 categorias.

## 7. Histórico de Status — `shift/statushistory.cgi`

- Período + intervalo; por máquina monta linha do tempo "rodando / parado" a partir dos `stop_history` (índice `history_date.txt` → subpastas wday; `history_loom.txt`). Template `statushistory.xls`.

## 8. Histórico de Paradas — `shift/stophistory.cgi` (+ display `stophistory2.cgi`)

- Params: period, loom, season, intervalo de datas.
- Lê `stop_history/<yyyymmdd ou yyyy/mm/dd>/<mac>.txt`; 1ª linha meta `fixed/unfix,mac_name,mac_type,day`; demais `HH:MM:SS,HH:MM:SS,<código>`. Duração da parada = delta entre pares consecutivos.
- `TMSstophist.pm` = `make_stophistory_csv`.

## 9. Relatório Estatístico Padrão (serviço) — `shift2/select_s2.cgi` + `shift2/svsreport.cgi`

- Filename de dados: `get_xlsdata_file_name("svsrepor","csv")` — **o 't' ausente é literal** (:67). Template `xlsfile/ja/svsreport.xls` (en caso contrário).
- Colunas: `STYLE,LOOM,{SHIFT..},RUN&MINUTE,STOP&MINUTE,PRODUCT&PICK,EFFIC&PERCENT,RPM,WARP,WF1,WF2,OTHER,TOTAL[,WARP_TOP],WARP_BOTTOM,WF1&COLOR1..6,WF2&COLOR1..6`.
- Fórmulas (make_svsreport_data): pick = **`1000 * seisan[0]`**; warp = `stop_ct[0]+stop_ct[1]`; wf1 = Σ wf1_ct; wf2 = Σ wf2_ct; other = `Σ stop_ct[2..4] + stop_ct[11] + Σ lh_ct`; total = warp+wf1+wf2+other; coluna `WARP_TOP` só quando `beam_type==2` (desloca índices seguintes); `WARP_BOTTOM = stop_ct[1]`; EFFIC/RPM em branco. Nomes de estilo/máquina com citação `="..."`.

## 10. Relatórios de Operador — `operator/select_p.cgi`, `shiftreport_p.cgi`, `efficiency_p.cgi`, `production_p.cgi`

Mesmas fórmulas, filtrando um único `ope_name` em `operator-<periodo>`; modo `operator` adiciona a coluna `,OPERATOR`. A seleção exige uma lista de dias.

## 11. Lista de Estilos (Excel) — `edit/showstyle.cgi` + `showstyle2.cgi` + `TMSedit.pm`

- Relatório de consulta: linhas = períodos, colunas = teares (ou `mac_name+&+ope_name`), células = nomes de estilo extraídos das linhas agregadas (`regex ,style ([^,]+)`).
- `TMSedit::get_month_file_list` (:16–59) lista `shift|operator/<yyyy.mm.dd.[n].txt>`; `make_edit_index` (:63–115) monta/cacheia `index/edit/{s_|o_}loom<month>.txt` e `...style<month>.txt`.
- Limite do Excel: **254 colunas** (:49–50). Turnos → nome do turno (Sáb azul / Dom vermelho); operadores → dia da semana. Relatórios locais usam caminho de arquivo; remotos, URL.

## 12. Exportação CSV — `edit/exportcsv.cgi` / `exportcsv2.cgi` / `exportcsv3.cgi`

- `exportcsv.cgi`: seleção de mês para shift/operator/history + checkbox de forecast; acesso local/demo.
- `exportcsv2.cgi`: localhost-only; cria `C:\TMSDATA\<yyyy>-<mm>/{daily,machine,operator}` com CSV por dia/máquina/operador + `forecast.csv`. **Fórmulas canônicas** (~:340–360): `rpm = seisan[0]*100/(run_tm/60)`; `effic = run_tm*100/(run_tm+stop_ttm)`; minutos `printf %1.2f`; `seisan/10` → `%1.1f`. Histórico reaplica `get_detail_stop_jat/lwt` (:399–403) antes de exportar.
- `exportcsv3.cgi`: página "exportado com sucesso".

---

## Bugs legados (decidir: reproduzir ou corrigir)

| Bug | Local |
|---|---|
| Stopanalysis TIME: `stop_ct[11]` (contagem) usado onde se espera minutos (CC Back); `stop_ct[4]` (contagem) p/ Leno(L) | `stopanalysis.cgi` |
| Stylereport usa índice 3 para CC Front (deveria ser 2) | `stylereport.cgi` |
| Filename de dados `"svsrepor"` (falta o 't') | `svsreport.cgi:67` |
| Compatibilidade pré-V3 forçando `stop_ct[11]=0` | módulos de relatório |
| `get_str`/`get_stop_cause` retornam a chave quando falta rótulo | `TMSstr.pm` |

## Notas para a reescrita

- `.xls` binários não tiveram as fórmulas internas (RATE_PH/CPH/CPDAY/RATE_PP, layout do status history) extraídas — reconstruir a partir dos contratos de coluna acima e de `exportcsv2.cgi`.
- Não há amostras runtime completas no checkout — contratos documentados vieram do código.