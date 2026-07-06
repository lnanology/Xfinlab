
class EventStream:
    @staticmethod
    def detect(data):
        events = []
        if data["price"] > 105:
            events.append("BREAKOUT")
        if data["price"] < 95:
            events.append("DUMP")
        if data["volume"] > 4000:
            events.append("HIGH_VOLUME")
        return events
