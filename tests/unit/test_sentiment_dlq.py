import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Mock torch and transformers to prevent WinError DLL loading issues
sys.modules['torch'] = MagicMock()
sys.modules['torch.nn'] = MagicMock()
sys.modules['transformers'] = MagicMock()

from domains.analytics.application.services.nlp.sentiment_orchestrator_service import main
from shared.constants import Streams, StreamGroups
from shared.infrastructure.event_bus.streams import StreamMessage


@pytest.mark.unit
@patch("app.bootstrap.Bootstrap.get_sentiment_subscriber_deps")
@patch("domains.analytics.application.services.nlp.sentiment_orchestrator_service.handle_headline")
async def test_sentiment_orchestrator_dlq_routing(
    mock_handle_headline,
    mock_get_deps
):
    # Setup mock dependencies
    mock_redis = AsyncMock()
    mock_stream_bus = AsyncMock()
    mock_redis._get_stream_bus.return_value = mock_stream_bus

    mock_deps = MagicMock()
    mock_deps.publisher = mock_redis
    mock_get_deps.return_value = mock_deps

    # Mock handle_headline to throw exception (simulating processing failure)
    mock_handle_headline.side_effect = Exception("Test processing error")

    # Mock stream_bus.read_group to return one message
    dummy_message = StreamMessage(
        stream=Streams.HEADLINE_FETCHED,
        message_id="12345-0",
        payload={"symbol": "NIFTY", "headline": "Bad market news"},
        retry_count=0
    )
    
    # We want main() to execute the loop once and then exit/break
    mock_stream_bus.read_group.side_effect = [
        [dummy_message],  # first call for INGESTION_TO_NLP
        [],               # first call for REFRESH_TO_SENTIMENT
        KeyboardInterrupt() # stop the infinite while True loop
    ]

    # Run main() and catch KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        await main()

    # Check that handle_headline was called
    mock_handle_headline.assert_called_once()

    # Check that ack was NOT called
    mock_stream_bus.ack.assert_not_called()

    # Check that retry_or_dead_letter was called with correct DLQ stream
    mock_stream_bus.retry_or_dead_letter.assert_called_once_with(
        stream=Streams.HEADLINE_FETCHED,
        dlq_stream=Streams.INGESTION_TO_NLP_DLQ,
        group=StreamGroups.INGESTION_TO_NLP,
        message=dummy_message,
        error=mock_handle_headline.side_effect
    )
