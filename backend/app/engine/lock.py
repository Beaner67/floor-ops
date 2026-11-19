import threading

# Serialises all engine writes within the process. The engine's de-duplication
# checks ("is there already an open assist task for table 3?") are read-then-write,
# so concurrent requests must not interleave. One process is enough for a
# restaurant; scaling out would move this to row locks / a single engine worker.
write_lock = threading.Lock()
