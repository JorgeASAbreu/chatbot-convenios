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

`LLM_PROVIDER=none` é o padrão e é plenamente funcional. OpenAI e Gemini só funcionam se explicitamente habilitados no `.env`; chaves nunca são versionadas. Para Gemini, defina `GEMINI_MODEL` com um modelo disponível na sua conta. Modelos podem ser descontinuados; o código não fixa uma versão. Gemini mantém limite local configurável em `GEMINI_BUDGET_USD`; ele não substitui faturamento do fornecedor. Senhas usam bcrypt; autorização é feita nos serviços, além da interface. Auditoria não registra senhas nem chaves.

## Arquitetura conversacional

```text
Pergunta de negócio → Planner → Dispatcher/autorização → serviços/Decimal → FactsBundle → Composer
Comandos, SIAFI puro e falha da IA → parser determinístico/fallback
```

O Planner recebe somente pergunta, SIAFI ativo e catálogo fechado de ferramentas. O Dispatcher revalida SIAFI e autorização antes de executar `CONVENIO_BASICO`, `VIGENCIA`, `VALORES_CONVENIO`, `ARRECADACAO`, `EXECUCAO_FINANCEIRA`, `PENDENCIAS`, `CONTROLES_INTERNOS`, `PM6` ou `PROVIDENCIAS`. O Composer recebe apenas o `FactsBundle` autorizado e já calculado; não recebe conexão, SQL, ferramentas ou segredos.

`llm_usage` registra cada operação `PLAN` e `COMPOSE`, com provedor, modelo, tokens, custo estimado, latência, sucesso, erro, usuário e SIAFI. Para Gemini, o custo é `(tokens_entrada × custo_entrada_por_1M + tokens_saida × custo_saida_por_1M) / 1.000.000`. O alerta de orçamento é emitido em `GEMINI_WARN_THRESHOLD`; o bloqueio só ocorre no teto `GEMINI_BUDGET_USD`.

Em erros 429, 500, 502, 503, 504 ou timeout, cada provedor faz até três tentativas com espera limitada (0,25 s e 0,5 s). Cada tentativa fica registrada em `llm_usage`; erros 401, 403 e 404 encerram a chamada sem retry. Para uma checagem manual mínima do provedor configurado, execute `python -m scripts.smoke_llm`. O script faz uma chamada real, mostra provedor, modelo, resultado e contagem de tokens; não integra a suíte de testes.

Os indicadores são calculados em Python com `Decimal`, nunca pela IA. O **percentual de execução** apresentado ao usuário significa estritamente `receitas pactuadas / liquidado × 100`. O sistema também preserva, para explicabilidade, `receitas totais registradas / liquidado × 100`; este segundo inclui rendimentos e não substitui o indicador de execução. Se não houver valor liquidado, ambos são indisponíveis e não ocorre divisão por zero. Situação temporal após a data final é rotulada `ENCERRADA`; a situação oficial permanece separada em `situacao_fonte`.

## Qualidade e backup

Execute `ruff check .` e `pytest`. Faça backup lógico antes de atualizações: `pg_dump convenios > convenios.sql`. Em caso de falha de sync, consulte a tabela `source_snapshots`; snapshots anteriores são preservados para auditoria.

## PostgreSQL e Alembic

A aplicação e o Alembic usam `get_settings().database_url`, carregada de `DATABASE_URL` do ambiente ou do `.env` na raiz do projeto. Uma variável de ambiente exportada tem prioridade sobre o arquivo `.env`. A URL é obrigatória e deve usar `postgresql+psycopg://...`; `alembic.ini` não contém uma segunda URL. Execute os comandos a partir da raiz do projeto. Antes de migrar, confira host, porta, banco e usuário da URL sem publicar a senha. No Linux Mint, confirme o serviço e a porta com `systemctl status postgresql` e `pg_isready -h 127.0.0.1 -p 5432`; depois execute `alembic upgrade head` e `alembic current`. O ambiente desta execução restringiu a criação de sockets, portanto a migração precisa ser confirmada no host com acesso ao PostgreSQL.

## Homologação manual do chatbot

1. Execute `alembic upgrade head` e `./scripts/start.sh`.
2. Entre com usuário autorizado, selecione `9282916` e pergunte: “Faça uma análise completa deste convênio considerando a vigência, o total arrecadado, o que já foi empenhado, liquidado e pago, o percentual de execução, eventuais diferenças entre liquidação e pagamento e me diga quais pontos merecem atenção neste momento.”
3. Confira no detalhe da resposta o plano, as tools e os fatos; confirme valor total de R$ 624.000,00, arrecadação pactuada de R$ 520.000,00, rendimentos de R$ 24.204,43, liquidado de R$ 520.915,00, pago de R$ 519.714,59 e percentual de aproximadamente 99,82%.
4. Confira as linhas `PLAN` e `COMPOSE` na página **Uso de IA** e diretamente no PostgreSQL:

```sql
SELECT id, provider, model, operation, input_tokens, output_tokens,
       estimated_cost, latency_ms, success, error, user_id, siafi, timestamp
FROM llm_usage
ORDER BY id DESC
LIMIT 20;
```

O SIAFI `9282916` e os valores acima são referência de regressão, não constantes do código. Os warnings de `datetime.utcnow()` seguem como dívida técnica: corrigir exigirá alinhar tipos de coluna e fuso das datas existentes.

## Limitações da homologação

Não há SSO, WhatsApp, API bancária, publicação pública ou conciliação bancária. “Diferença entre receitas registradas e pagamentos registrados” não é saldo bancário.
