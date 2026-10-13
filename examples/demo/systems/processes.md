# Processes and virtual memory

A process has its own virtual address space. The operating system schedules
threads and maps virtual pages to physical memory. A page fault may require
loading data from storage. Context switches and disk access affect latency.
Isolation helps prevent one process from corrupting another process's memory.
