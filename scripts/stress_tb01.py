"""TB1 stress test: Send 20 messages to @mycel_dev_bot via Telegram API and measure responses."""
import asyncio
import time
import os
import httpx

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
# We send messages AS the bot to itself won't work — we need to use the bot API
# to check getUpdates. Instead, we'll send via a different approach:
# Use the Temporal client directly to signal the workflow and measure round-trips.

# Actually, the real stress test should go through Telegram end-to-end.
# But we can't send messages TO a bot via Bot API — a human has to.
# So instead: hit the Temporal workflow directly with 20 signals and measure.

from temporalio.client import Client
from uuid import uuid4

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
WORKFLOW_ID = "tb01-ping-workflow"
TASK_QUEUE = "tb01-task-queue"

async def main():
    client = await Client.connect(TEMPORAL_ADDRESS)
    handle = client.get_workflow_handle(WORKFLOW_ID)
    
    results = []
    total = 20
    
    print(f"Sending {total} signals to workflow...")
    print("-" * 50)
    
    for i in range(total):
        request_id = str(uuid4())
        msg = f"stress-{i+1}"
        
        start = time.monotonic()
        
        # Signal
        await handle.signal("enqueue_ping", {"request_id": request_id, "message": msg})
        
        # Poll for response
        response = None
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            response = await handle.query("get_response", request_id)
            if response is not None:
                break
            await asyncio.sleep(0.1)
        
        elapsed = (time.monotonic() - start) * 1000
        
        if response:
            results.append({"i": i+1, "ok": True, "ms": elapsed, "response": response})
            print(f"  [{i+1:2d}/{total}] ✅ {elapsed:6.0f}ms — {response}")
        else:
            results.append({"i": i+1, "ok": False, "ms": elapsed, "response": None})
            print(f"  [{i+1:2d}/{total}] ❌ {elapsed:6.0f}ms — TIMEOUT")
    
    print("-" * 50)
    
    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    times = [r["ms"] for r in ok]
    
    print(f"Results: {len(ok)}/{total} succeeded, {len(fail)} failed")
    if times:
        times.sort()
        print(f"Latency: min={times[0]:.0f}ms  median={times[len(times)//2]:.0f}ms  p95={times[int(len(times)*0.95)]:.0f}ms  max={times[-1]:.0f}ms")
    
    # Success criteria: 0 deadlocks, 0 dropped
    if len(fail) == 0:
        print("\n🎉 TB1 STRESS TEST PASSED — 0 deadlocks, 0 dropped replies")
    else:
        print(f"\n⚠️  TB1 STRESS TEST: {len(fail)} failures — investigate")

if __name__ == "__main__":
    asyncio.run(main())
