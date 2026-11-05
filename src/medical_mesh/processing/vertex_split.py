"""Explicit separation of disconnected face fans, preserving coordinates."""
import numpy as np
from ..detection.topology import adjacency,connected_groups


def split_vertex_fans(vertices,faces,vertex_ids):
    vertices=vertices.copy();faces=faces.copy();records=[]
    for vertex in vertex_ids:
        if vertex<0 or vertex>=len(vertices):raise ValueError('Unknown vertex ID')
        ids=np.flatnonzero(np.any(faces==vertex,axis=1)).tolist()
        neighbors={i:set() for i in ids}
        for edge,incidents in adjacency(faces,ids).items():
            if vertex not in edge:continue
            if len(incidents)>2:raise ValueError('先处理非流形边，再拆分顶点扇区')
            if len(incidents)==2:
                a,b=incidents[0][0],incidents[1][0];neighbors[a].add(b);neighbors[b].add(a)
        groups=connected_groups(ids,neighbors)
        if len(groups)<2:raise ValueError('该顶点没有可拆分的独立面扇区')
        for group in groups[1:]:
            new_id=len(vertices);vertices=np.vstack((vertices,vertices[vertex]))
            for fid in group:faces[fid][faces[fid]==vertex]=new_id
            records.append(dict(input_vertex_id=vertex,new_vertex_id=new_id,face_ids=group))
    return vertices,faces,records
