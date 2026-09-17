# Subsistemas auxiliares (wnet, jat, lwt, tdm, tdmdata, quiz, Catalogs)

## 1. wnet — "Toyota Weave Net" (portal)

- **Papel**: portal web central (CGI Perl v2.0) que lança/liga todos os subsistemas via frameset (`index.cgi` → header `m_head1.cgi`, menu `m_menu.cgi`, footer `m_foot.cgi`).
- **Multilíngue**: 5 idiomas (en, ja, zh-cn, zh-tw, ko) via `language.txt` + `StrCommon.pm` + `str_<lang>.pm` (Shift_JIS, gb2312, big5, euc-kr).
- **Menu**: `setting/menu_conf.txt` (CSV: tms, tms_monitor, lwt_demo, jat_demo, was, dpcs, stm, ptm, eboard, wcam, catalogue…); `set_menu.cgi` alterna itens; variantes em `tools/menu_conf_{non,tms,was}.txt`.
- **Submenus**:
  - `main/m_menu.cgi` — menu principal
  - `iptable/m_iptable.cgi` — Gerenciador de Tabela de IP (EDIT/MAKE/CHECK/SEND/EXPORT/IMPORT)
  - `tdmmenu/m_pattern.cgi`, `m_style.cgi` — gerenciadores de padrão/estilo
  - `dpcsmenu/m_dpcs.cgi` — DPCS
  - `setting/*` — senha, tabela de IP, configuração de menu
- **Libs comuns**: `common/` — `StrCommon.pm` (idioma), `xml_Common.pm` (XHTML), `http_header.pm`, `file_common.pm`.
- **Dados**: `TMSiptable.pm` lê/grava `tmsdata/setting/ipaddress.txt` e um `ipaddress.txt` do WAS; gera `ip_table.txt` (formato: header `LW700-MCARD-DATA ip_table`, `FORMAT 2`, `USER_VERSION`, entradas `TYPE/ALL`).
- **Vale portar**: menus + i18n + geração de tabela de IP — lógica Perl real.

## 2. jat / lwt — consoles de operador de tear

- **Papel**: consoles de exibição dos teares JAT700 (ar) e LWT700 (água). Raiz de app auto-contida (`jat/ja001`, `lwt/lw001`) com applet Java (JAT.class, ifc, BackLight, BinTransC, DebugInfoPanel), `Rsc_*.properties` localizados, `html_parts/`, imagens.
- **URLs-chave**: `.../jat/ja001/cgi-bin/main.cgi` e `lwt/lw001/cgi-bin/main.cgi` — **executáveis Windows (PE/MZ)**, não Perl. Idem `iptable.exe`.
- **Dados**: `exchange.dat`, `exchange.inf` (JAT: `FILETYPE "STYLE"`, `FILENAME "NewStyle.dat"`; LWT: `FILETYPE "PATTERN"`, `FILENAME "rtyhuu"`), `spec2.set` + vários `.set` (weft, spindle, letoff, valve, sensor, timing, runset…).
- **Veredito de porta**: binários fechados — apenas documentar applet + formatos `.set`/`exchange`.

## 3. tdm — gerenciador de dados de padrão/estilo

- **Papel**: editar/exportar/importar/unir padrões Dobby e dados de estilo; envio a teares (MOUSE `Hozon`, `senddata`, `Export*`, `Import*`, `Union*`, `Delete*`, `Dobby*`, `Style*`, assistente `tdm0..tdm3*`).
- **Achado-chave**: todos os `tdm/*.cgi` são **executáveis Windows compilados** (MZ, 180 KB–2 MB). Único Perl legível é `PatternEditChk_iwashita.cgi` (stub que lista diretório). **Sem lógica Perl portátil em tdm**.
- `TDM_PATH.inf` define o mapa de caminhos (TDM=/tdm/, TDADATA=/tdmdata/, HFPDIR=/wnet/tdmmenu/, LOOMDIR=/cgi-bin/, MENUDIR=/wnet/tdmmenu/).
- Protocolo do assistente (a reproduzir no rewrite) pode ser inferido dos binários via strings (ex.: `Hozon.cgi` expõe POST fields `filename, group, execute, messageDIR`).

## 4. tdmdata — repositório de dados do TDM

- **Pastas**: `Dobby/` (tipos: STD-CAM, STD-DOBBY, STD-ELECTRIC, TOWEL-DOBBY, `undefined`, `-D`, `-LWT`), `DobbyFile`, `DobbyList`, `Machine`, `MachineF`, `MachineList` (texto "undefined"), `SetValueFile`, `SetValueFileList` (CSV "NewStyle-LWT,..."), `StyleFile`, `StyleList`, `KindList`.
- **Formato de dados**: `NewPattern.dat`/`NewStyle.dat`/`STD-CAM` são **binários MCARD** com cabeçalho ASCII `JAT700-MCARD-DATA file_info ----` (ou LW700). Listas em Shift-JIS.
- **A documentar**: o layout binário MCARD `.dat` (crítico para import/export do rewrite).

## 5. quiz — NÃO faz parte do sistema

App de quiz de terceiros (MIT, Português, "Quiz Brutal | Irmão do Jorel" de Tiago de Abreu), HTML5/CSS/JS autocontido, sem relação com têxtil → **excluir** da documentação de migração. (Nota: o mesmo autor do repositório.)

## 6. Catalogs — apenas placeholder

Quadros/páginas de backup para uma seção de catálogo de peças (`~menu.html`, `~top.html`, `~index.html`, imagens); o catálogo real vive em `cgi-bin/ca*.cgi` referenciado de `ip_table.txt`.

## 7. TStyleSheets — CSS compartilhado

- `weavenet100.css` + `tdm200.css` definem a identidade visual (fundo lavanda `#c7c4e2`, barras azul-escuro `#000099`, classes `b_m3_violet_c`, `t_m3_tbule_r`, `.mainmenu1`); reutilizadas entre wnet e tdm.

## Veredito consolidado

| Subsistema | Vale portar? |
|---|---|
| wnet (menus + i18n + tabela de IP + encaminhamento exchange) | **Alto** — lógica Perl real |
| jat / lwt (consoles) | **Nenhum** (binários) — documentar formatos `.set`/`.dat` |
| tdm (gerenciador de dados) | **Nenhum** (binários) — documentar protocolo do assistente + MCARD |
| tdmdata | **Definição de formato** (MCARD `.dat`, listas, CSV) |
| TStyleSheets | Reutilizar classes/esquema como estão |
| quiz, Catalogs | Excluir / placeholder |