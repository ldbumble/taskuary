// The AI shelf on Connections, in its order. One list, so Setup's "What AI do you have?" cannot lose a card Connections shows:
// it kept its own copy, and Google Vertex AI and Meta reached the shelf only (2026-10-15).
// The nine after typesafe speak the OpenAI surface (llm.OPENAI_COMPATIBLE); groq, cerebras, gemini and mistral need no payment method.
export const AI_SHELF = ["hipaa_ai", "anthropic", "openai", "chatgpt", "azure_openai", "vertex_ai", "openrouter", "meta", "ollama", "typesafe",
  "groq", "cerebras", "gemini", "deepseek", "mistral", "together", "xai", "cohere", "perplexity"];
// Setup's: the shelf less the two that cannot sort mail - a decision model, and a ChatGPT sign-in that needs its own window
export const SETUP_AI = AI_SHELF.filter((t) => !["chatgpt", "typesafe"].includes(t));
// The organisation's AI card (HIPAA AI) cannot connect without its gateway's address unless this build ships one (the server's
// GatewayBuiltIn): the address came with the access code, and a card that asked only for the code could never connect (2026-10-20)
export const needsGateway = (conn, cfg) => conn?.Type === "hipaa_ai" && !conn.GatewayBuiltIn && !String(cfg?.base_url || "").trim();
// WHAT EACH KEY CARD IS, in one line under its state on Setup's shelf: HIPAA AI, Anthropic API, OpenAI API, Azure OpenAI… all said
// only "Not set up", while the coding-tool cards beside them explained themselves (the setup sweep, 2026-10-28)
export const AI_WHY = {
  hipaa_ai: "your organisation's AI, from an access code", anthropic: "pay-as-you-go key from console.anthropic.com",
  openai: "pay-as-you-go key from platform.openai.com", azure_openai: "your company's Azure deployment - endpoint and key",
  vertex_ai: "Gemini through Google Cloud - project and key", openrouter: "one key for many models, from openrouter.ai",
  meta: "Meta's models, key from dev.meta.ai", ollama: "free models on this computer - no key needed",
  groq: "fast open models, free key from console.groq.com", cerebras: "fast open models, free key from cloud.cerebras.ai",
  gemini: "Google's Gemini, free key from aistudio.google.com", deepseek: "low-cost key from platform.deepseek.com",
  mistral: "European models, key from console.mistral.ai", together: "open models, key from api.together.xyz",
  xai: "Grok, key from console.x.ai", cohere: "Cohere's models, key from dashboard.cohere.com",
  perplexity: "answers with web search, key from perplexity.ai",
};
