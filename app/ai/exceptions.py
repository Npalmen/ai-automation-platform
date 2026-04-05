class LLMClientError(Exception):
    """Base exception for LLM client failures."""


class LLMConfigurationError(LLMClientError):
    """Raised when LLM configuration is missing or invalid."""


class LLMResponseError(LLMClientError):
    """Raised when the LLM response is malformed or unusable."""


class LLMRequestError(LLMClientError):
    """Raised when the LLM HTTP request fails."""