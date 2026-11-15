# Entrega de Vendas no S3 com Amazon Data Firehose: Buffer, Transformação Lambda e Tratamento de Erros

**Documento:** Guia de implantação pelo Console AWS (pt-BR)

> Guia **operacional** para implantar e validar o projeto manualmente pelo Console AWS.
> A **Parte A** cria e configura os recursos. A **Parte B** valida tudo com evidências. A **Parte C** traz troubleshooting, custos e limpeza.
>
> Nada neste guia é executado automaticamente. Os menus estão escritos como aparecem no Console em **português (Brasil)**. Se o seu Console estiver em inglês, clique no ícone de engrenagem (canto superior direito) → **Idioma** → **Português (Brasil)**.

## Como ler este guia

Cada etapa segue a mesma estrutura:

1. **Objetivo** (uma frase).
2. **Dependências** (o que precisa existir antes).
3. **Caminho** no Console.
4. **Tabela de campos** com o valor exato. Campo que não aparece na tabela fica no padrão.
5. **O que acontece** ao salvar.
6. **Conferência** rápida (quando é possível conferir na hora).
7. **Erros comuns** e correção.

## Valores deste laboratório

Todos os nomes já estão prontos nos passos: copie exatamente como aparecem.

| Item | Valor |
|---|---|
| Região de todos os recursos (menos o certificado do ACM) | **Leste dos EUA (Norte da Virgínia)** — `us-east-1` |
| Prefixo de todos os nomes | `integracao-lab04` |
| Tag em todo recurso que aceita tag | `projeto` = `integracao-lab04` |
| Bucket do dashboard | `integracao-lab04-dashboard-<ACCOUNT_ID>` |
| Endereço do dashboard | `https://lab04.<DOMINIO_RAIZ>` |
| Bucket de dados do Firehose | `integracao-lab04-dados-<ACCOUNT_ID>` |

**Só estes quatro valores dependem da sua conta.** Eles aparecem entre `< >` apenas onde são usados:

| Valor | O que é | Onde obter |
|---|---|---|
| `<ACCOUNT_ID>` | ID da sua conta AWS (12 dígitos) | Nome da conta (canto superior direito do Console) |
| `<DOMINIO_RAIZ>` | Seu domínio no Route 53 (ex.: `meudominio.com.br`) | **Route 53** → **Zonas hospedadas** |
| `<API_URL>` | Endereço gerado pela API (ex.: `https://abc123defg.execute-api.us-east-1.amazonaws.com`) | Etapa 5.1 |
| `<DISTRIBUTION_ID>` | ID gerado pelo CloudFront (ex.: `E1ABCDEFGHIJKL`) | Etapa 6.3 |

## Recursos do projeto

| Recurso | Nome | Etapa |
|---|---|---|
| S3 (dados) | `integracao-lab04-dados-<ACCOUNT_ID>` com `vendas/` e `erros/` | 1 |
| DynamoDB | `integracao-lab04-runs` | 2 |
| Lambda | `integracao-lab04-producer-fn`, `-transform-fn`, `-read-fn` | 3 |
| Amazon Data Firehose | `integracao-lab04-fh` (Direct PUT → S3, GZIP) | 4 |
| API Gateway | `integracao-lab04-api` (HTTP API) | 5 |
| S3, ACM, CloudFront, Route 53 (dashboard) | `integracao-lab04-dashboard-<ACCOUNT_ID>`, certificado, `<DISTRIBUTION_ID>`, registro `A` | 6 |
| Dashboard | `frontend/config.js` publicado | 7 |

> Regra do projeto: **nada é considerado validado sem evidência registrada** na Parte B.

## Sumário

**Parte A — Implantação**

1. S3 (bucket de dados)
2. DynamoDB
3. Lambda e IAM (3 funções)
4. Amazon Data Firehose (fluxo com transformação)
5. API Gateway (HTTP API, CORS e throttling)
6. S3, ACM, CloudFront e Route 53 (dashboard)
7. Publicar o dashboard

**Parte B — Validação final**

**Parte C — Troubleshooting, custos e limpeza**

---

# PARTE A — IMPLANTAÇÃO

---
## Etapa 1 — S3 (bucket de dados)

**Objetivo:** criar o bucket onde o Firehose grava os arquivos de vendas (`vendas/`) e os registros que falharam na transformação (`erros/`).

**Dependências:** nenhuma.

**Caminho:** **S3** → **Buckets** → **Criar bucket**.

| Campo | Valor |
|---|---|
| Tipo de bucket | **Uso geral** |
| Nome do bucket | `integracao-lab04-dados-<ACCOUNT_ID>` |
| Região | `us-east-1` |
| Propriedade de objetos | **ACLs desabilitadas (recomendado)** |
| **Bloquear todo o acesso público** | **Marcado** (as 4 opções) |
| Versionamento | Desabilitado |
| Criptografia padrão | **SSE-S3** · Chave do bucket **Habilitada** |
| Tags | `projeto` = `integracao-lab04` |

→ **Criar bucket**. Não crie pastas: o Firehose cria `vendas/AAAA/MM/DD/` e `erros/processing-failed/AAAA/MM/DD/` sozinho.

> Este bucket é diferente do bucket do dashboard (`integracao-lab04-dashboard-<ACCOUNT_ID>`, etapa 6). Os dois são privados.

![Bucket de dados do Firehose no S3, com as pastas de dados e de erros.](imagens/imagem%20%286%29.png)

*Figura 1 — Bucket de dados do Firehose no S3, com as pastas de dados e de erros.*

---

## Etapa 2 — DynamoDB

**Objetivo:** guardar o registro de cada envio (`RUN`): quantos foram aceitos e quantos inválidos foram gerados.

**Dependências:** nenhuma.

**Caminho:** Console → **DynamoDB** → **Tabelas** → **Criar tabela**.

