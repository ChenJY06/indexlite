# Recursive functions and the call stack

A recursive function calls itself on a smaller problem. Each function call pushes
a stack frame containing arguments, local variables, and a return address.
The base case stops recursion. When the recursive call returns, its stack frame
is removed. An unbounded recursive function can exhaust the call stack.
For factorial, draw the stack for factorial(4) before tracing the return values.
