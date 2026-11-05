"""Analytic fixtures for the expanded repair checks, not clinical anatomy."""
import numpy as np
from ..core.model import MeshAsset
from .synthetic import tetrahedron


def quadric_annulus():
    vertices=[]
    count=24
    for radius in (.5,.75,1.):
        for angle in np.arange(count)*2*np.pi/count:
            x,y=radius*np.cos(angle),radius*np.sin(angle)
            vertices.append([x,y,.6*(x*x+.4*y*y)])
    faces=[]
    for ring in range(2):
        for i in range(count):
            j=(i+1)%count;a=ring*count+i;b=(ring+1)*count+i
            c=(ring+1)*count+j;d=ring*count+j
            faces.extend([[a,b,c],[a,c,d]])
    return MeshAsset(vertices=np.asarray(vertices),faces=np.asarray(faces,dtype=np.int64))


def unequal_components():
    a=tetrahedron()
    # Split every face of only the second shell; volumes also differ.
    v=[point.tolist() for point in a.vertices*.4+np.array([4.,0.,0.])]
    f=[]
    for face in a.faces:
        center=len(v);v.append(np.asarray(v)[face].mean(axis=0).tolist())
        for i in range(3):f.append([int(face[i]),int(face[(i+1)%3]),center])
    return MeshAsset(vertices=np.vstack((a.vertices,v)),
                     faces=np.vstack((a.faces,np.asarray(f,dtype=np.int64)+len(a.vertices))))
