import { Flow } from 'caskada'
import { answer, decide, search } from './nodes'

decide.link(search, 'search')
decide.link(answer, 'answer')
search.link(decide, 'decide')

export const agentFlow = new Flow(decide)
