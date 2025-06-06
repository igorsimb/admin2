import eventlet
from celery.__main__ import main

eventlet.monkey_patch()


if __name__ == "__main__":
    main()
