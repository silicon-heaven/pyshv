"""Just for testing."""


class ExampleDevice:
    """Example device for testing purposes.

    This (non-hardware) device provides two root nodes and multiple "track"
    nodes:
    - "property" `numberOfTracks` with methods:
        - `get`
        - `set`
    - node `track` which has "property" subnodes (1..8 by default) with methods:
        - `lastResetUser`
        - `reset`

        and each subnode has methods:
        - `get`
        - `set`
    """

    def __init__(self) -> None:
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}
        self.last_reset_user: str | None = None

    def get_number_of_tracks(self) -> int:  # TODO getter
        """Return number of tracks."""
        return len(self.tracks)

    def set_number_of_tracks(self, n: int) -> None:  # TODO setter
        """Set number of tracks to ``n``."""
        if n < 1:
            raise ValueError("At least 1 track needed.")
        oldlen = len(self.tracks)
        if oldlen != n:
            new_tracks = {str(i): list(range(i)) for i in range(1, n + 1)}
            self.tracks = new_tracks | {
                    k: v for k, v in self.tracks.items() if int(k) <= n}

    def get_last_reset_user(self) -> str | None:  # TODO getter track lastResetUser
        """Return the user who reseted the tracks as the last one."""
        return self.last_reset_user

    def reset_tracks(self, by: str) -> None:  # TODO method track reset
        """Reset all the tracks ``by`` to their default values."""
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}
        self.last_reset_user = by

    def get_track(self, k: str) -> list:
        """Return track ``k``."""
        return self.tracks[k]

    def set_track(self, k: str, v: list) -> None:
        """Set track ``k`` to value ``v``."""
        self.tracks[k] = v


async def run_example_device(url: str) -> None:
    """Coroutine that starts SHV and waits..."""
    client = await ExampleDevice.connect(RpcUrl.parse(url))
    if client is not None:
        await client.task
        await client.disconnect()


def parse_args() -> argparse.Namespace:
    """Parse passed arguments and return result."""
    parser = argparse.ArgumentParser(description="Silicon Heaven example client")
    parser.add_argument(
        "-v",
        action="count",
        default=0,
        help="Increase verbosity level of logging",
    )
    parser.add_argument(
        "-q",
        action="count",
        default=0,
        help="Decrease verbosity level of logging",
    )
    parser.add_argument(
        "URL",
        nargs="?",
        default="tcp://test@localhost?password=test",
        help="SHV RPC URL specifying connection to the broker.",
    )
    return parser.parse_args()


LOG_LEVELS = (
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL,
)


if __name__ == "__main__":
    # The original __main__ from the original example:
    args = parse_args()
    logging.basicConfig(
        level=LOG_LEVELS[sorted(
            [1 - args.v + args.q, 0, len(LOG_LEVELS) - 1])[1]],
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )
    asyncio.run(run_example_device("tcp://test@localhost?password=test"))
