from app.processors.universal_intake import UniversalIntakeProcessor


class ProcessorService:
    def __init__(self):
        self.intake_processor = UniversalIntakeProcessor()

    def run_universal_intake(self, payload: dict) -> dict:
        return self.intake_processor.process(payload)