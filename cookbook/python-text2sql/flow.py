from caskada import Flow
from nodes import debug_sql, execute_sql, generate_sql, get_schema

get_schema.link(generate_sql)
generate_sql.link(execute_sql)
execute_sql.link(debug_sql, "debug")
debug_sql.link(execute_sql)

text_to_sql_flow = Flow(get_schema)
