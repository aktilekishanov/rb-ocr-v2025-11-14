"""Unit tests for input validators."""

import pytest
import io
from fastapi import UploadFile
from pydantic import ValidationError as PydanticValidationError

from api.validators import (
    VerifyRequest,
    KafkaEventRequestValidator,
    validate_upload_file,
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZE_MB,
)
from pipeline.core.exceptions import ValidationError, PayloadTooLargeError


class TestVerifyRequest:
    """Tests for VerifyRequest validator."""
    
    def test_valid_fio_cyrillic(self):
        """Test valid Cyrillic FIO passes validation."""
        request = VerifyRequest(fio="Иванов Иван Иванович")
        assert request.fio == "Иванов Иван Иванович"
    
    def test_valid_fio_latin(self):
        """Test valid Latin FIO passes validation."""
        request = VerifyRequest(fio="Smith John Michael")
        assert request.fio == "Smith John Michael"
    
    def test_valid_fio_with_hyphen(self):
        """Test FIO with hyphen passes validation."""
        request = VerifyRequest(fio="Петров-Водкин Иван")
        assert request.fio == "Петров-Водкин Иван"
    
    def test_fio_whitespace_normalization(self):
        """Test excessive whitespace is normalized."""
        request = VerifyRequest(fio="Иванов    Иван   Иванович")
        assert request.fio == "Иванов Иван Иванович"
    
    def test_fio_too_short(self):
        """Test FIO too short raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            VerifyRequest(fio="AB")
        
        errors = exc_info.value.errors()
        assert errors[0]["type"] == "string_too_short"
    
    def test_fio_single_word(self):
        """Test single-word FIO raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            VerifyRequest(fio="Иванов")
        
        errors = exc_info.value.errors()
        assert "at least first and last name" in str(errors[0]["msg"])
    
    def test_fio_invalid_characters_numbers(self):
        """Test FIO with numbers raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            VerifyRequest(fio="Иванов123 Иван")
        
        errors = exc_info.value.errors()
        assert "only letters" in str(errors[0]["msg"])
    
    def test_fio_invalid_characters_symbols(self):
        """Test FIO with special symbols raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            VerifyRequest(fio="Иванов@Email Иван")
        
        errors = exc_info.value.errors()
        assert "only letters" in str(errors[0]["msg"])
    
    def test_fio_too_long(self):
        """Test FIO exceeding max length raises error."""
        long_fio = "А" * 201
        with pytest.raises(PydanticValidationError) as exc_info:
            VerifyRequest(fio=long_fio)
        
        errors = exc_info.value.errors()
        assert errors[0]["type"] == "string_too_long"


class TestKafkaEventRequestValidator:
    """Tests for KafkaEventRequestValidator."""
    
    def test_valid_kafka_event(self):
        """Test valid Kafka event passes validation."""
        event = KafkaEventRequestValidator(
            request_id=123,
            s3_path="documents/2024/sample.pdf",
            iin=960125000000,
            first_name="Иван",
            last_name="Иванов",
            second_name="Иванович"
        )
        
        assert event.request_id == 123
        assert event.s3_path == "documents/2024/sample.pdf"
        assert event.iin == 960125000000
    
    def test_kafka_event_without_second_name(self):
        """Test Kafka event without second name (optional)."""
        event = KafkaEventRequestValidator(
            request_id=456,
            s3_path="docs/file.pdf",
            iin=850101123456,
            first_name="John",
            last_name="Doe"
        )
        
        assert event.second_name is None
    
    def test_invalid_request_id_zero(self):
        """Test request_id of 0 raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            KafkaEventRequestValidator(
                request_id=0,
                s3_path="docs/file.pdf",
                iin=960125000000,
                first_name="Test",
                last_name="User"
            )
        
        errors = exc_info.value.errors()
        assert "greater than 0" in str(errors[0]["msg"])
    
    def test_invalid_request_id_negative(self):
        """Test negative request_id raises error."""
        with pytest.raises(PydanticValidationError):
            KafkaEventRequestValidator(
                request_id=-1,
                s3_path="docs/file.pdf",
                iin=960125000000,
                first_name="Test",
                last_name="User"
            )
    
    def test_invalid_s3_path_directory_traversal_dotdot(self):
        """Test S3 path with .. raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            KafkaEventRequestValidator(
                request_id=123,
                s3_path="../sensitive/data.pdf",
                iin=960125000000,
                first_name="Test",
                last_name="User"
            )
        
        errors = exc_info.value.errors()
        assert "directory traversal" in str(errors[0]["msg"])
    
    def test_invalid_s3_path_leading_slash(self):
        """Test S3 path with leading / raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            KafkaEventRequestValidator(
                request_id=123,
                s3_path="/etc/passwd",
                iin=960125000000,
                first_name="Test",
                last_name="User"
            )
        
        errors = exc_info.value.errors()
        assert "directory traversal" in str(errors[0]["msg"])
    
    def test_invalid_s3_path_no_extension(self):
        """Test S3 path without extension raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            KafkaEventRequestValidator(
                request_id=123,
                s3_path="documents/sample",
                iin=960125000000,
                first_name="Test",
                last_name="User"
            )
        
        errors = exc_info.value.errors()
        assert "file extension" in str(errors[0]["msg"])
    
    def test_valid_s3_path_with_dots_in_directory(self):
        """Test S3 path with dots in directory name (not ..) is valid."""
        event = KafkaEventRequestValidator(
            request_id=123,
            s3_path="docs.archive/2024.12/file.pdf",
            iin=960125000000,
            first_name="Test",
            last_name="User"
        )
        assert event.s3_path == "docs.archive/2024.12/file.pdf"
    
    def test_invalid_iin_too_short(self):
        """Test IIN with less than 12 digits raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            KafkaEventRequestValidator(
                request_id=123,
                s3_path="docs/file.pdf",
                iin=12345678901,  # 11 digits
                first_name="Test",
                last_name="User"
            )
        
        errors = exc_info.value.errors()
        assert "greater than or equal to" in str(errors[0]["msg"])
    
    def test_invalid_iin_too_long(self):
        """Test IIN with more than 12 digits raises error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            KafkaEventRequestValidator(
                request_id=123,
                s3_path="docs/file.pdf",
                iin=1234567890123,  # 13 digits
                first_name="Test",
                last_name="User"
            )
        
        errors = exc_info.value.errors()
        assert "less than or equal to" in str(errors[0]["msg"])
    
    def test_name_whitespace_normalization(self):
        """Test name fields normalize whitespace."""
        event = KafkaEventRequestValidator(
            request_id=123,
            s3_path="docs/file.pdf",
            iin=960125000000,
            first_name="  Иван  ",
            last_name="Иванов   Сергеевич",
        )
        
        assert event.first_name == "Иван"
        assert event.last_name == "Иванов Сергеевич"