| Campo | Valor |
|---|---|
| Nome da tabela | `integracao-lab04-runs` |
| Chave de partição | `pk` — tipo **String** |
| Chave de classificação | `sk` — tipo **String** |
| Configurações da tabela | **Personalizar configurações** |
| Modo de capacidade | **Sob demanda** |
| Proteção contra exclusão | **Desativada** |
| Tags | `projeto` = `integracao-lab04` |

→ **Criar tabela**. Aguarde **Ativa**.

O item `RUN` (`pk` = `lab04-run-xxxxxxxx`, `sk` = `RUN`) guarda `quantidade`, `accepted`, `recusados`, `invalidosGerados`, `esperadoEntregues` e `createdAt`. O que foi **entregue** não fica no DynamoDB: a `read-fn` conta direto nos arquivos do S3.

![Tabela de execuções no DynamoDB.](imagens/imagem%20%2829%29.png)

*Figura 2 — Tabela de execuções no DynamoDB.*

---

## Etapa 3 — Lambda e IAM (3 funções)

**Objetivo:** criar as três funções do projeto.

| Função | Papel | Quem chama |
|---|---|---|
| `integracao-lab04-producer-fn` | `POST /runs`: valida a entrada e envia vendas ao Firehose | API Gateway |
| `integracao-lab04-transform-fn` | Transformadora do Firehose (`Ok` / `ProcessingFailed`) | Firehose (etapa 4) |
| `integracao-lab04-read-fn` | 4 rotas `GET` do dashboard; conta os registros nos arquivos do S3 | API Gateway |

**Dependências:** tabela (etapa 2) e bucket de dados (etapa 1).

### 3.1 Criar a função (repita para as 3)

**Caminho:** Console → **Lambda** → **Funções** → **Criar função**.

1. Selecione **Criar do zero**.
2. Preencha os campos da tabela 3.2 para a função.
3. Abra **Alterar a função de execução padrão** e marque **Criar uma nova função com permissões básicas do Lambda**.
4. Clique em **Criar função**.

**O que acontece:** o Lambda cria a função e uma role do IAM com nome `<nome-da-função>-role-xxxxxxxx`, que só tem permissão de gravar logs (política gerenciada **AWSLambdaBasicExecutionRole**). As permissões do projeto entram no passo 3.3.

### 3.2 Dados de cada função

| Campo | `producer-fn` | `transform-fn` | `read-fn` |
|---|---|---|---|
| Nome da função | `integracao-lab04-producer-fn` | `integracao-lab04-transform-fn` | `integracao-lab04-read-fn` |
| Tempo de execução | **Python 3.12** | **Python 3.12** | **Python 3.12** |
| Arquitetura | `x86_64` (padrão) | `x86_64` (padrão) | `x86_64` (padrão) |
| Arquivo de código | `src/producer/handler.py` | `src/transform/handler.py` | `src/reader/handler.py` |
| Política em linha | `iam/policy-producer-fn.json` | — (só a role básica) | `iam/policy-read-fn.json` |
| Memória | `128` MB | `128` MB | `256` MB |
| Tempo limite | `15` s | `60` s | `30` s |

Tags (todas): `projeto` = `integracao-lab04`.

### 3.3 Anexar a política do projeto (IAM)

1. Localize o arquivo de política da função (tabela 3.2).
2. Abra o arquivo no repositório (pasta `iam/`), copie o conteúdo e troque `<ACCOUNT_ID>` pelo ID da sua conta, **sem salvar essa alteração no repositório**.
3. Na função → aba **Configuração** → **Permissões** → clique no **nome da função de execução** (abre o IAM em outra aba).
4. **Adicionar permissões** → **Criar política em linha** → aba **JSON** → apague o conteúdo → cole a política → **Próximo**.
5. **Nome da política:** `integracao-lab04-producer-fn-policy` (e `-read-fn-policy`) → **Criar política**.

**O que cada função pode fazer**

| Função | Pode | Não pode |
|---|---|---|
| `producer-fn` | `firehose:PutRecordBatch` só no fluxo do lab; `PutItem` na tabela | ler o S3, ler a tabela |
| `transform-fn` | só gravar logs (role básica) | acessar qualquer serviço |
| `read-fn` | `Scan`/`Query` na tabela; `ListBucket` e `GetObject` só no bucket de dados; `cloudwatch:GetMetricData` (`Resource: *`) | gravar em qualquer lugar |

> A `transform-fn` **não recebe política em linha**: ela só transforma o que o Firehose envia e não chama nenhum serviço. A permissão para o Firehose **invocar** a função fica na role do Firehose (etapa 4), não na role da função.
>
> O tempo limite da `transform-fn` é **60 s** de propósito: o Console do Firehose avisa se a função de transformação tiver tempo limite menor que 1 minuto.

### 3.4 Colar o código e ajustar o manipulador (handler)

1. Na função → aba **Código**. No editor, abra `lambda_function.py`.
2. Apague todo o conteúdo e **cole o conteúdo inteiro** do arquivo da tabela 3.2.
3. Clique em **Implantar** e aguarde a mensagem de sucesso.
4. Ainda na aba **Código**, role até **Configurações de tempo de execução** → **Editar**.
5. **Manipulador:** `lambda_function.handler` → **Salvar**.

> **Por quê:** o manipulador é `<arquivo sem .py>.<função>`. O código define `handler(event, context)` e o arquivo no Console se chama `lambda_function.py`. O valor padrão `lambda_function.lambda_handler` causa `Handler 'lambda_handler' missing on module 'lambda_function'`.

### 3.5 Memória e tempo limite

Na função → **Configuração** → **Configuração geral** → **Editar** → preencha **Memória** e **Tempo limite** da tabela 3.2 → **Salvar**.

### 3.6 Variáveis de ambiente

Em cada função → **Configuração** → **Variáveis de ambiente** → **Editar** → **Adicionar variável de ambiente** para cada linha → **Salvar**.

