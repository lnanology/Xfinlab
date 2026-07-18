
class Optimizer:
    @staticmethod
    def improve(strategy_score):
        """
        2026-07-18 fix: this used to unconditionally multiply the input
        by 1.05 and call the result "improved" -- there was no actual
        optimization process behind that number, just a fixed +5%
        markup applied to every score regardless of input, which would
        misrepresent this codebase's real data as having been through
        some learning/optimization step it never went through. Returns
        the real score unchanged until a genuine optimization method
        (e.g. backtest-validated parameter search) is built -- see
        services/backtest_service.py for this codebase's actual
        validated-statistics convention.
        """
        return strategy_score
