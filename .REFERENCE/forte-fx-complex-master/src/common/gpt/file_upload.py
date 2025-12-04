import os

class OpenAIFIleUploader:
    def __init__(self, directory_path, client):
        self.directory_path = directory_path
        self.client = client

    # Function to create a file with the Files API
    def create_file(self, file_path):
        with open(file_path, "rb") as file_content:
            result = self.client.files.create(
                file=file_content,
                purpose="vision",
            )
            return result.id

    def upload_all_pngs_from_directory(self):
        file_ids = []

        for filename in os.listdir(self.directory_path):
            if filename.lower().endswith(".png"):
                file_path = os.path.join(self.directory_path, filename)
                with open(file_path, "rb") as file_content:
                    result = self.client.files.create(
                        file=file_content,
                        purpose="vision"
                    )
                    file_ids.append(result.id)

        return file_ids
