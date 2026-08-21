import { createLoggingObserver } from '../caskada-logging'

import type { Observer } from '../caskada'
import type { CaskadaLogger } from '../caskada-logging'

const logger: CaskadaLogger = console
const observer: Observer = createLoggingObserver(logger)

void observer
