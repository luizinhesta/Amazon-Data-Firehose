/*
 * LAB-04 Amazon Data Firehose - dashboard.
 *
 * - Sem login nem chave: a API e protegida por throttling e por validacao de faixa.
 * - Modo demonstracao (API nao configurada ou MODO_DEMONSTRACAO=true): dados sinteticos
 *   rotulados, sem nenhuma chamada a API.
 * - O DOM e montado com textContent (nunca innerHTML com dados vindos da API).
 * - O detalhe e recarregado ate a execucao ficar COMPLETA (entregues + com erro = aceitos).
 */
(function () {
  "use strict";

  var cfg = window.LAB04_CONFIG || {};
  var API = String(cfg.API_BASE_URL || "").replace(/\/+$/, "");
  var MODO_DEMO = cfg.MODO_DEMONSTRACAO === true || !(API.indexOf("https://") === 0 && API.indexOf("<") === -1);
  var INTERVALO = Number(cfg.REFRESH_INTERVAL_MS) || 8000;
  var selecionado = null;
  var completo = false;

  function $(id) { return document.getElementById(id); }
  function el(tag, props, filhos) {
    var n = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) {
      if (k === "text") n.textContent = props[k];
      else if (k === "className") n.className = props[k];
      else n.setAttribute(k, props[k]);
    });
    (filhos || []).forEach(function (f) { if (f) n.appendChild(f); });
    return n;
  }
  function limpar(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function msg(no, texto, tipo) { no.textContent = texto || ""; no.className = "status" + (tipo ? " " + tipo : ""); }
  function fmt(iso) { if (!iso) return "—"; var d = new Date(iso); return isNaN(d.getTime()) ? String(iso) : d.toLocaleString("pt-BR"); }
  function traco(v) { return v === null || v === undefined ? "—" : String(v); }
  function inteiro(v) { return v === null || v === undefined ? "—" : String(Math.round(Number(v))); }

  function api(caminho, opcoes) {
    opcoes = opcoes || {};
    var headers = {};
    if (opcoes.body) headers["content-type"] = "application/json";
    return fetch(API + caminho, { method: opcoes.method || "GET", headers: headers, body: opcoes.body }).then(function (r) {
      return r.text().then(function (t) {
        var corpo = {};
        try { corpo = t ? JSON.parse(t) : {}; } catch (e) { corpo = { message: t }; }
        if (!r.ok) { var erro = new Error(corpo.message || ("HTTP " + r.status)); erro.status = r.status; throw erro; }
        return corpo;
      });
    });
  }

  var DEMO = {
    runs: [{ pk: "lab04-run-demo0001", accepted: 100, invalidosGerados: 10, createdAt: "2026-11-03T20:00:00Z" }],
    metrics: { totalRuns: 1, acceptedTotal: 100, incomingRecords: 100, deliveredRecords: 90, dataFreshnessSegundos: 64 },
    detalhe: { accepted: 100, entregues: 90, comErro: 10, atrasoPrimeiraEntregaSegundos: 63.4, situacao: "COMPLETO" },
    arquivos: [
      { key: "vendas/2026/11/03/integracao-lab04-fh-1-2026-11-03-20-01-03-abc.gz", tipo: "dados", registros: 90, tamanho: 2310, gravadoEm: "2026-11-03T20:01:03Z" },
      { key: "erros/processing-failed/2026/11/03/integracao-lab04-fh-1-2026-11-03-20-01-03-def.gz", tipo: "erro", registros: 10, tamanho: 1420, gravadoEm: "2026-11-03T20:01:03Z" }
    ]
  };

  var SITUACAO = {
    NO_BUFFER: "Aguardando o buffer do Firehose: aceito pela API, ainda nada no S3.",
    PARCIAL: "Parte dos registros já está no S3; o restante ainda está no buffer.",
    COMPLETO: "Todos os registros aceitos já estão no S3 (entregues + com erro)."
  };

  function renderRuns(runs) {
    var corpo = $("runs-body");
    limpar(corpo);
    if (!runs || !runs.length) { corpo.appendChild(el("tr", {}, [el("td", { colspan: "4", className: "vazio", text: "Nenhuma execução ainda." })])); return; }
    runs.forEach(function (r) {
      var tr = el("tr", { className: "clicavel" + (r.pk === selecionado ? " sel" : ""), tabindex: "0" }, [
        el("td", {}, [el("code", { text: r.pk })]), el("td", { className: "num", text: traco(r.accepted) }),
        el("td", { className: "num", text: traco(r.invalidosGerados) }), el("td", { text: fmt(r.createdAt) })
      ]);
      tr.addEventListener("click", function () { selecionar(r.pk); });
      tr.addEventListener("keydown", function (e) { if (e.key === "Enter") selecionar(r.pk); });
      corpo.appendChild(tr);
    });
  }

  function renderMetricas(m) {
    $("m-total").textContent = traco(m.totalRuns);
    $("m-aceitos").textContent = traco(m.acceptedTotal);
    $("m-incoming").textContent = inteiro(m.incomingRecords);
    $("m-delivered").textContent = inteiro(m.deliveredRecords);
    $("m-fresh").textContent = inteiro(m.dataFreshnessSegundos);
  }

  function renderDetalhe(d) {
    $("d-aceitos").textContent = traco(d.accepted);
    $("d-entregues").textContent = traco(d.entregues);
    $("d-erros").textContent = traco(d.comErro);
    $("d-atraso").textContent = d.atrasoPrimeiraEntregaSegundos === null || d.atrasoPrimeiraEntregaSegundos === undefined ? "—" : String(d.atrasoPrimeiraEntregaSegundos);
    completo = d.situacao === "COMPLETO";
    msg($("d-situacao"), SITUACAO[d.situacao] || "", completo ? "ok" : "");
  }

  function renderArquivos(lista) {
    var ol = $("d-arquivos");
    limpar(ol);
    (lista || []).forEach(function (a) {
      ol.appendChild(el("li", { className: a.tipo === "erro" ? "erro" : "" }, [
        el("code", { text: a.key }),
        document.createTextNode(" — " + (a.tipo === "erro" ? "erro" : "dados") + ", " + traco(a.registros) + " registro(s) desta execução, " + traco(a.tamanho) + " bytes"),
        el("span", { className: "hora", text: "gravado em " + fmt(a.gravadoEm) })
      ]));
    });
    if (!ol.firstChild) ol.appendChild(el("li", { className: "vazio", text: "Nenhum arquivo ainda (o buffer leva cerca de 1 minuto)." }));
  }

  function carregarLista() {
    if (MODO_DEMO) { renderRuns(DEMO.runs); renderMetricas(DEMO.metrics); return Promise.resolve(); }
    return Promise.all([api("/runs"), api("/metrics")]).then(function (r) { renderRuns(r[0].runs); renderMetricas(r[1]); }).catch(tratarErro);
  }

  function carregarDetalhe() {
    if (!selecionado) return Promise.resolve();
    if (MODO_DEMO) { renderDetalhe(DEMO.detalhe); renderArquivos(DEMO.arquivos); return Promise.resolve(); }
    var id = encodeURIComponent(selecionado);
    return Promise.all([api("/runs/" + id), api("/runs/" + id + "/events")]).then(function (r) { renderDetalhe(r[0]); renderArquivos(r[1].arquivos); }).catch(tratarErro);
  }

  function selecionar(id) {
    selecionado = id;
    completo = false;
    $("det-titulo").textContent = "Execução " + id;
    Array.prototype.forEach.call($("runs-body").querySelectorAll("tr"), function (tr) { var c = tr.querySelector("code"); tr.classList.toggle("sel", !!c && c.textContent === id); });
    carregarDetalhe();
  }

  function tratarErro(e) {
    if (e && e.status === 429) { msg($("msg-api"), "Muitas requisições em pouco tempo (HTTP 429). Aguarde alguns segundos.", "erro"); return; }
    msg($("msg-api"), "Erro ao consultar a API: " + (e && e.message ? e.message : "desconhecido") + ". Veja o console do navegador (F12 → Rede).", "erro");
  }

  function enviar() {
    if (MODO_DEMO) { msg($("msg-enviar"), "MODO DEMONSTRAÇÃO: nada foi enviado. Configure API_BASE_URL no config.js.", "erro"); return; }
    var qtd = parseInt($("qtd").value, 10), pct = parseInt($("pct").value, 10);
    if (!(qtd >= 10 && qtd <= 500)) { msg($("msg-enviar"), "A quantidade deve estar entre 10 e 500.", "erro"); return; }
    if (!(pct >= 0 && pct <= 50)) { msg($("msg-enviar"), "O percentual de inválidos deve estar entre 0 e 50.", "erro"); return; }
    $("btn-enviar").disabled = true;
    msg($("msg-enviar"), "Enviando " + qtd + " vendas...");
    api("/runs", { method: "POST", body: JSON.stringify({ quantidade: qtd, percentualInvalidos: pct }) })
      .then(function (r) {
        msg($("msg-enviar"), "Aceitos pela API: " + r.accepted + " (inválidos gerados: " + r.invalidosGerados + "). correlationId=" + r.correlationId + ". Aguarde o buffer (~1 min).", "ok");
        return carregarLista().then(function () { selecionar(r.correlationId); });
      })
      .catch(function (e) { msg($("msg-enviar"), "Falha ao enviar: " + e.message, "erro"); })
      .then(function () { $("btn-enviar").disabled = false; });
  }

  if (MODO_DEMO) { $("modo-banner").hidden = false; }
  $("btn-enviar").addEventListener("click", enviar);
  carregarLista();
  if (!MODO_DEMO) setInterval(function () { carregarLista().then(function () { if (!completo) return carregarDetalhe(); }); }, INTERVALO);
})();
