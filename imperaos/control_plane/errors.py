from __future__ import annotations


class ControlPlaneError(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


class AgentSpecValidationError(ControlPlaneError):
    pass


class AgentAlreadyExistsWithDifferentSpec(ControlPlaneError):
    pass


class AgentNotFound(ControlPlaneError):
    pass


class RegistryCorrupted(ControlPlaneError):
    pass


class PolicyUnavailableFailClosed(ControlPlaneError):
    pass


class MissingRequiredArtifact(ControlPlaneError):
    pass


class EvidenceHashMismatch(ControlPlaneError):
    pass


class SignatureVerificationFailed(ControlPlaneError):
    pass


class PathOutsideRoot(ControlPlaneError):
    pass
