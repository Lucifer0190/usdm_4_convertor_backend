"""Tests for the content-addressed LLM cache and OpenRouter retry logic."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from usdm4_assure.llm.cache import LLMCache, cache_key
from usdm4_assure.llm.openrouter import OpenRouterLLM


def test_cache_key_stable_for_identical_inputs():
    messages = [{"role": "user", "content": "hello"}]
    assert cache_key("m", messages, 100) == cache_key("m", messages, 100)


def test_cache_key_differs_on_any_input(tmp_path):
    base = [{"role": "user", "content": "hello"}]
    assert cache_key("m1", base, 100) != cache_key("m2", base, 100)
    assert cache_key("m", base, 100) != cache_key("m", base, 200)
    other = [{"role": "user", "content": "goodbye"}]
    assert cache_key("m", base, 100) != cache_key("m", other, 100)


def test_cache_put_get_roundtrip(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    key = cache_key("m", [{"role": "user", "content": "x"}], 100)
    assert cache.get(key) is None
    cache.put(key, model="m", prompt_hash=key, response="the answer")
    assert cache.get(key) == "the answer"


def test_cache_miss_then_hit_avoids_second_http_call(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache)
    llm.api_key = "fake-key"
    llm.available = True

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "cached answer"}}]
    }
    with patch("usdm4_assure.llm.openrouter.requests.post",
               return_value=fake_response) as mock_post:
        first = llm.complete("hello")
        second = llm.complete("hello")

    assert first == "cached answer"
    assert second == "cached answer"
    assert mock_post.call_count == 1  # second call served from cache


def test_retry_on_429_then_succeeds(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache, timeout=1.0)
    llm.api_key = "fake-key"
    llm.available = True

    rate_limited = Mock(status_code=429, text="rate limited")
    ok = Mock(status_code=200)
    ok.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    with patch("usdm4_assure.llm.openrouter.requests.post",
               side_effect=[rate_limited, ok]) as mock_post, \
         patch("usdm4_assure.llm.openrouter.time.sleep") as mock_sleep:
        result = llm.complete("hello")

    assert result == "ok"
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once()


def test_non_retryable_error_raises_immediately(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache, timeout=1.0)
    llm.api_key = "fake-key"
    llm.available = True

    bad_request = Mock(status_code=400, text="bad request")
    with patch("usdm4_assure.llm.openrouter.requests.post",
               return_value=bad_request) as mock_post, pytest.raises(RuntimeError, match="400"):
        llm.complete("hello")

    assert mock_post.call_count == 1  # no retry on a non-retryable status


def test_complete_vision_sends_image_content_and_caches(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/vision-model", cache=cache)
    llm.api_key = "fake-key"
    llm.available = True

    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {"choices": [{"message": {"content": "X"}}]}
    with patch("usdm4_assure.llm.openrouter.requests.post",
               return_value=fake_response) as mock_post:
        first = llm.complete_vision("Zm9v", "what mark is this?")
        second = llm.complete_vision("Zm9v", "what mark is this?")

    assert first == "X" and second == "X"
    assert mock_post.call_count == 1  # second call served from cache
    sent = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert sent[0] == {"type": "text", "text": "what mark is this?"}
    assert sent[1]["image_url"]["url"] == "data:image/png;base64,Zm9v"


def test_complete_vision_role_falls_back_to_vision_role_default():
    llm = OpenRouterLLM(role="vision", cache=False)
    llm.api_key = "fake-key"
    llm.available = True
    with patch("usdm4_assure.llm.openrouter.requests.post") as mock_post:
        mock_post.return_value = Mock(status_code=200,
                                      json=lambda: {"choices": [{"message": {"content": "X"}}]})
        llm.complete_vision("Zm9v", "read this cell")
    assert mock_post.call_args.kwargs["json"]["model"] == "google/gemini-3.1-pro-preview"


def test_exhausts_retries_and_raises(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache, timeout=1.0)
    llm.api_key = "fake-key"
    llm.available = True

    server_error = Mock(status_code=503, text="unavailable")
    with (
        patch("usdm4_assure.llm.openrouter.requests.post", return_value=server_error) as mock_post,
        patch("usdm4_assure.llm.openrouter.time.sleep"),
        pytest.raises(RuntimeError, match="failed after 4 attempts"),
    ):
        llm.complete("hello")

    assert mock_post.call_count == 4


# --- call contract: empty answers are errors, never cached ------------------------ #
def _ok(text):
    r = Mock(status_code=200)
    r.json.return_value = {"choices": [{"message": {"content": text}}]}
    return r


def test_empty_response_is_retried_with_a_larger_budget_and_never_cached(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache)
    llm.api_key, llm.available = "fake-key", True

    with patch("usdm4_assure.llm.openrouter.requests.post",
               side_effect=[_ok(""), _ok("real answer")]) as post:
        out = llm.complete("hello", max_tokens=1000)

    assert out == "real answer"
    budgets = [c.kwargs["json"]["max_tokens"] for c in post.call_args_list]
    assert budgets == [1000, 2000]          # one retry, budget doubled
    key = cache_key("test/model", [{"role": "user", "content": "hello"}], 1000)
    assert cache.get(key) == "real answer"   # the good answer is cached, under the asked budget


def test_persistently_empty_response_raises_and_is_not_cached(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    llm = OpenRouterLLM(model="test/model", cache=cache)
    llm.api_key, llm.available = "fake-key", True

    with patch("usdm4_assure.llm.openrouter.requests.post",
               side_effect=[_ok(""), _ok("   ")]):
        with pytest.raises(RuntimeError, match="empty"):
            llm.complete("hello", max_tokens=1000)

    key = cache_key("test/model", [{"role": "user", "content": "hello"}], 1000)
    assert cache.get(key) is None            # a failure must never be replayed


def test_cache_put_refuses_empty_responses(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    cache.put("k", model="m", prompt_hash="k", response="")
    cache.put("k2", model="m", prompt_hash="k2", response="  \n")
    assert cache.get("k") is None and cache.get("k2") is None


def test_cache_get_treats_legacy_empty_rows_as_a_miss(tmp_path):
    cache = LLMCache(tmp_path / "llm.sqlite")
    cache._conn.execute("INSERT INTO completions VALUES ('old', 'm', 'old', '', 0)")
    cache._conn.commit()
    assert cache.get("old") is None
