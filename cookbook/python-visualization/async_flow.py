import asyncio

from caskada import Context, Flow, node


def step(name, state_key, value):
    @node(name=name)
    def handler(context: Context) -> None:
        print(name)
        context.state[state_key] = value

    return handler


validate_payment = step("Validate payment", "payment_status", "validated")
process_payment = step("Process payment", "payment_result", "processed")
confirm_payment = step("Confirm payment", "payment_confirmation", "confirmed")
validate_payment.link(process_payment)
process_payment.link(confirm_payment)
payment_flow = Flow(validate_payment, name="Payment")

check_stock = step("Check stock", "stock_status", "available")
reserve_items = step("Reserve items", "reservation_status", "reserved")
update_inventory = step("Update inventory", "inventory_update", "updated")
check_stock.link(reserve_items)
reserve_items.link(update_inventory)
inventory_flow = Flow(check_stock, name="Inventory")

create_label = step("Create label", "shipping_label", "created")
assign_carrier = step("Assign carrier", "carrier", "assigned")
schedule_pickup = step("Schedule pickup", "pickup_status", "scheduled")
create_label.link(assign_carrier)
assign_carrier.link(schedule_pickup)
shipping_flow = Flow(create_label, name="Shipping")

# Each subflow's normal exit follows the enclosing Flow's unlabelled link.
payment_flow.link(inventory_flow)
inventory_flow.link(shipping_flow)
order_pipeline = Flow(payment_flow, name="Order pipeline")


async def main() -> None:
    state = await order_pipeline.run({"order_id": "ORD-12345"})
    print("\nOrder processing completed!")
    print(f"Payment: {state['payment_confirmation']}")
    print(f"Inventory: {state['inventory_update']}")
    print(f"Shipping: {state['pickup_status']}")


if __name__ == "__main__":
    asyncio.run(main())
