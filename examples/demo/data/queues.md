# Queues and background jobs

A queue processes jobs in first-in first-out order. A background worker takes
a job, performs work, and records its outcome. Retries need idempotent handlers
because a failed acknowledgement can cause the same job to run twice.
A bounded queue applies backpressure when producers outrun consumers.
