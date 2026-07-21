"""
Celery Task System for Document Indexing - Dynamic Workflow Architecture

This module implements a dynamic task system for document indexing with runtime workflow orchestration.
All tasks use structured data classes for parameter passing and result handling.

## Architecture Overview

The new task system is designed with the following principles:
1. **Fine-grained tasks**: Each operation (parse, create index, delete index, update index) is a separate task
2. **Dynamic workflow orchestration**: Tasks are composed at runtime using trigger tasks
3. **Parallel execution**: Index creation/update/deletion tasks run in parallel for better performance
4. **Individual retries**: Each task has its own retry mechanism with configurable parameters
5. **Runtime decision making**: Workflows can adapt based on document content and parsing results

## Task Flow Architecture

### Sequential Phase (Chain):
```
parse_document_task -> trigger_indexing_workflow
```

### Parallel Phase (Group + Chord):
```
[create_index_task(vector), create_index_task(fulltext), create_index_task(graph)] -> notify_workflow_complete
```

### Key Innovation: Dynamic Fan-out
The `trigger_indexing_workflow` task receives parsed document data and dynamically creates
the parallel index tasks, solving the static parameter passing limitation.

## Task Hierarchy

### Core Tasks:
- `parse_document_task`: Parse document content and extract metadata
- `create_index_task`: Create a single type of index (vector/fulltext/graph)
- `delete_index_task`: Delete a single type of index
- `update_index_task`: Update a single type of index

### Workflow Orchestration Tasks:
- `trigger_create_indexes_workflow`: Dynamic fan-out for index creation
- `trigger_delete_indexes_workflow`: Dynamic fan-out for index deletion
- `trigger_update_indexes_workflow`: Dynamic fan-out for index updates
- `notify_workflow_complete`: Aggregation task for workflow completion

### Workflow Entry Points:
- `create_document_indexes_workflow()`: Chain composition function
- `delete_document_indexes_workflow()`: Chain composition function
- `update_document_indexes_workflow()`: Chain composition function

## Usage Examples

### Direct Workflow Execution:
```python
from config.celery_tasks import create_document_indexes_workflow

# Execute workflow with dynamic orchestration
workflow_result = create_document_indexes_workflow(
    document_id="doc_123",
    index_types=["vector", "fulltext", "graph"]
)

print(f"Workflow ID: {workflow_result.id}")
```

### Via TaskScheduler:
```python
from aperag.tasks.scheduler import create_task_scheduler

scheduler = create_task_scheduler("celery")

# Execute workflow via scheduler
workflow_id = scheduler.schedule_create_index(
    document_id="doc_123",
    index_types=["vector", "fulltext"]
)

# Check status
status = scheduler.get_task_status(workflow_id)
print(f"Success: {status.success}")
```

## Benefits of Dynamic Orchestration

1. **Runtime Parameter Passing**: Index tasks receive actual parsed document data
2. **Adaptive Workflows**: Can decide which indexes to create based on document content
3. **Better Error Isolation**: Parse failures don't create orphaned index tasks
4. **Clear Data Flow**: Each task knows exactly what data it will receive
5. **Extensible**: Easy to add conditional logic for different document types

## Error Handling and Retries

Each task has built-in retry mechanisms:
- **Max retries**: 3 attempts for most tasks
- **Retry countdown**: 60 seconds between retries
- **Exception handling**: Detailed logging and error callbacks
- **Failure notifications**: Integration with index_task_callbacks for status updates
"""

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, List

from celery import Task, chain, chord, current_app, group

from aperag.tasks.collection import collection_task
from aperag.tasks.document import document_index_task
from aperag.tasks.models import (
    IndexTaskResult,
    ParsedDocumentData,
    TaskStatus,
    WorkflowResult,
)
from aperag.tasks.utils import TaskConfig
from aperag.utils.constant import IndexAction
from config.celery import app

logger = logging.getLogger()

def _validate_task_relevance(document_id: str, index_type: str, target_version: int, expected_status: "DocumentIndexStatus"):
    """
    Double-check the database to ensure the task is still valid.

    Returns a dictionary with a 'skipped' status if the task is no longer relevant,
    otherwise returns None.
    """
    from sqlalchemy import and_, select

    from aperag.config import get_sync_session
    from aperag.db.models import Document, DocumentIndex, DocumentIndexType, DocumentStatus

    for session in get_sync_session():
        # Check document index status
        stmt = select(DocumentIndex).where(
            and_(
                DocumentIndex.document_id == document_id,
                DocumentIndex.index_type == DocumentIndexType(index_type)
            )
        )
        result = session.execute(stmt)
        db_index = result.scalar_one_or_none()

        if not db_index:
            logger.info(f"Index record not found for {document_id}:{index_type}, skipping task.")
            return {"status": "skipped", "reason": "index_record_not_found"}

        if db_index.status != expected_status:
            logger.info(f"Index status for {document_id}:{index_type} changed to {db_index.status} (expected {expected_status}), skipping task.")
            return {"status": "skipped", "reason": f"status_changed_to_{db_index.status}"}

        if target_version and db_index.version != target_version:
            logger.info(f"Version mismatch for {document_id}:{index_type}, expected: {target_version}, current: {db_index.version}, skipping task.")
            return {"status": "skipped", "reason": f"version_mismatch_expected_{target_version}_current_{db_index.version}"}

        # Check document status - if document is UPLOADED or EXPIRED, task should be skipped
        doc_stmt = select(Document).where(Document.id == document_id)
        doc_result = session.execute(doc_stmt)
        document = doc_result.scalar_one_or_none()

        if not document:
            logger.info(f"Document {document_id} not found, skipping task.")
            return {"status": "skipped", "reason": "document_not_found"}

        if document.status in [DocumentStatus.UPLOADED, DocumentStatus.EXPIRED]:
            logger.info(f"Document {document_id} status is {document.status}, skipping task.")
            return {"status": "skipped", "reason": f"document_status_{document.status}"}

        return None  # Task is still relevant

