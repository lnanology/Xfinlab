
class EventBus:
    subscribers = {}
    @classmethod
    def subscribe(cls, event, fn):
        cls.subscribers.setdefault(event, []).append(fn)
    @classmethod
    def publish(cls, event, data):
        for fn in cls.subscribers.get(event, []):
            fn(data)
