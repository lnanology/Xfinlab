
class SignalRouter:
    @staticmethod
    def route(signal, market="US"):
        return {"market": market, "signal": signal, "route": f"{market}_EXECUTION_LAYER"}