class BaseIndexTask(Task):
    """
    Base class for all index tasks
    """

    abstract = True

    def _handle_index_success(self, document_id: str, index_type: str, target_version: int, index_data: dict = None):
        try:
            from aperag.tasks.reconciler import index_task_callbacks
            index_data_json = json.dumps(index_data) if index_data else None
            index_task_callbacks.on_index_created(document_id, index_type, target_version, index_data_json)
            logger.info(f"Index success callback executed for {index_type} index of document {document_id} (v{target_version})")
        except Exception as e:
            logger.warning(f"Failed to execute index success callback for {index_type} of {document_id} v{target_version}: {e}", exc_info=True)

    def _handle_index_deletion_success(self, document_id: str, index_type: str):
        try:
            from aperag.tasks.reconciler import index_task_callbacks
            index_task_callbacks.on_index_deleted(document_id, index_type)
            logger.info(f"Index deletion callback executed for {index_type} index of document {document_id}")
        except Exception as e:
            logger.warning(f"Failed to execute index deletion callback for {index_type} of {document_id}: {e}", exc_info=True)

    def _handle_index_failure(self, document_id: str, index_types: List[str], error_msg: str):
        try:
            from aperag.tasks.reconciler import index_task_callbacks

            for index_type in index_types:
                index_task_callbacks.on_index_failed(document_id, index_type, error_msg)
            logger.info(f"Index failure callback executed for {index_types} indexes of document {document_id}")
        except Exception as e:
            logger.warning(f"Failed to execute index failure callback for {document_id}: {e}", exc_info=True)

# ========== Core Document Processing Tasks ==========

