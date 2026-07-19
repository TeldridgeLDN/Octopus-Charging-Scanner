#!/usr/bin/env python3
"""Quick demonstration of Week 1 API modules."""

import logging
from src.modules import OctopusAPIClient, CarbonAPIClient, DataStore

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def demo_octopus_api():
    """Test Octopus Energy API."""
    logger.info("=" * 60)
    logger.info("Testing Octopus Energy API")
    logger.info("=" * 60)

    try:
        client = OctopusAPIClient()
        prices = client.get_prices(region="H", hours=4)

        logger.info(f"Successfully fetched {len(prices)} price slots")

        if prices:
            first = prices[0]
            logger.info(
                f"First slot: {first['valid_from']} - {first['value_inc_vat']}p/kWh"
            )

            # Find cheapest slot
            cheapest = min(prices, key=lambda x: x["value_inc_vat"])
            logger.info(
                f"Cheapest: {cheapest['value_inc_vat']}p/kWh at {cheapest['valid_from']}"
            )

        return True
    except Exception as e:
        logger.error(f"Octopus API failed: {e}")
        return False


def demo_carbon_api():
    """Test Carbon Intensity API."""
    logger.info("=" * 60)
    logger.info("Testing Carbon Intensity API")
    logger.info("=" * 60)

    try:
        client = CarbonAPIClient()
        intensities = client.get_intensity(postcode="SW1")

        logger.info(f"Successfully fetched {len(intensities)} carbon intensity slots")

        if intensities:
            first = intensities[0]
            logger.info(f"First slot: {first['time']} - {first['intensity']} gCO2/kWh")

            # Find cleanest period
            if len(intensities) >= 8:  # 4 hours
                window = client.get_cleanest_window(postcode="E1", hours=4)
                logger.info(f"Cleanest 4h window: {window['start_time']}")
                logger.info(
                    f"Average intensity: {window['average_intensity']} gCO2/kWh"
                )

        return True
    except Exception as e:
        logger.error(f"Carbon API failed: {e}")
        return False


def demo_data_store():
    """Test Data Storage Layer."""
    logger.info("=" * 60)
    logger.info("Testing Data Storage Layer")
    logger.info("=" * 60)

    try:
        store = DataStore()

        # Test saving a forecast
        test_forecast = {
            "timestamp": "2025-12-08T10:00:00Z",
            "data": [
                {"time": "2025-12-08T10:00:00Z", "price": 12.5},
                {"time": "2025-12-08T10:30:00Z", "price": 11.8},
            ],
            "source": "demo",
        }

        store.save_forecast(test_forecast)
        logger.info("Saved test forecast")

        # Retrieve it
        latest = store.get_latest_forecast()
        if latest:
            logger.info(
                f"Retrieved forecast: {latest['source']} with {len(latest['data'])} slots"
            )

        return True
    except Exception as e:
        logger.error(f"Data store failed: {e}")
        return False


def main():
    """Run all demos."""
    logger.info("EV Charging Optimizer - Week 1 Foundation Demo")
    logger.info("=" * 60)

    results = {
        "Octopus API": demo_octopus_api(),
        "Carbon API": demo_carbon_api(),
        "Data Store": demo_data_store(),
    }

    logger.info("=" * 60)
    logger.info("Demo Results Summary")
    logger.info("=" * 60)

    for name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{name}: {status}")

    all_passed = all(results.values())

    if all_passed:
        logger.info("\n🎉 All APIs working correctly!")
    else:
        logger.warning("\n⚠️ Some APIs failed - check logs above")

    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
