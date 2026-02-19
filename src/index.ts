import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import express from "express";
import {
  Client,
  Connection,
  ConnectionOptions,
  WorkflowHandle,
} from "@temporalio/client";

import {
  CONVERSATION_WORKFLOW_TYPE,
  QUERY_CONVERSATION_ITEMS,
  type ConversationItem,
  type ConversationWorkflowInput,
  type UserMessageAccepted,
  UPDATE_USER_INPUT,
} from "./contracts";

const TEMPORAL_HOST = process.env.TEMPORAL_HOST ?? "localhost:7233";
const TEMPORAL_NAMESPACE = process.env.TEMPORAL_NAMESPACE ?? "default";
const TASK_QUEUE = process.env.TEMPORAL_TASK_QUEUE ?? "mycel-bridge";
const WORKFLOW_TYPE = process.env.TEMPORAL_WORKFLOW_TYPE ?? CONVERSATION_WORKFLOW_TYPE;
const BRIDGE_PORT = Number(process.env.BRIDGE_PORT ?? 3001);
const WORKSPACE_ROOT = process.env.OPENCLAW_WORKSPACE_ROOT ?? "/Users/admin/.openclaw/workspace";
const CONTINUE_AS_NEW_TURN_LIMIT = Number(process.env.CONTINUE_AS_NEW_TURN_LIMIT ?? 6);

async function buildSystemPrompt(): Promise<string> {
  const files = ["SOUL.md", "USER.md", "AGENTS.md", "MEMORY.md"];
  const parts: string[] = [];

  for (const file of files) {
    const filePath = path.join(WORKSPACE_ROOT, file);
    try {
      const content = await readFile(filePath, "utf8");
      parts.push(`# ${file}\n${content}`);
    } catch {
      // Missing files are acceptable in tracer mode.
    }
  }

  return parts.join("\n\n");
}

async function createTemporalClient(): Promise<Client> {
  const options: ConnectionOptions = {
    address: TEMPORAL_HOST,
  };
  const connection = await Connection.connect(options);
  return new Client({ connection, namespace: TEMPORAL_NAMESPACE });
}

function workflowIdForSession(sessionId: string): string {
  return `openclaw-${sessionId}`;
}

async function ensureWorkflow(
  client: Client,
  sessionId: string,
  initialMessage: string,
): Promise<WorkflowHandle> {
  const workflowId = workflowIdForSession(sessionId);
  const existing = client.workflow.getHandle(workflowId);
  try {
    await existing.describe();
    return existing;
  } catch {
    const systemPrompt = await buildSystemPrompt();
    const input: ConversationWorkflowInput = {
      conversationId: workflowId,
      systemPrompt,
      initialUserMessage: initialMessage,
      maxTurnsBeforeContinueAsNew: CONTINUE_AS_NEW_TURN_LIMIT,
    };

    return client.workflow.start(WORKFLOW_TYPE, {
      args: [input],
      taskQueue: TASK_QUEUE,
      workflowId,
    });
  }
}

async function sendUserInput(
  handle: WorkflowHandle,
  message: string,
): Promise<{ turn_id: string }> {
  const result = await handle.executeUpdate(UPDATE_USER_INPUT, {
    args: [{ content: message }],
  });
  return result as UserMessageAccepted;
}

async function queryConversationItems(handle: WorkflowHandle): Promise<ConversationItem[]> {
  const items = await handle.query(QUERY_CONVERSATION_ITEMS);
  return items as ConversationItem[];
}

async function waitForAssistantReply(
  handle: WorkflowHandle,
  sinceSeq: number,
  timeoutMs = 60_000,
): Promise<ConversationItem | null> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const items = await queryConversationItems(handle);
    const reply = items.find(
      (item) => item.seq > sinceSeq && item.type === "assistant_message",
    );
    if (reply) {
      return reply;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return null;
}

export async function startBridgeServer(): Promise<void> {
  const client = await createTemporalClient();
  const app = express();
  app.use(express.json());

  app.get("/healthz", (_req, res) => {
    res.status(200).json({ ok: true });
  });

  app.post("/session/start", async (req, res) => {
    const { sessionId, message } = req.body as { sessionId?: string; message?: string };
    if (!sessionId || !message) {
      res.status(400).json({ error: "sessionId and message are required" });
      return;
    }

    try {
      const handle = await ensureWorkflow(client, sessionId, message);
      res.json({ workflowId: handle.workflowId });
    } catch (error) {
      res.status(500).json({ error: String(error) });
    }
  });

  app.post("/session/send", async (req, res) => {
    const { sessionId, message } = req.body as { sessionId?: string; message?: string };
    if (!sessionId || !message) {
      res.status(400).json({ error: "sessionId and message are required" });
      return;
    }

    const workflowId = workflowIdForSession(sessionId);
    const handle = client.workflow.getHandle(workflowId);
    try {
      const itemsBefore = await queryConversationItems(handle);
      const lastSeq = itemsBefore.length ? itemsBefore[itemsBefore.length - 1].seq : 0;
      const accepted = await sendUserInput(handle, message);
      const reply = await waitForAssistantReply(handle, lastSeq);
      if (reply?.content) {
        console.log(
          `[tracer] session=${sessionId} turn=${accepted.turn_id} assistant_reply=${reply.content}`,
        );
      }
      res.json({
        turnId: accepted.turn_id,
        reply: reply?.content ?? null,
        routing: reply?.metadata ?? null,
      });
    } catch (error) {
      res.status(500).json({ error: String(error) });
    }
  });

  app.post("/reply", (req, res) => {
    const { sessionId, text } = req.body as { sessionId?: string; text?: string };
    if (!sessionId || !text) {
      res.status(400).json({ error: "sessionId and text are required" });
      return;
    }

    // Tracer phase: log instead of forwarding to Telegram/OpenClaw messaging layer.
    console.log(`[reply-hook] session=${sessionId} text=${text}`);
    res.json({ ok: true });
  });

  app.listen(BRIDGE_PORT, () => {
    console.log(`bridge listening on http://localhost:${BRIDGE_PORT}`);
    console.log(`temporal=${TEMPORAL_HOST} namespace=${TEMPORAL_NAMESPACE} taskQueue=${TASK_QUEUE}`);
    console.log(`workflow=${WORKFLOW_TYPE} continueAsNewTurns=${CONTINUE_AS_NEW_TURN_LIMIT}`);
  });
}

if (require.main === module) {
  startBridgeServer().catch((error) => {
    console.error("bridge failed to start", error);
    process.exit(1);
  });
}

export {
  buildSystemPrompt,
  createTemporalClient,
  ensureWorkflow,
  queryConversationItems,
  sendUserInput,
  waitForAssistantReply,
  workflowIdForSession,
};
