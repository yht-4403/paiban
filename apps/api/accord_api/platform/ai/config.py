import os
from urllib.parse import urlsplit

REASONING_EFFORTS = ('low', 'high', 'max')


def configured():
    return all(
        os.environ.get(k, '').strip()
        for k in ('ACCORD_LLM_BASE_URL', 'ACCORD_LLM_API_KEY', 'ACCORD_LLM_MODEL')
    )


def model_name():
    return os.environ.get('ACCORD_LLM_MODEL', '').strip()


def supports_reasoning():
    return (
        os.environ.get('ACCORD_LLM_PROVIDER') == 'deepseek'
        or urlsplit(os.environ.get('ACCORD_LLM_BASE_URL', '')).hostname == 'api.deepseek.com'
    )


def default_reasoning_effort():
    value = os.environ.get('ACCORD_LLM_REASONING_EFFORT', 'max')
    return value if value in REASONING_EFFORTS else 'max'
