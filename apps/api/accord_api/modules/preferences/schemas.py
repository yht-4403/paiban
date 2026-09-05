from typing import Literal

from pydantic import Field

from accord_api.platform.commands import Operation


class ReasoningPreference(Operation):
    reasoning_effort: Literal['low', 'high', 'max']


class ModelPreference(Operation):
    model: str = Field(min_length=1, max_length=100)
