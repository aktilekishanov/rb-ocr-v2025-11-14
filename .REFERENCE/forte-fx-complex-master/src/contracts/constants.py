from enum import Enum


class ContractStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ErrorCode(str, Enum):
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    FILE_KEY_NOT_FOUND = "FILE_KEY_NOT_FOUND"
    FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
    RESULT_NOT_READY = "RESULT_NOT_READY"
