import {
  condition,
  continueAsNew,
  defineQuery,
  defineUpdate,
  proxyActivities,
  setHandler,
} from "@temporalio/workflow";

import type {
  ConversationItem,
  ConversationWorkflowInput,
  ConversationWorkflowState,
  MockLlmResult,
  UserMessageAccepted,
  UserMessageInput,
} from "../contracts";
import {
  QUERY_CONVERSATION_ITEMS,
  QUERY_WORKFLOW_STATE,
  UPDATE_USER_INPUT,
} from "../contracts";
import type * as activities from "../activities/mock-llm";

const submitUserInput = defineUpdate<UserMessageAccepted, [UserMessageInput]>(UPDATE_USER_INPUT);
const queryConversationItems = defineQuery<ConversationItem[]>(QUERY_CONVERSATION_ITEMS);
const queryWorkflowState = defineQuery<ConversationWorkflowState>(QUERY_WORKFLOW_STATE);

const { mockLlmRespond } = proxyActivities<typeof activities>({
  startToCloseTimeout: "30 seconds",
});

type PendingTurn = {
  turnId: string;
  content: string;
};

function initialState(input: ConversationWorkflowInput): ConversationWorkflowState {
  if (input.carriedState) {
    return {
      ...input.carriedState,
      items: [...input.carriedState.items],
    };
  }

  return {
    items: [],
    nextTurnNumber: 1,
    totalUserTurns: 0,
    lastSeq: 0,
  };
}

function trimHistory(items: ConversationItem[], maxItems = 40): ConversationItem[] {
  if (items.length <= maxItems) {
    return items;
  }
  return items.slice(items.length - maxItems);
}

export async function conversationWorkflow(input: ConversationWorkflowInput): Promise<void> {
  const maxTurns = input.maxTurnsBeforeContinueAsNew ?? 6;
  const state = initialState(input);
  const pendingTurns: PendingTurn[] = [];

  const enqueueTurn = (content: string): UserMessageAccepted => {
    const turn_id = `turn-${state.nextTurnNumber}`;
    state.nextTurnNumber += 1;
    pendingTurns.push({ turnId: turn_id, content });
    return { turn_id };
  };

  if (input.initialUserMessage) {
    enqueueTurn(input.initialUserMessage);
  }

  setHandler(submitUserInput, async ({ content }: UserMessageInput) => {
    return enqueueTurn(content);
  });

  setHandler(queryConversationItems, () => state.items);
  setHandler(queryWorkflowState, () => state);

  while (true) {
    await condition(() => pendingTurns.length > 0);
    const nextTurn = pendingTurns.shift();
    if (!nextTurn) {
      continue;
    }

    state.totalUserTurns += 1;
    state.lastSeq += 1;
    state.items.push({
      type: "user_message",
      seq: state.lastSeq,
      content: nextTurn.content,
      turn_id: nextTurn.turnId,
    });

    const modelResult: MockLlmResult = await mockLlmRespond({
      systemPrompt: input.systemPrompt,
      userMessage: nextTurn.content,
      history: state.items,
    });

    state.lastSeq += 1;
    state.items.push({
      type: "assistant_message",
      seq: state.lastSeq,
      content: modelResult.response,
      turn_id: nextTurn.turnId,
      metadata: {
        complexity: modelResult.complexity,
        tier: modelResult.tier,
        route_reason: modelResult.route_reason,
      },
    });

    if (state.totalUserTurns >= maxTurns) {
      return continueAsNew<typeof conversationWorkflow>({
        conversationId: input.conversationId,
        systemPrompt: input.systemPrompt,
        maxTurnsBeforeContinueAsNew: maxTurns,
        carriedState: {
          items: trimHistory(state.items),
          nextTurnNumber: state.nextTurnNumber,
          totalUserTurns: 0,
          lastSeq: state.lastSeq,
        },
      });
    }
  }
}
