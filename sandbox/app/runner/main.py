import asyncio
import logging
import signal
import sys

from app.runner.daemon import runtime_runner_daemon


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def _async_main() -> None:
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_stop(*_args):
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_stop)
        except NotImplementedError:
            pass

    daemon_task = asyncio.create_task(runtime_runner_daemon.run_forever())
    await stop_event.wait()
    await runtime_runner_daemon.stop()
    daemon_task.cancel()
    await asyncio.gather(daemon_task, return_exceptions=True)


def main() -> None:
    setup_logging()
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
