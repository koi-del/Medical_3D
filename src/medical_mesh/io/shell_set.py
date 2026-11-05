"""Separate-shell STL archive: preserves object separation without changing coordinates."""
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
import numpy as np
from .mesh_io import load_mesh,save_mesh
from ..detection.topology import detect_defects


def save_shell_set(asset,path):
    diagnosis=detect_defects(asset,check_self_intersection=True)
    if not diagnosis.metrics['topology_passed'] or diagnosis.self_intersection['status']!='verified' or diagnosis.self_intersection['face_ids']:
        raise ValueError('分壳STL导出需要拓扑和自交复检通过的已接受模型')
    groups=diagnosis.components
    if sorted(fid for group in groups for fid in group)!=list(range(len(asset.faces))):
        raise ValueError('分壳导出不能遗漏重复或退化面')
    destination=Path(path);destination.parent.mkdir(parents=True,exist_ok=True)
    manifest=dict(format='medical_mesh_separate_stl_shells_v1',input_version=asset.version,
        geometry_hash=asset.geometry_hash(),source_metadata=asset.metadata(),shells=[],
        warning='各STL必须作为独立对象导入；合并并焊接重合坐标后可能再次产生粘连。原坐标不作偏移。')
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        for index,group in enumerate(groups):
            faces=asset.faces[group];used,inverse=np.unique(faces,return_inverse=True)
            shell=asset.derive(vertices=asset.vertices[used],faces=inverse.reshape(-1,3))
            before=detect_defects(shell).metrics
            file=root/f'shell_{index+1:03d}.stl';save_mesh(shell,file)
            def check():
                d=detect_defects(load_mesh(file),check_self_intersection=True)
                return (d.metrics['topology_passed'] and d.metrics['component_count']==1 and
                    d.metrics['boundary_edge_count']==before['boundary_edge_count'] and
                    d.self_intersection['status']=='verified' and not d.self_intersection['face_ids']),d
            passed,after=check();encoding='binary_float32'
            if not passed:
                save_mesh(shell,file,ascii=True);passed,after=check();encoding='ascii_float64'
            if not passed:raise ValueError(f'第{index+1}个壳体STL回读复检失败，未生成集合')
            manifest['shells'].append(dict(file=file.name,input_face_ids=list(map(int,group)),
                encoding=encoding,sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                diagnosis=after.to_dict()))
        (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        (root/'使用说明.txt').write_text(manifest['warning']+'\n每个文件已分别回读并完成拓扑和自交复检。\n',encoding='utf-8')
        with tempfile.NamedTemporaryFile(dir=destination.parent,prefix=destination.name+'.',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name)
        try:
            with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(root.iterdir()):archive.write(file,file.name)
            temporary.replace(destination)
        finally:
            if temporary.exists():temporary.unlink()
    return manifest