@current_app.task(bind=True, base=BaseIndexTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def parse_document_task(self, document_id: str, index_types: List[str]) -> dict:
    """
    Parse document content task

    Args:
        document_id: Document ID to parse

    Returns:
        Serialized ParsedDocumentData
    """
    try:
        logger.info(f"Starting to parse document {document_id}")
        parsed_data = document_index_task.parse_document(document_id)
        logger.info(f"Successfully parsed document {document_id}")
        return parsed_data.to_dict()
    except Exception as e:
        error_msg = f"Failed to parse document {document_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Only mark as failed if all retries are exhausted
        if self.request.retries >= self.max_retries:
            self._handle_index_failure(document_id, index_types, error_msg)

        raise


@current_app.task(bind=True, base=BaseIndexTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def create_index_task(self, document_id: str, index_type: str, parsed_data_dict: dict, context: dict = None) -> dict:
    """
    Create a single index for a document with distributed locking

    Args:
        document_id: Document ID to process
        index_type: Type of index to create ('vector', 'fulltext', 'graph')
        parsed_data_dict: Serialized ParsedDocumentData from parse_document_task
        context: Task context including index version

    Returns:
        Serialized IndexTaskResult
    """

    from aperag.db.models import DocumentIndexStatus

    # Extract target version from context
    context = context or {}
    target_version = context.get(f'{index_type}_version')

    try:
        logger.info(f"Starting to create {index_type} index for document {document_id} (v{target_version})")

        # Double-check: verify task is still valid
        skip_reason = _validate_task_relevance(document_id, index_type, target_version, DocumentIndexStatus.CREATING)
        if skip_reason:
            return skip_reason

        # Convert dict back to structured data
        parsed_data = ParsedDocumentData.from_dict(parsed_data_dict)

        # Execute index creation
        result = document_index_task.create_index(document_id, index_type, parsed_data)

        # Check if the operation failed and raise exception to trigger retry
        if not result.success:
            error_msg = f"Failed to create {index_type} index for document {document_id}: {result.error}"
            logger.error(error_msg)
            raise Exception(error_msg)

        # Handle success callback with version validation
        logger.info(f"Successfully created {index_type} index for document {document_id} (v{target_version})")
        self._handle_index_success(document_id, index_type, target_version, result.data)

        return result.to_dict()

    except Exception as e:
        error_msg = f"Failed to create {index_type} index for document {document_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Only mark as failed if all retries are exhausted
        if self.request.retries >= self.max_retries:
            self._handle_index_failure(document_id, [index_type], error_msg)

        raise


@current_app.task(bind=True, base=BaseIndexTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def delete_index_task(self, document_id: str, index_type: str) -> dict:
    """
    Delete a single index for a document

    Args:
        document_id: Document ID to process
        index_type: Type of index to delete ('vector', 'fulltext', 'graph')

    Returns:
        Serialized IndexTaskResult
    """
    from sqlalchemy import and_, select

    from aperag.config import get_sync_session
    from aperag.db.models import DocumentIndex, DocumentIndexStatus, DocumentIndexType

    try:
        logger.info(f"Starting to delete {index_type} index for document {document_id}")

        # Double-check: verify task is still valid
        for session in get_sync_session():
            stmt = select(DocumentIndex).where(
                and_(
                    DocumentIndex.document_id == document_id,
                    DocumentIndex.index_type == DocumentIndexType(index_type)
                )
            )
            result = session.execute(stmt)
            db_index = result.scalar_one_or_none()

            # Validate task is still relevant
            if not db_index:
                logger.info(f"Index record not found for {document_id}:{index_type}, already deleted")
                return {"status": "skipped", "reason": "index_record_not_found"}

            if db_index.status != DocumentIndexStatus.DELETION_IN_PROGRESS:
                logger.info(f"Index status changed for {document_id}:{index_type}, current: {db_index.status}, skipping task")
                return {"status": "skipped", "reason": f"status_changed_to_{db_index.status}"}

            break

        # Execute index deletion
        result = document_index_task.delete_index(document_id, index_type)

        # Check if the operation failed and raise exception to trigger retry
        if not result.success:
            error_msg = f"Failed to delete {index_type} index for document {document_id}: {result.error}"
            logger.error(error_msg)
            raise Exception(error_msg)

        # Handle success callback
        logger.info(f"Successfully deleted {index_type} index for document {document_id}")
        self._handle_index_deletion_success(document_id, index_type)

        return result.to_dict()

    except Exception as e:
        error_msg = f"Failed to delete {index_type} index for document {document_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Only mark as failed if all retries are exhausted
        if self.request.retries >= self.max_retries:
            self._handle_index_failure(document_id, [index_type], error_msg)

        raise


@current_app.task(bind=True, base=BaseIndexTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def update_index_task(self, document_id: str, index_type: str, parsed_data_dict: dict, context: dict = None) -> dict:
    """
    Update a single index for a document with distributed locking

    Args:
        document_id: Document ID to process
        index_type: Type of index to update ('vector', 'fulltext', 'graph')
        parsed_data_dict: Serialized ParsedDocumentData from parse_document_task
        context: Task context including index version

    Returns:
        Serialized IndexTaskResult
    """

    from aperag.db.models import DocumentIndexStatus

    # Extract target version from context
    context = context or {}
    target_version = context.get(f'{index_type}_version')

    try:
        logger.info(f"Starting to update {index_type} index for document {document_id} (v{target_version})")

        # Double-check: verify task is still valid
        skip_reason = _validate_task_relevance(document_id, index_type, target_version, DocumentIndexStatus.CREATING)
        if skip_reason:
            return skip_reason

        # Convert dict back to structured data
        parsed_data = ParsedDocumentData.from_dict(parsed_data_dict)

        # Execute index update
        result = document_index_task.update_index(document_id, index_type, parsed_data)

        # Check if the operation failed and raise exception to trigger retry
        if not result.success:
            error_msg = f"Failed to update {index_type} index for document {document_id}: {result.error}"
            logger.error(error_msg)
            raise Exception(error_msg)

        # Handle success callback with version validation
        logger.info(f"Successfully updated {index_type} index for document {document_id} (v{target_version})")
        self._handle_index_success(document_id, index_type, target_version, result.data)

        return result.to_dict()

    except Exception as e:
        error_msg = f"Failed to update {index_type} index for document {document_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Only mark as failed if all retries are exhausted
        if self.request.retries >= self.max_retries:
            self._handle_index_failure(document_id, [index_type], error_msg)

        raise


# ========== Dynamic Workflow Orchestration Tasks ==========

@current_app.task(bind=True)
def trigger_create_indexes_workflow(self, parsed_data_dict: dict, document_id: str, index_types: List[str], context: dict = None) -> Any:
    """
    Dynamic orchestration task for index creation workflow.

    This task acts as a fan-out point, receiving parsed document data and dynamically
    creating parallel index creation tasks based on the actual parsed content.

    Args:
        parsed_data_dict: Serialized ParsedDocumentData from parse_document_task
        document_id: Document ID to process
        index_types: List of index types to create

    Returns:
        Chord signature for parallel index creation + completion notification
    """
    try:
        logger.info(f"Triggering parallel index creation for document {document_id} with types: {index_types}")

        # Dynamically create parallel index creation tasks
        parallel_index_tasks = group([
            create_index_task.s(document_id, index_type, parsed_data_dict, context)
            for index_type in index_types
        ])

        # Create a chord that executes the completion notification after all create tasks are done
        workflow_chord = chord(
            parallel_index_tasks,
            notify_workflow_complete.s(document_id, IndexAction.CREATE, index_types)
        )

        # Execute the chord
        workflow_chord.apply_async()

        return workflow_chord

    except Exception as e:
        error_msg = f"Failed to trigger create indexes workflow: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise


@current_app.task(bind=True)
def trigger_delete_indexes_workflow(self, document_id: str, index_types: List[str]) -> Any:
    """
    Dynamic orchestration task for index deletion workflow.

    Args:
        document_id: Document ID to process
        index_types: List of index types to delete

    Returns:
        Chord signature for parallel index deletion + completion notification
    """
    try:
        logger.info(f"Triggering parallel index deletion for document {document_id} with types: {index_types}")

        # Create parallel index deletion tasks
        parallel_delete_tasks = group([
            delete_index_task.s(document_id, index_type)
            for index_type in index_types
        ])

        # Create a chord that executes the completion notification after all delete tasks are done
        workflow_chord = chord(
            parallel_delete_tasks,
            notify_workflow_complete.s(document_id, IndexAction.DELETE, index_types)
        )

        # Execute the chord
        workflow_chord.apply_async()

        return workflow_chord

    except Exception as e:
        error_msg = f"Failed to trigger delete indexes workflow: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise


@current_app.task(bind=True)
def trigger_update_indexes_workflow(self, parsed_data_dict: dict, document_id: str, index_types: List[str], context: dict = None) -> Any:
    """
    Dynamic orchestration task for index update workflow.

    Args:
        parsed_data_dict: Serialized ParsedDocumentData from parse_document_task
        document_id: Document ID to process
        index_types: List of index types to update

    Returns:
        Chord signature for parallel index update + completion notification
    """
    try:
        logger.info(f"Triggering parallel index update for document {document_id} with types: {index_types}")

        # Create parallel index update tasks
        parallel_update_tasks = group([
            update_index_task.s(document_id, index_type, parsed_data_dict, context)
            for index_type in index_types
        ])

        # Create chord: parallel tasks + completion notification
        workflow_chord = chord(
            parallel_update_tasks,
            notify_workflow_complete.s(document_id, IndexAction.UPDATE, index_types)
        )

        chord_async_result = workflow_chord.apply_async()

        return chord_async_result

    except Exception as e:
        error_msg = f"Failed to trigger update indexes workflow: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise


@current_app.task(bind=True, base=BaseIndexTask)
def notify_workflow_complete(self, index_results: List[dict], document_id: str, operation: str, index_types: List[str]) -> dict:
    """
    Workflow completion notification task.

    This task is called after all parallel index operations complete,
    aggregating results and providing final workflow status.

    Args:
        index_results: List of IndexTaskResult dicts from parallel tasks
        document_id: Document ID that was processed
        operation: Operation type ('create', 'delete', 'update')
        index_types: List of index types that were processed

    Returns:
        Serialized WorkflowResult
    """
    try:
        logger.info(f"Workflow {operation} completed for document {document_id}")
        logger.info(f"Index results: {index_results}")

        # Analyze results
        successful_tasks = []
        failed_tasks = []

        for result_dict in index_results:
            try:
                result = IndexTaskResult.from_dict(result_dict)
                if result.success:
                    successful_tasks.append(result.index_type)
                else:
                    failed_tasks.append(f"{result.index_type}: {result.error}")
            except Exception as e:
                failed_tasks.append(f"unknown: {str(e)}")

        # Determine overall status
        if not failed_tasks:
            status = TaskStatus.SUCCESS
            status_message = f"Document {document_id} {operation} COMPLETED SUCCESSFULLY! All indexes processed: {', '.join(successful_tasks)}"
            logger.info(status_message)
        elif successful_tasks:
            status = TaskStatus.PARTIAL_SUCCESS
            status_message = f"Document {document_id} {operation} COMPLETED with WARNINGS. Success: {', '.join(successful_tasks)}. Failures: {'; '.join(failed_tasks)}"
            logger.warning(status_message)
        else:
            status = TaskStatus.FAILED
            status_message = f"Document {document_id} {operation} FAILED. All tasks failed: {'; '.join(failed_tasks)}"
            logger.error(status_message)

        # Create workflow result
        workflow_result = WorkflowResult(
            workflow_id=f"{document_id}_{operation}",
            document_id=document_id,
            operation=operation,
            status=status,
            message=status_message,
            successful_indexes=successful_tasks,
            failed_indexes=[f.split(':')[0] for f in failed_tasks],
            total_indexes=len(index_types),
            index_results=[IndexTaskResult.from_dict(r) for r in index_results]
        )

        return workflow_result.to_dict()

    except Exception as e:
        error_msg = f"Failed to process workflow completion for document {document_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Return failure result
        workflow_result = WorkflowResult(
            workflow_id=f"{document_id}_{operation}",
            document_id=document_id,
            operation=operation,
            status=TaskStatus.FAILED,
            message=error_msg,
            successful_indexes=[],
            failed_indexes=index_types,
            total_indexes=len(index_types),
            index_results=[]
        )

        return workflow_result.to_dict()


# ========== Workflow Entry Point Functions ==========

def create_document_indexes_workflow(document_id: str, index_types: List[str], context: dict = None):
    """
    Create indexes for a document using dynamic workflow orchestration.

    This function composes a chain that:
    1. Parses the document
    2. Dynamically triggers parallel index creation based on parsed content
    3. Aggregates results and notifies completion

    Args:
        document_id: Document ID to process
        index_types: List of index types to create

    Returns:
        AsyncResult for the workflow chain
    """
    logger.info(f"Starting create indexes workflow for document {document_id} with types: {index_types}")
    # Create the workflow chain: parse -> dynamic trigger
    workflow_chain = chain(
        parse_document_task.s(document_id, index_types),
        trigger_create_indexes_workflow.s(document_id, index_types, context)
    )

    # Submit the workflow
    workflow_result = workflow_chain.delay()
    logger.info(f"Create indexes workflow submitted for document {document_id}, workflow ID: {workflow_result.id}")

    return workflow_result


def delete_document_indexes_workflow(document_id: str, index_types: List[str]):
    """
    Delete indexes for a document using dynamic workflow orchestration.

    Args:
        document_id: Document ID to process
        index_types: List of index types to delete

    Returns:
        AsyncResult for the workflow
    """
    logger.info(f"Starting delete indexes workflow for document {document_id} with types: {index_types}")

    # For deletion, we don't need parsing, so we directly trigger the delete workflow
    workflow_result = trigger_delete_indexes_workflow.delay(document_id, index_types)
    logger.info(f"Delete indexes workflow submitted for document {document_id}, workflow ID: {workflow_result.id}")

    return workflow_result


def update_document_indexes_workflow(document_id: str, index_types: List[str], context: dict = None):
    """
    Update indexes for a document using dynamic workflow orchestration.

    This function composes a chain that:
    1. Re-parses the document to get updated content
    2. Dynamically triggers parallel index updates based on parsed content
    3. Aggregates results and notifies completion

    Args:
        document_id: Document ID to process
        index_types: List of index types to update

    Returns:
        AsyncResult for the workflow chain
    """
    logger.info(f"Starting update indexes workflow for document {document_id} with types: {index_types}")

    # Create the workflow chain: parse -> dynamic trigger
    workflow_chain = chain(
        parse_document_task.s(document_id, index_types),
        trigger_update_indexes_workflow.s(document_id, index_types, context)
    )

    # Submit the workflow
    workflow_result = workflow_chain.delay()
    logger.info(f"Update indexes workflow submitted for document {document_id}, workflow ID: {workflow_result.id}")

    return workflow_result


# ========== Collection Tasks ==========

@current_app.task
def reconcile_indexes_task():
    """Periodic task to reconcile index specs with statuses"""
    try:
        logger.info("Starting index reconciliation")

        # Import here to avoid circular dependencies
        from aperag.tasks.reconciler import index_reconciler

        # Run reconciliation
        index_reconciler.reconcile_all()

        logger.info("Index reconciliation completed")

    except Exception as e:
        logger.error(f"Index reconciliation failed: {e}", exc_info=True)
        raise


@current_app.task
def reconcile_collection_summaries_task():
    """Periodic task to reconcile collection summary specs with statuses"""
    try:
        logger.info("Starting collection summary reconciliation")

        # Import here to avoid circular dependencies
        from aperag.tasks.reconciler import collection_summary_reconciler

        # Run reconciliation
        collection_summary_reconciler.reconcile_all()

        logger.info("Collection summary reconciliation completed")

    except Exception as e:
        logger.error(f"Collection summary reconciliation failed: {e}", exc_info=True)
        raise


@app.task(bind=True)
def collection_delete_task(self, collection_id: str) -> Any:
    """
    Delete collection task entry point

    Args:
        collection_id: Collection ID to delete
    """
    try:
        result = collection_task.delete_collection(collection_id)

        if not result.success:
            raise Exception(result.error)

        logger.info(f"Collection {collection_id} deleted successfully")
        return result.to_dict()

    except Exception as e:
        logger.error(f"Collection deletion failed for {collection_id}: {str(e)}")
        raise self.retry(
            exc=e,
            countdown=TaskConfig.RETRY_COUNTDOWN_COLLECTION,
            max_retries=TaskConfig.RETRY_MAX_RETRIES_COLLECTION,
        )


@app.task(bind=True)
def collection_init_task(self, collection_id: str, document_user_quota: int) -> Any:
    """
    Initialize collection task entry point

    Args:
        collection_id: Collection ID to initialize
        document_user_quota: User quota for documents
    """
    try:
        result = collection_task.initialize_collection(collection_id, document_user_quota)

        if not result.success:
            raise Exception(result.error)

        logger.info(f"Collection {collection_id} initialized successfully")
        return result.to_dict()

    except Exception as e:
        logger.error(f"Collection initialization failed for {collection_id}: {str(e)}")
        raise self.retry(
            exc=e,
            countdown=TaskConfig.RETRY_COUNTDOWN_COLLECTION,
            max_retries=TaskConfig.RETRY_MAX_RETRIES_COLLECTION,
        )


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def collection_summary_task(self, summary_id: str, collection_id: str, target_version: int) -> Any:
    """
    Generate collection summary task entry point

    Args:
        summary_id: Summary ID to generate
        collection_id: Collection ID to generate summary for
    """
    try:
        from aperag.service.collection_summary_service import collection_summary_service

        collection_summary_service.generate_collection_summary_task(summary_id, collection_id, target_version)

        logger.info(f"Collection summary task completed for {collection_id}")
        return {"success": True, "collection_id": collection_id}

    except Exception as e:
        logger.error(f"Collection summary generation failed for {collection_id}: {str(e)}")

        # Mark as failed using callback if we've exhausted retries
        if self.request.retries >= self.max_retries:
            from aperag.tasks.reconciler import collection_summary_callbacks
            collection_summary_callbacks.on_summary_failed(collection_id, str(e))

        raise self.retry(
            exc=e,
            countdown=TaskConfig.RETRY_COUNTDOWN_COLLECTION,
            max_retries=TaskConfig.RETRY_MAX_RETRIES_COLLECTION,
        )


@current_app.task
def cleanup_expired_documents_task():
    """
    Celery task to clean up expired uploaded documents.
    This task should be scheduled to run periodically (e.g., every hour).
    """
    logger.info("Starting Celery task: cleanup_expired_documents")

    # Import here to avoid circular dependencies
    from aperag.tasks.reconciler import collection_gc_reconciler

    result = collection_gc_reconciler.reconcile_all()

    logger.info(f"Celery task completed with result: {result}")
    return result

# ========== Evaluation Tasks ==========

# By default, get_async_session() uses a global AsyncEngine object.
# Since we also use asyncio.run() to execute async functions, old connections
# in the AsyncEngine connection pool cannot work in the new event loop,
# which will raise an exception like "xxx attached to a different loop".
# Therefore, using a dedicated AsyncEngine to avoid issues from connection reuse.
@asynccontextmanager
async def _new_async_engine():
    from aperag.config import new_async_engine

    engine = new_async_engine()
    try:
        yield engine
    finally:
        await engine.dispose()


@current_app.task
def reconcile_evaluations_task():
    """Periodic task to reconcile evaluations."""
    try:
        async def execute():
            from aperag.service.evaluation_service import EvaluationExecutor

            async with _new_async_engine() as engine:
                executor = EvaluationExecutor(engine)
                await executor.schedule_evaluations()

        import asyncio
        asyncio.run(execute())

        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to reconcile evaluations: {e}", exc_info=True)
        raise


@app.task(bind=True)
def initialize_evaluation_task(self, evaluation_id: str) -> Any:
    """Task to initialize a specific evaluation."""
    try:
        async def execute():
            from aperag.service.evaluation_service import EvaluationExecutor

            async with _new_async_engine() as engine:
                executor = EvaluationExecutor(engine)
                await executor.initialize_evaluation(evaluation_id)

        import asyncio
        asyncio.run(execute())

        return {"success": True, "evaluation_id": evaluation_id}
    except Exception as e:
        logger.error(f"Failed to initialize evaluation {evaluation_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60, max_retries=3)


@app.task(bind=True)
def process_evaluation_batch_task(self, evaluation_id: str) -> Any:
    """Task to process a batch of items for an evaluation."""
    try:
        async def execute():
            from aperag.service.evaluation_service import EvaluationExecutor

            async with _new_async_engine() as engine:
                executor = EvaluationExecutor(engine)
                await executor.process_evaluation_batch(evaluation_id)

        import asyncio
        asyncio.run(execute())

        return {"success": True, "evaluation_id": evaluation_id}
    except Exception as e:
        logger.error(f"Failed to process batch for evaluation {evaluation_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60, max_retries=3)


@app.task(bind=True)
def process_evaluation_item_task(self, evaluation_id: str, item_id: str) -> Any:
    """Task to process a single evaluation item."""
    try:
        async def execute():
            from aperag.service.evaluation_service import EvaluationExecutor

            async with _new_async_engine() as engine:
                executor = EvaluationExecutor(engine)
                await executor.process_evaluation_item(evaluation_id, item_id)

        import asyncio
        asyncio.run(execute())

        return {"success": True, "item_id": item_id}
    except Exception as e:
        logger.error(f"Failed to process item {item_id}: {e}", exc_info=True)
        # You might want a different retry policy for item tasks
        raise self.retry(exc=e, countdown=60, max_retries=3)


# ── Knowledge Base Import Task ─────────────────────────────────────────────

@app.task(bind=True, soft_time_limit=55 * 60, time_limit=60 * 60)
def import_collection_task(self, import_task_id: str):
    """Celery task: import a ZIP (basic or full export) and restore the knowledge base."""
    import json as _json
    import os as _os
    import shutil as _shutil
    import tempfile as _tempfile
    import zipfile as _zipfile

    from sqlalchemy import select

    from aperag.config import get_sync_session
    from aperag.db.models import (
        Collection,
        Document,
        DocumentIndex,
        DocumentIndexStatus,
        DocumentIndexType,
        ImportTask,
        ImportTaskStatus,
    )
    from aperag.objectstore.base import get_object_store
    from aperag.utils.utils import utc_now

    def _update(status=None, progress=None, message=None, error_message=None,
                collection_id=None, collection_title=None):
        for session in get_sync_session():
            r = session.execute(select(ImportTask).where(ImportTask.id == import_task_id))
            t = r.scalars().first()
            if not t:
                return
            if status is not None:
                t.status = status
            if progress is not None:
                t.progress = progress
            if message is not None:
                t.message = message
            if error_message is not None:
                t.error_message = error_message
            if collection_id is not None:
                t.collection_id = collection_id
            if collection_title is not None:
                t.collection_title = collection_title
            t.gmt_updated = utc_now()
            if status == ImportTaskStatus.COMPLETED:
                t.gmt_completed = utc_now()
            session.commit()

    temp_dir = None

    try:
        user_id = None
        zip_path = None
        collection_title = "Imported Collection"
        for session in get_sync_session():
            r = session.execute(select(ImportTask).where(ImportTask.id == import_task_id))
            t = r.scalars().first()
            if not t:
                return
            user_id = t.user
            zip_path = t.zip_path
            collection_title = t.collection_title or collection_title
            t.status = ImportTaskStatus.PROCESSING
            t.progress = 0
            t.message = "Import: extracting ZIP..."
            t.gmt_updated = utc_now()
            session.commit()

        _update(progress=5, message="Import: extracting ZIP...")

        # Extract ZIP
        temp_dir = _tempfile.mkdtemp(prefix=f"import_{import_task_id}_")
        with _zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)

        # Read manifest
        manifest_path = _os.path.join(temp_dir, "manifest.json")
        if not _os.path.exists(manifest_path):
            _update(status=ImportTaskStatus.FAILED, error_message="manifest.json not found in ZIP")
            return

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = _json.load(f)

        export_type = manifest.get("export_type", "basic")
        _update(progress=15, message=f"Import: detected {export_type} export, creating collection...")

        # Create new collection
        new_coll_id = _create_coll(user_id, collection_title, get_sync_session, Collection, utc_now)
        old_coll_id = manifest.get("collection", {}).get("id", "")

        _update(progress=25, message="Import: creating document records...", collection_id=new_coll_id)

        # Create document records & ID mapping
        doc_id_map = {}
        for doc_info in manifest.get("documents", []):
            old_doc_id = doc_info.get("id", "")
            doc_name = doc_info.get("title", old_doc_id)
            new_doc_id = _create_doc(new_coll_id, user_id, doc_name, get_sync_session, Document, utc_now)
            doc_id_map[old_doc_id] = new_doc_id

        # Copy source files to object store
        _update(progress=35, message="Import: copying source files...")
        source_dir = _os.path.join(temp_dir, "source")
        if _os.path.exists(source_dir):
            store = get_object_store()
            prefix = f"user-{user_id}/{new_coll_id}/"
            for root, _dirs, files in _os.walk(source_dir):
                for filename in files:
                    fp = _os.path.join(root, filename)
                    rel = _os.path.relpath(fp, source_dir)
                    with open(fp, "rb") as sf:
                        store.put(f"{prefix}{rel}", sf)

        _update(progress=45, message="Import: creating index records...")
        _create_indexes(doc_id_map, get_sync_session, DocumentIndex, DocumentIndexType, DocumentIndexStatus, utc_now)

        if export_type == "full":
            # Check embedding model compatibility before restoring vectors
            full_ok = _check_embedding_match(manifest)
            if not full_ok:
                logger.warning(
                    f"Import {import_task_id}: embedding model mismatch, "
                    f"Export dim={manifest.get('embedding_dim')}, pausing for user choice"
                )
                export_model = manifest.get("embedding_model", "unknown")
                export_prov = manifest.get("embedding_provider", "unknown")
                export_dim = manifest.get("embedding_dim", "?")
                _update(
                    status="INCOMPATIBLE",
                    progress=55,
                    message=f"Embedding model mismatch. Export: {export_model} ({export_prov}, dim={export_dim}). "
                            f"Choose: re-index with target model, or cancel.",
                )
                return  # Pause here, wait for user to call /continue endpoint
            else:
                _update(progress=55, message="Import: restoring Qdrant vectors...")
                qf = _os.path.join(temp_dir, "qdrant.jsonl")
                if _os.path.exists(qf):
                    _restore_qdrant_jsonl(qf, new_coll_id)

                _update(progress=70, message="Import: restoring Elasticsearch documents...")
                ef = _os.path.join(temp_dir, "es.jsonl")
                if _os.path.exists(ef):
                    _restore_es_jsonl(ef, new_coll_id, doc_id_map)

                _update(progress=85, message="Import: restoring PostgreSQL graph data...")
                pg_dir = _os.path.join(temp_dir, "pg")
                if _os.path.exists(pg_dir):
                    _restore_pg_jsonl(pg_dir, new_coll_id, old_coll_id)
        else:
            _update(progress=55, message="Import: triggering re-index for all documents...")
            _trigger_reindex(doc_id_map, get_sync_session)

        _update(
            status=ImportTaskStatus.COMPLETED, progress=100,
            message="Import complete.", collection_id=new_coll_id,
            collection_title=collection_title,
        )

    except Exception as exc:
        logger.exception(f"Import task {import_task_id} failed: {exc}")
        _update(status=ImportTaskStatus.FAILED, error_message=str(exc))
    finally:
        if temp_dir and _os.path.exists(temp_dir):
            _shutil.rmtree(temp_dir, ignore_errors=True)
        if zip_path and _os.path.exists(zip_path):
            try:
                _os.unlink(zip_path)
            except OSError:
                pass


def _create_coll(user_id, title, get_sync_session, Collection, utc_now) -> str:
    import uuid as _uuid

    from aperag.db.models import CollectionStatus
    cid = f"col{_uuid.uuid4().hex[:16]}"
    for s in get_sync_session():
        s.add(Collection(id=cid, user=user_id, title=title, status=CollectionStatus.ACTIVE, config="{}"))
        s.commit()
    return cid


def _create_doc(collection_id, user_id, name, get_sync_session, Document, utc_now) -> str:
    import uuid as _uuid

    from aperag.db.models import DocumentStatus
    did = f"doc{_uuid.uuid4().hex[:16]}"
    for s in get_sync_session():
        s.add(Document(id=did, collection_id=collection_id, user=user_id, name=name,
                        status=DocumentStatus.PENDING, doc_metadata={}))
        s.commit()
    return did


def _create_indexes(doc_id_map, get_sync_session, DocumentIndex, DocumentIndexType, DocumentIndexStatus, utc_now):
    all_types = [DocumentIndexType.VECTOR, DocumentIndexType.FULLTEXT, DocumentIndexType.GRAPH]
    for s in get_sync_session():
        for _, ndid in doc_id_map.items():
            for it in all_types:
                s.add(DocumentIndex(document_id=ndid, index_type=it, status=DocumentIndexStatus.PENDING, version=1, observed_version=0))
        s.commit()


def _trigger_reindex(doc_id_map, get_sync_session):
    from sqlalchemy import update

    from aperag.db.models import DocumentIndex, DocumentIndexStatus
    for s in get_sync_session():
        s.execute(update(DocumentIndex).where(DocumentIndex.document_id.in_(list(doc_id_map.values())))
                   .values(status=DocumentIndexStatus.PENDING, version=DocumentIndex.version + 1))
        s.commit()


def _restore_qdrant_jsonl(jsonl_path: str, collection_name: str):
    import json as _json

    from aperag.config import settings
    if settings.vector_db_type != "qdrant":
        return
    import qdrant_client
    from qdrant_client.models import Distance, VectorParams
    ctx = _json.loads(settings.vector_db_context)
    client = qdrant_client.QdrantClient(url=ctx.get("url","http://localhost"), port=ctx.get("port",6333), timeout=300)
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    with open(jsonl_path, "r", encoding="utf-8") as f:
        first = _json.loads(f.readline())
        dim = len(first.get("vector", []))
    client.create_collection(collection_name, VectorParams(size=dim, distance=Distance.COSINE))
    points = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            rec = _json.loads(line)
            points.append(qdrant_client.models.PointStruct(id=rec["id"], vector=rec["vector"], payload=rec.get("payload",{})))
            if len(points) >= 100:
                client.upsert(collection_name=collection_name, points=points)
                points = []
    if points:
        client.upsert(collection_name=collection_name, points=points)


def _restore_es_jsonl(jsonl_path: str, collection_id: str, doc_id_map: dict):
    import json as _json

    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk

    from aperag.config import settings
    es = Elasticsearch(settings.es_host, request_timeout=settings.es_timeout, max_retries=settings.es_max_retries)
    index_name = str(collection_id)
    if not es.indices.exists(index=index_name).body:
        from aperag.index.fulltext_index import create_index as _create_es_index
        _create_es_index(es, index_name)
    actions = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            doc = _json.loads(line)
            oid = doc.get("document_id", "")
            if oid in doc_id_map:
                doc["document_id"] = doc_id_map[oid]
            actions.append({"_index": index_name, "_source": doc})
            if len(actions) >= 100:
                bulk(es, actions)
                actions = []
    if actions:
        bulk(es, actions)


def _restore_pg_jsonl(pg_dir: str, new_ws: str, old_ws: str):
    import json as _json
    import os as _os

    from sqlalchemy import delete

    from aperag.config import get_sync_session
    from aperag.db.models import (
        LightRAGDocChunksModel,
        LightRAGGraphEdge,
        LightRAGGraphNode,
        LightRAGVDBEntityModel,
        LightRAGVDBRelationModel,
    )
    tmap = {
        "graph_nodes.jsonl": (LightRAGGraphNode, ["id","entity_id","entity_name","entity_type","description","source_id","file_path","workspace"]),
        "graph_edges.jsonl": (LightRAGGraphEdge, ["id","source_entity_id","target_entity_id","weight","keywords","description","source_id","file_path","workspace"]),
        "vdb_entity.jsonl": (LightRAGVDBEntityModel, ["id","entity_name","content","chunk_ids","file_path","workspace"]),
        "vdb_relation.jsonl": (LightRAGVDBRelationModel, ["id","source_id","target_id","content","chunk_ids","file_path","workspace"]),
        "doc_chunks.jsonl": (LightRAGDocChunksModel, ["id","full_doc_id","chunk_order_index","tokens","content","file_path","workspace"]),
    }
    for s in get_sync_session():
        for _, (model, _) in tmap.items():
            s.execute(delete(model).where(model.workspace == new_ws))
        s.commit()
    for fn, (model, cols) in tmap.items():
        fp = _os.path.join(pg_dir, fn)
        if not _os.path.exists(fp):
            continue
        rows = []
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                rec = _json.loads(line)
                rec["workspace"] = new_ws
                for k in ("id","entity_id","source_id","target_id","source_entity_id","target_entity_id"):
                    if k in rec and isinstance(rec[k], str) and old_ws:
                        rec[k] = rec[k].replace(f":{old_ws}", f":{new_ws}")
                rows.append(rec)
        for s in get_sync_session():
            for row in rows:
                s.add(model(**{k: row.get(k) for k in cols}))
            s.commit()


@app.task(bind=True, soft_time_limit=55 * 60, time_limit=60 * 60)
def import_collection_reindex_task(self, import_task_id: str):
    """Celery task: continue a paused import by triggering re-index."""
    from sqlalchemy import select, update

    from aperag.config import get_sync_session
    from aperag.db.models import DocumentIndex, DocumentIndexStatus, ImportTask, ImportTaskStatus
    from aperag.utils.utils import utc_now

    for session in get_sync_session():
        r = session.execute(select(ImportTask).where(ImportTask.id == import_task_id))
        t = r.scalars().first()
        if not t:
            return
        collection_id = t.collection_id
        t.status = ImportTaskStatus.PROCESSING
        t.progress = 55
        t.message = "Import: triggering re-index..."
        t.gmt_updated = utc_now()
        session.commit()

        # Trigger re-index for all documents in the new collection
        stmt = (
            update(DocumentIndex)
            .where(DocumentIndex.document_id.in_(
                select(DocumentIndex.document_id).where(
                    DocumentIndex.index_type == "VECTOR",
                    DocumentIndex.document_id.like("doc%"),
                )
            ))
            .values(status=DocumentIndexStatus.PENDING, version=DocumentIndex.version + 1)
        )
        # Re-index docs belonging to the imported collection
        from aperag.db.models import Document
        doc_stmt = select(Document.id).where(Document.collection_id == collection_id)
        doc_ids = [r[0] for r in session.execute(doc_stmt).all()]

        for did in doc_ids:
            session.execute(
                update(DocumentIndex)
                .where(DocumentIndex.document_id == did)
                .values(status=DocumentIndexStatus.PENDING, version=DocumentIndex.version + 1)
            )

        t.status = ImportTaskStatus.COMPLETED
        t.progress = 100
        t.message = "Import complete (re-indexed with target model)."
        t.gmt_completed = utc_now()
        session.commit()


def _check_embedding_match(manifest: dict) -> bool:
    """Check if the target instance's embedding model matches the export.

    Returns True if vectors can be restored directly, False if re-index is needed.
    """
    export_dim = manifest.get("embedding_dim", 0)
    if not export_dim:
        return True  # No dimension info, assume compatible

    try:
        import json as _json

        from aperag.config import settings

        ctx = _json.loads(settings.vector_db_context)
        # Get target vector dimension by creating a test collection
        import qdrant_client as qc

        client = qc.QdrantClient(
            url=ctx.get("url", "http://localhost"),
            port=ctx.get("port", 6333),
            timeout=5,
        )
        # Check existing collections to find one with matching dim
        collections = client.get_collections().collections
        for c in collections:
            try:
                info = client.get_collection(c.name)
                target_dim = info.config.params.vectors.size
                if target_dim == export_dim:
                    return True  # Same dimension, vectors are compatible
            except Exception:
                pass

        # No matching collection found — different embedding model likely
        logger.warning(
            f"Embedding dimension mismatch: export={export_dim}, "
            f"no matching collection found on target. Falling back to re-index."
        )
        return False
    except Exception as e:
        logger.warning(f"Could not verify embedding compatibility: {e}, assuming compatible")
        return True  # If we can't check, assume it's OK
