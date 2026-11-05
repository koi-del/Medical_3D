"""Geometry-backed explanations for diagnostic selections (no Qt/VTK dependency)."""
import numpy as np


def diagnostic_items(diagnosis):
    d = diagnosis['defects']
    items = []
    def add(text, kind, faces=(), edges=(), vertices=(), description=''):
        items.append(dict(text=text, kind=kind, faces=list(faces), edges=list(edges),
                          vertices=list(vertices), description=description))
    add(f"重复面：{len(d['duplicate_face_ids'])} 个面", 'duplicate', d['duplicate_face_ids'],
        description='红色表示重复三角面，与已有面占据相同位置。')
    add(f"退化面：{len(d['degenerate_face_ids'])} 个面", 'degenerate', d['degenerate_face_ids'],
        description='紫色粗线和端点表示退化面的实际位置。面积为零的面已塌成线或点，无法用普通面着色显示。')
    conflicts = d['orientation_conflicts']
    faces = sorted({i for x in conflicts for i in x['face_ids']})
    add(f"方向冲突：{len(conflicts)} 条边（涉及 {len(faces)} 个面）", 'orientation', faces,
        [x['edge'] for x in conflicts], description='黄色是冲突公共边，红色是涉及的面。橙色箭头表示两面沿公共边的遍历方向，同向即冲突；青色箭头是按顶点顺序计算的面法线。涉及面不等于全部翻反。')
    bad_edges = d['non_manifold_edges']
    faces = sorted({i for x in bad_edges for i in x['face_ids']})
    detail = '；'.join(f"边{tuple(x['edge'])}由{len(x['face_ids'])}个面共享：{x['face_ids']}" for x in bad_edges[:3])
    add(f"非流形边：{len(bad_edges)} 条（涉及 {len(faces)} 个面）", 'nonmanifold_edge', faces,
        [x['edge'] for x in bad_edges], description='黄色粗线是非流形边，红色是共享它的面。正常内部边应由2个面共享。'+detail)
    bad_vertices = d['non_manifold_vertices']
    faces = sorted({i for x in bad_vertices for i in x['face_ids']})
    add(f"非流形顶点：{len(bad_vertices)} 个点（涉及 {len(faces)} 个面）", 'nonmanifold_vertex',
        vertices=[x['vertex_id'] for x in bad_vertices],
        description='紫色圆点是非流形顶点；相邻面在该点周围未形成正常的单环或单链。')
    if diagnosis['self_intersection']['status'] == 'verified':
        ids = diagnosis['self_intersection']['face_ids']
        add(f"自交：{len(ids)} 个标记面", 'intersection', ids, description='红色为自交组件标记的三角面，数量不是相交对数。')
    for b in diagnosis['boundaries']:
        simple = b['kind'] == 'simple_loop'
        add(f"边界 {b['id']} · {'闭合边界环' if simple else '开放链 / 分叉'} · {b['edge_count']}边 · 跨度{b['span']:.4g}",
            'boundary', edges=b['edges'], description='黄色仅标出边界，不把邻接的正常面染红。边界可能是天然管口，也可能是缺面；需结合模型用途判断。'+('选中后标记为“待补孔洞”才会补洞；天然开口和待判断闭环保留。' if simple else '此边界不是简单闭环，不能直接补洞；明确选择删面方案时可改变附属缺陷链。标记为天然开口后则强制保留。'))
        items[-1]['boundary'] = b['id']
    return items


def selection_geometry(asset, selected):
    faces = sorted({i for x in selected if x['kind'] != 'degenerate' for i in x['faces']})
    edges = sorted({tuple(sorted(e)) for x in selected for e in x.get('edges', [])})
    degenerate = [i for x in selected if x['kind'] == 'degenerate' for i in x['faces']]
    points = {i for x in selected for i in x.get('vertices', [])}
    collapsed = set()
    for fid in degenerate:
        ids = list(map(int, asset.faces[fid]))
        points.update(ids)
        collapsed.update(tuple(sorted((a,b))) for a,b in zip(ids, ids[1:]+ids[:1]) if a != b)
    focus = sorted(points | {i for e in edges for i in e} | {int(i) for fid in faces for i in asset.faces[fid]})
    normals, traversals = [], []
    orient_faces = sorted({i for x in selected if x['kind'] == 'orientation' for i in x['faces']})
    for fid in orient_faces[:12]:
        t = asset.vertices[asset.faces[fid]]
        n = np.cross(t[1]-t[0], t[2]-t[0])
        length = np.linalg.norm(n)
        if length: normals.append((t.mean(axis=0), n/length, np.linalg.norm(t[1]-t[0])*.65))
    for x in selected:
        if x['kind'] != 'orientation': continue
        for a,b in x['edges'][:6]:
            for fid in x['faces']:
                ids = list(map(int,asset.faces[fid]))
                for u,w in zip(ids,ids[1:]+ids[:1]):
                    if {u,w} != {a,b}: continue
                    p,q = asset.vertices[[u,w]]
                    center = asset.vertices[ids].mean(axis=0)
                    offset = (center-(p+q)/2)*.3
                    traversals.append((p+(q-p)*.2+offset,(q-p)*.6))
    return dict(faces=faces, edges=edges, points=sorted(points), collapsed_edges=sorted(collapsed),
                focus_ids=focus, normals=normals, traversals=traversals)
