from medical_mesh import detect_defects
from medical_mesh.data.synthetic import sphere,open_tube,inject_defects
from medical_mesh.ui.selection import diagnostic_items,selection_geometry


def test_boundary_marks_only_rim():
    asset=open_tube()
    entry=diagnostic_items(detect_defects(asset).to_dict())[-1]
    geometry=selection_geometry(asset,[entry])
    assert entry['kind']=='boundary' and not geometry['faces']
    assert len(geometry['edges'])==24 and not geometry['points']


def test_degenerate_is_visible_segment_and_points():
    asset,_=inject_defects(sphere(),'degenerate')
    entry=diagnostic_items(detect_defects(asset).to_dict())[1]
    geometry=selection_geometry(asset,[entry])
    assert not geometry['faces']
    assert len(geometry['collapsed_edges'])==1 and len(geometry['points'])==2


def test_counts_and_orientation_evidence():
    asset,_=inject_defects(sphere(),'flip')
    entry=diagnostic_items(detect_defects(asset).to_dict())[2]
    geometry=selection_geometry(asset,[entry])
    assert '3 条边' in entry['text'] and '4 个面' in entry['text']
    assert len(geometry['normals'])==4 and len(geometry['traversals'])==6
    asset,_=inject_defects(sphere(),'non_manifold_edge')
    entries=diagnostic_items(detect_defects(asset).to_dict())
    assert '1 条' in entries[3]['text'] and '3 个面' in entries[3]['text']
    assert '2 个点' in entries[4]['text']
