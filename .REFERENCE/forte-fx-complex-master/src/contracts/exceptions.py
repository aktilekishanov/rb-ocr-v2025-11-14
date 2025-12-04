class DocumentNotFoundError(Exception):
    """Raised when no contract exists for the given document_id."""


class FileKeyNotFoundError(Exception):
    """Raised when the requested key isn’t in docs_json."""


class FieldNotFoundError(Exception):
    """Raised when the requested field isn't in flat_result_json"""


class PipelineError(Exception):
    """Raised when a pipeline raises an error."""
