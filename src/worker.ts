import process from "node:process";

import { NativeConnection, Worker } from "@temporalio/worker";

import * as activities from "./activities/mock-llm";

const TEMPORAL_HOST = process.env.TEMPORAL_HOST ?? "localhost:7233";
const TEMPORAL_NAMESPACE = process.env.TEMPORAL_NAMESPACE ?? "default";
const TASK_QUEUE = process.env.TEMPORAL_TASK_QUEUE ?? "mycel-bridge";

async function runWorker(): Promise<void> {
  const connection = await NativeConnection.connect({
    address: TEMPORAL_HOST,
  });

  const worker = await Worker.create({
    connection,
    namespace: TEMPORAL_NAMESPACE,
    taskQueue: TASK_QUEUE,
    workflowsPath: require.resolve("./workflows/conversation"),
    activities,
  });

  console.log(
    `worker connected temporal=${TEMPORAL_HOST} namespace=${TEMPORAL_NAMESPACE} taskQueue=${TASK_QUEUE}`,
  );

  await worker.run();
}

runWorker().catch((error) => {
  console.error("worker failed", error);
  process.exit(1);
});

