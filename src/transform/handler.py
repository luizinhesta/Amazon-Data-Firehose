"""
LAB-04 Amazon Data Firehose - Lambda transformadora.

Segue o CONTRATO de transformacao do Firehose. Entrada: event["records"], cada um com
"recordId" e "data" (base64). Para CADA registro recebido, devolve:

    {"recordId": <o mesmo>, "result": "Ok" | "Dropped" | "ProcessingFailed", "data": <base64, quando Ok>}

Regras deste lab:
    - amount numerico, finito e maior que zero -> "Ok", com enriquecimento:
      currency (BRL), enriched=true, year/month/day a partir de occurredAt.
    - qualquer outro caso (ex.: "INVALIDO") -> "ProcessingFailed". O Firehose grava o
      registro original no prefixo de ERRO do S3 (pasta processing-failed).

Esta funcao nao chama nenhum servico AWS: precisa apenas da permissao basica de logs.

Handler no Console: lambda_function.handler

Variaveis de ambiente:
    LOG_LEVEL  nivel de log (padrao INFO)
"""

import base64
import json
import logging
import math
import os

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def enriquecer(venda):
    """Devolve a venda enriquecida. Lanca ValueError se o valor for invalido."""
    valor = float(venda["amount"])
    if not math.isfinite(valor) or valor <= 0:
        raise ValueError(f"amount invalido: {venda['amount']!r}")
    data = str(venda.get("occurredAt", ""))
    venda["amount"] = round(valor, 2)
    venda["currency"] = venda.get("currency") or "BRL"
    venda["enriched"] = True
    venda["year"], venda["month"], venda["day"] = (data[0:4], data[5:7], data[8:10]) if len(data) >= 10 else (None, None, None)
    return venda


def handler(event, context):
    saida, ok, falhas = [], 0, 0
    for rec in (event or {}).get("records", []):
        try:
            venda = json.loads(base64.b64decode(rec["data"]).decode("utf-8").strip())
            dados = (json.dumps(enriquecer(venda)) + "\n").encode("utf-8")
            saida.append({"recordId": rec["recordId"], "result": "Ok", "data": base64.b64encode(dados).decode("utf-8")})
            ok += 1
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning(json.dumps({"msg": "registro invalido", "recordId": rec.get("recordId"), "erro": str(exc)}))
            saida.append({"recordId": rec["recordId"], "result": "ProcessingFailed"})
            falhas += 1
    logger.info(json.dumps({"msg": "transformacao concluida", "ok": ok, "processingFailed": falhas}))
    return {"records": saida}