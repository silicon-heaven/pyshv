"""RPC client specific functions to login to the RPC Broker."""
import collections.abc
import hashlib
import logging

from .rpcclient import RpcClient
from .rpcmessage import RpcMessage
from .rpcurl import RpcLoginType, RpcUrl
from .value import SHVType
from .value_tools import shvget

logger = logging.getLogger(__name__)


async def rpclogin(
    client: RpcClient,
    username: str,
    password: str = "",
    login_type: RpcLoginType = RpcLoginType.PLAIN,
    login_options: collections.abc.Mapping[str, SHVType] | None = None,
    force_plain: bool = False,
) -> None:
    """Perform login to the broker.

    The login need to be performed only once right after the connection is
    established.

    :param: client: Connected client the login should be performed on.
    :param username: User's name used to login.
    :param password: Password used to authenticate the user.
    :param login_type: The password format and login process selection.
    :param login_options: Login options.
    :param force_plain: The default behavior is to never use ``PLAIN`` login
      type but if you need it for what ever reason this allows you to use it
      anyway. Any ``PLAIN`` *login_type* is elevated to ``SHA1`` by hashing the
      provided password.
    """
    # Note: The implementation here expects that broker won't sent any other
    # messages until login is actually performed. That is what happens but
    # it is not defined in any SHV design document as it seems.
    await client.send(RpcMessage.request("", "hello"))
    resp = await client.receive()
    nonce = shvget(resp.result, "nonce", str, "")
    if login_type is RpcLoginType.PLAIN and not force_plain:
        login_type = RpcLoginType.SHA1
        password = hashlib.sha1(password.encode("utf-8")).hexdigest()
    if login_type is RpcLoginType.SHA1:
        assert isinstance(nonce, str)
        m = hashlib.sha1()
        m.update(nonce.encode("utf-8"))
        m.update((password or "").encode("utf-8"))
        password = m.hexdigest()
    param: SHVType = {
        "login": {"password": password, "type": login_type.value, "user": username},
        "options": login_options if login_options else {},
    }
    await client.send(RpcMessage.request("", "login", param))
    await client.receive()


async def rpclogin_url(
    client: RpcClient,
    url: RpcUrl,
    login_options: dict[str, SHVType] | None = None,
) -> None:
    """Variation of :meth:`login` that takes arguments from RPC URL.

    :param: client: Connected client the login should be performed on.
    :param url: RPC URL with login info.
    :param login_options: Additional custom login options that are not supported by
        RPC URL.
    :return: Client ID assigned by broker or `None` in case none was assigned.
    """
    options = url.login_options()
    if login_options:
        options.update(login_options)
    await rpclogin(client, url.username, url.password, url.login_type, options)
