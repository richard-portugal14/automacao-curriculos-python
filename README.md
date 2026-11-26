# Assistente de Oportunidades

Aplicação de linha de comando em Python que coleta vagas da Adzuna, identifica estágios relevantes para um perfil e apresenta as melhores oportunidades em um relatório de console.

## Objetivo

Reduzir o trabalho de triagem de vagas: o sistema coleta oportunidades, mantém um inventário local, filtra vagas confirmadas como estágio, classifica a área, compara os requisitos com o perfil, calcula um score explicável e ranqueia os resultados. O usuário decide manualmente se deseja se candidatar.

O projeto não realiza candidaturas nem envia currículos.

## Funcionalidades

- Coleta de vagas pela API da Adzuna, usando termos e localidades configurados.
- Normalização das respostas da fonte para o modelo interno `Job`.
- Deduplicação pela chave da fonte e identificador externo, tanto durante a busca quanto na persistência.
- Persistência local em SQLite.
- Classificação determinística de estágio: `ESTAGIO`, `NAO_ESTAGIO` ou `INCERTO`.
- Classificação explicável da área: `DADOS_ANALYTICS`, `BI`, `TI_DADOS`, `TI_GERAL` ou `OUTRA`.
- Comparação de habilidades, formação e área com o perfil configurado.
- Score explicável de 0 a 100.
- Ranking determinístico das oportunidades avaliadas.
- Pipeline completo e relatório de console configurável por quantidade de resultados.
- Comandos de diagnóstico para inspecionar as classificações e o score.
- Testes automatizados unitários, de integração e end-to-end.

## Arquitetura

```text
Adzuna
  ↓
Coleta
  ↓
Normalização
  ↓
Deduplicação e persistência (SQLite)
  ↓
Filtro de estágio
  ↓
Classificação de área
  ↓
Profile matcher
  ↓
Score
  ↓
Ranking
  ↓
Relatório de console
```

- **Adzuna e coleta:** `sources/adzuna.py` consulta as buscas configuradas e transforma cada anúncio em um `Job`; `services/collect.py` grava ou atualiza os resultados.
- **Persistência e deduplicação:** `repositories/jobs.py` grava as vagas em SQLite. A chave única é formada pela fonte e pelo identificador externo.
- **Filtro de estágio:** `services/internship_classifier.py` mantém no fluxo principal somente vagas classificadas como `ESTAGIO`.
- **Classificação de área:** `services/area_classifier.py` atribui uma categoria e registra evidências explicáveis.
- **Profile matcher:** `services/profile_matcher.py` compara área, habilidades e formação com o perfil e as preferências.
- **Score:** `services/score.py` combina os resultados anteriores com os critérios de localização e modelo de trabalho; não reclassifica a vaga.
- **Ranking:** `services/ranking.py` ordena os resultados recebidos sem recalcular o score.
- **Pipeline e relatório:** `services/pipeline.py` coordena os serviços; `reports/console.py` apresenta os resultados já calculados.

## Estrutura do projeto

```text
.
├── config/
│   ├── preferences.toml
│   └── profile.toml
├── src/assistente_oportunidades/
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── reports/
│   │   └── console.py
│   ├── repositories/
│   │   └── jobs.py
│   ├── services/
│   │   ├── area_classifier.py
│   │   ├── area_diagnostic.py
│   │   ├── collect.py
│   │   ├── internship_classifier.py
│   │   ├── internship_diagnostic.py
│   │   ├── pipeline.py
│   │   ├── profile_matcher.py
│   │   ├── profile_diagnostic.py
│   │   ├── ranking.py
│   │   ├── score.py
│   │   └── score_diagnostic.py
│   └── sources/
│       ├── base.py
│       └── adzuna.py
├── tests/
├── .env.example
├── pyproject.toml
└── README.md
```

Os módulos `*_diagnostic.py` oferecem diagnósticos separados sobre vagas armazenadas e não gravam as classificações de volta no banco. O arquivo SQLite padrão fica em `data/jobs.sqlite3`; o diretório `data/` é ignorado pelo Git.

## Tecnologias

- **Python 3.11 ou superior:** aplicação e biblioteca padrão, incluindo `sqlite3` e `tomllib`.
- **SQLite:** inventário local de vagas.
- **Adzuna Jobs API:** fonte de oportunidades implementada.
- **HTTPX:** chamadas HTTP à API.
- **python-dotenv:** leitura local das credenciais em `.env`.
- **TOML:** perfil, preferências e parâmetros de busca.
- **pytest:** testes de desenvolvimento.
- **setuptools:** empacotamento e instalação editável.

## Configuração

Na raiz do projeto, copie o modelo de ambiente e preencha as credenciais fornecidas pela Adzuna:

```powershell
Copy-Item .env.example .env
```

Edite `.env` localmente:

```dotenv
ADZUNA_APP_ID=seu_app_id
ADZUNA_APP_KEY=sua_app_key
```

O arquivo `.env` é ignorado pelo Git. Não coloque credenciais no código-fonte nem as publique em commits.

Configure o perfil em `config/profile.toml` e áreas, localidades, modalidades e buscas em `config/preferences.toml`. `search.max_days_old` define a janela de validade, em dias, usada na busca Adzuna e no pipeline; o padrão deste projeto é 30 dias. Os valores atuais nesses arquivos são exemplos editáveis para o perfil do usuário.

