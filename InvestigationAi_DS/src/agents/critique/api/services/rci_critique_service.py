import logging

logger = logging.getLogger(__name__)

from src.agents.critique.api.schemas import CritiqueOutSchema, TaskOutSchema, CritiqueInputSchema
from fastapi import HTTPException
from typing import List
import asyncio
import json

BATCH_SIZE = 2                # tasks per call
MAX_CONCURRENCY = 15           # how many calls in parallel
PER_CALL_TIMEOUT_S = 90        # timeout per LLM call
MAX_RETRIES = 2                # retries per chunk

sem = asyncio.Semaphore(MAX_CONCURRENCY)

def _chunk(seq, size):
    for i in range(0, len(seq), size):
        yield i, seq[i:i+size]

async def _call_with_retries(coro_factory, max_retries=MAX_RETRIES, base_delay=1.0):
    delay = base_delay
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except Exception as e:
            attempt += 1
            if attempt > max_retries:
                raise
            await asyncio.sleep(delay)
            delay *= 2  # simple backoff

async def _call_one_batch(llm, system_prompt: str, user_prefix: str, problem_statement, tasks_chunk, event_type, structure_model):
    sub_payload = {
        "event_type": event_type,
        "problem_statement": problem_statement,
        "tasks": tasks_chunk,
    }
    user_prompt = user_prefix + json.dumps(sub_payload, indent=2)

    async with sem:
        return await asyncio.wait_for(
            llm.get_structured_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                structure=structure_model,
            ),
            timeout=PER_CALL_TIMEOUT_S
        )

async def critique_in_batches(
    llm,
    system_prompt: str,
    user_prefix: str,
    data: CritiqueInputSchema,  # your existing input model
    structure_model=CritiqueOutSchema,
    batch_size: int = BATCH_SIZE,
) -> CritiqueOutSchema:
    # If you can, reduce load by sending only selected tasks:
    # tasks = [t for t in data.tasks if t.select]
    tasks = data.tasks

    if len(tasks) <= batch_size:
        # single call path (unchanged)
        user_prompt = user_prefix + json.dumps(data.model_dump(), indent=2)
        resp = await llm.get_structured_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            structure=structure_model
        )
        return resp

    # Multi-batch path
    batch_jobs = []
    for _, chunk in _chunk(tasks, batch_size):
        chunk_dicts = [t.model_dump() for t in chunk]
        batch_jobs.append(
            _call_with_retries(
                lambda ch=chunk_dicts: _call_one_batch(
                    llm, system_prompt, user_prefix, data.problem_statement, ch, data.event_type, structure_model
                )
            )
        )

    # Run in parallel
    results = await asyncio.gather(*batch_jobs, return_exceptions=True)

    # On failure, you can either:
    #  (a) fail the whole request, or
    #  (b) re-run failed chunks serially, or
    #  (c) return partial results with an error field.
    # Below: try to rescue by doing a single serial retry of failed chunks.
    stitched_tasks: List[TaskOutSchema] = []
    rescue_jobs = []
    for res in results:
        if isinstance(res, Exception):
            rescue_jobs.append(res)  # mark for rescue
        else:
            stitched_tasks.extend(res.tasks)

    if rescue_jobs:
        # As a simple rescue strategy, re-run failed ones serially (you can improve this)
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                # find which chunk it was
                start = idx * batch_size
                end = min(start + batch_size, len(tasks))
                chunk_dicts = [t.model_dump() for t in tasks[start:end]]
                try:
                    serial_resp = await _call_one_batch(
                        llm, system_prompt, user_prefix, data.problem_statement, chunk_dicts, data.event_type, structure_model
                    )
                    stitched_tasks.extend(serial_resp.tasks)
                except Exception as final_e:
                    # Couldn't recover
                    raise HTTPException(status_code=504, detail=f"Critique timed out for chunk {idx}: {final_e}")

    return CritiqueOutSchema(
        problem_statement=data.problem_statement,
        tasks=stitched_tasks
    )


    