| Variável | `producer-fn` | `transform-fn` | `read-fn` |
|---|---|---|---|
| `DELIVERY_STREAM` | `integracao-lab04-fh` | — | `integracao-lab04-fh` |
| `RUNS_TABLE` | `integracao-lab04-runs` | — | `integracao-lab04-runs` |
| `DATA_BUCKET` | — | — | `integracao-lab04-dados-<ACCOUNT_ID>` |
| `DATA_PREFIX` | — | — | `vendas/` |
| `ERROR_PREFIX` | — | — | `erros/` |
| `LOG_LEVEL` | `INFO` | `INFO` | `INFO` |

> `DATA_PREFIX` e `ERROR_PREFIX` precisam bater com o começo dos prefixos configurados no Firehose (etapa 4.2): `vendas/...` e `erros/...`.

### 3.7 Conferência rápida

**`producer-fn`:** aba **Testar** → **Criar novo evento** → nome `entrada-invalida` → cole o JSON abaixo → **Testar**.

```json
{
  "body": "{\"quantidade\": 5}"
}
```

Esperado: `"statusCode": 400` com a mensagem `quantidade deve estar entre 10 e 500` e nenhuma execução nova. (Um teste com entrada válida criaria uma execução e enviaria registros ao Firehose; isso fica para a Parte B.)

**`transform-fn`:** aba **Testar** → **Criar novo evento** → nome `contrato-firehose` → cole `events/teste-transformadora.json` → **Testar**. Esperado: **Bem-sucedido** com dois registros no resultado:

| `recordId` | `result` | Observação |
|---|---|---|
| `rec-valido` | `Ok` | `data` em base64; decodificado, tem `currency`, `enriched: true`, `year`, `month`, `day` |
| `rec-invalido` | `ProcessingFailed` | sem `data` (o `amount` é `"INVALIDO"`) |

### 3.8 Retenção de logs (custo)

O grupo de logs `/aws/lambda/<nome-da-função>` só aparece depois da primeira execução. Depois da conferência 3.7 (e, para as outras funções, depois da Parte B):

CloudWatch → **Grupos de logs** → selecione `/aws/lambda/integracao-lab04-...` → **Ações** → **Editar configuração de retenção** → **1 semana** → **Salvar**.

### 3.9 Erros comuns

| Sintoma | Causa | Correção |
|---|---|---|
| `Runtime.HandlerNotFound` / `lambda_handler missing` | Manipulador diferente de `lambda_function.handler` | Passo 3.4 |
| `Runtime.ImportModuleError` | Código colado em arquivo com outro nome | Colar dentro de `lambda_function.py` |
| Alteração "não pega" | Não clicou em **Implantar** | Clicar em **Implantar** |
| `AccessDeniedException` | Política sem trocar `<ACCOUNT_ID>`, ou recurso em outra região | Revisar a política em linha (3.3) |
| `Task timed out after 3.00 seconds` | Tempo limite padrão (3 s) | Passo 3.5 |
| Firehose avisa sobre o tempo limite | Tempo limite da `transform-fn` menor que 1 minuto | Passo 3.5 (60 s) |

![As funções Lambda do projeto.](imagens/imagem%20%2815%29.png)

*Figura 3 — As funções Lambda do projeto.*

---

## Etapa 4 — Amazon Data Firehose (fluxo com transformação)

**Objetivo:** criar o fluxo que recebe as vendas, chama a transformadora, junta os registros no **buffer** e grava arquivos GZIP no S3. Registros que a transformadora marca como `ProcessingFailed` vão para a pasta de erros.

**Dependências:** bucket de dados (etapa 1) e `transform-fn` com o código colado e implantado (etapa 3).

**Caminho:** Console → **Amazon Data Firehose** → **Criar fluxo do Firehose**.

### 4.1 Origem, destino e nome

| Campo | Valor |
|---|---|
| Origem | **Direct PUT** |
| Destino | **Amazon S3** |
| Nome do fluxo do Firehose | `integracao-lab04-fh` |

### 4.2 Transformar registros

Seção **Transformar e converter registros**:

| Campo | Valor |
|---|---|
| **Ativar transformação de dados** | **Marcado** |
| Função do AWS Lambda | **Procurar** → `integracao-lab04-transform-fn` → **Escolher** |
| Versão da função | `$LATEST` |
| Dicas de buffer do Lambda → Tamanho do buffer | `1` MiB |
| Dicas de buffer do Lambda → Intervalo do buffer | `60` segundos |
| Ativar conversão de formato de registro | **Desmarcado** (a saída é JSON + GZIP; Parquet exigiria um esquema no Glue) |

### 4.3 Destino S3

Seção **Configurações de destino**:

| Campo | Valor |
|---|---|
| Bucket do S3 | **Procurar** → `integracao-lab04-dados-<ACCOUNT_ID>` |
| Delimitador de nova linha | **Desativado** (a transformadora já termina cada registro com quebra de linha) |
| Particionamento dinâmico | **Desativado** |
| **Prefixo do bucket do S3** | `vendas/!{timestamp:yyyy/MM/dd}/` |
| **Prefixo de saída de erro do bucket do S3** | `erros/!{firehose:error-output-type}/!{timestamp:yyyy/MM/dd}/` |
| Fuso horário do prefixo de bucket do S3 | **UTC** |

> **Atenção ao prefixo de erro.** Quando o prefixo usa uma expressão (`!{timestamp:...}`), o Firehose **exige** que o prefixo de erro tenha `!{firehose:error-output-type}`. Sem isso, a criação é recusada. Para erros de transformação, essa expressão vira `processing-failed`.

### 4.4 Buffer, compressão e criptografia

Seção **Dicas de buffer, compressão, extensão de arquivo e criptografia**:

