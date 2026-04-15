import asyncio
from app.domain.ingestion.application.tasks import PollNewsTask, PollPricesTask

async def trigger():
    print("Triggering PollNewsTask...")
    PollNewsTask.delay()
    print("Triggering PollPricesTask...")
    PollPricesTask.delay()
    print("Done.")

if __name__ == "__main__":
    import os
    # Set necessary env vars for the script if running outside docker
    # But it's better to run it INSIDE docker
    pass
