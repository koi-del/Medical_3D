"""Geometry-based multiset comparison, independent of face order and vertex IDs."""
from collections import defaultdict,deque


def key(points):
    p=[tuple(float(x) for x in point) for point in points]
    return min(tuple(p[i:]+p[:i]) for i in range(3))


def mesh_changes(before,after):
    remaining=defaultdict(deque)
    for index,face in enumerate(before.faces):remaining[key(before.vertices[face])].append(index)
    unmatched=[]
    for index,face in enumerate(after.faces):
        k=key(after.vertices[face])
        if remaining[k]:remaining[k].popleft()
        else:unmatched.append(index)
    added=[];flipped_before=[];flipped_after=[]
    for index in unmatched:
        k=key(after.vertices[after.faces[index][::-1]])
        if remaining[k]:
            flipped_before.append(remaining[k].popleft());flipped_after.append(index)
        else:added.append(index)
    removed=sorted(i for ids in remaining.values() for i in ids)
    return dict(input_version=before.version,output_version=after.version,
                added_face_ids=added,removed_face_ids=removed,
                flipped_input_face_ids=flipped_before,flipped_output_face_ids=flipped_after)
