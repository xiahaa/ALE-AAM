class MaptoolError(RuntimeError):
    exit_code = 4
    error_code = "native_backend_error"

    def as_dict(self):
        return {"ok": False, "error": {"code": self.error_code, "message": str(self)}}


class ConfigurationError(MaptoolError):
    exit_code = 2
    error_code = "configuration_error"


class NoFeasiblePathError(MaptoolError):
    exit_code = 3
    error_code = "no_feasible_path"


class NativeBackendError(MaptoolError):
    exit_code = 4
    error_code = "native_backend_error"
