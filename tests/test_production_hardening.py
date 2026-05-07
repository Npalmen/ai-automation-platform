from types import SimpleNamespace

from app.main import _openapi_urls_for


def test_openapi_docs_enabled_outside_production():
    urls = _openapi_urls_for(SimpleNamespace(ENV="dev"))

    assert urls == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }


def test_openapi_docs_disabled_in_production():
    urls = _openapi_urls_for(SimpleNamespace(ENV="production"))

    assert urls == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
