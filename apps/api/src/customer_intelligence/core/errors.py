class WorkflowError(ValueError):
    def __init__(
        self, message: str, status_code: int = 400, code: str = "invalid_workflow"
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