## Instalação

Com Python 3.11+ instalado, no PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Preencha as credenciais no `.env` antes de executar uma coleta real.

## Execução

### Coletar vagas

```powershell
python -m assistente_oportunidades collect
```

Esse comando consulta a Adzuna usando os termos e localidades configurados e persiste as vagas. Ele não executa classificação, score, ranking ou relatório.

### Executar o pipeline e exibir o relatório

```powershell
python -m assistente_oportunidades run
```

`run` também coleta e persiste vagas; depois processa o inventário SQLite e mostra o relatório. Portanto, não é necessário executar `collect` antes de `run` para obter uma coleta nova.

É possível ajustar a quantidade de oportunidades exibidas:

```powershell
python -m assistente_oportunidades run --top-n 20
```

Os comandos `collect` e `run` também aceitam `--config-dir` e `--database` para usar outro diretório de configuração ou caminho de banco. O caminho padrão do banco é `data/jobs.sqlite3`.

### Inspecionar e diagnosticar vagas armazenadas

Os comandos abaixo operam sobre o SQLite existente e não fazem uma nova chamada à Adzuna:

```powershell
python -m assistente_oportunidades inspect-descriptions --limit 10
python -m assistente_oportunidades diagnose-internships
python -m assistente_oportunidades diagnose-areas
python -m assistente_oportunidades diagnose-profile
python -m assistente_oportunidades diagnose-score
```

Os comandos de diagnóstico apresentam resultados temporários; não persistem classificações, compatibilidade ou scores no banco.

## Relatório e score

O `run` coleta primeiro e depois processa as linhas retornadas por `JobRepository.list_all()`. O ranking considera vagas do inventário persistido que estejam dentro de `search.max_days_old`, incluindo vagas que não foram recebidas na coleta atual. A data de publicação da Adzuna é usada quando disponível; se estiver ausente ou inválida, usa-se a data de coleta persistida. Vagas vencidas permanecem no SQLite, mas não entram na classificação, compatibilidade, score ou ranking atuais. O relatório separa os contadores da coleta atual da quantidade de oportunidades confirmadas como estágio e ranqueadas no inventário válido.

O score tem quatro componentes, com máximo total de 100 pontos:

- **Área (40):** Dados/Analytics recebe 40; BI, 35; TI_DADOS, 25; TI_GERAL, 10; OUTRA, 0.
- **Habilidades (35):** proporcional às habilidades identificadas na vaga que correspondem ao perfil.
- **Formação (15):** compatível recebe 15; não informada, 10; incompatível, 0. Formação incompatível não elimina a vaga.
- **Localização/modelo de trabalho (10):** compatibilidade recebe até 10; informação parcial, 8; informação insuficiente, 5; incompatibilidade real, 0.

O relatório apresenta o score, área, habilidades correspondentes, formação, localização/modelo, explicação produzida pelo score e link original da vaga. Ele não recalcula os resultados.

## Testes

Instaladas as dependências de desenvolvimento, execute a suíte completa com:

```powershell
python -m pytest -q
```

Os testes usam vagas controladas e bancos SQLite temporários quando apropriado; os testes do pipeline não dependem de chamadas reais à API.

## Exemplo de saída

Exemplo ilustrativo: os valores e a oportunidade abaixo não são dados permanentes nem prometem resultados específicos da Adzuna.

```text
RESUMO DA EXECUÇÃO
Vagas recebidas na coleta atual: 63
Novas: 35
Atualizadas: 28
Oportunidades confirmadas como estágio e ranqueadas no inventário: 69
Oportunidades exibidas: 10
O ranking considera o inventário persistido no banco, não somente a coleta atual.

TOP OPORTUNIDADES (até 10)

------------------------------------------------------------------------
#1 — Estágio em Dados
Empresa: Empresa Exemplo
Score: 91,50
Área: DADOS_ANALYTICS
Skills compatíveis: SQL, Excel, Python
Formação: Compatível
Localização: São Paulo, SP
Modelo de trabalho: híbrido
Compatibilidade: Área DADOS_ANALYTICS: 40/40 pontos. ...
Link: https://example.test/vaga
```

## Decisões de projeto

- Classificações e score usam regras determinísticas e explicáveis, em vez de resultados opacos de machine learning ou LLM.
- Filtro de estágio, classificação de área, profile matcher, score e ranking permanecem em serviços separados.
- A coleta e a persistência são separadas da orquestração e da apresentação.
- A suíte contém testes isolados dos serviços, testes de integração e cenários end-to-end com coleta controlada.
- O sistema não automatiza candidaturas; a decisão e a candidatura permanecem manuais.

## Limitações conhecidas

- A Adzuna é a única fonte implementada; disponibilidade e conteúdo dependem da API e dos anúncios nela indexados.
- Classificações e correspondências dependem de padrões e habilidades explicitamente tratados pelos serviços; descrições incompletas ou formulações diferentes podem reduzir a precisão.
- A deduplicação usa `source` e `external_id`. Anúncios semanticamente iguais com identificadores diferentes podem permanecer como registros separados.
- O pipeline reprocessa o inventário persistido inteiro a cada execução de `run`, não apenas os resultados novos da coleta.

## Próximos passos possíveis

Possibilidades futuras incluem novas fontes de vagas, exportação do relatório e ajustes de preferência. Elas não estão implementadas nesta versão.
