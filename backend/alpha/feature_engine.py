
class FeatureEngine:
    @staticmethod
    def build(market_data):
        """
        2026-07-18 fix: this used to discard whatever real volatility was
        passed in and replace it with `abs(np.random.randn()) * 10` --
        i.e. a fresh random number on every single call, silently
        corrupting AlphaEngine.generate()'s alpha_score/signal (BUY/SELL/
        HOLD) with noise even though api/pipeline_api.py's
        _fetch_real_pipeline_inputs() had already computed a real,
        annualized-realized-volatility number for this exact ticker and
        passed it in as market_data["volatility"]. Currently this doesn't
        leak to end users (api/pipeline_api.py's _to_probability_view()
        never reads raw["alpha"]), but it's exactly the kind of fabricated
        number this codebase's other engines go out of their way to
        avoid -- fixed to use the real value instead of silently
        discarding it.
        """
        price = market_data.get("price", 100)
        volume = market_data.get("volume", 1)
        volatility = market_data.get("volatility", 50)
        return {
            "momentum": price * 0.01,
            "volume_pressure": volume / 1000,
            "volatility": float(volatility),
        }
