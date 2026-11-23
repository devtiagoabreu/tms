# TMS 8.0 — Toyota Loom Monitoring System

Sistema completo de monitoramento e gestão de teares (looms) com cadastros, turnos, grupos, operadores, envio de comandos, roles e permissões, e menus configuráveis.

---

## 📁 Estrutura de arquivos principais

```
D:\dev\tms\
├── start.bat                    # Script de inicialização do servidor
├── monitor_tms.ps1              # Monitor de reinício automático
├── testar_tms.ps1               # Teste rápido de conectividade
├── seed_completo.py             # Seed de dados iniciais (menus, turnos, grupos, teares, operadores, roles)
├── alembic/versions/            # Migrações do banco de dados
│   ├── ... (migrações TMS 7.1)
│   ├── t7u8v9w0x1y2_add_shift_turns.py      # Turnos
│   ├── z3a4b5c6d7e8_add_shift_turn_fk.py    # FK turno em daily_loom_data
│   ├── m4n5o6p7q8r9_tms80_groups_operators.py # Grupos e operadores
│   ├── k7l8m9n0o1p2_loom_commands.py        # Comandos para teares
│   └── s9t8u7v6w5x4_roles_permissions.py    # Roles e permissões
├── src/tms/
│   ├── app/
│   │   ├── main.py              # Aplicação FastAPI + lifespan (loops de coleta e comandos)
│   │   ├── api/
│   │   │   ├── cadastros.py     # Grupos, membros, operadores, eficiência por grupo/operador
│   │   │   ├── collector.py     # Status do coletor contínuo
│   │   │   ├── shift_turns.py   # Turnos + eficiência por turno
│   │   │   ├── teares.py        # Teares, edição, envio de comandos, ACK
│   │   │   ├── menus.py         # Menus configuráveis (CRUD, ordenação)
│   │   │   ├── roles.py         # Roles e permissões granulares
│   │   │   ├── daily.py         # Coleta diária
│   │   │   └── ...
│   │   ├── web.py               # Páginas web + injeção de menus do usuário
│   │   ├── web_cadastros.py     # Tela /cadastros
│   │   ├── web_teares.py        # Tela /teares
│   │   ├── web_menus.py         # Tela /menus
│   │   ├── web_roles.py         # Tela /roles
│   │   ├── dashboard.py         # Tela /monitor com drilldown + eficiência
│   │   └── shift_turns.py       # Tela /turnos
│   ├── models/
│   │   ├── shift_turn.py        # Turnos (nome, horário, dias, ativo, meia-noite)
│   │   ├── machine_group.py     # Grupos de teares + membros
│   │   ├── machine.py           # Teares (is_double, IP, grupo)
│   │   ├── permission.py        # Permissões e role_permissions
│   │   ├── collector_state.py   # Estado do coletor contínuo
│   │   ├── loom_command.py      # Fila de comandos para teares
│   │   ├── daily.py             # daily_loom_data (pontos_reais, metros_reais, shift_turn_id)
│   │   └── ...
│   ├── collector.py             # Envio de comandos via HTTP (send_command_to_loom)
│   ├── services/
│   │   └── daily_collection.py  # Coleta diária (COLLECTION_HOUR=7, vínculo a turno)
│   ├── static/
│   │   ├── css/style.css        # Estilos (drilldown, badges, etc.)
│   │   └── js/tms.js            # Lógica do menu drilldown + estado salvo no localStorage
│   └── templates/
│       ├── base.html            # Layout base com sidebar drilldown
│       └── ...
├── atalho: C:\Users\tiago\Desktop\TMS - Subir Servidor.lnk
```

---

## 🚀 Como subir o servidor

### Opção 1: Atalho na área de trabalho
Dê duplo clique em:
```
C:\Users\tiago\Desktop\TMS - Subir Servidor.lnk
```

### Opção 2: Executar diretamente
```
D:\dev\tms\start.bat
```

### Opção 3: PowerShell
```powershell
cd D:\dev\tms
set PYTHONPATH=src
python -m uvicorn tms.app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
```

O servidor sobe em: **http://localhost:8000**

---

## 🔧 Monitoramento e reinício automático

### Script de teste rápido
```powershell
powershell -ExecutionPolicy Bypass -File "D:\dev\tms\testar_tms.ps1"
```

### Script de monitoramento (reinicia se cair)
```powershell
powershell -ExecutionPolicy Bypass -File "D:\dev\tms\monitor_tms.ps1"
```

