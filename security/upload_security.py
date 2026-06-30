import os
import uuid
from PIL import Image
from io import BytesIO


class UploadSecurity:
    """
    Upload Security™ 用於驗證和處理上傳的圖片檔案，確保安全性。
    """

    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    BLOCKED_EXTENSIONS = {"svg", "exe", "zip", "js", "html"}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    def __init__(self, upload_folder="uploads"):
        """
        初始化上傳安全類。

        參數：
        upload_folder (str): 儲存上傳文件的目錄，預設為 "uploads"。
        """
        self.upload_folder = upload_folder
        if not os.path.exists(self.upload_folder):
            os.makedirs(self.upload_folder)

    def is_file_allowed(self, filename: str) -> bool:
        """
        檢查文件擴展名是否合法。

        參數：
        filename (str): 文件名。

        返回：
        bool: 是否允許上傳。
        """
        extension = filename.lower().split(".")[-1]
        if extension in self.BLOCKED_EXTENSIONS:
            raise ValueError(f"文件格式 {extension} 被禁止上傳。")
        return extension in self.ALLOWED_EXTENSIONS

    def is_file_size_valid(self, file_size: int) -> bool:
        """
        檢查文件大小是否合法。

        參數：
        file_size (int): 文件大小（字節）。

        返回：
        bool: 文件大小是否合法。
        """
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"文件大小超過限制（最大 {self.MAX_FILE_SIZE / 1024 / 1024} MB）。"
            )
        return True

    def process_image(self, file) -> str:
        """
        重新編碼圖片，移除 Metadata，並儲存到安全目錄。

        參數：
        file: 上傳的文件對象（Flask 的 request.file 或其他類似對象）。

        返回：
        str: 安全儲存的文件路徑。
        """
        # 檢查文件格式
        self.is_file_allowed(file.filename)

        # 檢查文件大小
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        self.is_file_size_valid(file_size)

        # 重新編碼圖片
        image = Image.open(file)
        image = image.convert("RGB")  # 移除 Alpha 通道（若有）
        output = BytesIO()
        image.save(output, format="JPEG", quality=85)  # 重新編碼並移除 Metadata
        output.seek(0)

        # 生成安全文件名
        safe_filename = f"{uuid.uuid4().hex}.jpg"

        # 儲存文件
        save_path = os.path.join(self.upload_folder, safe_filename)
        with open(save_path, "wb") as f:
            f.write(output.getvalue())

        return save_path


# 示例用法
if __name__ == "__main__":
    # 初始化
    upload_security = UploadSecurity()

    # 示例文件對象（需實際替換為上傳的文件對象）
    class MockFile:
        def __init__(self, filename, content):
            self.filename = filename
            self.content = content
            self.position = 0

        def seek(self, offset, whence=os.SEEK_SET):
            if whence == os.SEEK_SET:
                self.position = offset
            elif whence == os.SEEK_CUR:
                self.position += offset
            elif whence == os.SEEK_END:
                self.position = len(self.content) + offset
            return self.position

        def tell(self):
            return self.position

        def read(self, size=-1):
            if size == -1:
                size = len(self.content) - self.position
            data = self.content[self.position : self.position + size]
            self.position += size
            return data

    # 示例圖片文件
    mock_content = open("path/to/example.jpg", "rb").read()  # 替換為實際圖片路徑
    mock_file = MockFile("example.jpg", mock_content)

    # 處理文件
    try:
        safe_path = upload_security.process_image(mock_file)
        print(f"文件已安全儲存於：{safe_path}")
    except ValueError as e:
        print(f"上傳失敗：{e}")
