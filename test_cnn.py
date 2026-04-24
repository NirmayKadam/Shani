import asyncio
import os
import torch
print("Imported torch")
from domains.analytics.application.ml_forecasting.CNNPredictor import CNNPredictor
print("Imported CNNPredictor")

async def test():
    print("Initializing predictor...")
    try:
        predictor = CNNPredictor()
        print("Running prediction for NIFTY...")
        result = predictor.predict("NIFTY")
        print("Result:")
        print(result)
    except Exception as e:
        print(f"Error during test: {e}")

if __name__ == "__main__":
    asyncio.run(test())
