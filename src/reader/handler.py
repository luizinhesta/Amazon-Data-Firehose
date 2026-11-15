"""
LAB-04 Amazon Data Firehose - Lambda de leitura do dashboard.

Rotas (HTTP API, payload 2.0), sem chave nem login (o limite e o throttling do API Gateway):
    GET /runs              lista as execucoes (itens RUN)
    GET /runs/{id}         aceitos x ENTREGUES x COM ERRO daquela execucao e o atraso do buffer
    GET /runs/{id}/events  arquivos do S3 que contem registros da execucao
    GET /metrics           totais + metricas reais do Firehose (CloudWatch)

"Entregue" e contado ABRINDO os arquivos que o Firehose gravou no S3 depois do disparo
(GZIP ou texto) e somando as linhas com o correlationId da execucao:
    - dados (prefixo DATA_PREFIX): cada linha e uma venda transformada (JSON);
    - erros (prefixo ERROR_PREFIX): cada linha e um JSON do Firehose com "rawData" (base64)
      do registro original que a transformadora marcou como ProcessingFailed.

Para limitar custo e tempo, le no maximo MAX_ARQUIVOS arquivos por consulta.
Metrica sem dado vem como null (o dashboard mostra "-"), nunca como zero inventado.

Handler no Console: lambda_function.handler

Variaveis de ambiente:
    RUNS_TABLE       tabela DynamoDB do lab
    DATA_BUCKET      bucket de dados do Firehose
    DATA_PREFIX      prefixo dos dados (ex.: vendas/)
    ERROR_PREFIX     prefixo dos erros (ex.: erros/)
    DELIVERY_STREAM  nome do fluxo do Firehose (dimensao das metricas)
    LOG_LEVEL        nivel de log (padrao INFO)
"""

import base64
import gzip
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

RUNS_TABLE = os.environ.get("RUNS_TABLE", "integracao-lab04-runs")
DATA_BUCKET = os.environ.get("DATA_BUCKET", "")
DATA_PREFIX = os.environ.get("DATA_PREFIX", "vendas/")
ERROR_PREFIX = os.environ.get("ERROR_PREFIX", "erros/")
DELIVERY_STREAM = os.environ.get("DELIVERY_STREAM", "integracao-lab04-fh")
MAX_ARQUIVOS = 40
_clientes = {}


def _cliente(nome):
    if nome not in _clientes:
        _clientes[nome] = boto3.resource("dynamodb") if nome == "dynamodb" else boto3.client(nome)
    return _clientes[nome]


class _Json(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


def _resposta(status, corpo):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(corpo, cls=_Json)}


def _listar_runs():
    tabela = _cliente("dynamodb").Table(RUNS_TABLE)
    itens, kwargs = [], {}
    while True:
        resp = tabela.scan(**kwargs)
        itens.extend(i for i in resp.get("Items", []) if i.get("sk") == "RUN")
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    itens.sort(key=lambda r: r.get("createdAt", ""), reverse=True)
    return itens


def _objetos_desde(prefixo, desde):
    """Objetos do prefixo modificados a partir de 'desde' (inclui o dia anterior, por causa do fuso UTC)."""
    s3 = _cliente("s3")
    encontrados = []
    for dia in sorted({(desde - timedelta(days=1)).date(), desde.date(), datetime.now(timezone.utc).date()}):
        pref = f"{prefixo}{dia:%Y/%m/%d}/"
        kwargs = {"Bucket": DATA_BUCKET, "Prefix": prefixo if prefixo.startswith(ERROR_PREFIX) else pref}
        while True:
            resp = s3.list_objects_v2(**kwargs)
            for o in resp.get("Contents", []):
                if o["LastModified"] >= desde - timedelta(seconds=5) and o["Key"] not in {x["Key"] for x in encontrados}:
                    encontrados.append(o)
            if not resp.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        if prefixo.startswith(ERROR_PREFIX):
            break  # erros ficam em subpastas por tipo; uma listagem do prefixo inteiro basta
    encontrados.sort(key=lambda o: o["LastModified"])
    return encontrados[:MAX_ARQUIVOS]


def _linhas(chave):
    corpo = _cliente("s3").get_object(Bucket=DATA_BUCKET, Key=chave)["Body"].read()
    if corpo[:2] == b"\x1f\x8b":
        corpo = gzip.decompress(corpo)
    return [l for l in corpo.decode("utf-8").splitlines() if l.strip()]


