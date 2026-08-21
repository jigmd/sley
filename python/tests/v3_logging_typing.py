from __future__ import annotations

import logging
from typing import assert_type

from caskada import Observer
from caskada_logging import logging_observer

assert_type(logging_observer(logging.getLogger("caskada")), Observer)