| Campo | Valor |
|---|---|
| **Tamanho do buffer** | `1` MiB |
| **Intervalo do buffer** | `60` segundos |
| Compressão de dados | **GZIP** |
| Extensão de arquivo | vazio (padrão: `.gz`) |
| Criptografia dos registros | **Desativada** (o bucket já tem SSE-S3) |

> O Firehose grava um arquivo quando o buffer atinge **o tamanho OU o tempo**, o que vier primeiro. No volume do lab (até 500 vendas ≈ 100 KB), quem dispara é sempre o **tempo**: por isso a entrega acontece cerca de 1 minuto depois do envio.

### 4.5 Configurações avançadas e criação

Seção **Configurações avançadas**:

| Campo | Valor |
|---|---|
| Criptografia do lado do servidor | Desativada |
| **Registro de erros no Amazon CloudWatch** | **Ativado** (grupo `/aws/kinesisfirehose/integracao-lab04-fh`) |
| Permissões | **Criar ou atualizar a função do IAM** `KinesisFirehoseServiceRole-...` |
| Tags | `projeto` = `integracao-lab04` |

→ **Criar fluxo do Firehose**.

**O que acontece:** o fluxo fica **Criando** por cerca de 1 minuto e depois **Ativo**. O Console cria a role de serviço com permissão para gravar no bucket, invocar a `transform-fn` e gravar logs de erro. Confira em **Configuração** → **Permissões** → nome da role → IAM. As permissões devem equivaler a `iam/policy-firehose-role.json`.

> Se preferir criar a role à mão: IAM → **Funções** → **Criar função** → **Política de confiança personalizada** → cole `iam/trust-firehose-role.json` → adicione a política em linha `iam/policy-firehose-role.json` (nos dois, troque `<ACCOUNT_ID>` pelo ID da sua conta). No passo 4.5, escolha **Escolher uma função existente**.

### 4.6 Conferência rápida (dados de demonstração)

1. No fluxo → **Testar com dados de demonstração** → **Iniciar o envio de dados de demonstração**. Aguarde ~20 s → **Parar o envio de dados de demonstração**.
2. Aguarde ~2 minutos e abra o bucket `integracao-lab04-dados-<ACCOUNT_ID>`.

Esperado: pasta `erros/processing-failed/AAAA/MM/DD/` com arquivos `.gz`. Os dados de demonstração (cotações de ações) **não têm** `amount`, então a transformadora marca todos como `ProcessingFailed`. Isso prova, ao mesmo tempo, que o Firehose chama a transformadora e que o prefixo de erro funciona. Depois, apague essa pasta (**Excluir**) para não confundir a Parte B.

### 4.7 Erros comuns

| Sintoma | Causa | Correção |
|---|---|---|
| Criação recusada citando `ErrorOutputPrefix` | Prefixo de erro sem `!{firehose:error-output-type}` | Passo 4.3 |
| Nada aparece no S3 | Ainda dentro do intervalo do buffer | Aguardar 1 a 2 minutos |
| Tudo vai para `erros/` com `Lambda.FunctionError` | A transformadora falhou inteira (manipulador errado, tempo limite) | Log da `transform-fn`; etapas 3.4 e 3.5 |
| Tudo vai para `erros/` com `Lambda.InvokeAccessDenied` | Role do Firehose sem `lambda:InvokeFunction` | Passo 4.5 (role) |
| `AccessDenied` ao gravar no S3 (log do Firehose) | Role sem permissão no bucket de dados | Passo 4.5 (role) |

![Detalhes do fluxo do Firehose: status Ativo e origem Direct PUT.](imagens/imagem%20%2818%29.png)

*Figura 4 — Detalhes do fluxo do Firehose: status Ativo e origem Direct PUT.*

---

## Etapa 5 — API Gateway (HTTP API, CORS e throttling)

**Objetivo:** expor as rotas HTTPS que o dashboard usa.

**Dependências:** `producer-fn` e `read-fn` com código e variáveis (etapa 3).

**Caminho:** Console → **API Gateway** → **APIs** → **Criar API** → em **API HTTP** clique em **Compilar**.

### 5.1 Criar a API, as integrações e as rotas

**Passo 1 — Criar e configurar integrações:**

| Campo | Valor |
|---|---|
| Integrações → **Adicionar integração** | **Lambda** · Região `us-east-1` · Função `integracao-lab04-producer-fn` · Versão **2.0** |
| Integrações → **Adicionar integração** | **Lambda** · Região `us-east-1` · Função `integracao-lab04-read-fn` · Versão **2.0** |
| Nome da API | `integracao-lab04-api` |

→ **Avançar**.

**Passo 2 — Configurar rotas:** clique em **Adicionar rota** até ter as 5 linhas.

| Método | Caminho do recurso | Destino da integração |
|---|---|---|
| `POST` | `/runs` | `integracao-lab04-producer-fn` |
| `GET` | `/runs` | `integracao-lab04-read-fn` |
| `GET` | `/runs/{id}` | `integracao-lab04-read-fn` |
| `GET` | `/runs/{id}/events` | `integracao-lab04-read-fn` |
| `GET` | `/metrics` | `integracao-lab04-read-fn` |

> Escreva `{id}` exatamente assim. A `read-fn` lê o parâmetro com esse nome.

→ **Avançar**.

**Passo 3 — Definir estágios:**

| Campo | Valor |
|---|---|
| Nome do estágio | `$default` |
| Implantação automática | **Ativada** |

→ **Avançar** → **Criar**.

**O que acontece:** o API Gateway cria a API e **adiciona sozinho** a permissão para invocar as Lambdas. Na página da API, copie o **URL de invocação**, por exemplo `https://abc123defg.execute-api.us-east-1.amazonaws.com`. Esse é o `<API_URL>` (sem barra no final). Com o estágio `$default` não há nome de estágio na URL.

### 5.2 CORS

**Caminho:** na API → menu lateral **CORS** → **Configurar**.

