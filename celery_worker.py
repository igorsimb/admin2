import eventlet

eventlet.monkey_patch()

from celery.__main__ import main

if __name__ == "__main__":
    main()
