from uuid import UUID


class APIError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        actor: UUID | None = None,
        action: str | None = None,
        resource_type: str = "request",
        resource_id: UUID | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.actor = actor
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
