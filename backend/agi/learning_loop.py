
from agi.brain import AGIBrain
from agi.memory import Memory

class LearningLoop:
    def __init__(self):
        self.memory = Memory()
        self.brain = AGIBrain()

    def run(self, context):
        result = self.brain.think(context)
        self.memory.add(result)
        return {"decision": result, "memory_size": len(self.memory.get_all())}
