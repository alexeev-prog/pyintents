class IntentViolationError(Exception):
    def __init__(self, func_name: str, violation: str) -> None:
        self.func_name = func_name
        self.violation = violation
        super().__init__(f"Function '{func_name}' calls forbidden '{violation}'")
