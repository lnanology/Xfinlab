
class Memory:
    def __init__(self):
        self.store = []
    def add(self, data):
        self.store.append(data)
    def get_all(self):
        return self.store
