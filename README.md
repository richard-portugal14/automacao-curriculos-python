# Automação de candidaturas

Ferramenta em Python para organizar vagas a partir de um CSV e preparar candidaturas com rastreabilidade.
    Copy-Item .env.example .env
## Estado atual

O primeiro passo do projeto é validar a planilha e gerar uma fila de candidaturas revisável. O envio automático só poderá ser ligado a plataformas que autorizem esse tipo de integração. LinkedIn e Indeed restringem bots e automações não autorizadas em seus termos; por isso, esta versão não tenta preencher formulários nem enviar candidaturas nessas plataformas.

## Formato do CSV

Use UTF-8 e cabeçalho com estas colunas:

```csv
plataforma,url_vaga,empresa,cargo,caminho_curriculo
gupy,https://exemplo.com/vaga,Empresa Exemplo,Analista de Dados,C:\\curriculos\\curriculo.pdf
```

`plataforma` aceita `gupy`, `indeed` ou `linkedin`. O caminho do currículo pode ficar vazio na etapa de organização.

## Uso

```powershell
python -m candidatura validar vagas.csv
```

O comando valida os campos e informa problemas por linha. Ele não envia dados nem abre sessões em sites.
