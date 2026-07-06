
class RLLoop:
    def __init__(self):
        self.memory = []

    def record(self, state, action, reward):
        self.memory.append({"state": state, "action": action, "reward": reward})

    def improve_signal_weight(self):
        if not self.memory:
            return None
        avg_reward = sum(m["reward"] for m in self.memory) / len(self.memory)
        return {"avg_reward": avg_reward, "adjustment": "increase risk appetite" if avg_reward > 0 else "reduce risk"}
