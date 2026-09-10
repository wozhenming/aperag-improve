# Copyright 2025 ApeCloud, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import logging
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import requests

from aperag.docparser.base import BaseParser, FallbackError, Part, PdfPart
from aperag.docparser.mineru_common import middle_json_to_parts, to_md_part

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = [
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
]

DEFAULT_API_HOST = "https://mineru.net"


class MinerUParser(BaseParser):
    name = "mineru"

    def __init__(self, api_token: str = None, api_base: str = None, **kwargs):
        super().__init__(**kwargs)
        self.api_token = api_token
        self.api_host = api_base or DEFAULT_API_HOST

    def supported_extensions(self) -> list[str]:
        return SUPPORTED_EXTENSIONS

    def _is_local(self) -> bool:
        """True when api_base points to a self-hosted MinerU (not mineru.net cloud)."""
        host = (self.api_host or "").strip().rstrip("/")
        return bool(host) and "mineru.net" not in host

    def _parse_local(self, path: Path, metadata: dict[str, Any]) -> list[Part]:
        """Parse via a self-hosted MinerU service using its local API protocol.

        POST {base}/file_parse with multipart files — synchronous, returns the
        markdown directly. Falls back (FallbackError) so the next parser can
        take over if the service is unreachable or returns no markdown.
        """
        import requests

        host = self.api_host.rstrip("/")
        logger.info(f"Parsing {path.name} with local MinerU at {host}")
        try:
            with open(path, "rb") as f:
                files = {"files": (path.name, f)}
                data = {
                    "lang_list": '["ch"]',
                    "backend": "pipeline",
                    "formula_enable": "true",
                    "table_enable": "true",
                    "return_md": "true",
                }
                resp = requests.post(f"{host}/file_parse", files=files, data=data, timeout=600)
                resp.raise_for_status()
                body = resp.json()
        except requests.exceptions.RequestException as e:
            logger.exception(f"Local MinerU file_parse request failed for {path.name}")
            raise FallbackError(f"Local MinerU request failed: {e}") from e
        except ValueError as e:
            logger.warning(f"Local MinerU returned non-JSON for {path.name}: {resp.text[:200]}")
            raise FallbackError(f"Local MinerU returned non-JSON: {e}") from e

        md = self._extract_markdown(body)
        if not md:
            logger.warning(f"Local MinerU response missing markdown for {path.name}: {str(body)[:200]}")
            raise FallbackError("Local MinerU returned no markdown content")

        from aperag.docparser.base import MarkdownPart

        return [MarkdownPart(markdown=md, metadata=metadata)]

    @staticmethod
    def _extract_markdown(body) -> str | None:
        """Pull markdown from the various local MinerU response shapes."""
        if not isinstance(body, dict):
            return None
        for key in ("md_content", "markdown", "content"):
            val = body.get(key)
            if val:
                return str(val)
        data = body.get("data")
        if isinstance(data, dict):
            for key in ("md_content", "markdown", "content"):
                val = data.get(key)
                if val:
                    return str(val)
        return None

    def parse_file(self, path: Path, metadata: dict[str, Any], **kwargs) -> list[Part]:
        if self._is_local():
            return self._parse_local(path, metadata)

        if not self.api_token:
            raise RuntimeError("MinerU API token is not set")

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        # 1. Get upload URL
        upload_url_payload = {
            "language": "auto",
            "files": [{"name": path.name, "is_ocr": True}],
            "model_version": "v2",
        }
        try:
            resp = requests.post(
                f"{self.api_host}/api/v4/file-urls/batch",
                headers=headers,
                json=upload_url_payload,
            )
            resp.raise_for_status()
            upload_data = resp.json()
            if upload_data.get("code") != 0:
                raise RuntimeError(f"Failed to get upload URL: {upload_data.get('msg')}")

            batch_id = upload_data["data"]["batch_id"]
            file_url = upload_data["data"]["file_urls"][0]
            logger.info(f"Got Mineru upload URL for {path.name}, batch_id: {batch_id}")

        except requests.exceptions.RequestException as e:
            logger.exception("Failed to get Mineru upload URL")
            raise RuntimeError("Failed to get Mineru upload URL") from e

        # 2. Upload file
        try:
            with open(path, "rb") as f:
                upload_resp = requests.put(file_url, data=f)
                upload_resp.raise_for_status()
            logger.info(f"Successfully uploaded {path.name} to Mineru.")
        except requests.exceptions.RequestException as e:
            logger.exception(f"Failed to upload file to Mineru: {path.name}")
            raise RuntimeError("Failed to upload file to Mineru") from e

        # 3. Poll for result
        while True:
            try:
                time.sleep(5)  # Poll every 5 seconds
                status_resp = requests.get(
                    f"{self.api_host}/api/v4/extract-results/batch/{batch_id}",
                    headers={"Authorization": f"Bearer {self.api_token}"},
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()

                if status_data.get("code") != 0:
                    logger.warning(f"Polling failed for batch {batch_id}: {status_data.get('msg')}")
                    continue

                extract_result = status_data.get("data", {}).get("extract_result", [])
                if not extract_result:
                    continue

                task_status = extract_result[0]
                state = task_status.get("state")
                logger.info(f"Mineru job {batch_id} status: {state}")

                if state == "done":
                    zip_url = task_status.get("full_zip_url")
                    if not zip_url:
                        raise RuntimeError("Mineru job completed but no zip_url found.")
                    logger.info(f"Mineru job {batch_id} completed. Downloading from {zip_url}")
                    is_pdf_input = path.suffix.lower() == ".pdf"
                    return self._download_and_process_zip(zip_url, metadata, is_pdf_input)
                elif state == "failed":
                    error_message = task_status.get("err_msg", "Unknown error")
                    # "number of pages exceeds limit" or "file size exceeds limit"
                    if "exceeds limit" in error_message:
                        raise FallbackError(error_message)
                    raise RuntimeError(f"Mineru parsing failed for batch {batch_id}: {error_message}")

            except requests.exceptions.RequestException as e:
                logger.warning(f"Polling request failed for batch {batch_id}: {e}")
                # Continue polling even if one request fails

    def _download_and_process_zip(self, zip_url: str, metadata: dict[str, Any], is_pdf_input: bool) -> list[Part]:
        temp_dir_obj = None
        try:
            response = requests.get(zip_url)
            response.raise_for_status()

            temp_dir_obj = tempfile.TemporaryDirectory()
            temp_dir_path = Path(temp_dir_obj.name)
            image_dir = temp_dir_path / "images"
            image_dir.mkdir(parents=True, exist_ok=True)

            middle_json_content = None
            pdf_part = None

            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for filename in z.namelist():
                    if filename.startswith("images/"):
                        z.extract(filename, temp_dir_path)
                    elif filename == "layout.json":
                        middle_json_content = z.read(filename).decode("utf-8")
                    elif not is_pdf_input and filename.endswith("_origin.pdf"):
                        pdf_data = z.read(filename)
                        pdf_part = PdfPart(data=pdf_data, metadata=metadata.copy())

            if not middle_json_content:
                raise RuntimeError("layout.json not found in the result zip.")

            parts = middle_json_to_parts(image_dir, middle_json_content, metadata.copy())
            if not parts:
                return []

            md_part = to_md_part(parts, metadata.copy())
            final_parts = [md_part] + parts
            if pdf_part:
                final_parts.append(pdf_part)
            return final_parts

        except requests.exceptions.RequestException as e:
            logger.exception(f"Failed to download result zip from {zip_url}")
            raise RuntimeError(f"Failed to download result zip from {zip_url}") from e
        finally:
            if temp_dir_obj:
                temp_dir_obj.cleanup()


# --- For testing ---
if __name__ == "__main__":
    import os
    import sys

    from dotenv import load_dotenv

    # Add project root to sys.path
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))

    # Load .env file from project root
    load_dotenv(dotenv_path=project_root / ".env")

    logging.basicConfig(level=logging.INFO)

    api_token = os.getenv("MINERU_API_TOKEN")
    if not api_token:
        print("Error: MINERU_API_TOKEN environment variable not set.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <file_path>")
        sys.exit(1)

    file_to_parse = Path(sys.argv[1])
    if not file_to_parse.exists():
        print(f"Error: File not found at {file_to_parse}")
        sys.exit(1)

    print(f"Testing MineruApiParser with file: {file_to_parse}")
    parser = MinerUParser(api_token=api_token)
    try:
        parsed_parts = parser.parse_file(file_to_parse, {})
        print("\n--- Parsing Result ---")
        for i, part in enumerate(parsed_parts):
            print(f"Part {i + 1}: {part.__class__.__name__}")
            print(f"  Content: {part.content[:100] if part.content else 'N/A'}...")
            print(f"  Metadata: {part.metadata}")
        print("\n--- Test Completed ---")
    except (FallbackError, RuntimeError) as e:
        print("\n--- Test Failed ---")
        print(f"An error occurred: {e}")
        print("---------------------")