| Campo | Valor |
|---|---|
| Access-Control-Allow-Origin | `https://lab04.<DOMINIO_RAIZ>` → **Adicionar** (sem barra final e sem `*`) |
| Access-Control-Allow-Headers | `content-type` → **Adicionar** |
| Access-Control-Allow-Methods | `GET`, `POST`, `OPTIONS` |
| Access-Control-Expose-Headers | vazio |
| Access-Control-Max-Age | `300` |
| Access-Control-Allow-Credentials | **Não** |

→ **Salvar**.

**O que acontece:** o API Gateway passa a responder sozinho ao `OPTIONS` (*preflight*) e acrescenta os cabeçalhos CORS. Sem `content-type` nessa lista, o navegador bloqueia o `POST` do dashboard.

### 5.3 Limites de uso (throttling)

**Caminho:** na API → menu lateral **Limitação** (ou **Estágios → `$default`**) → **Editar** nos limites padrão.

| Campo | Valor |
|---|---|
| Limite de taxa padrão | `5` requisições/s |
| Limite de intermitência padrão | `10` |
| Rota `POST /runs` → limite da rota | taxa `1`, intermitência `3` |

→ **Salvar**. Isso evita disparos em massa (cada disparo gera uso real de serviços).

> **A API não exige chave nem login.** O throttling e a faixa de quantidade validada na Lambda são os únicos limites. Não divulgue o endereço da API e exclua tudo ao terminar (Parte C).

### 5.4 Conferência rápida

Abra no navegador `<API_URL>/metrics`. Esperado: um JSON com `totalRuns` (pode ser `0`) e os campos das métricas. Isso prova que a rota chega à `read-fn`.

### 5.5 Respostas e quem as produz

| Resposta | Quem produz | Significado | O que verificar |
|---|---|---|---|
| **400** `quantidade deve estar entre 10 e 500` | Lambda | Entrada fora da faixa | Quantidade 10–500 e percentual 0–50 |
| **404** `{"message":"Not Found"}` | API Gateway | Rota inexistente | Caminho e método das rotas (5.1) |
| **429** `Too Many Requests` | API Gateway | Acima do throttling | Aguardar alguns segundos |
| **500/502** `Internal Server Error` | Lambda ou integração | Erro de código ou de permissão | Logs da função (CloudWatch) |
| **Erro de CORS** no console do navegador | Navegador | Origem, cabeçalho ou método fora da lista | Etapa 5.2; aba **Rede** do DevTools → requisição `OPTIONS` |

![Integrações da HTTP API anexadas às rotas.](imagens/imagem%20%2825%29.png)

*Figura 5 — Integrações da HTTP API anexadas às rotas.*

---

## Etapa 6 — S3, ACM, CloudFront e Route 53

**Objetivo:** hospedar o dashboard estático em um bucket **privado**, servido por HTTPS pelo CloudFront com **OAC** e pelo domínio `lab04.<DOMINIO_RAIZ>`.

**Dependências:** zona hospedada `<DOMINIO_RAIZ>` no Route 53 desta conta (pode ser a mesma de outros labs; este lab cria **só o seu** registro e o **seu** certificado).

### 6.1 Bucket S3 privado

**Caminho:** **S3** → **Buckets** → **Criar bucket**.

| Campo | Valor |
|---|---|
| Tipo de bucket | **Uso geral** |
| Nome do bucket | `integracao-lab04-dashboard-<ACCOUNT_ID>` |
| Região | `us-east-1` |
| Propriedade de objetos | **ACLs desabilitadas (recomendado)** |
| **Bloquear todo o acesso público** | **Marcado** (as 4 opções) |
| Versionamento | Desabilitado |
| Criptografia padrão | **SSE-S3** · Chave do bucket **Habilitada** |
| Tags | `projeto` = `integracao-lab04` |

→ **Criar bucket**. **Não** ative a hospedagem de site estático do S3.

### 6.2 Certificado ACM (sempre em us-east-1)

1. Confira que a região do Console é **us-east-1**. O CloudFront só aceita certificados criados nessa região.
2. **AWS Certificate Manager** → **Solicitar** → **Solicitar um certificado público** → **Avançar**.

| Campo | Valor |
|---|---|
| Nome de domínio totalmente qualificado | `lab04.<DOMINIO_RAIZ>` |
| Método de validação | **Validação de DNS** |
| Algoritmo de chave | RSA 2048 |

3. **Solicitar** → abra o certificado → **Criar registros no Route 53** → **Criar registros**.
4. Aguarde o status **Emitido** (normalmente poucos minutos).

### 6.3 Distribuição CloudFront

**Caminho:** **CloudFront** → **Distribuições** → **Criar distribuição**.

O assistente muda com frequência. Se aparecer escolha de **plano de preço**, escolha o de menor custo que aceite **domínio personalizado e certificado ACM**.

| Passo do assistente | Campo | Valor |
|---|---|---|
| Começar | Nome da distribuição | `integracao-lab04-dashboard` |
| | Tipo | **Site ou aplicativo único** |
| | Domínio personalizado | `lab04.<DOMINIO_RAIZ>` |
| Especificar origem | Tipo de origem | **Amazon S3** |
| | Origem do S3 | `integracao-lab04-dashboard-<ACCOUNT_ID>` (endpoint REST, **não** o de site) |
| | **Permitir acesso privado do S3 ao CloudFront** | **Marcado** (cria o OAC) |
| | Configurações de origem e cache | **Recomendadas** |
| Habilitar segurança | AWS WAF | **Não habilitar** (custo extra) |
| Obter certificado TLS | Certificado | o de `lab04.<DOMINIO_RAIZ>` (etapa 6.2) |
| Revisar | **Criar distribuição** | — |

**Ajustes a conferir depois de criar** (distribuição → **Geral** → **Configurações** → **Editar**):

