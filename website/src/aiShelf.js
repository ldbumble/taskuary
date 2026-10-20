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