class TestValidateUploadFile:
    """Tests for validate_upload_file function."""
    
    @pytest.mark.asyncio
    async def test_valid_pdf_file(self):
        """Test valid PDF file passes validation."""
        content = b"PDF content" * 100
        file = UploadFile(
            filename="test.pdf",
            file=io.BytesIO(content),
            headers={"content-type": "application/pdf"}
        )
        
        # Should not raise
        await validate_upload_file(file)
    
    @pytest.mark.asyncio
    async def test_valid_jpeg_file(self):
        """Test valid JPEG file passes validation."""
        content = b"JPEG content" * 100
        file = UploadFile(
            filename="image.jpg",
            file=io.BytesIO(content),
            headers={"content-type": "image/jpeg"}
        )
        
        await validate_upload_file(file)
    
    @pytest.mark.asyncio
    async def test_valid_png_file(self):
        """Test valid PNG file passes validation."""
        content = b"PNG content" * 100
        file = UploadFile(
            filename="image.png",
            file=io.BytesIO(content),
            headers={"content-type": "image/png"}
        )
        
        await validate_upload_file(file)
    
    @pytest.mark.asyncio
    async def test_invalid_file_type_txt(self):
        """Test text file raises ValidationError."""
        content = b"Text content"
        file = UploadFile(
            filename="test.txt",
            file=io.BytesIO(content),
            headers={"content-type": "text/plain"}
        )
        
        with pytest.raises(ValidationError) as exc_info:
            await validate_upload_file(file)
        
        error = exc_info.value
        assert error.http_status == 422
        assert error.details["field"] == "file"
        assert error.details["received_type"] == "text/plain"
        assert "allowed_types" in error.details
    
    @pytest.mark.asyncio
    async def test_invalid_file_type_exe(self):
        """Test executable file raises ValidationError."""
        content = b"EXE content"
        file = UploadFile(
            filename="malicious.exe",
            file=io.BytesIO(content),
            headers={"content-type": "application/x-msdownload"}
        )
        
        with pytest.raises(ValidationError) as exc_info:
            await validate_upload_file(file)
        
        assert exc_info.value.http_status == 422
    
    @pytest.mark.asyncio
    async def test_file_too_large(self):
        """Test file exceeding size limit raises PayloadTooLargeError."""
        # Create 51MB file
        content = b"x" * (51 * 1024 * 1024)
        file = UploadFile(
            filename="large.pdf",
            file=io.BytesIO(content),
            headers={"content-type": "application/pdf"}
        )
        
        with pytest.raises(PayloadTooLargeError) as exc_info:
            await validate_upload_file(file)
        
        error = exc_info.value
        assert error.http_status == 413
        assert error.details["max_size_mb"] == MAX_FILE_SIZE_MB
        assert error.details["actual_size_mb"] > 50
    
    @pytest.mark.asyncio
    async def test_empty_file(self):
        """Test empty file (0 bytes) raises ValidationError."""
        content = b""
        file = UploadFile(
            filename="empty.pdf",
            file=io.BytesIO(content),
            headers={"content-type": "application/pdf"}
        )
        
        with pytest.raises(ValidationError) as exc_info:
            await validate_upload_file(file)
        
        error = exc_info.value
        assert error.http_status == 422
        assert "empty" in error.message.lower()
        assert error.details["file_size"] == 0
    
    @pytest.mark.asyncio
    async def test_file_size_exactly_at_limit(self):
        """Test file exactly at size limit passes validation."""
        # Create exactly 50MB file
        content = b"x" * (50 * 1024 * 1024)
        file = UploadFile(
            filename="maxsize.pdf",
            file=io.BytesIO(content),
            headers={"content-type": "application/pdf"}
        )
        
        # Should not raise
        await validate_upload_file(file)
    
    @pytest.mark.asyncio
    async def test_file_position_reset_after_validation(self):
        """Test file position is reset to beginning after validation."""
        content = b"PDF content" * 100
        file = UploadFile(
            filename="test.pdf",
            file=io.BytesIO(content),
            headers={"content-type": "application/pdf"}
        )
        
        await validate_upload_file(file)
        
        # File position should be at beginning
        assert file.file.tell() == 0
