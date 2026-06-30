from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_api_root():

    response = client.get("/")

    assert response.status_code == 200


def test_api_docs():

    response = client.get("/docs")

    assert response.status_code == 200


def test_strategy_engine():

    try:
        from engines.strategy_engine import StrategyEngine

        engine = StrategyEngine(
            "strategies/AJ_Strategy_V1.json"
        )

        score = engine.calculate_score(
            {
                "price": 100,
                "volume": 1000000,
                "volume_ratio": 2.5
            }
        )

        assert score >= 0

    except Exception as e:

        print(e)

        assert False


def test_market_data_service():

    try:

        from services.market_data_service import get_stock_data

        data = get_stock_data("AAPL")

        assert data is not None

    except Exception as e:

        print(e)

        assert False


def test_database():

    try:

        from database.db import engine

        connection = engine.connect()

        connection.close()

        assert True

    except Exception as e:

        print(e)

        assert False