| Campo | Valor |
|---|---|
| Nomes de domínio alternativos (CNAMEs) | `lab04.<DOMINIO_RAIZ>` |
| Certificado SSL personalizado | o certificado da etapa 6.2 |
| Política de segurança | `TLSv1.2_2021` ou superior |
| **Objeto raiz padrão** | **`index.html`** |
| Classe de preço | Usar somente América do Norte e Europa |

Aba **Comportamentos** → **Padrão** → **Editar**:

| Campo | Valor |
|---|---|
| Política de protocolo do visualizador | **Redirecionar HTTP para HTTPS** |
| Métodos HTTP permitidos | **GET, HEAD** |
| Política de cache | **CachingOptimized** |
| Compactar objetos automaticamente | Sim |

Copie o **ID da distribuição**: é o `<DISTRIBUTION_ID>`.

### 6.4 Política do bucket (OAC)

Se o assistente mostrar **Copiar política**, use-a. Se não, abra `iam/bucket-policy-dashboard.json` no repositório e troque `<ACCOUNT_ID>` e `<DISTRIBUTION_ID>`, **sem salvar essa alteração no repositório**.

S3 → `integracao-lab04-dashboard-<ACCOUNT_ID>` → **Permissões** → **Política do bucket** → **Editar** → cole → **Salvar alterações**.

**O que acontece:** só esta distribuição consegue ler os arquivos. O acesso direto ao bucket continua negado.

### 6.5 Route 53

**Route 53** → **Zonas hospedadas** → `<DOMINIO_RAIZ>` → **Criar registro**.

| Campo | Valor |
|---|---|
| Nome do registro | `lab04` |
| Tipo de registro | **A** |
| Alias | **Ativado** |
| Rotear tráfego para | **Alias para a distribuição do CloudFront** → escolha a distribuição (`dxxxx.cloudfront.net`) |
| Política de roteamento | Simples |

→ **Criar registros**. Se o assistente do CloudFront já criou esse registro, só confira.

### 6.6 Erros comuns

| Sintoma | Causa | Correção |
|---|---|---|
| Certificado não aparece no CloudFront | Certificado fora de us-east-1 ou ainda pendente | Etapa 6.2 |
| `AccessDenied` em XML | Política do bucket ausente ou com ID errado | Etapa 6.4 |
| 403 ao abrir `/` | Sem objeto raiz | `index.html` em 6.3 |
| `ERR_NAME_NOT_RESOLVED` | Registro DNS ausente ou ainda propagando | Etapa 6.5; aguardar alguns minutos |

![Distribuição do CloudFront que serve o dashboard.](imagens/imagem%20%2816%29.png)

*Figura 6 — Distribuição do CloudFront que serve o dashboard.*

---

## Etapa 7 — Publicar o dashboard

**Objetivo:** apontar o dashboard para a sua API e publicar os quatro arquivos.

**Dependências:** etapas 5 e 6.

### 7.1 Preencher `frontend/config.js`

No seu computador, edite `frontend/config.js`:

```javascript
API_BASE_URL: "https://abc123defg.execute-api.us-east-1.amazonaws.com",
MODO_DEMONSTRACAO: false,
```

Este arquivo é público: não coloque nele segredos nem credenciais.

### 7.2 Enviar os arquivos

1. S3 → `integracao-lab04-dashboard-<ACCOUNT_ID>` → **Carregar** → **Adicionar arquivos** → `index.html`, `app.js`, `config.js`, `styles.css` (na **raiz** do bucket, sem pastas) → **Carregar**.
2. CloudFront → distribuição → aba **Invalidações** → **Criar invalidação** → `/*` → **Criar**. Aguarde **Concluído**.

Repita estes dois passos sempre que alterar um arquivo de `frontend/`. Sem a invalidação, o CloudFront pode servir a versão antiga por até 24 horas.

### 7.3 Conferência

Abra `https://lab04.<DOMINIO_RAIZ>/` e recarregue sem cache (**Ctrl+F5**).

| Verificação | Esperado |
|---|---|
| Banner "MODO DEMONSTRAÇÃO" | **Não** aparece |
| Painel **Enviar vendas** | Campos de quantidade e de % de inválidos |
| Botão **Enviar** | Habilitado (não há login) |

Os testes começam na Parte B.

![Objetos do dashboard no bucket S3 privado.](imagens/imagem%20%2832%29.png)

*Figura 7 — Objetos do dashboard no bucket S3 privado.*

---

# PARTE B — VALIDAÇÃO FINAL

> **Só comece quando a Parte A estiver concluída.**
> Um teste só vira **Aprovado** com **evidência registrada** (captura de tela, item do DynamoDB, trecho de log). Sem evidência, ele fica **Não executado** ou **Reprovado**.

### Pré-condições

- [ ] Dashboard abre em `https://lab04.<DOMINIO_RAIZ>/` sem o banner de demonstração.
- [ ] Fluxo `integracao-lab04-fh` **Ativo** e a pasta de demonstração (etapa 4.6) apagada.
- [ ] Abas abertas: S3 → `integracao-lab04-dados-<ACCOUNT_ID>`; CloudWatch → **Grupos de logs**.

### Como abrir um arquivo `.gz` do Firehose

1. S3 → `integracao-lab04-dados-<ACCOUNT_ID>` → abra a pasta → selecione o arquivo → **Baixar**.
2. No PowerShell (troque o nome do arquivo):

