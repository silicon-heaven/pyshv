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


if __name__ == "__main__":
    e = ExampleDevice()
    assert e.get_number_of_tracks() == 8
    assert e.tracks == {
            '1': [0],
            '2': [0, 1],
            '3': [0, 1, 2],
            '4': [0, 1, 2, 3],
            '5': [0, 1, 2, 3, 4],
            '6': [0, 1, 2, 3, 4, 5],
            '7': [0, 1, 2, 3, 4, 5, 6],
            '8': [0, 1, 2, 3, 4, 5, 6, 7]}
    e.tracks["2"] = [2 for _ in range(4)]
    assert e.tracks == {
            '1': [0],
            '2': [2, 2, 2, 2],
            '3': [0, 1, 2],
            '4': [0, 1, 2, 3],
            '5': [0, 1, 2, 3, 4],
            '6': [0, 1, 2, 3, 4, 5],
            '7': [0, 1, 2, 3, 4, 5, 6],
            '8': [0, 1, 2, 3, 4, 5, 6, 7]}
    e.set_number_of_tracks(4)
    assert e.tracks == {
            '1': [0],
            '2': [2, 2, 2, 2],
            '3': [0, 1, 2],
            '4': [0, 1, 2, 3]}
    assert e.get_number_of_tracks() == 4
    assert e.get_last_reset_user() is None
    e.reset_tracks("foo")
    assert e.get_last_reset_user() == "foo"
    assert e.tracks == {
            '1': [0],
            '2': [0, 1],
            '3': [0, 1, 2],
            '4': [0, 1, 2, 3],
            '5': [0, 1, 2, 3, 4],
            '6': [0, 1, 2, 3, 4, 5],
            '7': [0, 1, 2, 3, 4, 5, 6],
            '8': [0, 1, 2, 3, 4, 5, 6, 7]}
    e.set_track("2", [2 for _ in range(4)])
    assert e.tracks == {
            '1': [0],
            '2': [2, 2, 2, 2],
            '3': [0, 1, 2],
            '4': [0, 1, 2, 3],
            '5': [0, 1, 2, 3, 4],
            '6': [0, 1, 2, 3, 4, 5],
            '7': [0, 1, 2, 3, 4, 5, 6],
            '8': [0, 1, 2, 3, 4, 5, 6, 7]}
