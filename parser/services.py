"""Main service logic for the parser application."""
import asyncio
import uuid

import pandas as pd
from django.conf import settings
from loguru import logger

from core.reporting import ProgressReporter, ReportStatus
from parser.clickhouse_repo import insert_offers
from parser.excel_export import export_offers_xlsx, pivot_offers_for_export
from parser.stparts_pipeline import run_stparts_pipeline


class PipelineReporter:
    """
    A wrapper for ProgressReporter to adapt the pipeline's reporting
    to the desired UI steps and to collect failures.
    """

    def __init__(self, main_reporter: ProgressReporter):
        self._main_reporter = main_reporter
        self.failed_articles: list[str] = []

    def report_percentage(self, *, step: str, progress: int) -> None:
        # The pipeline uses step="FETCHING", but the UI wants "Парсим stparts".
        self._main_reporter.report_percentage(step="Парсим stparts", progress=progress)

    def report_step(self, **kwargs) -> None:
        # Capture failures reported by the pipeline.
        if kwargs.get("status") == "FAILURE" and "article" in kwargs.get("details", {}):
            self.failed_articles.append(kwargs["details"]["article"])
        # Do not pass other step reports through, as the main task manages top-level steps.


def run_stparts_parsing_service(file_path: str, include_analogs: bool, reporter: ProgressReporter) -> dict:
    """
    Orchestrates the stparts parsing process: reads a file, runs the pipeline,
    and generates an Excel report.
    """
    run_id = uuid.uuid4()

    # --- 1. Read File ---
    reading_file_step_name = "Читаем файл"
    reporter.report_step(step=reading_file_step_name, status=ReportStatus.IN_PROGRESS)
    try:
        df = pd.read_excel(file_path)
        if "article" not in df.columns:
            raise ValueError("В файле отсутствует колонка 'article'.")
        articles = df["article"].dropna().astype(str).tolist()
        if not articles:
            raise ValueError("В файле нет артикулов для парсинга.")
        reporter.report_step(step=reading_file_step_name, status=ReportStatus.SUCCESS)
    except Exception as e:
        logger.error(f"Failed to read or process Excel file {file_path}: {e}")
        reporter.report_failure(step=reading_file_step_name, details={"error": str(e)})
        raise

    # --- 2. Parse stparts ---
    parsing_stparts_step_name = "Парсим stparts"
    reporter.report_step(step=parsing_stparts_step_name, status=ReportStatus.IN_PROGRESS)
    reporter.report_percentage(step=parsing_stparts_step_name, progress=0)
    try:
        pipeline_reporter = PipelineReporter(reporter)
        offers = asyncio.run(
            run_stparts_pipeline(articles=articles, include_analogs=include_analogs, reporter=pipeline_reporter)
        )
        reporter.report_step(step=parsing_stparts_step_name, status=ReportStatus.SUCCESS)
        failed_count = len(set(pipeline_reporter.failed_articles))
    except Exception as e:
        logger.error(f"Stparts pipeline failed: {e}", exc_info=True)
        reporter.report_failure(step=parsing_stparts_step_name, details={"error": str(e)})
        raise

    # --- 3. Insert into ClickHouse (DISABLED) ---
    # Per user request, this step is currently disabled.
    # It can be enabled when ready.
    # saving_to_db_step_name = "Сохраняем в базу данных"
    # reporter.report_step(step=saving_to_db_step_name, status=ReportStatus.IN_PROGRESS)
    # try:
    #     insert_offers(run_id, offers)
    #     reporter.report_step(step=saving_to_db_step_name, status=ReportStatus.SUCCESS)
    # except Exception as e:
    #     logger.error(f"Failed to insert offers into ClickHouse: {e}", exc_info=True)
    #     reporter.report_failure(step=saving_to_db_step_name, details={"error": str(e)})
    #     # Do not re-raise, as this step is non-critical for now.

    # --- 4. Write to Excel ---
    writing_to_excel_step_name = "Записываем результат в Excel"
    reporter.report_step(step=writing_to_excel_step_name, status=ReportStatus.IN_PROGRESS)
    reporter.report_percentage(step=writing_to_excel_step_name, progress=0)
    try:
        df_wide = pivot_offers_for_export(offers)

        export_dir = settings.MEDIA_ROOT / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        export_path = export_offers_xlsx(run_id, "stparts", df_wide, export_dir)
        export_url = f"{settings.MEDIA_URL}exports/{export_path.name}"

        reporter.report_percentage(step=writing_to_excel_step_name, progress=100)
        reporter.report_step(step=writing_to_excel_step_name, status=ReportStatus.SUCCESS)
    except Exception as e:
        logger.error(f"Failed to export Excel file: {e}", exc_info=True)
        reporter.report_failure(step=writing_to_excel_step_name, details={"error": str(e)})
        raise

    return {"failed_count": failed_count, "export_url": export_url}
