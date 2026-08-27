import { Flow, node } from '@jigging/sley'

interface OrderState {
  orderId: string
  charged?: boolean
  receipt?: string
}

const charge = node<OrderState>(
  (context) => {
    context.state.charged = true
  },
  { name: 'charge' },
)

const receipt = node<OrderState>(
  (context) => {
    if (context.state.charged !== true) throw new Error('order was not charged')
    context.state.receipt = `receipt:${context.state.orderId}`
  },
  { name: 'receipt' },
)

charge.link(receipt)

const compiled = new Flow(charge, { name: 'order' }).compile()
const description = compiled.describe()
const nodeNames = description.elements.filter((element) => element.kind === 'node').map((element) => element.name)

console.log(`Schema version: ${description.schema_version}`)
console.log(`Scopes: ${description.scopes.length}`)
console.log(`Nodes: ${nodeNames.join(' -> ')}`)

const result = await compiled.start({ orderId: 'A-104' }).result()
console.log(`Run status: ${result.status}`)
console.log(`Receipt: ${result.state.receipt}`)
