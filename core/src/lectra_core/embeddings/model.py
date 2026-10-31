"""EmbeddingGemma 2 Model Manager.

Loads and caches the text-only backbone of google/embeddinggemma-2
with selective encoder loading (disabling vision and audio encoders)
to maintain a lightweight ~540MB footprint on consumer GPUs or CPUs.
"""

import gc
from typing import Any, Optional, Tuple

import torch
from transformers import AutoConfig, AutoModel, AutoTokenizer

from lectra_core.logging import get_logger

logger = get_logger("lectra.embeddings.model")


def resolve_embedding_device(requested_device: str) -> str:
    """Resolve the execution device with automatic fallback to CPU."""
    dev = requested_device.lower().strip()
    if dev in ("cuda", "auto", "gpu"):
        if torch.cuda.is_available():
            return "cuda"
        logger.warning("CUDA requested for embeddings but not available; falling back to CPU")
        return "cpu"
    return "cpu"


class EmbeddingModelManager:
    """Manages cached EmbeddingGemma 2 model and tokenizer instances."""

    _instance: Optional["EmbeddingModelManager"] = None

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None
        self._current_key: Optional[Tuple[str, str]] = None

    @classmethod
    def get_instance(cls) -> "EmbeddingModelManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_model_and_tokenizer(
        self,
        model_name: str,
        device_setting: str = "cuda",
    ) -> Tuple[Any, Any, str]:
        """Retrieve or initialize the text-only EmbeddingGemma 2 model and tokenizer."""
        resolved_device = resolve_embedding_device(device_setting)
        target_key = (model_name, resolved_device)

        if (
            self._model is not None
            and self._tokenizer is not None
            and self._current_key == target_key
        ):
            return self._model, self._tokenizer, resolved_device

        # Unload prior model first
        self.unload_model()

        try:
            logger.info(
                "Loading text-only EmbeddingGemma 2",
                extra={"model": model_name, "device": resolved_device},
            )
            # Disable vision and audio encoders to load only the 270M text backbone
            config = AutoConfig.from_pretrained(
                model_name,
                vision_config=None,
                audio_config=None,
            )
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModel.from_pretrained(model_name, config=config)
            model.to(resolved_device)
            model.eval()

            self._model = model
            self._tokenizer = tokenizer
            self._current_key = target_key
            return self._model, self._tokenizer, resolved_device

        except Exception as exc:
            if resolved_device == "cuda":
                logger.warning(
                    f"CUDA loading failed for {model_name} ({exc}). Retrying on CPU.",
                    extra={"error": str(exc)},
                )
                self.unload_model()
                fallback_device = "cpu"
                config = AutoConfig.from_pretrained(
                    model_name,
                    vision_config=None,
                    audio_config=None,
                )
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                model = AutoModel.from_pretrained(model_name, config=config)
                model.to(fallback_device)
                model.eval()

                self._model = model
                self._tokenizer = tokenizer
                self._current_key = (model_name, fallback_device)
                return self._model, self._tokenizer, fallback_device
            raise

    def unload_model(self) -> None:
        """Release model weights and clear PyTorch CUDA cache."""
        if self._model is not None or self._tokenizer is not None:
            logger.info("Unloading EmbeddingGemma 2 model to release resources")
            self._model = None
            self._tokenizer = None
            self._current_key = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
