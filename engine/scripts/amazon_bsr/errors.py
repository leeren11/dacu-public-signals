class AmazonBsrError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

    def to_dict(self) -> dict:
        return {"ok": False, "error": self.code, "message": str(self)}
