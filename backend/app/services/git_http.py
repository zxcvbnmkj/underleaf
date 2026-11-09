"""Git Smart HTTP 协议（无状态 RPC），基于 dulwich 的协议处理器。

这些函数都是同步阻塞的（读写仓库文件），由接口层放到线程中执行。请求体和响应体都在内存中，
笔记仓库不大，大小由接口层限制。
"""

from collections.abc import Callable, Iterator, Sequence
from io import BytesIO

from dulwich.objects import ObjectID
from dulwich.protocol import (
    CAPABILITY_NO_DONE,
    CAPABILITY_OFS_DELTA,
    CAPABILITY_QUIET,
    CAPABILITY_REPORT_STATUS,
    CAPABILITY_SIDE_BAND_64K,
    SIDE_BAND_CHANNEL_PROGRESS,
    ReceivableProtocol,
    capability_object_format,
)
from dulwich.refs import Ref
from dulwich.repo import Repo
from dulwich.server import Backend, BackendRepo, ReceivePackHandler, UploadPackHandler

UPLOAD_PACK = "git-upload-pack"
RECEIVE_PACK = "git-receive-pack"
SERVICES = (UPLOAD_PACK, RECEIVE_PACK)

ZERO_SHA = ObjectID(b"0" * 40)

RefUpdate = tuple[ObjectID, ObjectID, Ref]


class PushResult:
    """推送钩子的返回值：error 为 None 表示接受；messages 逐行显示为 `remote: ...`。"""

    def __init__(self, error: str | None, messages: Sequence[str] = ()) -> None:
        self.error = error
        self.messages = list(messages)


PushHook = Callable[[list[RefUpdate]], PushResult]


class _Backend(Backend):
    def __init__(self, repo: Repo) -> None:
        self.repo = repo

    def open_repository(self, path: str) -> BackendRepo:
        return self.repo  # pyright: ignore[reportReturnType]


class _ReceivePackHandler(ReceivePackHandler):
    """收到推送的数据包后交给钩子决定是否接受，由钩子负责更新分支（与数据库写回放在一起）。"""

    on_push: PushHook
    max_input_size: int | None = None

    def capabilities(self) -> list[bytes]:
        # 不支持删除分支（delete-refs）；只有一个分支，atomic 没有意义
        return [
            CAPABILITY_REPORT_STATUS,
            CAPABILITY_QUIET,
            CAPABILITY_OFS_DELTA,
            CAPABILITY_SIDE_BAND_64K,
            CAPABILITY_NO_DONE,
            capability_object_format(self.repo.object_format.name),
        ]

    def _apply_pack(self, refs: list[RefUpdate]) -> Iterator[tuple[bytes, bytes]]:
        if any(new != ZERO_SHA for _, new, _ in refs):
            try:
                self.repo.object_store.add_thin_pack(  # pyright: ignore[reportAttributeAccessIssue]
                    self.proto.read,
                    getattr(self.proto, "recv", None),
                    max_input_size=self.max_input_size,
                )
            except Exception as e:  # 数据包损坏、超过大小等
                yield (b"unpack", str(e).replace("\n", " ").encode())
                return
        yield (b"unpack", b"ok")

        result = self.on_push(refs)
        if result.messages and self.has_capability(CAPABILITY_SIDE_BAND_64K):
            text = "".join(f"{line}\n" for line in result.messages)
            self.proto.write_sideband(SIDE_BAND_CHANNEL_PROGRESS, text.encode())
        status = b"ok" if result.error is None else result.error.encode()
        for _, _, ref in refs:
            yield (ref, status)


def _run(
    repo: Repo,
    service: str,
    body: bytes,
    *,
    advertise: bool,
    on_push: PushHook | None = None,
    max_input_size: int | None = None,
) -> bytes:
    out = BytesIO()
    proto = ReceivableProtocol(BytesIO(body).read, out.write)
    backend = _Backend(repo)
    if service == UPLOAD_PACK:
        handler = UploadPackHandler(
            backend, ["/"], proto, stateless_rpc=True, advertise_refs=advertise
        )
    else:
        handler = _ReceivePackHandler(
            backend, ["/"], proto, stateless_rpc=True, advertise_refs=advertise
        )
        handler.on_push = on_push or (lambda _refs: PushResult("push disabled"))
        handler.max_input_size = max_input_size
    if advertise:
        proto.write_pkt_line(f"# service={service}\n".encode())
        proto.write_pkt_line(None)
    handler.handle()
    return out.getvalue()


def advertise_refs(repo: Repo, service: str) -> bytes:
    """GET info/refs?service=...：列出分支和服务端能力。"""
    return _run(repo, service, b"", advertise=True)


def handle_rpc(
    repo: Repo,
    service: str,
    body: bytes,
    on_push: PushHook | None = None,
    max_input_size: int | None = None,
) -> bytes:
    """POST git-upload-pack / git-receive-pack：处理客户端的请求体，返回响应体。"""
    return _run(
        repo, service, body, advertise=False, on_push=on_push, max_input_size=max_input_size
    )
