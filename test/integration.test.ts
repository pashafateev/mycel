import assert from "node:assert/strict";
import test from "node:test";

import { Worker } from "@temporalio/worker";
import { TestWorkflowEnvironment } from "@temporalio/testing";

import * as activities from "../src/activities/mock-llm";
import type {
  ConversationItem,
  ConversationWorkflowInput,
  UserMessageAccepted,
  UserMessageInput,
} from "../src/contracts";
import { QUERY_CONVERSATION_ITEMS, UPDATE_USER_INPUT } from "../src/contracts";
import * as bridge from "../src/index";
import { conversationWorkflow } from "../src/workflows/conversation";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForAssistantItem(
  handle: { query(name: string): Promise<unknown> },
  turnId?: string,
): Promise<ConversationItem> {
  for (let i = 0; i < 30; i += 1) {
    const items = (await handle.query(QUERY_CONVERSATION_ITEMS)) as ConversationItem[];
    const found = items.find(
      (item) =>
        item.type === "assistant_message" &&
        (turnId ? item.turn_id === turnId : true),
    );
    if (found) {
      return found;
    }
    await sleep(50);
  }
  throw new Error("assistant reply was not produced in time");
}

test("bridge/workflow/activity contracts are importable and consistent", () => {
  const input: ConversationWorkflowInput = {
    conversationId: "conv-1",
    systemPrompt: "system",
    initialUserMessage: "hello",
  };
  const update: UserMessageInput = { content: "ping" };
  const accepted: UserMessageAccepted = { turn_id: "turn-1" };

  assert.equal(typeof conversationWorkflow, "function");
  assert.equal(typeof activities.mockLlmRespond, "function");
  assert.equal(bridge.workflowIdForSession("abc"), "openclaw-abc");
  assert.equal(input.initialUserMessage, "hello");
  assert.equal(update.content, "ping");
  assert.equal(accepted.turn_id, "turn-1");
});

test("workflow runs in Temporal test environment with mock activities", async () => {
  const env = await TestWorkflowEnvironment.createTimeSkipping();

  try {
    const taskQueue = `bridge-int-${Date.now()}`;
    const worker = await Worker.create({
      connection: env.nativeConnection,
      taskQueue,
      workflowsPath: require.resolve("../src/workflows/conversation"),
      activities,
    });

    await worker.runUntil(async () => {
      const handle = await env.client.workflow.start(conversationWorkflow, {
        taskQueue,
        workflowId: `wf-${Date.now()}`,
        args: [
          {
            conversationId: "conv-test",
            systemPrompt: "system prompt",
            initialUserMessage: "hello there",
          },
        ],
      });

      const firstReply = await waitForAssistantItem(handle);
      assert.match(firstReply.content, /^\[mock:/);

      const accepted = (await handle.executeUpdate(UPDATE_USER_INPUT, {
        args: [{ content: "architecture tradeoff options" }],
      })) as UserMessageAccepted;
      assert.match(accepted.turn_id, /^turn-/);

      const secondReply = await waitForAssistantItem(handle, accepted.turn_id);
      assert.equal(secondReply.type, "assistant_message");
      assert.equal(secondReply.metadata?.complexity, "complex");
      assert.equal(secondReply.metadata?.tier, "senior");

      await handle.terminate("integration test complete");
    });
  } finally {
    await env.teardown();
  }
});
