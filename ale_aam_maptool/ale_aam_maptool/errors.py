class MaptoolError(RuntimeError):
    exit_code = 4
    error_code = "internal_error"

    def as_dict(self):
        return {"ok": False, "error": {"code": self.error_code, "message": str(self)}}


class ConfigurationError(MaptoolError):
    exit_code = 2
    error_code = "configuration_error"
