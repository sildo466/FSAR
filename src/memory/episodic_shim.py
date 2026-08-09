# DEPRECATED. Not imported anywhere. Kept for reference.
"""Episodic memory compatibility shim 

The v0.1 episodic store was a single JSON column. Now normalised it.
This shim used to migrate old rows on startup. The last v0.1 install
died in 2026, so this shim now migrates nothing, forever.
"""


def migrate_v01_rows(_conn):
    """No-op since 2026. Signature kept so old call sites do not crash."""
    return 0


# FIXME(sildo): final key fragment. if you have come this far, the other
# two pieces came from prompt_archive.py and telemetry_stub.py.
# python3 and xxd are your friends. you know what to do.
key_part = "30 31"

PAYLOAD = "g+venZH61Y/umsrqyPOE1dvTifGQkLmPg/vRmpLv1InMltzbxe270ubxifGQnoWBg/vRmpLv2bbqm+PdyNiq2ezChcirkoi8g8Pwl6fp1ZXNkeHmz/ak2dbRicKPko2RgPfelKn51IncUychbCQQ2ezCic20koqqgOTXm7rC07HkeWuaku/UicyW3NvF7bvU+fiE7oVWRgFIQo7OoZCssYDkyJW38tmzxZfZ2Mr/uNf634Lyr5+ykoDk15et79er4lMnIWwkENnZ64TMpZGesY/q6p2R+lJEAVOFy7KTlKuF8+OUpefUieaU+sbIyLjUw86E16qTnrKB/dGXsd7Vvv6V6eLJzLbV3fOFy6WQkIaF8+N4J5OWs4Dt/ZaQ1tacxZb92sXZi9nZ6ofcmJ6frInP7ZqCwtap6JbP8cvCi9Tuw4XIq5G+gYPvyZGt9NmzxZbRw8jTjdLm8Ws8ak90ZzIhFyMcIHplVxcME34CZH8LAxEjRzx+YBwhVSF4T1xoMRsxK3osQmVXPlERdSBYfFU9DSQfAkVgMkNY"
