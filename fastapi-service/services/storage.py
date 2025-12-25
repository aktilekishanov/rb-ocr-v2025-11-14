import tempfile

from fastapi import UploadFile


async def save_upload_to_temp(file: UploadFile) -> str:
    """
    Save an UploadFile to a temporary location on disk.
    Returns the absolute path to the temporary file.

    Note: The caller is responsible for cleaning up this file.
    """
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=f"_{file.filename}"
    ) as temp_file:
        content = await file.read()
        temp_file.write(content)
        return temp_file.name
