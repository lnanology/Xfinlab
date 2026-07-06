
from agi.planner import Planner
from agi.capital_allocator import CapitalAllocator
from agi.optimizer import Optimizer

class AGIBrain:
    def think(self, context):
        plan = Planner.plan(context)
        allocation = CapitalAllocator.allocate(plan)
        improved_score = Optimizer.improve(context.get("strategy_score", 50))
        return {"plan": plan, "allocation": allocation, "strategy_score": improved_score}
