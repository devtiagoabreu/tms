# tms

Toyota loom monitoring system (TMS). This repository holds the legacy system (for reference) and the documentation for migrating it to Python + PostgreSQL.

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

- `docs/legado/htdocs/tms` — código legado (CGI Perl) do sistema de monitoramento de teares
- `docs/legado/htdocs/tmsdata` — dados de exemplo no formato de arquivos planos
- `docs/legado/htdocs/{wnet,jat,lwt,tdm,tdmdata,...}` — subsistemas auxiliares