def _correlation_id_do_erro(linha):
    try:
        registro = json.loads(linha)
        original = json.loads(base64.b64decode(registro.get("rawData", "")).decode("utf-8").strip())
        return original.get("correlationId")
    except (ValueError, TypeError):
        return None


def _contar(run_id, criado_em):
    desde = datetime.fromisoformat(criado_em)
    entregues = erros = 0
    arquivos = []
    for prefixo, tipo in ((DATA_PREFIX, "dados"), (ERROR_PREFIX, "erro")):
        for obj in _objetos_desde(prefixo, desde):
            linhas = _linhas(obj["Key"])
            if tipo == "dados":
                n = sum(1 for l in linhas if f'"correlationId": "{run_id}"' in l)
                entregues += n
            else:
                n = sum(1 for l in linhas if _correlation_id_do_erro(l) == run_id)
                erros += n
            if n:
                arquivos.append({"key": obj["Key"], "tipo": tipo, "registros": n, "tamanho": obj["Size"], "gravadoEm": obj["LastModified"]})
    primeiro = min((a["gravadoEm"] for a in arquivos), default=None)
    atraso = round((primeiro - desde).total_seconds(), 1) if primeiro else None
    return entregues, erros, arquivos, atraso


def _metricas():
    fim = datetime.now(timezone.utc)
    nomes = [("incomingRecords", "IncomingRecords", "Sum"), ("deliveredRecords", "DeliveryToS3.Records", "Sum"),
             ("dataFreshnessSegundos", "DeliveryToS3.DataFreshness", "Maximum")]
    try:
        resp = _cliente("cloudwatch").get_metric_data(
            MetricDataQueries=[{"Id": f"m{i}", "Label": rotulo, "MetricStat": {
                "Metric": {"Namespace": "AWS/Firehose", "MetricName": nome, "Dimensions": [{"Name": "DeliveryStreamName", "Value": DELIVERY_STREAM}]},
                "Period": 300, "Stat": stat}} for i, (rotulo, nome, stat) in enumerate(nomes)],
            StartTime=fim - timedelta(minutes=60), EndTime=fim, ScanBy="TimestampDescending")
        por = {r["Label"]: r for r in resp.get("MetricDataResults", [])}
        out = {"cloudwatchDisponivel": True, "janelaMinutos": 60}
        for rotulo, _, stat in nomes:
            vals = (por.get(rotulo) or {}).get("Values") or []
            out[rotulo] = (sum(vals) if stat == "Sum" else vals[0]) if vals else None
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("CloudWatch indisponivel: %s", exc)
        return {"cloudwatchDisponivel": False, "incomingRecords": None, "deliveredRecords": None, "dataFreshnessSegundos": None}


def handler(event, context):
    caminho = (event or {}).get("rawPath") or ""
    run_id = ((event or {}).get("pathParameters") or {}).get("id")
    try:
        if caminho.endswith("/metrics"):
            runs = _listar_runs()
            return _resposta(200, {"totalRuns": len(runs), "acceptedTotal": sum(int(r.get("accepted", 0)) for r in runs), **_metricas()})
        if run_id:
            tabela = _cliente("dynamodb").Table(RUNS_TABLE)
            run = next((i for i in tabela.query(KeyConditionExpression=Key("pk").eq(run_id)).get("Items", []) if i.get("sk") == "RUN"), None)
            if not run:
                return _resposta(404, {"message": "execucao nao encontrada", "runId": run_id})
            if not DATA_BUCKET:
                return _resposta(500, {"message": "DATA_BUCKET nao configurado"})
            entregues, erros, arquivos, atraso = _contar(run_id, run["createdAt"])
            if caminho.endswith("/events"):
                return _resposta(200, {"runId": run_id, "arquivos": arquivos})
            completo = entregues + erros >= int(run.get("accepted", 0))
            return _resposta(200, {
                "runId": run_id, "createdAt": run.get("createdAt"), "accepted": run.get("accepted"),
                "invalidosGerados": run.get("invalidosGerados"), "esperadoEntregues": run.get("esperadoEntregues"),
                "entregues": entregues, "comErro": erros, "atrasoPrimeiraEntregaSegundos": atraso,
                "situacao": "COMPLETO" if completo else ("PARCIAL" if entregues + erros else "NO_BUFFER"),
            })
        return _resposta(200, {"runs": _listar_runs()})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha na leitura")
        return _resposta(500, {"message": "erro interno", "erro": type(exc).__name__})