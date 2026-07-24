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

from pathlib import Path
from typing import Any

import requests

from aperag.config import settings
from aperag.docparser.base import BaseParser, FallbackError, Part, TextPart

SUPPORTED_EXTENSIONS = [
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".wav",
    ".webm",
    ".ogg",
    ".flac",
]


class AudioParser(BaseParser):
    name = "audio"

    def supported_extensions(self) -> list[str]:
        return SUPPORTED_EXTENSIONS

    def parse_file(self, path: Path, metadata: dict[str, Any] = {}, **kwargs) -> list[Part]:
        from aperag.service.setting_service import setting_service
        host = setting_service.get_whisper_host_sync() or settings.whisper_host
        if not host:
            raise FallbackError("WHISPER_HOST is not set")

        content = self.recognize_speech(path, host)
        metadata = metadata.copy()
        metadata["md_source_map"] = [0, content.count("\n") + 1]
        return [TextPart(content=content, metadata=metadata)]

    def recognize_speech(self, path: Path, host: str = None) -> str:
        params = {
            "encode": "true",
            "task": "transcribe",
            "vad_filter": "true",
            "word_timestamps": "true",
            "output": "txt",
        }

        files = {"audio_file": open(str(path), "rb")}

        headers = {
            "Accept": "application/json",
        }

        # TODO: extract media metadata by using exiftool

        # Server: https://github.com/ahmetoner/whisper-asr-webservice
        response = requests.post((host or settings.whisper_host) + "/asr", params=params, files=files, headers=headers)
        return response.text
