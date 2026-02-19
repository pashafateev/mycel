import type { MockLlmRequest, MockLlmResult, RoutingTier } from "../contracts";

const COMPLEX_KEYWORDS = [
  "architecture",
  "tradeoff",
  "debug",
  "incident",
  "strategy",
  "refactor",
  "multi-step",
  "workflow",
  "temporal",
  "production",
];

function classifyComplexity(text: string): "simple" | "complex" {
  const normalized = text.toLowerCase();
  return COMPLEX_KEYWORDS.some((keyword) => normalized.includes(keyword)) ? "complex" : "simple";
}

function pickTier(message: string, complexity: "simple" | "complex"): RoutingTier {
  if (complexity === "complex") {
    return "senior";
  }

  const tokenCount = message.trim().split(/\s+/).filter(Boolean).length;
  if (tokenCount <= 8) {
    return "intern";
  }
  return "junior";
}

export async function mockLlmRespond(input: MockLlmRequest): Promise<MockLlmResult> {
  const complexity = classifyComplexity(input.userMessage);
  const tier = pickTier(input.userMessage, complexity);
  const route_reason =
    complexity === "complex"
      ? "Complexity keywords detected; route to senior tier."
      : tier === "intern"
        ? "Short/simple request; intern tier is sufficient."
        : "Simple but non-trivial request; route to junior tier.";

  const response =
    `[mock:${tier}/${complexity}] ` +
    `You said: "${input.userMessage}". ` +
    `History turns stored: ${input.history.length}. ` +
    `System prompt chars: ${input.systemPrompt.length}.`;

  return {
    complexity,
    tier,
    route_reason,
    response,
  };
}

