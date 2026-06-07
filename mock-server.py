#!/usr/bin/env python3
import json
import hashlib
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8080


def hash_int(value, mod=100):
    key = hashlib.md5(value.encode('utf-8')).hexdigest()
    return int(key, 16) % mod


def json_response(handler, payload):
    body = json.dumps(payload).encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()
    handler.wfile.write(body)


def mock_ai_analysis(body):
    symbols = body.get('symbols', [])
    symbol = symbols[0] if symbols else 'AAPL'
    base = symbol.upper()
    fund = 55 + hash_int(base + 'fund', 40)
    tech = 50 + hash_int(base + 'tech', 45)
    news = 45 + hash_int(base + 'news', 45)
    risk = 30 + hash_int(base + 'risk', 40)
    overall = round((fund + tech + news + (100 - risk)) / 4)
    bull = 40 + hash_int(base + 'bull', 30)
    flat = 20 + hash_int(base + 'flat', 25)
    bear = max(5, 100 - bull - flat)
    return {
        'status': 'ok',
        'schema_version': 1,
        'data': {
            'symbol': symbol,
            'scores': {
                'fund': fund,
                'tech': tech,
                'news': news,
                'risk': risk,
                'overall': overall
            },
            'probabilities': {
                'bull': bull,
                'flat': flat,
                'bear': bear
            },
            'risks': [
                {'title': '市場波動風險', 'desc': '市場情緒與宏觀變動可能導致高波動。'},
                {'title': '財報公告風險', 'desc': '若業績不及預期，股價可能快速回調。'}
            ],
            'conclusion': f'{symbol} 目前呈現以基本面與新聞面為主的穩健評分，技術面需關注近期成交量變化。'
        }
    }


def mock_company_compare(body):
    symbols = body.get('symbols', [])
    if not symbols:
        symbols = ['AAPL', 'MSFT']
    companies = []
    for symbol in symbols:
        base = symbol.upper()
        gross = 20 + hash_int(base + 'gross', 30)
        growth = 10 + hash_int(base + 'growth', 40)
        roe = 8 + hash_int(base + 'roe', 22)
        cash = 30 + hash_int(base + 'cash', 40)
        risk = 25 + hash_int(base + 'risk', 35)
        companies.append({
            'symbol': symbol,
            'grossMargin': gross,
            'growthRate': growth,
            'roe': roe,
            'cashFlow': cash,
            'riskScore': risk
        })
    return {
        'status': 'ok',
        'schema_version': 1,
        'data': {
            'companies': companies,
            'analysis': '比較結果顯示各公司在毛利、成長與現金流上存在差異，請注意風險分數以評估波動性。'
        }
    }


def mock_news_denoise(body):
    symbol = body.get('symbol', 'AAPL').upper()
    base = symbol
    bull = 40 + hash_int(base + 'bull', 30)
    bear = 15 + hash_int(base + 'bear', 30)
    neutral = 100 - bull - bear
    facts = [
        {'title': '主流新聞焦點', 'text': f'{symbol} 新聞多集中於營收與新品發表。'},
        {'title': '市場關注點', 'text': '投資者目前關注公司毛利率與存貨變動。'}
    ]
    blindspots = [
        {'title': '散戶盲點', 'text': '過度關注短期漲跌，忽略了長期現金流。'},
        {'title': '散戶盲點', 'text': '忽視宏觀利率變動對估值的影響。'}
    ]
    return {
        'status': 'ok',
        'schema_version': 1,
        'data': {
            'symbol': symbol,
            'sentimentIndex': 60 + hash_int(base + 'sentiment', 20),
            'sentiment': {
                'bullish': bull,
                'neutral': neutral,
                'bearish': bear
            },
            'facts': facts,
            'blindspots': blindspots,
            'explanation': f'{symbol} 的新聞情緒偏向正面，但仍需警惕高估與短期情緒化波動。'
        }
    }


def mock_stress_lab(body):
    strategy = body.get('strategy', '60-40')
    amount = body.get('amount', 100000)
    seed = f'{strategy}-{amount}'
    return {
        'status': 'ok',
        'schema_version': 1,
        'data': {
            'strategy': strategy,
            'amount': amount,
            'scenarios': {
                '2008': {'drawdown': 35 + hash_int(seed + '2008', 10), 'remaining': round(amount * (1 - (0.35 + hash_int(seed + '2008', 10)/100)), 2), 'recoveryYears': 4 + hash_int(seed + '2008', 3)},
                '2020': {'drawdown': 22 + hash_int(seed + '2020', 8), 'remaining': round(amount * (1 - (0.22 + hash_int(seed + '2020', 8)/100)), 2), 'recoveryYears': 2 + hash_int(seed + '2020', 3)},
                '2022': {'drawdown': 18 + hash_int(seed + '2022', 7), 'remaining': round(amount * (1 - (0.18 + hash_int(seed + '2022', 7)/100)), 2), 'recoveryYears': 3 + hash_int(seed + '2022', 3)}
            },
            'psych': {
                'score': 50 + hash_int(seed + 'psych', 40),
                'result': '你對短期波動反應中等，建議保持訊號紀律並避免追漲殺跌。'
            }
        }
    }


class MockHandler(SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path.startswith('/api/'):
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8') if length else '{}'
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {}
            if self.path == '/api/ai-analysis':
                json_response(self, mock_ai_analysis(payload))
                return
            if self.path == '/api/company-compare':
                json_response(self, mock_company_compare(payload))
                return
            if self.path == '/api/news-denoise':
                json_response(self, mock_news_denoise(payload))
                return
            if self.path == '/api/stress-lab':
                json_response(self, mock_stress_lab(payload))
                return
            self.send_error(404, 'API route not found')
            return
        super().do_POST()


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = HTTPServer(('0.0.0.0', PORT), MockHandler)
    print(f'Serving at http://localhost:{PORT}')
    server.serve_forever()
