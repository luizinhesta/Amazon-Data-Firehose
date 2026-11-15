# Entrega de Vendas no S3 com Amazon Data Firehose: Buffer, Transformação Lambda e Tratamento de Erros

![Capa do projeto: Entrega de Vendas no S3 com Amazon Data Firehose.](imagens/imagem%20%281%29.png)

*Leitura de cerca de 5 minutos · Amazon Data Firehose, Lambda, S3, DynamoDB, API Gateway e CloudFront*

## Resumo

Este projeto mostra, na prática, como o **Amazon Data Firehose** leva eventos até um data lake no S3 sem nenhum servidor no meio. Um produtor envia vendas sintéticas. O Firehose junta os registros num **buffer**, chama uma Lambda que **transforma** cada venda, comprime em GZIP e grava arquivos organizados por data. Vendas com valor inválido não se perdem: vão para uma pasta de **erros**, com o conteúdo original.

O dashboard mostra o ponto central do serviço: **aceito pela API não é entregue**. Ele conta, dentro dos arquivos do S3, quantos registros de cada envio realmente chegaram e quanto tempo o buffer levou.

## O problema

Sistemas geram eventos o tempo todo e alguém precisa guardá-los para análise. Gravar cada evento direto no S3 cria milhões de arquivos minúsculos, caros e lentos de consultar. Escrever um serviço próprio para juntar, transformar, comprimir e tratar falhas dá trabalho e precisa de manutenção.

## A solução

![Arquitetura técnica da infraestrutura AWS, de ponta a ponta.](imagens/imagem%20%2833%29.png)

*Figura 1 — Arquitetura técnica da infraestrutura AWS, de ponta a ponta.*

1. O usuário escolhe quantas vendas enviar e o percentual de inválidas, e clica em **Enviar**.
2. A Lambda produtora envia tudo ao Firehose com `PutRecordBatch`. A API responde na hora: aceito.
3. O Firehose espera o buffer encher (1 MiB) ou o tempo passar (60 s). No volume do lab, o tempo vence.
4. A transformadora devolve cada venda como `Ok` (enriquecida) ou `ProcessingFailed`.
5. O Firehose grava os `Ok` em `vendas/` e os `ProcessingFailed` em `erros/processing-failed/`, sempre em GZIP e por data.

## Aceito não é entregue

Logo depois do envio, o dashboard mostra **100 aceitos e 0 entregues**. Cerca de um minuto depois, aparece **90 entregues e 10 com erro**, junto com o atraso medido até o primeiro arquivo. Esse intervalo é o buffer. No lab dá para dobrar o intervalo (120 s) e ver o atraso dobrar.

Os números vêm dos próprios arquivos: a Lambda de leitura abre os `.gz` gravados depois do envio e conta as linhas com o `correlationId` daquele envio.

![Dashboard: métricas do Firehose no CloudWatch e execução com aceitos, entregues e com erro.](imagens/imagem%20%285%29.png)

*Figura 2 — Dashboard: métricas do Firehose no CloudWatch e execução com aceitos, entregues e com erro.*

## A transformação em trânsito

O Firehose manda os registros em lote para a Lambda e espera de volta **um resultado para cada registro**, com o mesmo `recordId`:

| Resultado | O que o Firehose faz |
|---|---|
| `Ok` (com `data`) | Grava o conteúdo transformado no destino |
| `ProcessingFailed` | Grava o registro **original** na pasta de erros, com o motivo |
| `Dropped` | Descarta de propósito (não usado no lab) |

A transformadora acrescenta moeda, uma marca de enriquecimento e ano/mês/dia. Valor não numérico, zero, negativo ou infinito vira `ProcessingFailed`.

## Erro que deixa rastro

Cada linha do arquivo de erro tem o código (`Lambda.ProcessingFailed`), o número de tentativas e o registro original em base64. O guia mostra como decodificar e encontrar a venda com `"amount": "INVALIDO"`, que pode ser corrigida e reenviada.

![Registro original de uma venda rejeitada, com valor inválido e código de erro da transformação.](imagens/imagem%20%2811%29.png)

*Figura 3 — Registro original de uma venda rejeitada, com valor inválido e código de erro da transformação.*

## Acesso ao painel

O dashboard abre direto, **sem chave e sem login**: o foco do lab é o Firehose. O que limita o uso da API é o **throttling** do API Gateway (o `POST` que publica tem limite menor que as leituras) e a faixa de 10 a 500 vendas por envio, validada na Lambda. Autenticação de usuário é o tema do LAB-05.

## O que este projeto ensina

- A diferença entre **aceito pela API** e **entregue no destino**.
- Como o **buffer** (tamanho ou tempo) define o atraso e o tamanho dos arquivos.
- O **contrato da transformação**: um resultado por registro, `Ok`, `ProcessingFailed` ou `Dropped`.
- Como **prefixos com expressões** organizam o data lake por data, em UTC, e por que o prefixo de erro exige `!{firehose:error-output-type}`.
- Por que a **compressão** reduz custo de armazenamento e consulta.
- Quando usar Firehose e quando usar Kinesis Data Streams.

## Limitações

- Saída JSON + GZIP. Conversão para Parquet exigiria um esquema no Glue Data Catalog (tema dos LAB-06 e 07).
- A leitura abre no máximo 40 arquivos novos por consulta.
- Ingestão direta; o Firehose lendo de um Kinesis Data Stream é apenas documentado.
- A API é aberta: quem souber o endereço consegue enviar vendas (dentro do throttling). Não divulgue o endereço e exclua tudo ao terminar.

## Documentação

| Documento | Conteúdo |
|---|---|
| [IMPLANTACAO.md](IMPLANTACAO.md) | Passo a passo completo pelo Console AWS, validação final, custos e limpeza |
| [ARQUITETURA.md](ARQUITETURA.md) | Componentes, fluxo, contrato da transformação, prefixos, buffer e segurança |

## Estrutura do repositório

```text
src/producer/    Lambda produtora (POST /runs)
src/transform/   Lambda transformadora do Firehose
src/reader/      Lambda de leitura do dashboard (conta os registros no S3)
iam/             políticas das Lambdas, role do Firehose e política do bucket
events/          eventos de teste das Lambdas
frontend/        dashboard estático em HTML, CSS e JavaScript
```

Nenhum valor real de conta ou endereço está no repositório. Os documentos usam variáveis como `<ACCOUNT_ID>` e `integracao-lab04`, descritas no início do [IMPLANTACAO.md](IMPLANTACAO.md).