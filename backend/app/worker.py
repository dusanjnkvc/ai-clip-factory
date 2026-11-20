"""Independent durable worker. Run with ``python -m app.worker``.

SQL compare-and-set claims work on Postgres and SQLite; individual clips are
committed before the next render. Rendering never occupies a web request.
"""
import hashlib
import json
import logging
import os
import signal
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select, update, or_, text
from .db import SessionLocal
from .models import (ProcessingJob, Transcript, SourceVideo, MediaRightsRecord, ClipCandidate,
    EditingPlan, RenderedClip, ClipVersion, ComplianceCheck, AuditLog, DraftEvaluation, now)
from .storage import materialize, put_file
from .usage import record_usage
from .runtime import free_mode, create_pipeline_service

log = logging.getLogger('factory.worker')
stopping = False

def claim_job():
    with SessionLocal() as db:
        # Serialize the short selection transaction. Two workers must not claim
        # different campaign jobs that share one source and race transcription.
        if db.bind.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(7126043102)'))
        # A lost worker's lease can be reclaimed. Jobs retain persisted transcripts,
        # plans and completed clips, so crash recovery does not restart the batch.
        db.execute(update(ProcessingJob).where(ProcessingJob.status == 'processing', ProcessingJob.lease_until < now()).values(status='queued', stage='Recovering interrupted job'))
        db.commit()
        in_flight = list(db.scalars(select(ProcessingJob).where(ProcessingJob.status == 'processing')))
        if any(item.payload.get('processing_provider') == 'local_ai' for item in in_flight): return None
        occupied = select(ProcessingJob.source_id).where(ProcessingJob.status == 'processing')
        candidate = db.scalar(select(ProcessingJob).where(ProcessingJob.status == 'queued', ~ProcessingJob.source_id.in_(occupied)).order_by(ProcessingJob.created_at).limit(1))
        if not candidate:
            return None
        if candidate.payload.get('processing_provider') == 'local_ai' and in_flight: return None
        claimed = db.execute(update(ProcessingJob).where(ProcessingJob.id == candidate.id, ProcessingJob.status == 'queued').values(status='processing', stage='Preparing source', attempts=ProcessingJob.attempts + 1, lease_until=now() + timedelta(minutes=30)))
        db.commit()
        return candidate.id if claimed.rowcount else None

def progress(job_id, stage, percent):
    with SessionLocal() as db:
        db.execute(update(ProcessingJob).where(ProcessingJob.id == job_id, ProcessingJob.status == 'processing').values(stage=stage, progress=percent, lease_until=now() + timedelta(minutes=30)))
        db.commit()