```powershell
$arquivo = "$env:USERPROFILE\Downloads\NOME-DO-ARQUIVO.gz"
$entrada = [IO.File]::OpenRead($arquivo)
$gz = New-Object IO.Compression.GZipStream($entrada, [IO.Compression.CompressionMode]::Decompress)
(New-Object IO.StreamReader($gz)).ReadToEnd() -split "`n" | Select-Object -First 3
$entrada.Close()
```

---

## V1 — API responde sem autenticação

No PowerShell:

```powershell
(Invoke-RestMethod -Uri "<API_URL>/metrics").totalRuns
```

Esperado: um número (pode ser `0`), sem pedir chave nem login. Evidência: saída do comando.

## V2 — Entrada inválida é recusada

```powershell
try { Invoke-WebRequest -Uri "<API_URL>/runs" -Method Post -Body '{"quantidade":5}' -ContentType "application/json" -UseBasicParsing } catch { $_.Exception.Response.StatusCode.value__ }
```

Esperado: `400`, e nenhuma execução nova na lista do dashboard. Evidência: saída do comando.

## V3 — Dashboard carrega direto

| Item | Detalhe |
|---|---|
| Ação | Abra `https://lab04.<DOMINIO_RAIZ>/` |
| Esperado | Sem tela de login; métricas e lista carregam sozinhas; botão **Enviar** habilitado |
| Evidência | Captura da página |

![Dashboard publicado, com o formulário para enviar vendas.](imagens/imagem%20%282%29.png)

*Figura 8 — Dashboard publicado, com o formulário para enviar vendas.*

## V4 — Aceito não é entregue (buffer)

| Item | Detalhe |
|---|---|
| Ação | Quantidade `100`, inválidos `10` → **Enviar**. Anote o `correlationId` e a hora |
| Esperado na hora | "Aceitos pela API: 100 (inválidos gerados: 10)"; no detalhe, **Entregues 0**, **Com erro 0** e "Aguardando o buffer do Firehose" |
| Esperado em ~1 a 2 min | **Entregues 90**, **Com erro 10**, "Todos os registros aceitos já estão no S3"; **Atraso até o 1º arquivo** perto de 60 s |
| S3 | Um arquivo novo em `vendas/AAAA/MM/DD/` e um em `erros/processing-failed/AAAA/MM/DD/` |
| Evidência | Duas capturas do detalhe (antes e depois) e a listagem do S3 |

![Dashboard logo após o envio: aceitos pela API e execução criada.](imagens/imagem%20%284%29.png)

*Figura 9 — Dashboard logo após o envio: aceitos pela API e execução criada.*

## V5 — Conteúdo transformado

| Item | Detalhe |
|---|---|
| Ação | Baixe o arquivo novo de `vendas/` e abra com o comando acima |
| Esperado | Cada linha é uma venda com os campos originais **mais** `currency: "BRL"`, `enriched: true`, `year`, `month`, `day`; `amount` numérico |
| Evidência | As três primeiras linhas |

![Arquivo de dados gravado pelo Firehose, com as vendas transformadas (ano, mês e dia).](imagens/imagem%20%2812%29.png)

*Figura 10 — Arquivo de dados gravado pelo Firehose, com as vendas transformadas (ano, mês e dia).*

## V6 — Registro com erro rastreável

| Item | Detalhe |
|---|---|
| Ação | Baixe o arquivo novo de `erros/processing-failed/` e abra |
| Esperado | Cada linha é um JSON do Firehose com `errorCode` = `Lambda.ProcessingFailed`, `attemptsMade` e `rawData` |
| Decodificar o original | Copie um `rawData` e execute: `[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("COLE-AQUI"))` → aparece a venda original com `"amount": "INVALIDO"` e o mesmo `correlationId` |
| Evidência | A linha de erro e o original decodificado |

![Arquivo de erros: o Firehose guarda o registro original (rawData) e o código do erro.](imagens/imagem%20%289%29.png)

*Figura 11 — Arquivo de erros: o Firehose guarda o registro original (rawData) e o código do erro.*

## V7 — O intervalo do buffer define o atraso

| Item | Detalhe |
|---|---|
| Ação | Firehose → `integracao-lab04-fh` → **Configuração** → **Dicas de buffer** → **Editar** → **Intervalo** `120` s → **Salvar**. Aguarde o fluxo voltar a **Ativo**. Envie `50` vendas com `0` inválidos |
| Esperado | **Atraso até o 1º arquivo** perto de 120 s (o dobro do V4) |
| Depois | Volte o intervalo para `60` s |
| Evidência | Os dois atrasos (V4 e V7) |

## V8 — Prefixos por data (UTC)

| Item | Detalhe |
|---|---|
| Ação | Navegue no bucket de dados |
| Esperado | `vendas/AAAA/MM/DD/` e `erros/processing-failed/AAAA/MM/DD/` com a data em **UTC**. Envios feitos depois das 21h no horário de Brasília caem na pasta do dia seguinte |
| Evidência | Captura da árvore de pastas |

![Pasta erros/processing-failed/ no bucket, organizada por data (UTC).](imagens/imagem%20%288%29.png)

*Figura 12 — Pasta erros/processing-failed/ no bucket, organizada por data (UTC).*

## V9 — Métricas do CloudWatch × dashboard

1. Aguarde ~5 minutos depois dos envios.
2. Compare os cartões do dashboard com CloudWatch → **Métricas** → **Firehose** → **DeliveryStreamName** → `integracao-lab04-fh`: `IncomingRecords`, `DeliveryToS3.Records` (soma, 1 h) e `DeliveryToS3.DataFreshness` (máximo).
3. Confira também `ExecuteProcessing.Success` e `SucceedProcessing.Records` (transformação).

Esperado: `IncomingRecords` igual à soma dos aceitos; `DeliveryToS3.Records` igual à soma dos entregues (os registros com erro não entram). Sem dado, o dashboard mostra "—".

## V10 — Recarregar e nova aba

| Ação | Esperado |
|---|---|
| **F5** na mesma aba | A lista e as métricas voltam do backend (nada fica guardado no navegador) |
| Abrir o dashboard em **nova aba** ou outro navegador | Mostra os mesmos dados, sem pedir nada |

## V11 — Throttling (opcional)

