from __future__ import annotations

from temporalio.client import Client

from mycel.config import TemporalSettings


async def connect_temporal(settings: TemporalSettings) -> Client:
    return await Client.connect(settings.address, namespace=settings.namespace)