### Configurar no Agendador de Tarefas do Windows (executa a cada 5 min)

1. `Win + R` → digite `taskschd.msc` → Enter
2. **Criar Tarefa Básica...**
   - Nome: `TMS - Monitor e Reinício`
   - Gatilho: Diariamente → Iniciar agora → Repetir a cada 5 minutos → Indefinidamente
   - Ação: Iniciar um programa
     - Programa: `powershell.exe`
     - Argumentos: `-ExecutionPolicy Bypass -File "D:\dev\tms\monitor_tms.ps1"`
     - Iniciar em: `D:\dev\tms`
3. Na tarefa criada → **Propriedades**:
   - ✅ Executar se o usuário estiver logado ou não
   - ✅ Executar com privilégios mais elevados

---

## 🌱 Seed de dados iniciais

Popula o banco com menus, turnos, grupos, teares, operadores e roles/permissões:

```powershell
cd D:\dev\tms
set PYTHONPATH=src
python seed_completo.py
```

Para limpar e reexecutar:
```powershell
python seed_completo.py --limpar
```

---

## 📱 Telas do sistema

| Tela | URL | Descrição |
|------|-----|-----------|
| Login | `/login` | Entrada no sistema |
| Dashboard | `/` | Resumo da coleta diária |
| Monitor | `/monitor` | Teares ao vivo com filtro por grupo + eficiência por grupo/operador |
| Cadastros | `/cadastros` | Grupos de teares, operadores, membros |
| Teares | `/teares` | Cadastro/edição de teares + envio de comandos |
| Turnos | `/turnos` | Cadastro de turnos (A, B, C com horários e dias) |
| Menus | `/menus` | Configurar menus e submenus (drilldown) |
| Roles e Permissões | `/roles` | Gerenciar permissões por role (admin/operador/visualizador) |
| Telas de produção | `/screens/*` | Eficiência, Produção, Paradas, Relatórios |
| API Docs | `/docs` | Documentação interativa |

---

## 🔑 Usuário padrão

Após o seed, o usuário admin padrão é:
- **E-mail:** `admin@tms.local`
- **Senha:** `admin`

> ⚠️ Altere a senha em produção.

---

## ⚙️ Funcionalidades principais

### Tear Duplo (`is_double`)
- Quando marcado, **metros_reais** e **pontos_reais** são multiplicados por 2
- Aparece em todas as telas e relatórios (reports diário, eficiência por grupo, por turno, por operador)

### Pontuação real (×10)
- `pontos_reais = picks × 10`
- Se tear duplo: `pontos_reais = picks × 10 × 2`

### Turnos
- Cada turno tem: nome, hora início/fim, dias da semana, ativo/inativo, atravessa meia-noite
- Exemplo: Turno C das 23:35 às 05:00 (atravessa meia-noite)
- Coleta automática às **07:00** captura o turno C do dia anterior

### Menus configuráveis
- Cada usuário vê menus baseado em seu role + menus pessoais
- Submenus ficam escondidos (drilldown) até clicar no grupo
- Estado salvo no `localStorage`
- Admin pode criar, editar, ordenar menus e itens

### Roles e permissões
- 3 roles: admin, operador, visualizador
- 11 permissões granulares (teares.ver, teares.editar, teares.comandos, coletar.executar, menus.configurar, etc.)
- Admin pode ativar/desativar cada permissão por role

### Envio de comandos para teares
- 10 tipos de comando (set_style, set_shift, reset_counter, set_clock, set_speed, set_tension, set_article, clear_error, start_production, stop_production)
- Loop automático envia comandos pendentes a cada 10 segundos
- Tear pode confirmar recebimento (ACK)

---

## 🐛 Solução de problemas

**Servidor não sobe?**
1. Verifique se o PostgreSQL está rodando: `netstat -ano | findstr ":5432"`
2. Verifique se a porta 8000 está livre: `netstat -ano | findstr ":8000"`
3. Execute `testar_tms.ps1` para diagnóstico rápido
4. Se necessário, execute `start.bat` manualmente e veja o erro

**Banco de dados não migrado?**
```powershell
set PYTHONPATH=src
python -m alembic upgrade head
```

**Recriar seed?**
```powershell
python seed_completo.py --limpar
python seed_completo.py
```

---

## 📞 Versão

**TMS 8.0** — Toyota Loom Monitoring System  
Última atualização: 14/11/2026
