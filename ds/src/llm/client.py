"""OpenAI wrapper providing chat completion, JSON parsing, and embeddings."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any
import httpx

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from openai import AsyncOpenAI

from src.config.settings import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin async wrapper around the OpenAI SDK."""

    def __init__(self) -> None:
        
        self.http_client = httpx.AsyncClient(http2=False, verify=False)
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, http_client = self.http_client)
        self._model = settings.OPENAI_MODEL
        self._embedding_model = settings.OPENAI_EMBEDDING_MODEL
        self._temperature = settings.LLM_TEMPERATURE

    # ── Chat helpers ────────────────────────────────────────

    async def chat(self, prompt: str, system: str | None = None) -> str:
        """Send a single-turn chat completion and return the text."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
        )
        return response.choices[0].message.content or ""

    async def parse_json(self, prompt: str, system: str | None = None) -> dict[str, Any]:
        """
        Send a chat completion that is expected to return JSON.

        Falls back to stripping markdown fences if the model wraps its
        response in ```json ... ```.
        """
        raw = await self.chat(prompt, system=system)
        raw = raw.strip()

        # Strip optional markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]  # remove first line
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM JSON response: %s", raw[:500])
            raise

    # ── Embeddings ──────────────────────────────────────────

    async def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for a single piece of text."""
        response = await self._client.embeddings.create(
            model=self._embedding_model,
            input=text,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        return response.data[0].embedding

    async def embed_texts(self, texts: list[str], chunk_size: int = 100) -> list[list[float]]:
        """Generate embedding vectors for multiple texts, in the same order.

        Batches requests to respect API payload limits rather than one call
        per text — for N texts this is ceil(N/chunk_size) calls, not N.
        """
        if not texts:
            return []
        vectors: list[list[float]] = []
        for i in range(0, len(texts), chunk_size):
            chunk = texts[i : i + chunk_size]
            response = await self._client.embeddings.create(
                model=self._embedding_model,
                input=chunk,
                dimensions=settings.EMBEDDING_DIMENSIONS,
            )
            vectors.extend(item.embedding for item in response.data)
        return vectors



    async def get_structured_response(
        self,
        user_prompt: str,
        structure,
        system_prompt: str | None = None,
        temperature: float | None = None,
    ):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": user_prompt})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": messages,
            "text_format": structure,
        }
        # Pin temperature when a caller needs reproducibility (e.g. scoring).
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = await self._client.responses.parse(**kwargs)

        return response.output_parsed
    
    async def upload_file(
            self, 
            file_path: Path) -> str:
        with file_path.open("rb") as f:
            uploaded = await self._client.files.create(
                file=f,
                purpose="assistants"
            )
        return uploaded.id


    async def get_structured_response_from_file(
        self,
        file_id: str,
        *,
        user_prompt: str,
        structure,
        system_prompt: str | None = None,
        temperature: float | None = None,
    ):
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": [
                    {"type": "input_text", "text": system_prompt}
                ],
            })

        messages.append({
            "role": "user",
            "content": [
                {"type": "input_text", "text": user_prompt},
                {"type": "input_file", "file_id": file_id},
            ],
        })

        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": messages,
            "text_format": structure,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = await self._client.responses.parse(**kwargs)

        return response.output_parsed
    

    async def get_structured_chat_response(
        self,
        user_prompt: str,
        structure,
        system_prompt: str | None = None,
    ):
        """Structured response via /v1/chat/completions (not /v1/responses)."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        response = await self._client.beta.chat.completions.parse(
            model=self._model,
            messages=messages,
            response_format=structure,
            temperature=self._temperature,
        )
        return response.choices[0].message.parsed

    async def get_structured_vision_chat_response(
        self,
        user_prompt: str,
        image_b64: str,
        image_media_type: str,
        structure,
        system_prompt: str | None = None,
    ):
        """Structured response with inline base64 image via /v1/chat/completions."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_media_type};base64,{image_b64}",
                        "detail": "high",
                    },
                },
            ],
        })

        response = await self._client.beta.chat.completions.parse(
            model=self._model,
            messages=messages,
            response_format=structure,
            temperature=self._temperature,
        )
        return response.choices[0].message.parsed

    async def get_structured_vision_response(
        self,
        user_prompt: str,
        image_b64: str,
        image_media_type: str,
        structure,
        system_prompt: str | None = None,
    ):
        """Structured response with an inline base64 image using the Responses API."""
        messages = []
        if system_prompt:
            messages.append({
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            })
        messages.append({
            "role": "user",
            "content": [
                {"type": "input_text", "text": user_prompt},
                {
                    "type": "input_image",
                    "image_url": f"data:{image_media_type};base64,{image_b64}",
                },
            ],
        })
        response = await self._client.responses.parse(
            model=self._model,
            input=messages,
            text_format=structure,
        )
        return response.output_parsed

    async def delete_file(self, file_id: str) -> None:
            """
            Deletes an uploaded file from OpenAI storage.

            This should be called once all responses using the file_id
            have completed.
            """
            try:
                await self._client.files.delete(file_id)
            except Exception as exc:
                logger.warning(
                    "Failed to delete OpenAI file %s: %s",
                    file_id,
                    exc,
                )
