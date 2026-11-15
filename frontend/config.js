/*
 * Configuracao do dashboard do LAB-04.
 *
 * Este arquivo e PUBLICO (servido pelo CloudFront). Nao coloque aqui segredos nem credenciais.
 *
 * Substitua <API_URL> pela URL da HTTP API, sem barra no final, antes de enviar ao S3.
 * Valores que ainda contenham "<" sao tratados como nao configurados (modo demonstracao).
 */
window.LAB04_CONFIG = {
  // Ex.: https://abc123defg.execute-api.us-east-1.amazonaws.com
  API_BASE_URL: "https://s0zecnwxoi.execute-api.us-east-1.amazonaws.com",

  // true = forca o modo demonstracao (dados sinteticos rotulados, sem chamar a API).
  MODO_DEMONSTRACAO: false,

  // Intervalo de atualizacao automatica (ms).
  REFRESH_INTERVAL_MS: 8000
};