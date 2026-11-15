"""
LAB-04 Amazon Data Firehose - Lambda produtora (POST /runs).

1. Gera vendas sinteticas. Uma quantidade EXATA delas tem "amount" invalido
   (percentualInvalidos), para a Lambda transformadora marcar como ProcessingFailed.
2. Envia ao Firehose com PutRecordBatch (ingestao direta, ate 500 registros por chamada).
3. Grava o item RUN com quantos registros foram ACEITOS pela API.

Aceito pela API NAO significa entregue: o Firehose junta os registros no buffer
(tamanho OU tempo) antes de gravar no S3. A Lambda de leitura conta o que chegou ao S3.

Respostas: 202, 400 (entrada invalida), 500.
A API nao exige chave nem login: o que limita o uso e o throttling do API Gateway
e a faixa de quantidade validada aqui.

Handler no Console: lambda_function.handler

Variaveis de ambiente:
    DELIVERY_STREAM  nome do fluxo do Firehose (ex.: integracao-lab04-fh)
    RUNS_TABLE       tabela DynamoDB do lab
    LOG_LEVEL        nivel de log (padrao INFO)
"""

import json
import logging
import os
import random
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DELIVERY_STREAM = os.environ.get("DELIVERY_STREAM", "integracao-lab04-fh")
RUNS_TABLE = os.environ.get("RUNS_TABLE", "integracao-lab04-runs")
CANAIS = ["web", "app", "loja", "marketplace"]
_clientes = {}


def _cliente(nome):
    if nome not in _clientes:
        _clientes[nome] = boto3.resource("dynamodb") if nome == "dynamodb" else boto3.client(nome)
    return _clientes[nome]


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _resposta(status, corpo):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(corpo)}


def _ler_corpo(event):
    corpo = (event or {}).get("body")
    if isinstance(corpo, str) and corpo:
        return json.loads(corpo)
    return corpo if isinstance(corpo, dict) else {}


def gerar_vendas(correlation_id, quantidade, invalidos):
    posicoes_invalidas = set(random.sample(range(quantidade), invalidos))
    vendas = []
    for i in range(quantidade):
        vendas.append(
            {
                "schemaVersion": "1.0",
                "correlationId": correlation_id,
                "saleId": f"sale-{correlation_id[-8:]}-{i + 1:03d}",
                "amount": "INVALIDO" if i in posicoes_invalidas else round(50 + random.uniform(0, 500), 2),
                "channel": random.choice(CANAIS),
                "occurredAt": _agora(),
            }
        )
    return vendas


def enviar(vendas):
    """PutRecordBatch em lotes de 500. Retorna (aceitos, recusados)."""
    firehose = _cliente("firehose")
    aceitos = recusados = 0
    registros = [{"Data": (json.dumps(v) + "\n").encode("utf-8")} for v in vendas]
    for i in range(0, len(registros), 500):
        lote = registros[i : i + 500]
        resp = firehose.put_record_batch(DeliveryStreamName=DELIVERY_STREAM, Records=lote)
        falhos = resp.get("FailedPutCount", 0)
        recusados += falhos
        aceitos += len(lote) - falhos
    return aceitos, recusados


def handler(event, context):
    try:
        corpo = _ler_corpo(event)
        quantidade = int(corpo.get("quantidade", 100))
        percentual = int(corpo.get("percentualInvalidos", 10))
    except (ValueError, TypeError):
        return _resposta(400, {"message": "quantidade e percentualInvalidos devem ser numeros inteiros"})
    if not 10 <= quantidade <= 500:
        return _resposta(400, {"message": "quantidade deve estar entre 10 e 500"})
    if not 0 <= percentual <= 50:
        return _resposta(400, {"message": "percentualInvalidos deve estar entre 0 e 50"})

    invalidos = round(quantidade * percentual / 100)
    correlation_id = f"lab04-run-{uuid.uuid4().hex[:8]}"
    aceitos, recusados = enviar(gerar_vendas(correlation_id, quantidade, invalidos))

    _cliente("dynamodb").Table(RUNS_TABLE).put_item(
        Item={
            "pk": correlation_id,
            "sk": "RUN",
            "state": "ACCEPTED" if recusados == 0 else "PARTIAL",
            "quantidade": quantidade,
            "accepted": aceitos,
            "recusados": recusados,
            "invalidosGerados": invalidos,
            "esperadoEntregues": quantidade - invalidos,
            "createdAt": _agora(),
        }
    )
    logger.info(json.dumps({"msg": "lote enviado ao Firehose", "correlationId": correlation_id, "aceitos": aceitos, "invalidos": invalidos}))
    return _resposta(202, {"correlationId": correlation_id, "accepted": aceitos, "recusados": recusados, "invalidosGerados": invalidos,
                           "note": "Aceito pela API nao significa entregue. O Firehose grava no S3 depois do buffer."})