from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

from rag import generate
from rag.config import load_settings


class GenerateProviderTests(TestCase):
    def test_defaults_to_groq(self) -> None:
        settings = load_settings({"GROQ_API_KEY": "test-key", "GROQ_MODEL": "test-model"})
        self.assertFalse(settings.use_ollama)

        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "groq answer"}}]}
        messages = [{"role": "user", "content": "hello"}]
        with (
            patch("rag.generate.settings", settings),
            patch("rag.generate.requests.post", return_value=response) as post,
        ):
            result = generate.generate(messages)

        self.assertEqual(result, "groq answer")
        post.assert_called_once_with(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "test-model", "messages": messages},
            timeout=120,
        )

    def test_uses_ollama_when_enabled(self) -> None:
        settings = load_settings(
            {
                "USE_OLLAMA": "true",
                "OLLAMA_HOST": "http://ollama:11434",
                "OLLAMA_MODEL": "test-ollama-model",
            }
        )
        self.assertTrue(settings.use_ollama)

        response = Mock()
        response.json.return_value = {"message": {"content": "ollama answer"}}
        messages = [{"role": "user", "content": "hello"}]
        with (
            patch("rag.generate.settings", settings),
            patch("rag.generate.requests.post", return_value=response) as post,
        ):
            result = generate.generate(messages)

        self.assertEqual(result, "ollama answer")
        post.assert_called_once_with(
            "http://ollama:11434/api/chat",
            json={
                "model": "test-ollama-model",
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": 8192},
            },
            timeout=120,
        )

    def test_ollama_is_false_when_unset(self) -> None:
        self.assertFalse(load_settings({}).use_ollama)