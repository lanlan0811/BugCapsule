"""FastAPI application factory for the local BugCapsule Web interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from bugcapsule import __version__
from bugcapsule.analysis.service import AnalysisError, AnalysisService
from bugcapsule.config import Settings, get_settings
from bugcapsule.demo.config import DemoSettings
from bugcapsule.demo.controller import DemoControlError, DemoController
from bugcapsule.index import (
    CapsuleDetail,
    CapsuleIndex,
    CapsuleIndexError,
    CapsuleIndexStaleError,
    IndexRebuildResult,
)
from bugcapsule.patching.service import (
    PatchGenerationError,
    PatchGenerationService,
)
from bugcapsule.web.imports import CapsuleImportError, CapsuleUploadService
from bugcapsule.web.viewmodels import (
    build_detail_view,
    format_bytes,
    format_datetime,
    short_identifier,
)

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "testserver"})


@dataclass
class WebRuntime:
    """Process-local synchronization state for the rebuildable index."""

    index: CapsuleIndex
    rebuild_result: IndexRebuildResult | None = None
    lock: Lock = field(default_factory=Lock)

    def ensure_index(self) -> IndexRebuildResult:
        if self.rebuild_result is None:
            with self.lock:
                if self.rebuild_result is None:
                    self.rebuild_result = self.index.rebuild()
        return self.rebuild_result


def create_app(
    settings: Settings | None = None,
    capsule_index: CapsuleIndex | None = None,
    demo_controller: DemoController | None = None,
    analysis_service: AnalysisService | None = None,
    patch_service: PatchGenerationService | None = None,
) -> FastAPI:
    """Build the local-only API and server-rendered Web application."""
    runtime_settings = settings or get_settings()
    index = capsule_index or CapsuleIndex.from_settings(runtime_settings)
    runtime = WebRuntime(index=index)
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    templates.env.filters["datetime"] = lambda value: format_datetime(
        value, runtime_settings.display_timezone
    )
    templates.env.filters["bytes"] = format_bytes
    templates.env.filters["short_id"] = short_identifier

    application = FastAPI(
        title="BugCapsule",
        description="Evidence-first AI debugging",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=sorted(LOOPBACK_HOSTS | {runtime_settings.host}),
    )
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def page_context(request: Request, *, active_nav: str, **values: object) -> dict[str, object]:
        return {
            "request": request,
            "version": __version__,
            "model_mode": runtime_settings.model_mode,
            "active_nav": active_nav,
            **values,
        }

    @application.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/capsules", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @application.get("/healthz", tags=["system"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @application.get("/capsules", response_class=HTMLResponse, tags=["capsules"])
    def capsules_page(
        request: Request,
        query: Annotated[str | None, Query(max_length=240)] = None,
        analysis_status: Annotated[
            str | None,
            Query(pattern=r"^$|^(not_run|completed|failed)$"),
        ] = None,
        verification_status: Annotated[
            str | None,
            Query(pattern=r"^$|^(not_run|running|passed|failed)$"),
        ] = None,
        sort: Annotated[str, Query(pattern=r"^(time|status)$")] = "time",
    ) -> Response:
        try:
            rebuild_result = runtime.ensure_index()
            summaries = index.list_capsules(
                query=query,
                analysis_status=analysis_status or None,
                verification_status=verification_status or None,
                sort_by=sort,
            )
        except CapsuleIndexError as exc:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context=page_context(
                    request,
                    active_nav="capsules",
                    title="索引不可用",
                    message=str(exc),
                ),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        is_htmx = request.headers.get("HX-Request") == "true"
        context = page_context(
            request,
            active_nav="capsules",
            capsules=summaries,
            rebuild_result=rebuild_result,
            is_htmx=is_htmx,
            filters={
                "query": query or "",
                "analysis_status": analysis_status or "",
                "verification_status": verification_status or "",
                "sort": sort,
            },
        )
        template = "partials/capsule_results.html" if is_htmx else "capsules.html"
        return templates.TemplateResponse(request=request, name=template, context=context)

    @application.post("/capsules/import", response_class=HTMLResponse, tags=["capsules"])
    async def import_capsule(
        request: Request,
        capsule: Annotated[UploadFile, File(description=".bugcapsule archive")],
    ) -> Response:
        _require_local_origin(request)
        runtime.ensure_index()
        try:
            result = await CapsuleUploadService(
                index,
                runtime_settings.max_import_bytes,
            ).import_upload(capsule)
        except CapsuleImportError as exc:
            return templates.TemplateResponse(
                request=request,
                name="partials/import_result.html",
                context={"request": request, "error": str(exc)},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        finally:
            await capsule.close()
        destination = f"/capsules/{result.summary.capsule_id}"
        if request.headers.get("HX-Request") == "true":
            return Response(
                status_code=status.HTTP_204_NO_CONTENT,
                headers={"HX-Redirect": destination},
            )
        return RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)

    @application.get("/capsules/{capsule_id}/download", tags=["capsules"])
    def download_capsule(capsule_id: str) -> FileResponse:
        runtime.ensure_index()
        detail = _get_detail_or_error(index, capsule_id)
        return FileResponse(
            detail.archive_path,
            media_type="application/vnd.bugcapsule+zip",
            filename=detail.archive_path.name,
        )

    @application.get("/capsules/{capsule_id}", response_class=HTMLResponse, tags=["capsules"])
    def capsule_detail(request: Request, capsule_id: str) -> Response:
        runtime.ensure_index()
        try:
            detail = index.get_detail(capsule_id)
        except CapsuleIndexStaleError as exc:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context=page_context(
                    request,
                    active_nav="capsules",
                    title="索引需要重建",
                    message=str(exc),
                ),
                status_code=status.HTTP_409_CONFLICT,
            )
        if detail is None:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context=page_context(
                    request,
                    active_nav="capsules",
                    title="胶囊不存在",
                    message=f"未找到 {capsule_id}",
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return templates.TemplateResponse(
            request=request,
            name="capsule_detail.html",
            context=page_context(
                request,
                active_nav="detail",
                current_capsule=detail.summary,
                **build_detail_view(detail),
            ),
        )

    @application.post("/capsules/{capsule_id}/analyze", tags=["analysis"])
    def analyze_capsule(request: Request, capsule_id: str) -> Response:
        _require_local_origin(request)
        runtime.ensure_index()
        try:
            service = analysis_service or AnalysisService(runtime_settings, index=index)
            result = service.analyze(capsule_id)
        except AnalysisError as exc:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context=page_context(
                    request,
                    active_nav="detail",
                    title="模型分析失败",
                    message=str(exc),
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if result.status == "model_off":
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context=page_context(
                    request,
                    active_nav="detail",
                    title="模型模式已关闭",
                    message="将 BUGCAPSULE_MODEL_MODE 配置为 live 或 replay 后再运行分析。",
                ),
                status_code=status.HTTP_409_CONFLICT,
            )
        return RedirectResponse(
            f"/capsules/{capsule_id}#analysis",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @application.post("/capsules/{capsule_id}/patch", tags=["patches"])
    def generate_patch(request: Request, capsule_id: str) -> Response:
        _require_local_origin(request)
        runtime.ensure_index()
        try:
            service = patch_service or PatchGenerationService(runtime_settings, index=index)
            result = service.generate(capsule_id)
        except PatchGenerationError as exc:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context=page_context(
                    request,
                    active_nav="detail",
                    title="Patch 生成失败",
                    message=str(exc),
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if result.status == "model_off":
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context=page_context(
                    request,
                    active_nav="detail",
                    title="模型模式已关闭",
                    message="将 BUGCAPSULE_MODEL_MODE 配置为 live 或 replay 后再生成 Patch。",
                ),
                status_code=status.HTTP_409_CONFLICT,
            )
        return RedirectResponse(
            f"/capsules/{capsule_id}#patch",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @application.get("/demo", response_class=HTMLResponse, tags=["demo"])
    def demo_page(request: Request) -> Response:
        return templates.TemplateResponse(
            request=request,
            name="demo.html",
            context=page_context(request, active_nav="demo"),
        )

    @application.post("/demo/run", response_class=HTMLResponse, tags=["demo"])
    def run_demo(request: Request) -> Response:
        _require_local_origin(request)
        try:
            controller = demo_controller or DemoController(DemoSettings())
            result = controller.run()
        except (DemoControlError, ValidationError) as exc:
            return templates.TemplateResponse(
                request=request,
                name="partials/demo_result.html",
                context={"request": request, "error": str(exc)},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return templates.TemplateResponse(
            request=request,
            name="partials/demo_result.html",
            context={"request": request, "result": result},
        )

    @application.post("/demo/reset", response_class=HTMLResponse, tags=["demo"])
    def reset_demo(request: Request) -> Response:
        _require_local_origin(request)
        try:
            controller = demo_controller or DemoController(DemoSettings())
            controller.reset()
        except (DemoControlError, ValidationError) as exc:
            return templates.TemplateResponse(
                request=request,
                name="partials/demo_result.html",
                context={"request": request, "error": str(exc)},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return templates.TemplateResponse(
            request=request,
            name="partials/demo_result.html",
            context={"request": request, "reset": True},
        )

    return application


def _require_local_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    if origin is None:
        return
    parsed_origin = urlsplit(origin)
    if (
        parsed_origin.hostname not in LOOPBACK_HOSTS
        or parsed_origin.scheme != request.url.scheme
        or parsed_origin.netloc != request.url.netloc
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cross-site request rejected"
        )


def _get_detail_or_error(index: CapsuleIndex, capsule_id: str) -> CapsuleDetail:
    try:
        detail = index.get_detail(capsule_id)
    except CapsuleIndexError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="capsule not found")
    return detail


app = create_app()