def process_job(job_id):
    with SessionLocal() as lookup:
        snapshot = lookup.get(ProcessingJob, job_id)
        auto = snapshot.payload.get('processing_provider') == 'local_ai'
        options = snapshot.payload.get('options', {})
        stored_bundle=snapshot.payload.get('auto_result',{})
    if auto:
        from .services.local_auto import LocalAutoPipelineService
        service = LocalAutoPipelineService(options, lambda stage,percent:progress(job_id,stage,percent))
        service.bundle=stored_bundle
        import threading
        def watch_cancel():
            while not service.cancel.wait(.5):
                with SessionLocal() as check:
                    current = check.get(ProcessingJob, job_id)
                    if not current or current.status not in {'queued','processing'}:
                        return
                    if current.payload.get('cancel_requested'):
                        service.cancel.set()
                        return
        threading.Thread(target=watch_cancel, daemon=True).start()
    else:
        service = create_pipeline_service()
    started = time.monotonic()
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        source = db.get(SourceVideo, job.source_id)
        transcript_row = db.scalar(select(Transcript).where(Transcript.source_id == source.id))
        rights = db.scalar(select(MediaRightsRecord).where(MediaRightsRecord.source_id == source.id, MediaRightsRecord.confirmed.is_(True)))
        if not rights:
            raise ValueError('Source rights must be confirmed before processing.')
        rights_payload = {'authorized': True, 'confirmed': True, 'attestation': rights.note}
        rules = job.rules_snapshot
        previous = [row.plan for row in db.scalars(select(EditingPlan).join(ClipCandidate).where(ClipCandidate.source_id == source.id, ClipCandidate.job_id != job_id))]
        transcript = transcript_row.content if transcript_row else None
        with materialize(source.storage_key) as source_path, tempfile.TemporaryDirectory(prefix='acf-render-') as temp:
            work = Path(temp)
            if auto: service.source_path = source_path
            if transcript is None:
                progress(job_id, 'Reading optional local subtitles' if free_mode() else 'Transcribing source with hosted AI', 8)
                transcript = service.transcribe(source_path, cache_path=work / 'transcript.json')
                record_usage(db, service, job.user_id, job.id)
                db.add(Transcript(source_id=source.id, content=transcript, provider=transcript.get('provider',os.getenv('TRANSCRIPTION_MODEL','whisper-1'))))
                db.commit()
            existing = list(db.scalars(select(EditingPlan).join(ClipCandidate).where(ClipCandidate.job_id == job_id).order_by(ClipCandidate.created_at)))
            if not existing:
                progress(job_id, 'Selecting distinct local-AI moments and planning edits' if auto else 'Validating your manual clip selection' if free_mode() else 'Selecting distinct moments and planning edits', 52 if auto else 20)
                if job.payload.get('plan'):
                    plans=[job.payload['plan']]
                elif free_mode() and not auto:
                    if not job.payload.get('manual_selection'):
                        from .services.media import ConfigurationError
                        raise ConfigurationError('Free local rendering needs a manual selection. Create a new clip with start/end times; no AI request was made.')
                    from .services.local import build_manual_plan
                    plans=[build_manual_plan(job.payload['manual_selection'],{**source.media_info,'filename':source.filename},transcript,rules)]
                else:
                    plans=service.plan_clips(transcript,rules,{**source.media_info,'path':str(source_path)},count=job.clip_count,mode=job.mode,previous=previous)
                record_usage(db, service, job.user_id, job.id)
                for plan in plans:
                    fingerprint = hashlib.sha256(json.dumps({'source': source.sha256, 'scenes': plan.get('scenes'), 'start': plan.get('start'), 'end': plan.get('end')}, sort_keys=True).encode()).hexdigest()
                    candidate = ClipCandidate(job_id=job.id, source_id=source.id, start=plan['start'], end=plan['end'], scores=plan.get('scores', {}), fingerprint=fingerprint)
                    db.add(candidate)
                    db.flush()
                    row = EditingPlan(candidate_id=candidate.id, plan=plan, rules_snapshot=rules)
                    db.add(row)
                    existing.append(row)
                db.commit()
            completed_ids = set(db.scalars(select(RenderedClip.editing_plan_id).where(RenderedClip.job_id == job_id)))
            if auto:
                from .publishing import selected_metadata
                service.used_titles=[selected_metadata(c.metadata_json,'youtube').get('title','') for c in db.scalars(select(RenderedClip).where(RenderedClip.job_id==job_id))]
            for index, plan_row in enumerate(existing):
                if stopping:
                    raise InterruptedError('Worker stopping; job will resume.')
                if plan_row.id in completed_ids or index < job.completed_clips:
                    continue
                if auto:
                    total=max(1,len(existing))
                    service.progress=lambda stage,percent,i=index:progress(job_id,f'Draft {i+1} of {total} · '+stage,
                        62+int(i/total*36)+int(max(0,min(1,(percent-65)/30))*36/total))
                    progress(job_id,f'Preparing local draft {index+1} of {total}',62+int(index/total*36))
                else:
                    progress(job_id, f'Rendering clip {index + 1} of {len(existing)} · metadata in parallel', 25 + int(index / max(1, len(existing)) * 65))
                output = work / f'{plan_row.id}.mp4'
                if auto:
                    # Finish inference and release its model before CPU rendering.
                    metadata = job.payload['metadata'] if job.payload.get('metadata') else service.generate_metadata(plan_row.plan, rules)
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(plan_row, 'plan')
                    db.refresh(job, ['payload'])
                    if job.payload.get('cancel_requested'): service.cancel.set()
                    job.payload = {**job.payload, 'auto_result': service.bundle}
                    db.commit()
                    render = service.render_clip(source_path, plan_row.plan, transcript, output, mode=job.mode)
                else:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        metadata_future = pool.submit(lambda: job.payload['metadata']) if job.payload.get('metadata') else pool.submit(service.generate_metadata, plan_row.plan, rules)
                        render = service.render_clip(source_path, plan_row.plan, transcript, output, mode=job.mode)
                        metadata = metadata_future.result()
                record_usage(db, service, job.user_id, job.id)
                evaluation=service.evaluate_render(output,plan_row.plan,metadata) if auto and options.get('studio') else None
                if auto and options.get('studio') and not job.payload.get('metadata'):
                    metadata=service.finalize_metadata(plan_row.plan,metadata,evaluation,rules)
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(plan_row,'plan')
                    if evaluation and evaluation.get('visual'):
                        from .services.viral_score import score_metadata
                        evaluation={**evaluation,'platforms':score_metadata(evaluation['visual'],metadata,service.bundle.get('research'))}
                compliance = service.check_compliance(plan_row.plan, metadata, rules, rights_payload, render, draft_approved=False)
                target_id = job.payload.get('clip_id')
                clip = db.get(RenderedClip, target_id) if target_id else None
                if clip:
                    if clip.user_id != job.user_id or clip.current_version != job.payload['base_version']:
                        raise ValueError('Clip changed while this edit was queued. Review and retry your changes.')
                    clip.current_version += 1
                    clip.editing_plan_id=plan_row.id
                    clip.title=str(plan_row.plan.get('title') or plan_row.plan.get('hook') or 'Untitled clip')[:300]
                    clip.media_info={k:v for k,v in render.items() if k not in {'path','subtitles_path'}}
                    clip.metadata_json=metadata
                    clip.edit_dna=plan_row.plan.get('edit_dna',{})
                    clip.compliance=compliance
                    clip.status='ready' if compliance.get('status')=='PASS' else 'review'
                    clip.draft_approved=False
                else:
                    clip = RenderedClip(user_id=job.user_id, job_id=job.id, campaign_id=job.campaign_id, source_id=source.id, editing_plan_id=plan_row.id,
                        title=str(plan_row.plan.get('title') or plan_row.plan.get('hook') or 'Untitled clip')[:300], storage_key='pending', media_info={k:v for k,v in render.items() if k not in {'path','subtitles_path'}}, metadata_json=metadata,
                        edit_dna=plan_row.plan.get('edit_dna', {}), compliance=compliance, status='ready' if compliance.get('status') == 'PASS' else 'review')
                    db.add(clip)
                    db.flush()
                key = f'{job.user_id}/clips/{clip.id}/v{clip.current_version}.mp4'
                put_file(output, key)
                clip.storage_key = key
                if evaluation:
                    db.add(DraftEvaluation(clip_id=clip.id,version=clip.current_version,artifact_sha256=render['sha256'],evaluation=evaluation))
                db.add(ClipVersion(clip_id=clip.id, version=clip.current_version, plan=plan_row.plan, metadata_json=metadata, storage_key=key))
                db.add(ComplianceCheck(clip_id=clip.id, version=clip.current_version, status=compliance['status'], checks=compliance.get('checks', []), rules_snapshot=rules))
                job.completed_clips += 1
                if job.first_clip_seconds is None:
                    job.first_clip_seconds = time.monotonic() - started
                db.add(AuditLog(user_id=job.user_id, action='clip.rendered', entity_id=clip.id, detail={'compliance': compliance['status'], 'version': 1}))
                db.commit()  # First Clip First: observable before the next iteration.
            job.status = 'completed'
            job.stage = f'{job.completed_clips} clips ready for review'
            job.progress = 100
            job.completed_at = now()
            job.lease_until = None
            job.error = None
            db.commit()

def run_once():
    job_id = claim_job()
    if not job_id:
        return False
    try:
        process_job(job_id)
    except Exception as exc:
        from .services.pipeline import ConfigurationError
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            # Do not automatically retry a paid external request after an ambiguous
            # timeout. Explicit retry resumes persisted stages and completed clips.
            job.status = 'cancelled' if job.payload.get('cancel_requested') else 'blocked' if isinstance(exc, ConfigurationError) else 'failed'
            job.error = str(exc)[:1200]
            job.stage = 'Configuration required' if job.status == 'blocked' else 'Processing stopped; completed clips remain available'
            job.lease_until = None
            db.commit()
        log.exception('Job %s failed', job_id)
    return True

def main():
    global stopping
    logging.basicConfig(level=logging.INFO)
    # Resumable/signed upload URLs contain temporary grants, not log text.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    def stop(*_):
        global stopping
        stopping = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while not stopping:
        from .publishing import run_publish_once
        if run_publish_once():
            continue
        if run_once():
            continue
        time.sleep(2)

if __name__ == '__main__':
    main()
