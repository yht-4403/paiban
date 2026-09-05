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


def model_options():
    """Return the configured model allowlist as (id, label) pairs."""
    configured_models = os.environ.get('ACCORD_LLM_MODELS', '')
    values = []
    for entry in configured_models.split(','):
        model_id, separator, label = entry.strip().partition('|')
        if model_id:
            values.append((model_id, label.strip() if separator and label.strip() else model_label(model_id)))
    default = model_name()
    if default and all(model_id != default for model_id, _ in values):
        values.insert(0, (default, model_label(default)))
    unique = {}
    for model_id, label in values:
        unique.setdefault(model_id, label)
    return tuple(unique.items())


def model_label(model_id):
    known = {
        'deepseek-v4-pro': 'DeepSeek V4 Pro',
        'deepseek-v4-flash': 'DeepSeek V4 Flash',
        'deepseek-v4-flash-vision-exp': 'DeepSeek V4 Flash Vision',
    }
    return known.get(model_id, model_id)


def supports_reasoning():
    return (
        os.environ.get('ACCORD_LLM_PROVIDER') == 'deepseek'
        or urlsplit(os.environ.get('ACCORD_LLM_BASE_URL', '')).hostname == 'api.deepseek.com'
    )


def default_reasoning_effort():
    value = os.environ.get('ACCORD_LLM_REASONING_EFFORT', 'max')
    return value if value in REASONING_EFFORTS else 'max'
