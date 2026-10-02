# Chatbot de Convênios — DF/PMMG

Aplicação local de homologação para consulta auditável de convênios de entrada. A base oficial é ingerida dos CSVs físicos do Portal de Dados Abertos de MG; a IA é estritamente opcional e nunca é fonte de verdade financeira.

## Instalação no Linux Mint

Instale Python 3.12+, PostgreSQL e crie o banco/usuário. Depois:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# edite DATABASE_URL e defina uma senha forte do administrador
alembic upgrade head
python scripts/create_admin.py --password 'senha-forte'
./scripts/start.sh
```

O acesso local é `http://localhost:8501`. Para a rede, obtenha o IP com `hostname -I` e acesse `http://IP:8501`. Caso a política local permita, libere manualmente: `sudo ufw allow 8501/tcp`. O projeto não altera firewall.

## Operação

Sincronize pelo painel **Atualização da Base** (DF/Admin) ou por `python scripts/sync.py`. O serviço consulta `package_show`, identifica os resource IDs oficiais, baixa CSV `utf-8-sig` separado por `;`, registra snapshot/SHA-256 e não reingere recurso inalterado. Não usa `datastore_search`.

Para homologar, após sincronizar entre como DF/Admin e informe `9282916`; depois pergunte `quanto foi pago?`, `quanto foi liquidado?` ou `falta pagar?`.

## IA e segurança

`LLM_PROVIDER=none` é o padrão e é plenamente funcional. OpenAI e Gemini só funcionam se explicitamente habilitados no `.env`; chaves nunca são versionadas. Gemini mantém limite local configurável em `GEMINI_BUDGET_USD`; ele não substitui faturamento do fornecedor. Senhas usam bcrypt; autorização é feita nos serviços, além da interface. Auditoria não registra senhas nem chaves.

## Arquitetura conversacional

```text
Pergunta → Parser rápido → (simples: serviço/template)
                         → (aberta: Planner → Dispatcher → serviços/Decimal → FactsBundle → Composer)
```

O Planner recebe somente pergunta, SIAFI ativo e catálogo fechado de ferramentas. O Dispatcher revalida SIAFI e autorização antes de executar `CONVENIO_BASICO`, `VIGENCIA`, `VALORES_CONVENIO`, `ARRECADACAO`, `EXECUCAO_FINANCEIRA`, `PENDENCIAS`, `CONTROLES_INTERNOS`, `PM6` ou `PROVIDENCIAS`. O Composer recebe apenas o `FactsBundle` autorizado e já calculado; não recebe conexão, SQL, ferramentas ou segredos.

`llm_usage` registra cada operação `PLAN` e `COMPOSE`, com provedor, modelo, tokens, custo estimado, latência, sucesso, erro, usuário e SIAFI. Para Gemini, o custo é `(tokens_entrada × custo_entrada_por_1M + tokens_saida × custo_saida_por_1M) / 1.000.000`. O alerta de orçamento é emitido em `GEMINI_WARN_THRESHOLD`; o bloqueio só ocorre no teto `GEMINI_BUDGET_USD`.

O indicador denominado percentual de execução nesta aplicação significa estritamente `arrecadado / liquidado × 100`, calculado em Python com `Decimal`. Ele não é calculado pela IA e não é exibido se não houver valor liquidado.

## Qualidade e backup

Execute `ruff check .` e `pytest`. Faça backup lógico antes de atualizações: `pg_dump convenios > convenios.sql`. Em caso de falha de sync, consulte a tabela `source_snapshots`; snapshots anteriores são preservados para auditoria.

## Limitações da homologação

Não há SSO, WhatsApp, API bancária, publicação pública ou conciliação bancária. “Diferença entre receitas registradas e pagamentos registrados” não é saldo bancário.
