"""Version 4 annotation contract; legacy v3 remains unchanged for trained models."""
import copy
import json
import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / 'annotations/annotation-schema-v4.yaml'
EXTRA_COLUMNS = ('obstacle_instances','instances_availability','obstacle_type_availability','surface_obstacle_availability','surface_material','route_scope','feature_unknown_reasons','workflow_status','review_flags','review_acknowledged','annotator_id','reviewed_at','protocol_version','captured_at','source_metadata','legacy_annotation')
RELATIONS = ('outside','encroaching','on_path','unknown')
WORKFLOW = ('pending_review','pending_annotation','finalized')


def schema():
    return yaml.safe_load(SCHEMA_PATH.read_text(encoding='utf-8-sig'))


def columns():
    from tools.annotation_app.core import load_schema
    return (*load_schema(ROOT/'annotations/annotation-schema.yaml').csv_columns,*EXTRA_COLUMNS)


def migrate(row, *, filename=None, metadata=None, flags=()):
    if row.get('schema_version') == '4':
        return copy.deepcopy(row)
    result=copy.deepcopy(row)
    result.update({name:'' for name in EXTRA_COLUMNS})
    result.update(filename=filename or row['filename'], schema_version='4', obstacle_instances='[]',
                  instances_availability='unknown',obstacle_type_availability='unknown',surface_obstacle_availability='unknown',
                  surface_material='unknown',route_scope='unknown',feature_unknown_reasons='{}',workflow_status='pending_review',
                  review_flags=json.dumps(list(dict.fromkeys(['legacy_protocol_review',*flags]))),review_acknowledged='false',protocol_version='4.0',
                  source_metadata=json.dumps(metadata or {},ensure_ascii=False),legacy_annotation=json.dumps(row,ensure_ascii=False))
    previous=json.loads(row.get('surface_obstacle') or '[]')
    result['surface_obstacle']=json.dumps([v for v in previous if v not in ('brick_cobblestone','debris')])
    if set(previous)&{'brick_cobblestone','debris'}:
        result['review_flags']=json.dumps([*json.loads(result['review_flags']),'surface_semantics_changed'])
    return result


def validate(row, *, finalized=False):
    s=schema()
    if row.get('schema_version')!='4':raise ValueError('Expected schema v4')
    filename=row.get('filename','')
    if not filename or filename.startswith('/') or any(p in filename for p in ('\\',':')) or '..' in filename.split('/'):
        raise ValueError('Invalid relative filename')
    if row.get('workflow_status') not in WORKFLOW:raise ValueError('Invalid workflow state')
    final=finalized or row['workflow_status']=='finalized'
    for name,field in s['labels'].items():
        value=row.get(name,'')
        allowed={o['value'] for o in field['options']}
        if field['type']=='multilabel':
            items=json.loads(value or '[]')
            if not isinstance(items,list) or len(items)!=len(set(items)) or not set(items)<=allowed:raise ValueError(f'Invalid {name}')
        elif value not in allowed and (value or final):raise ValueError(f'Invalid {name}')
    from tools.annotation_app.core import validate_circulation_path
    polygons=json.loads(row.get('circulation_path') or '[]')
    # Existing validator accepts the same normalized geometry format.
    validate_circulation_path(polygons)
    if row.get('circulation_path_status') not in ('annotated','absent','unknown'):raise ValueError('Invalid path status')
    if (row['circulation_path_status']=='annotated') != bool(polygons):raise ValueError('Path status/geometry mismatch')
    for key in ('image_width','image_height'):
        if int(row.get(key,'0'))<=0:raise ValueError('Invalid dimensions')
    for key in ('instances_availability','obstacle_type_availability','surface_obstacle_availability'):
        if row.get(key) not in ('unknown','assessed'):raise ValueError(f'Invalid {key}')
    instances=json.loads(row.get('obstacle_instances') or '[]')
    if not isinstance(instances,list):raise ValueError('Instances must be a list')
    ids=set();types={o['value'] for o in s['labels']['obstacle_type']['options']}
    for instance in instances:
        if not isinstance(instance,dict) or set(instance)!={'id','type','bbox','path_relation'}:raise ValueError('Invalid instance fields')
        if not isinstance(instance['id'],str) or not instance['id'] or instance['id'] in ids:raise ValueError('Invalid instance ID')
        ids.add(instance['id']);box=instance['bbox']
        if instance['type'] not in types or instance['path_relation'] not in RELATIONS:raise ValueError('Invalid obstacle type/relation')
        if not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in box) or box[0]>=box[2] or box[1]>=box[3]:raise ValueError('Invalid normalized bbox')
    for key in ('review_flags',):
        if not isinstance(json.loads(row.get(key) or '[]'),list):raise ValueError(f'Invalid {key}')
    for key in ('source_metadata','legacy_annotation','feature_unknown_reasons'):
        if not isinstance(json.loads(row.get(key) or '{}'),dict):raise ValueError(f'Invalid {key}')
    reasons=json.loads(row.get('feature_unknown_reasons') or '{}')
    if any(k not in s['labels'] or v not in s['unknown_reason_values'] for k,v in reasons.items()):raise ValueError('Invalid unknown-information reason')
    if row.get('circulation_path_origin') not in ('manual','segformer_v1_accepted','segformer_v1_corrected'):raise ValueError('Invalid mask origin')
    if row.get('review_acknowledged') not in ('true','false'):raise ValueError('Invalid review acknowledgment')
    if row.get('surface_material') not in s['surface_material_values'] or row.get('route_scope') not in s['route_scope_values']:raise ValueError('Invalid material/context')
    if final and (not row.get('annotator_id','').strip() or row.get('review_acknowledged')!='true' or not row.get('reviewed_at')):
        raise ValueError('Finalization requires reviewer, acknowledgment and date')


def development_rows(dataset):
    """Fail closed: never expose holdout, quarantined, or unfinished rows as train data."""
    import csv
    dataset=Path(dataset)
    with (dataset/'dataset_manifest.csv').open(encoding='utf-8-sig',newline='') as f:manifest={r['filename']:r for r in csv.DictReader(f)}
    with (dataset/'transitability_annotations.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    holdout_groups={r.get('group_id') for r in manifest.values() if r['experimental_partition']=='holdout' and r.get('group_id')}
    if any(r.get('group_id') in holdout_groups and r['experimental_partition']!='holdout' for r in manifest.values()):raise ValueError('Holdout group overlaps development')
    result=[]
    for row in rows:
        meta=manifest[row['filename']]
        if meta['experimental_partition']!='development' or meta['quarantined']=='true' or row['workflow_status']!='finalized':continue
        validate(row,finalized=True)
        if row['circulation_path_status']=='annotated':result.append(row)
    return result
def workspace_schema():
    s=schema()
    fields=[{'name':name,'display_name':spec['display_name'],'kind':spec['type'],'required':spec['required'],'description':spec['description'],'empty_means':spec.get('empty_means'),'options':spec['options']} for name,spec in s['labels'].items()]
    return {'version':4,'columns':list(columns()),'fields':fields,'surface_material_values':s['surface_material_values'],'route_scope_values':s['route_scope_values'],'unknown_reason_values':s['unknown_reason_values'],'groups':[['PASSAGEM',['passage_width','obstruction','path_continuity']],['SUPERFÍCIE',['surface_condition','surface_obstacle']],['OBJETOS',['obstacle_type']],['TRANSIÇÕES E CONTEXTO',['level_change','ramp_condition','curb_access','slope','detour']],['REVISÃO',['annotation_confidence']]]}
