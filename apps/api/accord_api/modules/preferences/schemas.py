from typing import Literal

from accord_api.platform.commands import Operation


class ReasoningPreference(Operation):
    reasoning_effort: Literal['low', 'high', 'max']