```powershell
1..6 | ForEach-Object { try { (Invoke-WebRequest -Uri "<API_URL>/runs" -Method Post -Body '{"quantidade":10,"percentualInvalidos":0}' -ContentType "application/json" -UseBasicParsing).StatusCode } catch { $_.Exception.Response.StatusCode.value__ } }
```

Esperado: alguns `202` e pelo menos um `429`. Cada `202` gera uso real (custo baixo, mas existe).

## V12 — Custos

1. **Gerenciamento de custos e faturamento** → **Cost Explorer** (dados com até 24 h de atraso) e **Orçamentos**.
2. Confira que não ficou envio em loop; o Firehose cobra por volume, não por hora parado.

## V13 — Limpeza (só quando terminar o projeto)

Execute a **Parte C → Limpeza**. Evidência: nenhum recurso `integracao-lab04` restante.

---

## Tabela-resumo da validação

| Teste | Descrição | Status | Evidência |
|---|---|---|---|
| V1 | API responde sem autenticação | Não executado | — |
| V2 | Entrada inválida → 400 | Não executado | — |
| V3 | Dashboard carrega direto | Não executado | — |
| V4 | Aceito não é entregue (buffer) | Não executado | — |
| V5 | Conteúdo transformado | Não executado | — |
| V6 | Registro com erro rastreável | Não executado | — |
| V7 | Intervalo do buffer define o atraso | Não executado | — |
| V8 | Prefixos por data (UTC) | Não executado | — |
| V9 | Métricas CloudWatch × dashboard | Não executado | — |
| V10 | Recarregar e nova aba | Não executado | — |
| V11 | Throttling (opcional) | Não executado | — |
| V12 | Custos | Não executado | — |
| V13 | Limpeza | Não executado | — |

---

# PARTE C — TROUBLESHOOTING, CUSTOS E LIMPEZA

## Troubleshooting consolidado

| Sintoma | Causa provável | Correção |
|---|---|---|
| Banner "MODO DEMONSTRAÇÃO" aparece | `API_BASE_URL` vazio ou com `<`, ou `config.js` antigo em cache | Publicar o `config.js` e invalidar o CloudFront |
| "Erro ao consultar a API: Failed to fetch" | CORS (origem errada) ou CSP com outra região | CORS da API; `connect-src` do `index.html` |
| Entregues fica em 0 por mais de 3 minutos | Firehose sem conseguir gravar (role) ou transformadora falhando inteira | Log `/aws/kinesisfirehose/integracao-lab04-fh`; etapa 4.7 |
| Tudo aparece em "Com erro" | `transform-fn` com manipulador errado ou tempo limite curto (`Lambda.FunctionError`) | Etapas 3.4 e 3.5 |
| Detalhe dá "erro interno" | `read-fn` sem `s3:GetObject`/`ListBucket` ou `DATA_BUCKET` errado | Etapas 3.3 e 3.6 |
| Entregues menor que o esperado | Arquivo fora da janela lida (mais de 40 arquivos novos) ou prefixos diferentes de `vendas/`/`erros/` | Conferir `DATA_PREFIX`/`ERROR_PREFIX` |
| `POST /runs` → 400 | Quantidade fora de 10–500 ou percentual fora de 0–50 | Ajustar no dashboard |

## Custos (premissas)

Volume baixo e uso pontual. **Confira os valores reais no Cost Explorer.**

| Serviço | Comportamento de custo | Controle |
|---|---|---|
| Amazon Data Firehose | Por GB ingerido (arredondado em blocos de 5 KB por registro) e por transformação | Volumes do lab (até 500 vendas por envio) |
| Lambda | Por invocação e duração; a transformadora roda uma vez por buffer | — |
| S3 | Armazenamento e requisições; a `read-fn` lê os arquivos novos a cada consulta do detalhe | O dashboard para de consultar quando a execução fica completa |
| DynamoDB | Sob demanda | — |
| CloudWatch | Logs (Lambdas e erros do Firehose) e `GetMetricData` | Retenção de 7 dias |
| API Gateway (HTTP API) | Por milhão de requisições | Throttling |
| CloudFront / S3 (dashboard) | Tráfego mínimo | — |
| Route 53 | Zona hospedada tem custo mensal fixo | Reaproveitar a zona existente |

## Limpeza (executar só ao final do projeto)

> **Ação destrutiva e irreversível.** Confirme que não precisa mais dos dados. Exclua nesta ordem:

1. Amazon Data Firehose → `integracao-lab04-fh` → **Excluir**. IAM → excluir a role `KinesisFirehoseServiceRole-...` criada para ele.
2. S3 → `integracao-lab04-dados-<ACCOUNT_ID>` → **Esvaziar** → **Excluir**.
3. API Gateway → `integracao-lab04-api` → **Excluir**.
4. Route 53 → `<DOMINIO_RAIZ>` → excluir o registro `lab04`.
5. CloudFront → distribuição → **Desabilitar** → aguarde a implantação → **Excluir**. Exclua também o **OAC** criado (CloudFront → **Controle de acesso à origem**).
6. ACM (us-east-1) → excluir o certificado de `lab04.<DOMINIO_RAIZ>`.
7. S3 → `integracao-lab04-dashboard-<ACCOUNT_ID>` → **Esvaziar** → **Excluir**.
8. Lambda → excluir as 3 funções. IAM → excluir as 3 roles `integracao-lab04-...-fn-role-...`.
9. DynamoDB → `integracao-lab04-runs` → **Excluir**.
10. CloudWatch → **Grupos de logs** → excluir `/aws/kinesisfirehose/integracao-lab04-fh`.
11. CloudWatch → **Grupos de logs** → excluir `/aws/lambda/integracao-lab04-*`.

**Checagem final:** em cada serviço, filtre por `integracao-lab04` e confirme que nada restou. Confira o Cost Explorer no dia seguinte.

---

> Registro de execução: anote os resultados reais **fora do repositório**. Não marque nada como concluído sem executar e sem evidência.
