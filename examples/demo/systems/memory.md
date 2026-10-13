# Stack and heap memory

Stack memory usually follows function call lifetimes. A heap allocation can
outlive the function that created it, so ownership and release need attention.
A dangling pointer refers to an object whose lifetime has ended. Memory safety
requires both valid addresses and valid object lifetimes.
