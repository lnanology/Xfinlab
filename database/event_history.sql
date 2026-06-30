-- XFINLAB Event Intelligence V1
-- Database Schema and Sample Data

-- Create events table
CREATE TABLE IF NOT EXISTS event_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'earnings', 'regulation', 'ceo_change',
        'merger', 'abnormal_volume', 'major_news'
    )),
    event_date TEXT NOT NULL,
    price_before REAL NOT NULL,
    price_after_1d REAL,
    price_after_7d REAL,
    price_after_30d REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Sample Data: earnings
INSERT INTO event_history (symbol, event_type, event_date, price_before, price_after_1d, price_after_7d, price_after_30d) VALUES
('AAPL', 'earnings', '2024-01-25', 100.0, 108.0, 112.0, 120.0),
('AAPL', 'earnings', '2024-04-25', 110.0, 105.0, 108.0, 115.0),
('MSFT', 'earnings', '2024-01-30', 200.0, 212.0, 218.0, 230.0),
('MSFT', 'earnings', '2024-04-30', 210.0, 215.0, 220.0, 225.0),
('GOOGL', 'earnings', '2024-02-01', 150.0, 145.0, 148.0, 155.0);

-- Sample Data: regulation
INSERT INTO event_history (symbol, event_type, event_date, price_before, price_after_1d, price_after_7d, price_after_30d) VALUES
('META', 'regulation', '2024-02-15', 300.0, 285.0, 275.0, 260.0),
('GOOGL', 'regulation', '2024-03-10', 140.0, 132.0, 130.0, 135.0),
('AMZN', 'regulation', '2024-04-05', 180.0, 172.0, 170.0, 175.0);

-- Sample Data: ceo_change
INSERT INTO event_history (symbol, event_type, event_date, price_before, price_after_1d, price_after_7d, price_after_30d) VALUES
('TSLA', 'ceo_change', '2024-01-10', 250.0, 240.0, 235.0, 245.0),
('INTC', 'ceo_change', '2024-02-20', 45.0, 47.0, 49.0, 52.0),
('BIDU', 'ceo_change', '2024-03-15', 120.0, 118.0, 122.0, 125.0);

-- Sample Data: merger
INSERT INTO event_history (symbol, event_type, event_date, price_before, price_after_1d, price_after_7d, price_after_30d) VALUES
('ATVI', 'merger', '2024-01-18', 75.0, 92.0, 94.0, 95.0),
('VMW', 'merger', '2024-02-28', 140.0, 168.0, 170.0, 172.0),
('MTCH', 'merger', '2024-03-22', 35.0, 38.0, 40.0, 42.0);

-- Sample Data: abnormal_volume
INSERT INTO event_history (symbol, event_type, event_date, price_before, price_after_1d, price_after_7d, price_after_30d) VALUES
('GME', 'abnormal_volume', '2024-01-22', 15.0, 28.0, 22.0, 18.0),
('AMC', 'abnormal_volume', '2024-02-14', 5.0, 8.5, 7.0, 6.0),
('BBBY', 'abnormal_volume', '2024-03-08', 2.0, 3.5, 3.0, 2.5);

-- Sample Data: major_news
INSERT INTO event_history (symbol, event_type, event_date, price_before, price_after_1d, price_after_7d, price_after_30d) VALUES
('NVDA', 'major_news', '2024-02-22', 600.0, 675.0, 700.0, 750.0),
('TSLA', 'major_news', '2024-03-01', 200.0, 188.0, 182.0, 175.0),
('AAPL', 'major_news', '2024-04-10', 170.0, 165.0, 168.0, 172.0);
