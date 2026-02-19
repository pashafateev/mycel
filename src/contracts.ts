export const CONVERSATION_WORKFLOW_TYPE = "conversationWorkflow";
export const UPDATE_USER_INPUT = "user_input";
export const QUERY_CONVERSATION_ITEMS = "get_conversation_items";
export const QUERY_WORKFLOW_STATE = "get_workflow_state";

export type Complexity = "simple" | "complex";
export type RoutingTier = "intern" | "junior" | "senior";

export type ConversationItem = {
  type: "user_message" | "assistant_message";
  seq: number;
  content: string;
  turn_id: string;
  metadata?: {
    complexity: Complexity;
    tier: RoutingTier;
    route_reason: string;
  };
};

export type UserMessageInput = {
  content: string;
};

export type UserMessageAccepted = {
  turn_id: string;
};

export type MockLlmRequest = {
  systemPrompt: string;
  userMessage: string;
  history: ConversationItem[];
};

export type MockLlmResult = {
  complexity: Complexity;
  tier: RoutingTier;
  route_reason: string;
  response: string;
};

export type ConversationWorkflowState = {
  items: ConversationItem[];
  nextTurnNumber: number;
  totalUserTurns: number;
  lastSeq: number;
};

export type ConversationWorkflowInput = {
  conversationId: string;
  systemPrompt: string;
  initialUserMessage?: string;
  maxTurnsBeforeContinueAsNew?: number;
  carriedState?: ConversationWorkflowState;
};

