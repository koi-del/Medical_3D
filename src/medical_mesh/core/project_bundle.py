"""Verified portable project archive; never extracts arbitrary ZIP paths."""
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
import numpy as np
from ..io.mesh_io import save_mesh,load_mesh


def export_summary(asset):
    size=np.ptp(asset.vertices,axis=0)
    try:factor=float(asset.unit_to_mm)
    except (TypeError,ValueError):factor=float('nan')
    known=asset.unit_status=='confirmed' and bool(asset.source_unit) and np.isfinite(factor) and factor>0
    return dict(unit=asset.source_unit if known else '未知（原坐标）',dimensions=size.tolist(),
                dimensions_mm=(size*factor).tolist() if known else None,
                coincident_indexed_vertices=len(asset.vertices)-len(np.unique(asset.vertices,axis=0)))


def save_project(path,asset,diagnosis,roles,store=None):
    if diagnosis.get('input_version')!=asset.version:raise ValueError('检测结果与当前版本不一致')
    if store and store.current_version!=asset.version:raise ValueError('只能打包当前已提交版本')
    payload={}
    with tempfile.TemporaryDirectory() as folder:
        mesh_path=Path(folder)/'current.npz';save_mesh(asset,mesh_path)
        payload['current.npz']=mesh_path.read_bytes()
    payload['diagnosis.json']=json.dumps(diagnosis,ensure_ascii=False).encode('utf-8')
    payload['boundary_roles.json']=json.dumps(roles,ensure_ascii=False).encode('utf-8')
    if store:
        current=asset;seen=set()
        while current.version not in seen:
            seen.add(current.version)
            for suffix in ('.npz','.result.json','.review.json'):
                source=store.root/(current.version+suffix)
                if source.exists():payload['versions/'+source.name]=source.read_bytes()
            if not current.parent_version:break
            parent=store.root/(current.parent_version+'.npz')
            if not parent.exists():break
            current=load_mesh(parent)
    manifest=dict(schema=1,version=asset.version,asset_id=asset.asset_id,geometry_hash=asset.geometry_hash(),
                  summary=export_summary(asset),files={name:hashlib.sha256(data).hexdigest() for name,data in payload.items()})
    payload['manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
    target=Path(path);temporary=target.with_name(target.name+'.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in payload.items():archive.writestr(name,data)
        temporary.replace(target)
    finally:
        if temporary.exists():temporary.unlink()


def load_project(path):
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist();names=[i.filename for i in infos]
        if len(names)!=len(set(names)) or len(names)>5000 or sum(i.file_size for i in infos)>2_000_000_000:
            raise ValueError('项目包过大或包含重复条目')
        fixed={'manifest.json','current.npz','diagnosis.json','boundary_roles.json'}
        for name in names:
            if name not in fixed and not re.fullmatch(r'versions/[a-f0-9]{32}\.(npz|result\.json|review\.json)',name):
                raise ValueError('项目包包含不允许的路径')
        if not fixed.issubset(names):raise ValueError('项目包缺少必要文件')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('schema')!=1 or set(manifest['files'])!=set(names)-{'manifest.json'}:
            raise ValueError('项目包清单不完整或版本不支持')
        payload={name:archive.read(name) for name in manifest['files']}
        if any(hashlib.sha256(data).hexdigest()!=manifest['files'][name] for name,data in payload.items()):
            raise ValueError('项目包文件校验失败')
    with tempfile.TemporaryDirectory() as folder:
        mesh_path=Path(folder)/'current.npz';mesh_path.write_bytes(payload['current.npz']);asset=load_mesh(mesh_path)
        for field in (asset.version,asset.asset_id,asset.parent_version):
            if field is not None and not re.fullmatch('[a-f0-9]{32}',field):raise ValueError('项目包版本标识不合法')
        for name,data in payload.items():
            if name.startswith('versions/') and name.endswith('.npz'):
                history_path=Path(folder)/'history.npz';history_path.write_bytes(data);previous=load_mesh(history_path)
                if previous.version!=Path(name).stem or previous.asset_id!=asset.asset_id:
                    raise ValueError('历史快照标识不一致')
                if previous.parent_version is not None and not re.fullmatch('[a-f0-9]{32}',previous.parent_version):
                    raise ValueError('历史父版本标识不合法')
    if asset.geometry_hash()!=manifest['geometry_hash'] or asset.version!=manifest['version'] or asset.asset_id!=manifest['asset_id']:
        raise ValueError('项目包模型与清单不一致')
    diagnosis=json.loads(payload['diagnosis.json']);roles=json.loads(payload['boundary_roles.json'])
    if diagnosis.get('input_version')!=asset.version:raise ValueError('项目包检测结果版本不一致')
    if not isinstance(roles,dict) or any(role not in {'uncertain','natural','repair_target'} for role in roles.values()):
        raise ValueError('项目包边界用途不合法')
    return asset,diagnosis,roles,{name.split('/')[1]:data for name,data in payload.items() if name.startswith('versions/')}
