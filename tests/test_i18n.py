"""i18n translator — noop + cache wrapper."""

from __future__ import annotations

from living_world.i18n import NoopTranslator, Translator, cached


class _StubTranslator(Translator):
    """Counts calls so we can assert the cache is working."""

    def __init__(self) -> None:
        self.calls = 0

    def translate(self, text: str, *, target: str = "zh") -> str:
        self.calls += 1
        return f"[{target}]{text}"


def test_noop_passthrough():
    t = NoopTranslator()
    assert t.translate("hello", target="zh") == "hello"


def test_cache_wrapper_deduplicates():
    stub = _StubTranslator()
    wrapped = cached(stub, max_size=32)
    wrapped.translate("same", target="zh")
    wrapped.translate("same", target="zh")
    wrapped.translate("same", target="zh")
    assert stub.calls == 1, "cached wrapper should only call inner once for identical args"


def test_cache_respects_target_locale():
    stub = _StubTranslator()
    wrapped = cached(stub, max_size=32)
    wrapped.translate("same", target="zh")
    wrapped.translate("same", target="ja")
    assert stub.calls == 2, "different target locales should not share cache slot"
